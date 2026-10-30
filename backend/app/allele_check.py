"""Reference-backed SPDI identity checks for pinned GRCh38 primary sequences."""

from datetime import datetime, timezone
import re
from typing import Literal

import httpx
from pydantic import Field

from .engine import digest
from .models import InvestigationResult, StrictModel, Variant
from .ncbi import EUTILS, VARIATION, ReferenceCheckError, _get, _json, _manifest, _sha


class SPDI(StrictModel):
    seq_id: str
    position: int = Field(ge=0, strict=True)
    deleted_sequence: str = Field(max_length=10000, pattern=r"^[ACGT]*$")
    inserted_sequence: str = Field(max_length=10000, pattern=r"^[ACGT]*$")

    def text(self) -> str:
        return f"{self.seq_id}:{self.position}:{self.deleted_sequence}:{self.inserted_sequence}"


def _validate_normalized_interval(allele: SPDI) -> None:
    chromosome = next((entry for entry in _manifest()["chromosomes"].values()
                       if entry["refseq_accession"] == allele.seq_id), None)
    if chromosome is None:
        raise ReferenceCheckError("Normalized SPDI accession is not in the pinned reference")
    # SPDI is zero based and interbase: insertion at sequence length is valid,
    # while a deletion must fit entirely inside the sequence.
    if allele.position + len(allele.deleted_sequence) > chromosome["length"]:
        raise ReferenceCheckError("Normalized SPDI interval exceeds the pinned chromosome length")


class AlleleObservation(StrictModel):
    variant: Variant
    accession: str
    reference_uri: str
    reference_fasta: str
    reference_sha256: str
    reference_matches: bool
    contextual_uri: str
    contextual_response: dict | None
    contextual_sha256: str | None
    normalized: SPDI | None
    hgvs_uri: str
    hgvs_response: dict | None
    hgvs_sha256: str | None
    hgvs: str | None


class AlleleCheck(StrictModel):
    id: str
    investigation_id: str
    input_sha256: str
    checked_at: str
    assembly_report_uri: str
    assembly_report_sha256: str
    status: Literal["agree", "disagree"]
    explanation: str
    observations: list[AlleleObservation] = Field(min_length=2, max_length=2)


def _target(variant: Variant) -> tuple[str, str]:
    manifest = _manifest()
    if variant.assembly not in {"GRCh38", manifest["assembly_name"], manifest["refseq_assembly_accession"], manifest["genbank_assembly_accession"]}:
        raise ReferenceCheckError("Reference-backed identity currently requires pinned GRCh38.p14 primary sequences")
    for chromosome, entry in manifest["chromosomes"].items():
        if variant.sequence_id in {chromosome, entry["refseq_accession"]}:
            if chromosome == "MT":
                raise ReferenceCheckError("Mitochondrial alleles are outside this primary nuclear reference check")
            if entry.get("genbank_refseq_relationship") != "=" or variant.position+len(variant.ref)-1 > entry["length"]:
                raise ReferenceCheckError("Variant lies outside the pinned reference sequence")
            accession = entry["refseq_accession"]
            reference_uri = (f"{EUTILS}?db=nuccore&id={accession}&strand=1&seq_start={variant.position}"
                             f"&seq_stop={variant.position+len(variant.ref)-1}&rettype=fasta&retmode=text&tool=GenomeDebugger")
            return accession, reference_uri
    raise ReferenceCheckError("Sequence accession is not a pinned GRCh38.p14 primary chromosome")


def _reference(variant: Variant, fasta: str) -> tuple[str, str, str, bool]:
    accession, reference_uri = _target(variant)
    fasta = fasta.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = fasta.splitlines()
    stop = variant.position+len(variant.ref)-1
    if (len(lines)<2 or not lines[0].startswith(f">{accession}:{variant.position}-{stop} ") or
            not re.fullmatch(r"[ACGT]+", "".join(lines[1:])) or len("".join(lines[1:])) != len(variant.ref)):
        raise ReferenceCheckError("NCBI reference response does not match the requested accession and interval")
    return accession, reference_uri, fasta, "".join(lines[1:]) == variant.ref


