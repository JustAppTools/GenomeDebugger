"""Independent, accession-pinned NCBI check for cached Ensembl SNVs."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import model_validator
from .ensembl import SourceRecord
from .models import StrictModel
from .json_text import parse_json

MANIFEST_PATH = Path(os.environ.get('GENOMEDEBUGGER_RESOURCES', str(Path(__file__).resolve().parents[2]))) / "fixtures" / "grch38-p14-primary-chromosomes.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
VARIATION = "https://api.ncbi.nlm.nih.gov/variation/v0"
_rate_lock = threading.Lock()
_last_variation_request = 0.0


class ReferenceCheck(StrictModel):
    id: str
    source_record_id: str
    source_response_sha256: str
    checked_at: str
    assembly_report_uri: str
    assembly_report_sha256: str
    refseq_assembly_accession: str
    refseq_accession: str
    reference_uri: str
    contextual_uri: str
    hgvs_uri: str
    reference_fasta: str
    contextual_response: dict | None = None
    hgvs_response: dict | None = None
    reference_fasta_sha256: str
    contextual_response_sha256: str | None = None
    hgvs_response_sha256: str | None = None
    expected_reference: str
    observed_reference: str
    expected_spdi: str
    observed_spdi: str | None = None
    expected_hgvs: str
    observed_hgvs: str | None = None
    reference_matches: bool
    representation_checked: bool
    spdi_matches: bool
    hgvs_matches: bool
    status: Literal["agree", "disagree"]

    @model_validator(mode="before")
    @classmethod
    def legacy_representation_flag(cls, value):
        if isinstance(value, dict) and "representation_checked" not in value:
            value = {**value, "representation_checked": bool(value.get("contextual_response") and value.get("hgvs_response"))}
        return value


class ReferenceCheckRequest(StrictModel):
    mode: Literal["cache_only", "fetch"] = "cache_only"


class ReferenceCheckResult(StrictModel):
    check: ReferenceCheck
    access: Literal["cache", "fetched", "cached_after_error"]
    warning: str | None = None


class ReferenceCheckError(Exception):
    pass


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha(value: str | dict) -> str:
    serialized = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _get(client: httpx.Client, url: str, *, variation: bool = False) -> httpx.Response:
    global _last_variation_request
    try:
        if variation:
            # NCBI Variation Services asks clients to stay near one request per second.
            with _rate_lock:
                remaining = 1.05 - (time.monotonic() - _last_variation_request)
                if remaining > 0:
                    time.sleep(remaining)
                _last_variation_request = time.monotonic()
                response = client.get(url, headers={"Accept": "application/json", "User-Agent": "GenomeDebugger/0.4"})
        else:
            response = client.get(url, headers={"User-Agent": "GenomeDebugger/0.4"})
        response.raise_for_status()
        if len(response.content) > 10_000:
            raise ReferenceCheckError("NCBI response exceeded the 10 KB single-variant limit")
        return response
    except httpx.HTTPError as exc:
        raise ReferenceCheckError(f"NCBI request failed: {type(exc).__name__}") from exc


def _json(client: httpx.Client, url: str, *, variation: bool = False) -> dict:
    response = _get(client, url, variation=variation)
    try:
        result = parse_json(response.content)
    except ValueError as exc:
        raise ReferenceCheckError("NCBI returned invalid JSON, text, or numeric data") from exc
    if not isinstance(result, dict) or not isinstance(result.get("data"), dict):
        raise ReferenceCheckError("NCBI returned an unexpected variation response")
    return result


def _reference_metadata(record: SourceRecord) -> dict:
    manifest = _manifest()
    if record.assembly_name != manifest["assembly_name"] or record.assembly_accession != manifest["genbank_assembly_accession"]:
        raise ReferenceCheckError("The pinned NCBI mapping does not match this Ensembl assembly")
    if record.query.chromosome == "MT":
        raise ReferenceCheckError("Mitochondrial HGVS notation is outside this SNV check")
    chromosome = manifest["chromosomes"].get(record.query.chromosome)
    if chromosome is None or record.query.position > chromosome["length"]:
        raise ReferenceCheckError("Variant lies outside the pinned NCBI primary chromosome")
    if chromosome.get("genbank_refseq_relationship") != "=":
        raise ReferenceCheckError("Pinned GenBank and RefSeq chromosome sequences are not marked identical")
    accession = chromosome["refseq_accession"]
    q = record.query
    spdi = f"{accession}:{q.position - 1}:{q.ref}:{q.alt}"
    hgvs = f"{accession}:g.{q.position}{q.ref}>{q.alt}"
    reference_uri = (f"{EUTILS}?db=nuccore&id={accession}&strand=1&seq_start={q.position}"
                     f"&seq_stop={q.position}&rettype=fasta&retmode=text&tool=GenomeDebugger")
    contextual_uri = f"{VARIATION}/spdi/{spdi}/contextual"
    hgvs_uri = f"{VARIATION}/spdi/{spdi}/hgvs"
    return dict(assembly_report_uri=manifest["assembly_report_uri"],
                assembly_report_sha256=manifest["assembly_report_sha256"],
                refseq_assembly_accession=manifest["refseq_assembly_accession"],
                refseq_accession=accession, reference_uri=reference_uri,
                contextual_uri=contextual_uri, hgvs_uri=hgvs_uri,
                expected_reference=q.ref, expected_spdi=spdi, expected_hgvs=hgvs)


def _observed_reference(record: SourceRecord, fasta: str, accession: str) -> str:
    lines = fasta.splitlines()
    position = record.query.position
    expected_header = f">{accession}:{position}-{position} "
    if len(lines) != 2 or not lines[0].startswith(expected_header) or not re.fullmatch(r"[ACGT]", lines[1]):
        raise ReferenceCheckError("NCBI returned an unexpected accession, coordinate, or FASTA sequence")
    return lines[1]


def replay_reference_check(record: SourceRecord, fasta: str, contextual: dict | None,
                           hgvs_result: dict | None, checked_at: str) -> ReferenceCheck:
    """Derive observations, flags, hashes, and IDs from preserved responses offline."""
    metadata = _reference_metadata(record)
    fasta = fasta.replace("\r\n", "\n").replace("\r", "\n").strip()
    observed_reference = _observed_reference(record, fasta, metadata["refseq_accession"])
    reference_matches = observed_reference == record.query.ref == record.reference_base
    observed_spdi = observed_hgvs = None
    if reference_matches:
        if not all(isinstance(value, dict) and isinstance(value.get("data"), dict) for value in (contextual, hgvs_result)):
            raise ReferenceCheckError("NCBI notation responses are missing or malformed")
        data = contextual["data"]
        if (not isinstance(data.get('seq_id'), str) or not data['seq_id'].strip() or
                type(data.get('position')) is not int or data['position'] < 0 or
                any(not isinstance(data.get(key), str) or not re.fullmatch(r'[ACGT]*', data[key])
                    for key in ('deleted_sequence', 'inserted_sequence')) or
                data['deleted_sequence'] == data['inserted_sequence']):
            raise ReferenceCheckError('NCBI returned missing or invalid SPDI fields')
        observed_spdi = f"{data['seq_id']}:{data['position']}:{data['deleted_sequence']}:{data['inserted_sequence']}"
        observed_hgvs = hgvs_result["data"].get("hgvs")
        if not isinstance(observed_hgvs, str) or not re.fullmatch(r'[^:\s]+:g\.\S+', observed_hgvs):
            raise ReferenceCheckError("NCBI returned a missing or invalid HGVS value")
    elif contextual is not None or hgvs_result is not None:
        raise ReferenceCheckError("NCBI notation responses must be absent after a reference disagreement")
    spdi_matches = observed_spdi == metadata["expected_spdi"]
    hgvs_matches = observed_hgvs == metadata["expected_hgvs"]
    id_ = _sha({"source_record_id": record.id, "checked_at": checked_at,
                "fasta": fasta, "contextual": contextual, "hgvs": hgvs_result})[:20]
    return ReferenceCheck(id=id_, source_record_id=record.id,
        source_response_sha256=record.source_response_sha256, checked_at=checked_at, **metadata,
        reference_fasta=fasta, contextual_response=contextual, hgvs_response=hgvs_result,
        reference_fasta_sha256=_sha(fasta), contextual_response_sha256=_sha(contextual) if contextual else None,
        hgvs_response_sha256=_sha(hgvs_result) if hgvs_result else None,
        observed_reference=observed_reference, observed_spdi=observed_spdi, observed_hgvs=observed_hgvs,
        reference_matches=reference_matches, representation_checked=reference_matches,
        spdi_matches=spdi_matches, hgvs_matches=hgvs_matches,
        status="agree" if all((reference_matches, spdi_matches, hgvs_matches)) else "disagree")


def validate_saved_reference_check(record: SourceRecord, check: ReferenceCheck) -> None:
    replay = replay_reference_check(record, check.reference_fasta, check.contextual_response,
                                    check.hgvs_response, check.checked_at)
    if replay != check:
        raise ReferenceCheckError('Saved NCBI check does not match its preserved observations')


def fetch_reference_check(record: SourceRecord, client: httpx.Client | None = None) -> ReferenceCheck:
    metadata = _reference_metadata(record)
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=20.0, follow_redirects=False)
    try:
        fasta = _get(client, metadata["reference_uri"]).text.replace("\r\n", "\n").replace("\r", "\n").strip()
        observed_reference = _observed_reference(record, fasta, metadata["refseq_accession"])
        reference_matches = observed_reference == record.query.ref == record.reference_base
        contextual = hgvs_result = None
        if reference_matches:
            contextual = _json(client, metadata["contextual_uri"], variation=owns_client)
            hgvs_result = _json(client, metadata["hgvs_uri"], variation=owns_client)
        return replay_reference_check(record, fasta, contextual, hgvs_result, datetime.now(timezone.utc).isoformat())
    except ValueError as exc:
        raise ReferenceCheckError('NCBI returned invalid reference or notation data') from exc
    finally:
        if owns_client:
            client.close()
