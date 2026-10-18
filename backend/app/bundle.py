"""Portable, replay-checked local investigation bundles.

The contained hashes detect accidental corruption. They are not signatures and
do not authenticate user-supplied source data.
"""

from datetime import datetime, timezone
import hashlib
import json

from .engine import compare, digest
from .models import InvestigationResult
from .ensembl import SourceRecord, TranscriptConsequence
from .ncbi import ReferenceCheck, _sha
from .snpeff import SnpEffCheck, SnpEffCheckRequest, compare_snpeff
from .storage import load_reference_check, load_source_record, load_snpeff_check

BUNDLE_VERSION = 2
ENGINE_VERSION = "0.5.0"


def _verify_source(source: SourceRecord) -> None:
    raw = json.dumps(source.source_response, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(raw.encode()).hexdigest() != source.source_response_sha256:
        raise ValueError("Bundle source response hash does not match")
    query = source.query
    item = source.source_response
    if (source.reference_base != query.ref or item.get("assembly_name") != "GRCh38" or
            item.get("seq_region_name") != query.chromosome or item.get("start") != query.position or
            item.get("end") != query.position or item.get("allele_string") != f"{query.ref}/{query.alt}"):
        raise ValueError("Bundle source response does not match its query")
    rows = item.get("transcript_consequences")
    if not isinstance(rows, list):
        raise ValueError("Bundle source response has no transcript rows")
    derived = [TranscriptConsequence(transcript_id=row["transcript_id"], gene_id=row["gene_id"],
               consequence_terms=row["consequence_terms"], protein_consequence=row.get("hgvsp"),
               biotype=row.get("biotype")) for row in rows if isinstance(row, dict) and
               row.get("transcript_id") and row.get("gene_id") and isinstance(row.get("consequence_terms"), list) and row["consequence_terms"]]
    if derived != source.transcripts:
        raise ValueError("Bundle transcript rows do not match the preserved response")
    expected_id = hashlib.sha256(json.dumps({"query": query.model_dump(), "release": source.releases,
        "assembly": source.assembly_accession, "raw": source.source_response_sha256,
        "retrieved_at": source.retrieved_at}, sort_keys=True).encode()).hexdigest()[:20]
    if source.id != expected_id:
        raise ValueError("Bundle source record ID does not match its contents")


def _verify_reference(check: ReferenceCheck) -> None:
    if (check.reference_fasta_sha256 != _sha(check.reference_fasta) or
            check.contextual_response_sha256 != (_sha(check.contextual_response) if check.contextual_response else None) or
            check.hgvs_response_sha256 != (_sha(check.hgvs_response) if check.hgvs_response else None)):
        raise ValueError("Bundle NCBI response hash does not match")
    expected_id = _sha({"source_record_id": check.source_record_id, "checked_at": check.checked_at,
                       "fasta": check.reference_fasta, "contextual": check.contextual_response,
                       "hgvs": check.hgvs_response})[:20]
    if check.id != expected_id:
        raise ValueError("Bundle NCBI check ID does not match its contents")


def _verify_snpeff(source: SourceRecord, check: SnpEffCheck) -> None:
    if hashlib.sha256(check.vcf_text.encode("utf-8")).hexdigest() != check.vcf_sha256:
        raise ValueError("Bundle SnpEff VCF hash does not match")
    expected_id = digest({"source": source.id, "vcf": check.vcf_text, "checked_at": check.checked_at})[:20]
    replay = compare_snpeff(source, SnpEffCheckRequest(vcf_text=check.vcf_text,
        snpeff_version=check.snpeff_version, genome_database=check.genome_database,
        database_sha256=check.database_sha256))
    if (check.id != expected_id or check.status != replay.status or check.matches != replay.matches or
            check.unmatched_ensembl != replay.unmatched_ensembl or check.unmatched_snpeff != replay.unmatched_snpeff):
        raise ValueError("Bundle SnpEff check does not match a comparison replay")


def create_bundle(db_path, result: InvestigationResult) -> dict:
    # Older records remain readable, but their stored output belongs to an
    # earlier engine. Export a current replay so import can check every result.
    replay = compare(result.input)
    replayed_from_id = result.id if replay != result else None
    result = replay
    entries = {"investigation": result.model_dump(mode="json")}
    source_ids = {s.provenance.configuration.get("source_record_id") for s in result.input.snapshots}
    if len(source_ids) > 1:
        raise ValueError("The snapshots do not share one preserved source record; a portable source bundle cannot be built")
    if len(source_ids) == 1 and None not in source_ids:
        source = load_source_record(db_path, next(iter(source_ids)))
        if not source:
            raise ValueError("Linked source record is missing; the bundle cannot preserve its evidence")
        entries["source_record"] = source.model_dump(mode="json")
        if result.input.annotation_check:
            snpeff = load_snpeff_check(db_path, result.input.annotation_check.id)
            if not snpeff:
                raise ValueError("Linked SnpEff check is missing; the bundle cannot preserve its evidence")
            entries["snpeff_check"] = snpeff.model_dump(mode="json")
    check_id = result.input.reference_check.id if result.input.reference_check else None
    if check_id:
        check = load_reference_check(db_path, check_id)
        if not check:
            raise ValueError("Linked NCBI check is missing; the bundle cannot preserve its evidence")
        entries["reference_check"] = check.model_dump(mode="json")
    return {"format": "GenomeDebugger bundle", "version": BUNDLE_VERSION, "engine_version": ENGINE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "replayed_from_id": replayed_from_id,
            "entries": entries, "sha256": {key: digest(value) for key, value in entries.items()}}


def verify_bundle(bundle: dict) -> tuple[InvestigationResult, SourceRecord | None, ReferenceCheck | None, SnpEffCheck | None]:
    if bundle.get("format") != "GenomeDebugger bundle" or bundle.get("version") != BUNDLE_VERSION or bundle.get("engine_version") != ENGINE_VERSION:
        raise ValueError("Unsupported bundle format or version")
    entries, hashes = bundle.get("entries"), bundle.get("sha256")
    allowed = {"investigation", "source_record", "reference_check", "snpeff_check"}
    if (not isinstance(entries, dict) or not isinstance(hashes, dict) or
            "investigation" not in entries or not set(entries) <= allowed or set(entries) != set(hashes)):
        raise ValueError("Bundle entries and hashes do not match")
    for name, value in entries.items():
        if digest(value) != hashes[name]:
            raise ValueError(f"Bundle entry {name} failed its SHA-256 check")
    result = InvestigationResult.model_validate(entries["investigation"])
    if digest(result.input.model_dump(mode="json")) != result.input_sha256 or result.id != result.input_sha256[:16]:
        raise ValueError("Investigation input hash or ID does not match")
    if result != compare(result.input):
        raise ValueError("Investigation result does not match a current engine replay")
    source = SourceRecord.model_validate(entries["source_record"]) if "source_record" in entries else None
    check = ReferenceCheck.model_validate(entries["reference_check"]) if "reference_check" in entries else None
    snpeff = SnpEffCheck.model_validate(entries["snpeff_check"]) if "snpeff_check" in entries else None
    if source:
        _verify_source(source)
    if check:
        _verify_reference(check)
    if source and any(s.provenance.configuration.get("source_record_id") != source.id for s in result.input.snapshots):
        raise ValueError("Bundle source record does not match investigation provenance")
    if any(s.provenance.configuration.get("source_record_id") for s in result.input.snapshots) and not source:
        raise ValueError("Bundle omits the linked source record")
    if check and (not source or check.source_record_id != source.id or
                  not result.input.reference_check or check.id != result.input.reference_check.id):
        raise ValueError("Bundle reference check does not match its source or investigation")
    reference_summary = result.input.reference_check
    if reference_summary and (not check or reference_summary.source_response_sha256 != check.source_response_sha256 or
        reference_summary.refseq_accession != check.refseq_accession or
        reference_summary.expected_reference != check.expected_reference or
        reference_summary.observed_reference != check.observed_reference or
        reference_summary.reference_matches != check.reference_matches or
        reference_summary.spdi_matches != check.spdi_matches or
        reference_summary.hgvs_matches != check.hgvs_matches or
        reference_summary.status != check.status):
        raise ValueError("Bundle NCBI check does not match its investigation summary")
    if snpeff and (not source or snpeff.source_record_id != source.id or snpeff.source_response_sha256 != source.source_response_sha256):
        raise ValueError("Bundle SnpEff check does not match its source record")
    annotation_summary = result.input.annotation_check
    if annotation_summary and (not snpeff or annotation_summary.id != snpeff.id or
        annotation_summary.vcf_sha256 != snpeff.vcf_sha256 or annotation_summary.status != snpeff.status or
        annotation_summary.matched_transcripts != len(snpeff.matches) or
        annotation_summary.snpeff_version != snpeff.snpeff_version or
        annotation_summary.genome_database != snpeff.genome_database or
        annotation_summary.database_sha256 != snpeff.database_sha256):
        raise ValueError("Bundle SnpEff check does not match its investigation summary")
    if snpeff and not annotation_summary:
        raise ValueError("Bundle includes a SnpEff check not linked by the investigation")
    if snpeff:
        _verify_snpeff(source, snpeff)
    return result, source, check, snpeff
