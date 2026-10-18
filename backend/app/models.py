from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReferenceContext(StrictModel):
    start: int = Field(ge=1)
    sequence: str = Field(min_length=1, max_length=10000, pattern=r"^[ACGT]+$")


class Variant(StrictModel):
    assembly: str = Field(min_length=1, max_length=50)
    sequence_id: str = Field(min_length=1, max_length=100)
    position: int = Field(ge=1, description="One-based genomic coordinate")
    ref: str = Field(min_length=1, max_length=100, pattern=r"^[ACGT]+$")
    alt: str = Field(min_length=1, max_length=100, pattern=r"^[ACGT]+$")
    reference_context: ReferenceContext | None = None

    @model_validator(mode="after")
    def check_change(self):
        if self.ref == self.alt:
            raise ValueError("reference and alternate alleles must differ")
        if self.reference_context:
            offset = self.position - self.reference_context.start
            if offset < 0 or offset + len(self.ref) > len(self.reference_context.sequence):
                raise ValueError("variant lies outside reference_context")
            actual = self.reference_context.sequence[offset:offset + len(self.ref)]
            if actual != self.ref:
                raise ValueError("ref does not match reference_context")
        return self


class ClinicalAssertion(StrictModel):
    framework: str = Field(min_length=1, max_length=100)
    condition_id: str = Field(min_length=1, max_length=100)
    classification: str = Field(min_length=1, max_length=100)
    review_status: str | None = None
    assertion_date: str | None = None


class Annotation(StrictModel):
    gene_id: str = Field(min_length=1, max_length=100)
    transcript_id: str = Field(min_length=1, max_length=100)
    consequence: str = Field(min_length=1, max_length=500)
    protein_consequence: str | None = None
    clinical: ClinicalAssertion | None = None


def annotation_key(row: Annotation) -> tuple[str, str, str | None, str | None]:
    return (row.gene_id, row.transcript_id, row.clinical.framework if row.clinical else None,
            row.clinical.condition_id if row.clinical else None)


def variant_key(variant: Variant) -> tuple[str, str, int, str, str]:
    return variant.assembly, variant.sequence_id, variant.position, variant.ref, variant.alt


class VariantRecord(StrictModel):
    variant: Variant
    annotations: list[Annotation] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_annotations(self):
        keys = [annotation_key(row) for row in self.annotations]
        if len(keys) != len(set(keys)):
            raise ValueError("variant record annotation rows must be unique")
        return self


class Provenance(StrictModel):
    tool: str = Field(min_length=1, max_length=100)
    tool_version: str = Field(min_length=1, max_length=100)
    source_name: str = Field(min_length=1, max_length=100)
    source_release: str = Field(min_length=1, max_length=100)
    source_uri: str | None = None
    input_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    configuration: dict[str, str] = Field(default_factory=dict)


class Snapshot(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=150)
    variant: Variant
    annotation: Annotation
    annotations: list[Annotation] = Field(default_factory=list, max_length=1000, description="Additional annotation rows for this variant")
    variant_records: list[VariantRecord] = Field(default_factory=list, max_length=50, description="Additional variants and their annotation rows")
    provenance: Provenance

    @model_validator(mode="after")
    def unique_annotation_rows(self):
        rows = [self.annotation, *self.annotations]
        keys = [annotation_key(row) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("annotation rows must have unique gene, transcript, and clinical context")
        variants = [variant_key(self.variant), *(variant_key(record.variant) for record in self.variant_records)]
        if len(variants) != len(set(variants)):
            raise ValueError("snapshot variants must have unique assembly, accession, position, and alleles")
        return self


class LookupRow(StrictModel):
    transcript_id: str
    gene_id: str
    consequence: str
    protein_consequence: str | None = None


class ControlledLookup(StrictModel):
    kind: Literal["synthetic_transcript_lookup"]
    id: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=1000)
    variant: Variant
    rows: list[LookupRow] = Field(min_length=2, max_length=1000)

    @model_validator(mode="after")
    def unique_transcripts(self):
        ids = [row.transcript_id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("controlled lookup transcript IDs must be unique")
        return self


class ReferenceCheckSummary(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=100)
    source_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    refseq_accession: str = Field(min_length=1, max_length=100)
    expected_reference: str = Field(pattern=r"^[ACGT]$")
    observed_reference: str = Field(pattern=r"^[ACGT]$")
    reference_matches: bool
    spdi_matches: bool
    hgvs_matches: bool
    status: Literal["agree", "disagree"]

    @model_validator(mode="after")
    def consistent_status(self):
        agrees = all((self.reference_matches, self.spdi_matches, self.hgvs_matches))
        if (self.status == "agree") != agrees:
            raise ValueError("reference check status disagrees with its check flags")
        if self.reference_matches != (self.expected_reference == self.observed_reference):
            raise ValueError("reference_matches disagrees with observed base")
        return self


class AnnotationCheckSummary(StrictModel):
    id: str
    source_record_id: str
    source_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    vcf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snpeff_version: str
    genome_database: str
    database_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["agree", "disagree", "unresolved"]
    matched_transcripts: int = Field(ge=0)


class InvestigationInput(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    synthetic: bool = False
    snapshots: list[Snapshot] = Field(min_length=2, max_length=2)
    controlled_lookup: ControlledLookup | None = None
    reference_check: ReferenceCheckSummary | None = None
    annotation_check: AnnotationCheckSummary | None = None
    meaningful_overrides: dict[str, bool] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        if self.snapshots[0].id == self.snapshots[1].id:
            raise ValueError("snapshot IDs must differ")
        if self.controlled_lookup and not self.synthetic:
            raise ValueError("synthetic lookup requires synthetic=true")
        if any(not key or len(key) > 200 for key in self.meaningful_overrides):
            raise ValueError("meaningful override field names must be 1–200 characters")
        if self.reference_check:
            check = self.reference_check
            for snapshot in self.snapshots:
                if snapshot.variant.ref != check.expected_reference:
                    raise ValueError("reference check allele does not match snapshot")
                if snapshot.provenance.configuration.get("source_record_id") != check.source_record_id:
                    raise ValueError("reference check source record does not match snapshot")
                if snapshot.provenance.input_sha256 != check.source_response_sha256:
                    raise ValueError("reference check source hash does not match snapshot")
        if self.annotation_check:
            check = self.annotation_check
            for snapshot in self.snapshots:
                if snapshot.provenance.configuration.get("source_record_id") != check.source_record_id or snapshot.provenance.input_sha256 != check.source_response_sha256:
                    raise ValueError("annotation check source record or hash does not match snapshot")
        return self


class Evidence(StrictModel):
    id: str
    kind: str
    description: str
    data: dict


class Difference(StrictModel):
    field: str
    category: str
    before: str | None
    after: str | None
    meaningful: bool
    evidence_ids: list[str]


class Finding(StrictModel):
    status: Literal["verified", "probable", "possible", "unresolved"]
    cause: str
    explanation: str
    affected_fields: list[str]
    evidence_ids: list[str]


class IdentityResult(StrictModel):
    status: Literal["verified", "rejected", "unresolved"]
    explanation: str
    normalized_a: str | None = None
    normalized_b: str | None = None
    evidence_ids: list[str]


class InvestigationResult(StrictModel):
    id: str
    engine_version: str = "0.5.0"
    input: InvestigationInput
    identity: IdentityResult
    differences: list[Difference]
    findings: list[Finding]
    evidence: list[Evidence]
    input_sha256: str
