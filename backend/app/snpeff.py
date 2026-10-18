"""Compare an explicitly supplied SnpEff ANN VCF with a preserved Ensembl record.

This compares two outputs. It does not authenticate the user-supplied SnpEff run.
"""

from datetime import datetime, timezone
import hashlib
from typing import Literal

from pydantic import Field

from .engine import digest
from .ensembl import SourceRecord
from .models import StrictModel


class SnpEffCheckRequest(StrictModel):
    vcf_text: str = Field(min_length=1, max_length=500_000)
    snpeff_version: str = Field(min_length=1, max_length=100)
    genome_database: str = Field(min_length=1, max_length=100)
    database_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConsequenceMatch(StrictModel):
    transcript_id: str
    ensembl_terms: list[str]
    snpeff_terms: list[str]
    agrees: bool


class SnpEffExecution(StrictModel):
    started_at: str
    elapsed_seconds: float
    command: list[str]
    java_sha256: str
    jar_sha256: str
    config_sha256: str
    database_files: dict[str, str]
    database_sha256: str
    input_vcf: str
    input_vcf_sha256: str
    output_vcf_sha256: str
    stderr: str
    software_version: str
    artifact_sources: dict[str,str] = Field(default_factory=dict)
    assembly_name: str | None = None
    assembly_accession: str | None = None


class SnpEffCheck(StrictModel):
    id: str
    source_record_id: str
    source_response_sha256: str
    checked_at: str
    snpeff_version: str
    genome_database: str
    database_sha256: str
    vcf_sha256: str
    vcf_text: str
    status: Literal["agree", "disagree", "unresolved"]
    matches: list[ConsequenceMatch]
    unmatched_ensembl: list[str]
    unmatched_snpeff: list[str]
    explanation: str
    execution: SnpEffExecution | None = None


def compare_snpeff(record: SourceRecord, request: SnpEffCheckRequest) -> SnpEffCheck:
    data_lines = [line for line in request.vcf_text.splitlines() if line and not line.startswith("#")]
    if len(data_lines) != 1:
        raise ValueError("SnpEff VCF must contain exactly one variant row")
    columns = data_lines[0].split("\t")
    if len(columns) < 8:
        raise ValueError("SnpEff VCF row must have at least eight tab-separated columns")
    chrom, position, _, ref, alt, _, _, info = columns[:8]
    q = record.query
    if chrom.removeprefix("chr") != q.chromosome or position != str(q.position) or ref != q.ref or alt != q.alt:
        raise ValueError("SnpEff VCF allele does not exactly match the preserved Ensembl query")
    tags = dict(part.split("=",1) for part in info.split(";") if "=" in part)
    if "ANN" not in tags:
        raise ValueError("SnpEff VCF has no ANN field")
    snpeff: dict[str,set[str]] = {}
    for entry in tags["ANN"].split(","):
        fields = entry.split("|")
        if len(fields) < 7:
            raise ValueError("SnpEff ANN row is incomplete")
        if fields[0] != q.alt:
            raise ValueError("SnpEff ANN allele does not match the VCF alternate")
        if fields[5].lower() != "transcript" or not fields[6]:
            continue
        if len(fields) > 15 and fields[15]:
            raise ValueError("SnpEff ANN reports a warning or error; resolve it before comparison")
        snpeff.setdefault(fields[6],set()).update(fields[1].split("&"))
    ensembl = {row.transcript_id: set(row.consequence_terms) for row in record.transcripts}
    shared = sorted(ensembl.keys() & snpeff.keys())
    matches = [ConsequenceMatch(transcript_id=key, ensembl_terms=sorted(ensembl[key]),
                                snpeff_terms=sorted(snpeff[key]), agrees=ensembl[key]==snpeff[key]) for key in shared]
    unmatched_ensembl = sorted(ensembl.keys()-snpeff.keys())
    unmatched_snpeff = sorted(snpeff.keys()-ensembl.keys())
    status = ("disagree" if any(not item.agrees for item in matches) else
              "unresolved" if not matches or unmatched_ensembl or unmatched_snpeff else "agree")
    explanation = ("At least one exact transcript match has different consequence terms; investigate releases and configurations." if status == "disagree" else
                   "Some transcript IDs could not be matched across the two outputs; agreement is incomplete." if status == "unresolved" and matches else
                   "No exact transcript IDs matched; transcript releases may differ." if status == "unresolved" else
                   "All transcript IDs and consequence terms agree between the two supplied outputs.")
    checked_at = datetime.now(timezone.utc).isoformat()
    return SnpEffCheck(id=digest({"source":record.id,"vcf":request.vcf_text,"checked_at":checked_at})[:20],
                       source_record_id=record.id, source_response_sha256=record.source_response_sha256,
                       checked_at=checked_at, snpeff_version=request.snpeff_version,
                       genome_database=request.genome_database, database_sha256=request.database_sha256,
                       vcf_sha256=hashlib.sha256(request.vcf_text.encode("utf-8")).hexdigest(), vcf_text=request.vcf_text,
                       status=status, matches=matches, unmatched_ensembl=unmatched_ensembl,
                       unmatched_snpeff=unmatched_snpeff, explanation=explanation)
