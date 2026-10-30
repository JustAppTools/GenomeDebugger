"""Small, explicit GRCh38 SNV adapter for the current Ensembl REST service."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import Field, StrictInt, ValidationError, model_validator
from .json_text import parse_json
from .unicode_text import MAX_JSON_DEPTH, validate_json_values

from .models import Annotation, AnnotationCheckSummary, InvestigationInput, MAX_ADDITIONAL_ANNOTATIONS, Provenance, ReferenceCheckSummary, ReferenceContext, Snapshot, StrictModel, Variant

BASE_URL = "https://rest.ensembl.org"
PUBLIC_EXAMPLE = {"chromosome": "1", "position": 6524705, "ref": "C", "alt": "T"}


class SourceQuery(StrictModel):
    chromosome: Literal[tuple(str(i) for i in range(1, 23)) + ("X", "Y", "MT")]
    position: int = Field(ge=1, le=250_000_000, strict=True)
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


def annotation_from_transcript(row: TranscriptConsequence) -> Annotation:
    return Annotation(gene_id=row.gene_id, transcript_id=row.transcript_id,
                      consequence=';'.join(row.consequence_terms),
                      protein_consequence=row.protein_consequence)


def parse_transcripts(rows: object) -> list[TranscriptConsequence]:
    """Require every captured transcript row to be usable before claiming completeness."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("VEP transcript consequences must be a nonempty array")
    if len(rows) > MAX_ADDITIONAL_ANNOTATIONS + 1:
        raise ValueError(f'VEP output exceeds the supported {MAX_ADDITIONAL_ANNOTATIONS + 1} transcript rows; no rows were omitted')
    parsed = []
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or
                any(not isinstance(row.get(key), str) or not row[key].strip()
                    for key in ('transcript_id', 'gene_id')) or
                not isinstance(row.get('consequence_terms'), list) or not row['consequence_terms'] or
                any(not isinstance(term, str) or not term.strip() for term in row['consequence_terms'])):
            raise ValueError(f"VEP transcript row {index + 1} is malformed; no rows were omitted")
        try:
            transcript = TranscriptConsequence(transcript_id=row['transcript_id'], gene_id=row['gene_id'],
                consequence_terms=row['consequence_terms'], protein_consequence=row.get('hgvsp'), biotype=row.get('biotype'))
            annotation_from_transcript(transcript)
            parsed.append(transcript)
        except ValidationError as exc:
            raise ValueError(f"VEP transcript row {index + 1} is malformed or exceeds supported annotation field limits") from exc
    if len({row.transcript_id for row in parsed}) != len(parsed):
        raise ValueError("VEP transcript identifiers must be unique")
    return parsed


class SourceRecord(StrictModel):
    id: str
    query: SourceQuery
    retrieved_at: str
    source_uri: str
    sequence_uri: str
    release_uri: str
    assembly_uri: str
    releases: list[StrictInt]
    assembly_name: str
    assembly_accession: str
    reference_base: str
    source_response_sha256: str
    source_response: dict
    transcripts: list[TranscriptConsequence]
    origin: Literal["current_api", "historical_artifact"] = "current_api"
    artifact: dict | None = None


def validate_assembly_metadata(name: str, accession: str) -> None:
    if not re.fullmatch(r'GRCh38(?:\.p[1-9]\d*)?', name):
        raise ValueError('Source assembly name must describe GRCh38 or a GRCh38 patch release')
    if not re.fullmatch(r'GC[AF]_\d+\.\d+', accession):
        raise ValueError('Source assembly accession must be a versioned GenBank or RefSeq accession')


def validate_source_assembly(source: SourceRecord) -> None:
    validate_json_values(source.source_response, max_depth=MAX_JSON_DEPTH)
    validate_assembly_metadata(source.assembly_name, source.assembly_accession)
    if source.source_response.get('assembly_name') != 'GRCh38':
        raise ValueError('Source assembly metadata contradicts its preserved VEP response')
    if any(type(source.source_response.get(key)) is not int for key in ('start', 'end')):
        raise ValueError('VEP coordinates must be integers, without boolean conversion')


class SourceLookupResult(StrictModel):
    record: SourceRecord
    access: Literal["cache", "fetched", "cached_after_error"]
    warning: str | None = None


class CompareTranscripts(StrictModel):
    transcript_a: str
    transcript_b: str
    reference_check_id: str | None = Field(default=None, min_length=1, max_length=100)
    annotation_check_id: str | None = Field(default=None, min_length=1, max_length=100)

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
        return parse_json(response.content)
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
        try:
            validate_assembly_metadata(assembly['assembly_name'], assembly['assembly_accession'])
        except ValueError as exc:
            raise SourceError(str(exc)) from exc
        if not isinstance(sequence, dict) or sequence.get("seq") != query.ref:
            raise SourceError("Reference allele does not match the Ensembl GRCh38 sequence")
        raw = _json(client, source_uri)
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
            raise SourceError("Ensembl returned an unexpected VEP record")
        item = raw[0]
        if (item.get("assembly_name") != "GRCh38" or item.get("seq_region_name") != query.chromosome
                or any(type(item.get(key)) is not int for key in ('start', 'end'))
                or item.get("start") != query.position or item.get("end") != query.position
                or item.get("allele_string") != f"{query.ref}/{query.alt}"):
            raise SourceError("VEP coordinates, allele, or assembly did not match the request")
        try:
            transcripts = parse_transcripts(item.get("transcript_consequences"))
        except ValueError as exc:
            raise SourceError(str(exc)) from exc
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