def _observation(variant: Variant, fasta: str, contextual: dict | None, hgvs: dict | None) -> AlleleObservation:
    accession, reference_uri, fasta, matches = _reference(variant, fasta)
    submitted = f"{accession}:{variant.position-1}:{variant.ref}:{variant.alt}"
    normalized = None
    notation = None
    if matches:
        if not isinstance(contextual, dict) or not isinstance(contextual.get("data"), dict):
            raise ReferenceCheckError("NCBI contextual SPDI response is missing")
        data = contextual["data"]
        if type(data.get("position")) is not int:
            raise ReferenceCheckError("NCBI SPDI position is invalid")
        normalized = SPDI.model_validate({key:data.get(key) for key in SPDI.model_fields})
        if normalized.seq_id != accession or normalized.deleted_sequence == normalized.inserted_sequence:
            raise ReferenceCheckError("NCBI contextual SPDI does not describe a changed allele on the pinned accession")
        _validate_normalized_interval(normalized)
        if not isinstance(hgvs, dict) or not isinstance(hgvs.get("data"), dict) or not isinstance(hgvs["data"].get("hgvs"), str):
            raise ReferenceCheckError("NCBI genomic HGVS response is missing or malformed")
        notation = hgvs["data"]["hgvs"]
        if not notation.startswith(accession+":g."):
            raise ReferenceCheckError("NCBI HGVS accession does not match the pinned sequence")
    elif contextual is not None or hgvs is not None:
        raise ReferenceCheckError("Notation requests must be skipped after a reference mismatch")
    return AlleleObservation(variant=variant, accession=accession, reference_uri=reference_uri,
        reference_fasta=fasta, reference_sha256=_sha(fasta), reference_matches=matches,
        contextual_uri=f"{VARIATION}/spdi/{submitted}/contextual", contextual_response=contextual,
        contextual_sha256=_sha(contextual) if contextual else None, normalized=normalized,
        hgvs_uri=f"{VARIATION}/spdi/{submitted}/hgvs", hgvs_response=hgvs,
        hgvs_sha256=_sha(hgvs) if hgvs else None, hgvs=notation)


def replay_allele_check(result: InvestigationResult, observations: list[AlleleObservation], checked_at: str) -> AlleleCheck:
    if result.input.synthetic:
        raise ReferenceCheckError("Synthetic fixtures cannot be checked as public reference observations")
    if len(observations) != 2:
        raise ReferenceCheckError("An allele identity check requires two observations")
    rebuilt = [_observation(snapshot.variant, saved.reference_fasta, saved.contextual_response, saved.hgvs_response)
               for snapshot, saved in zip(result.input.snapshots, observations)]
    if rebuilt[0].accession != rebuilt[1].accession:
        raise ReferenceCheckError("Cross-sequence or cross-assembly identity requires a separate validated mapping")
    agrees = all(item.reference_matches for item in rebuilt) and rebuilt[0].normalized == rebuilt[1].normalized
    manifest = _manifest()
    data = {"investigation_id":result.id, "input_sha256":result.input_sha256, "checked_at":checked_at,
            "assembly_report_uri":manifest["assembly_report_uri"],
            "assembly_report_sha256":manifest["assembly_report_sha256"],
            "status":"agree" if agrees else "disagree",
            "explanation":("Both submitted reference alleles match pinned RefSeq observations and NCBI contextual SPDI identifies the same allele."
                           if agrees else "The submitted reference or normalized contextual allele differs between the two analyses."),
            "observations":[item.model_dump(mode="json") for item in rebuilt]}
    return AlleleCheck(id=digest(data)[:20], **data)


def validate_saved_allele_check(result: InvestigationResult, check: AlleleCheck) -> None:
    if replay_allele_check(result, check.observations, check.checked_at) != check:
        raise ValueError("Saved allele check does not match its preserved observations")


def fetch_allele_check(result: InvestigationResult, client: httpx.Client | None = None) -> AlleleCheck:
    if result.input.synthetic:
        raise ReferenceCheckError("Synthetic fixtures cannot be checked as public reference observations")
    targets = [_target(snapshot.variant) for snapshot in result.input.snapshots]
    if targets[0][0] != targets[1][0]:
        raise ReferenceCheckError("Cross-sequence or cross-assembly identity requires a separate validated mapping")
    owns_client = client is None
    client = client or httpx.Client(timeout=20.0, follow_redirects=False)
    observations = []
    try:
        for snapshot, (accession, uri) in zip(result.input.snapshots, targets):
            variant = snapshot.variant
            fasta = _get(client, uri).text.strip()
            # Parse and verify the reference before transmitting a normalization request.
            _, _, fasta, matches = _reference(variant, fasta)
            contextual = hgvs = None
            if matches:
                spdi = f"{accession}:{variant.position-1}:{variant.ref}:{variant.alt}"
                contextual = _json(client, f"{VARIATION}/spdi/{spdi}/contextual", variation=owns_client)
                hgvs = _json(client, f"{VARIATION}/spdi/{spdi}/hgvs", variation=owns_client)
            observations.append(_observation(variant, fasta, contextual, hgvs))
        return replay_allele_check(result, observations, datetime.now(timezone.utc).isoformat())
    finally:
        if owns_client:
            client.close()
