"""Bind source-specific checks to the actual variants being compared."""

from .ensembl import SourceRecord
from .models import InvestigationInput
from .ncbi import _manifest


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