def source_release_text(record: SourceRecord) -> str:
    prefix = 'reported ' if record.origin == 'current_api' else 'declared historical '
    text = prefix + ','.join(str(value) for value in record.releases)
    if len(text) <= 100:
        return text
    count = len(record.releases)
    return f"{prefix}{count} release{'s' if count != 1 else ''} (see source record)"


def snapshot_from_record(record: SourceRecord, transcript_id: str, side: str,
                         reference_check: ReferenceCheckSummary | None = None,
                         annotation_check: AnnotationCheckSummary | None = None) -> Snapshot:
    validate_source_assembly(record)
    if parse_transcripts(record.source_response.get("transcript_consequences")) != record.transcripts:
        raise ValueError("VEP transcript rows do not match the preserved response")
    rows = {row.transcript_id: row for row in record.transcripts}
    if transcript_id not in rows:
        raise ValueError("selected transcript was not present in the cached record")
    q = record.query
    variant = Variant(assembly="GRCh38", sequence_id=q.chromosome, position=q.position,
                      ref=q.ref, alt=q.alt, reference_context=(ReferenceContext(start=q.position, sequence=record.reference_base)
                          if record.origin == "current_api" else None))
    source_release = source_release_text(record)
    configuration = {"assembly_accession": record.assembly_accession,
                     "source_annotation_scope": "all_transcripts",
                     "source_record_id": record.id, "retrieved_at": record.retrieved_at}
    if reference_check:
        configuration.update({"reference_check_id": reference_check.id,
                              "reference_check_status": reference_check.status})
    if annotation_check:
        configuration.update({"annotation_check_id": annotation_check.id,
                              "annotation_check_status": annotation_check.status})
    if record.origin == "historical_artifact":
        configuration.update({"source_origin":record.origin,"artifact_sha256":record.artifact["sha256"],
                              "generated_at":record.artifact["generated_at"]})
    provenance = Provenance(tool="Ensembl VEP REST" if record.origin == "current_api" else "Ensembl VEP historical output",
                            tool_version="not reported by API" if record.origin == "current_api" else record.artifact["tool_version"],
                            source_name="Ensembl", source_release=source_release,
                            source_uri=record.source_uri, input_sha256=record.source_response_sha256,
                            configuration=configuration)
    row = rows[transcript_id]
    other_rows = [annotation_from_transcript(other)
                  for other in record.transcripts if other.transcript_id != transcript_id]
    return Snapshot(id=f"{record.id}-{side}", label=f"Ensembl VEP {transcript_id}",
                                  variant=variant, annotation=annotation_from_transcript(row), annotations=other_rows,
                                  provenance=provenance)


def comparison_input(record: SourceRecord, selection: CompareTranscripts,
                     reference_check: ReferenceCheckSummary | None = None,
                     annotation_check: AnnotationCheckSummary | None = None) -> InvestigationInput:
    snapshots = [snapshot_from_record(record,transcript,side,reference_check,annotation_check)
                 for side,transcript in (("a",selection.transcript_a),("b",selection.transcript_b))]
    q = record.query
    label = "Current" if record.origin == "current_api" else "Historical artifact"
    return InvestigationInput(title=f"{label} Ensembl transcript comparison: {q.chromosome}:{q.position} {q.ref}>{q.alt}",
                              synthetic=False, snapshots=snapshots, reference_check=reference_check,
                              annotation_check=annotation_check)


def validate_source_snapshot(source, snapshot):
    validate_source_assembly(source)
    declared_origin = snapshot.provenance.configuration.get("source_origin")
    if declared_origin is not None and declared_origin != source.origin:
        raise ValueError("Snapshot source origin contradicts its preserved source record")
    # Custom tools may cite the response as an input. A VEP-generated snapshot
    # claims that its outputs were derived directly from this captured response.
    if snapshot.provenance.tool not in {"Ensembl VEP REST", "Ensembl VEP historical output"}:
        return
    expected = snapshot_from_record(source, snapshot.annotation.transcript_id, "verify")
    for key in ('assembly_accession', 'retrieved_at', 'artifact_sha256', 'generated_at'):
        if (key in snapshot.provenance.configuration and
                snapshot.provenance.configuration[key] != expected.provenance.configuration.get(key)):
            raise ValueError(f'VEP snapshot {key} contradicts its preserved source record')
    if snapshot.variant != expected.variant or snapshot.annotation != expected.annotation or snapshot.variant_records:
        raise ValueError("VEP snapshot does not match its preserved source variant and annotation")
    expected_rows = {row.transcript_id: row for row in expected.annotations}
    if any(expected_rows.get(row.transcript_id) != row for row in snapshot.annotations):
        raise ValueError("VEP snapshot annotation rows contradict the preserved source")
    if (snapshot.provenance.configuration.get("source_annotation_scope") == "all_transcripts" and
            {row.transcript_id for row in snapshot.annotations} != set(expected_rows)):
        raise ValueError("VEP snapshot is missing rows from its declared complete source annotation set")
    for key in ("tool", "tool_version", "source_name", "source_release", "source_uri"):
        actual = getattr(snapshot.provenance, key)
        legacy_release = (key == "source_release" and source.origin == "current_api" and
            "source_annotation_scope" not in snapshot.provenance.configuration and
            actual == "Ensembl " + ",".join(str(value) for value in source.releases))
        if actual != getattr(expected.provenance, key) and not legacy_release:
            raise ValueError("VEP snapshot provenance contradicts its preserved source")
