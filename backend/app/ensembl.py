"""Small, explicit GRCh38 SNV adapter for the current Ensembl REST service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import Field, ValidationError, model_validator

from .models import Annotation, InvestigationInput, Provenance, ReferenceCheckSummary, ReferenceContext, Snapshot, StrictModel, Variant

BASE_URL = "https://rest.ensembl.org"
PUBLIC_EXAMPLE = {"chromosome": "1", "position": 6524705, "ref": "C", "alt": "T"}


class SourceQuery(StrictModel):
    chromosome: Literal[tuple(str(i) for i in range(1, 23)) + ("X", "Y", "MT")]
    position: int = Field(ge=1, le=250_000_000)
    ref: Literal["A", "C", "G", "T"]
    alt: Literal["A", "C", "G", "T"]

    @model_validator(mode="after")
    def different_alleles(self):
        if self.ref == self.alt:
            raise ValueError("ref and alt must differ")
        return self


class SourceLookup(StrictModel):
    query: SourceQuery
    mode: Literal["cache_only", "fetch"] = "cache_only"


class TranscriptConsequence(StrictModel):
    transcript_id: str
    gene_id: str
    consequence_terms: list[str]
    protein_consequence: str | None = None
    biotype: str | None = None


class SourceRecord(StrictModel):
    id: str
    query: SourceQuery
    retrieved_at: str
    source_uri: str
    sequence_uri: str
    release_uri: str
    assembly_uri: str
    releases: list[int]
    assembly_name: str
    assembly_accession: str
    reference_base: str
    source_response_sha256: str
    source_response: dict
    transcripts: list[TranscriptConsequence]


class SourceLookupResult(StrictModel):
    record: SourceRecord
    access: Literal["cache", "fetched", "cached_after_error"]
    warning: str | None = None


class CompareTranscripts(StrictModel):
    transcript_a: str
    transcript_b: str

    @model_validator(mode="after")
    def different_transcripts(self):
        if self.transcript_a == self.transcript_b:
            raise ValueError("select two different transcripts")
        return self


class SourceError(Exception):
    pass


def _json(client: httpx.Client, path: str):
    try:
        response = client.get(BASE_URL + path, headers={"Accept": "application/json", "User-Agent": "GenomeDebugger/0.3"})
        response.raise_for_status()
        if len(response.content) > 250_000:
            raise SourceError("Ensembl response exceeded the 250 KB adapter limit")
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceError(f"Ensembl request failed: {type(exc).__name__}") from exc


def fetch_record(query: SourceQuery, client: httpx.Client | None = None) -> SourceRecord:
    """Fetch one current record. No historical-release claim is made."""
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0, follow_redirects=False)
    try:
        release_uri = "/info/data?content-type=application/json"
        assembly_uri = "/info/assembly/human?content-type=application/json"
        sequence_uri = f"/sequence/region/human/{query.chromosome}:{query.position}..{query.position}:1?content-type=application/json"
        source_uri = f"/vep/human/region/{query.chromosome}:{query.position}-{query.position}:1/{query.alt}?content-type=application/json"
        release = _json(client, release_uri)
        assembly = _json(client, assembly_uri)
        sequence = _json(client, sequence_uri)
        if not isinstance(release, dict) or not isinstance(release.get("releases"), list) or not release["releases"] or not all(type(x) is int for x in release["releases"]):
            raise SourceError("Ensembl release metadata was incomplete")
        if (not isinstance(assembly, dict) or assembly.get("default_coord_system_version") != "GRCh38"
                or not isinstance(assembly.get("assembly_name"), str)
                or not isinstance(assembly.get("assembly_accession"), str)):
            raise SourceError("Ensembl did not report the expected GRCh38 assembly")
        if not isinstance(sequence, dict) or sequence.get("seq") != query.ref:
            raise SourceError("Reference allele does not match the Ensembl GRCh38 sequence")
        raw = _json(client, source_uri)
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
            raise SourceError("Ensembl returned an unexpected VEP record")
        item = raw[0]
        if (item.get("assembly_name") != "GRCh38" or item.get("seq_region_name") != query.chromosome
                or item.get("start") != query.position or item.get("end") != query.position
                or item.get("allele_string") != f"{query.ref}/{query.alt}"):
            raise SourceError("VEP coordinates, allele, or assembly did not match the request")
        rows = item.get("transcript_consequences")
        if not isinstance(rows, list):
            raise SourceError("VEP transcript consequences were absent")
        transcripts = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("transcript_id") and row.get("gene_id") and isinstance(row.get("consequence_terms"), list) and row["consequence_terms"]:
                try:
                    transcripts.append(TranscriptConsequence(
                        transcript_id=row["transcript_id"], gene_id=row["gene_id"],
                        consequence_terms=row["consequence_terms"],
                        protein_consequence=row.get("hgvsp"), biotype=row.get("biotype"),
                    ))
                except ValidationError as exc:
                    raise SourceError("VEP returned a malformed transcript consequence") from exc
        if not transcripts:
            raise SourceError("VEP returned no usable transcript consequences")
        if len({row.transcript_id for row in transcripts}) != len(transcripts):
            raise SourceError("VEP returned duplicate transcript identifiers")
        canonical = json.dumps(item, sort_keys=True, separators=(",", ":"))
        raw_hash = hashlib.sha256(canonical.encode()).hexdigest()
        retrieved_at = datetime.now(timezone.utc).isoformat()
        record_id = hashlib.sha256(json.dumps({"query": query.model_dump(), "release": release["releases"], "assembly": assembly["assembly_accession"], "raw": raw_hash, "retrieved_at": retrieved_at}, sort_keys=True).encode()).hexdigest()[:20]
        return SourceRecord(
            id=record_id, query=query, retrieved_at=retrieved_at,
            source_uri=BASE_URL + source_uri, sequence_uri=BASE_URL + sequence_uri,
            release_uri=BASE_URL + release_uri, assembly_uri=BASE_URL + assembly_uri,
            releases=release["releases"], assembly_name=assembly["assembly_name"],
            assembly_accession=assembly["assembly_accession"], reference_base=sequence["seq"],
            source_response_sha256=raw_hash, source_response=item, transcripts=transcripts,
        )
    finally:
        if owns_client:
            client.close()


def comparison_input(record: SourceRecord, selection: CompareTranscripts,
                     reference_check: ReferenceCheckSummary | None = None) -> InvestigationInput:
    rows = {row.transcript_id: row for row in record.transcripts}
    if selection.transcript_a not in rows or selection.transcript_b not in rows:
        raise ValueError("selected transcript was not present in the cached record")
    q = record.query
    variant = Variant(assembly="GRCh38", sequence_id=q.chromosome, position=q.position,
                      ref=q.ref, alt=q.alt, reference_context=ReferenceContext(start=q.position, sequence=record.reference_base))
    source_release = "reported " + ",".join(str(x) for x in record.releases)
    configuration = {"assembly_accession": record.assembly_accession,
                     "source_record_id": record.id, "retrieved_at": record.retrieved_at}
    if reference_check:
        configuration.update({"reference_check_id": reference_check.id,
                              "reference_check_status": reference_check.status})
    provenance = Provenance(tool="Ensembl VEP REST", tool_version="not reported by API",
                            source_name="Ensembl", source_release=source_release,
                            source_uri=record.source_uri, input_sha256=record.source_response_sha256,
                            configuration=configuration)
    snapshots = []
    for side, transcript_id in (("a", selection.transcript_a), ("b", selection.transcript_b)):
        row = rows[transcript_id]
        snapshots.append(Snapshot(id=f"{record.id}-{side}", label=f"Ensembl VEP {transcript_id}",
                                  variant=variant, annotation=Annotation(gene_id=row.gene_id,
                                  transcript_id=row.transcript_id, consequence=";".join(row.consequence_terms),
                                  protein_consequence=row.protein_consequence), provenance=provenance))
    return InvestigationInput(title=f"Current Ensembl transcript comparison: {q.chromosome}:{q.position} {q.ref}>{q.alt}",
                              synthetic=False, snapshots=snapshots, reference_check=reference_check)
