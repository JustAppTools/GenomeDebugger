"""Bind source-specific checks to the actual variants being compared."""

from .ensembl import SourceRecord
from .models import InvestigationInput
from .ncbi import _manifest
from .engine import canonical_consequence


def validate_reference_provenance(payload: InvestigationInput) -> None:
    summary = payload.reference_check
    expected = {"reference_check_id": summary.id, "reference_check_status": summary.status} if summary else {}
    for snapshot in payload.snapshots:
        for key in ("reference_check_id", "reference_check_status"):
            value = snapshot.provenance.configuration.get(key)
            if value is not None and value != expected.get(key):
                raise ValueError("NCBI reference check provenance contradicts the linked investigation summary; "
                                 "update or remove reference_check_id and reference_check_status with the summary")


def validate_annotation_provenance(payload: InvestigationInput) -> None:
    summary = payload.annotation_check
    expected = {"annotation_check_id": summary.id, "annotation_check_status": summary.status} if summary else {}
    for snapshot in payload.snapshots:
        configuration = snapshot.provenance.configuration
        for key in ("annotation_check_id", "annotation_check_status"):
            if key in configuration and configuration[key] != expected.get(key):
                raise ValueError("SnpEff annotation check provenance contradicts the linked investigation summary")
        if summary is None and "annotation_check_origin" in configuration:
            raise ValueError("SnpEff execution origin requires a linked annotation check")


def validate_annotation_origin(payload: InvestigationInput, check) -> None:
    expected = "local_execution" if check.execution is not None else "user_supplied"
    for snapshot in payload.snapshots:
        origin = snapshot.provenance.configuration.get("annotation_check_origin")
        if origin is not None and origin != expected:
            raise ValueError("SnpEff execution origin contradicts the preserved check record")


def validate_check_annotations(payload: InvestigationInput, source: SourceRecord) -> None:
    rows = {row.transcript_id: row for row in source.transcripts}
    for snapshot in payload.snapshots:
        for annotation in (snapshot.annotation, *snapshot.annotations):
            original = rows.get(annotation.transcript_id)
            if (original is None or annotation.gene_id != original.gene_id or
                    canonical_consequence(annotation.consequence) !=
                    canonical_consequence(';'.join(original.consequence_terms))):
                raise ValueError(f'SnpEff annotation check does not apply to the edited annotations in snapshot {snapshot.id}; '
                                 'remove the annotation check or compare the changed output separately')


def validate_check_variants(payload: InvestigationInput, source: SourceRecord, label: str) -> None:
    query = source.query
    assemblies = {"GRCh38", source.assembly_accession}
    if source.assembly_name.startswith("GRCh38"):
        assemblies.add(source.assembly_name)
    sequences = {query.chromosome}
    manifest = _manifest()
    if source.assembly_accession in {manifest["genbank_assembly_accession"], manifest["refseq_assembly_accession"]}:
        chromosome = manifest["chromosomes"].get(query.chromosome)
        if chromosome and chromosome.get("genbank_refseq_relationship") == "=":
            sequences.add(chromosome["refseq_accession"])
            assemblies.update({manifest["assembly_name"], manifest["genbank_assembly_accession"],
                               manifest["refseq_assembly_accession"]})
    for snapshot in payload.snapshots:
        variant = snapshot.variant
        if (variant.assembly not in assemblies or variant.sequence_id not in sequences or
                (variant.position, variant.ref, variant.alt) != (query.position, query.ref, query.alt)):
            raise ValueError(f"{label} check does not apply to the full variant in snapshot {snapshot.id}; "
                             "remove the check from transformed outputs or check their actual alleles")
