"""Portable, replay-checked local investigation bundles.

The contained hashes detect accidental corruption. They are not signatures and
do not authenticate user-supplied source data.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from .models import StrictModel
from .admission import validate_required_text

from .engine import canonical_json, compare, digest
from .legacy_engine_v050 import compare as compare_v050
from .legacy_engine_v060 import compare as compare_v060
from .legacy_engine_v061 import compare as compare_v061
from .legacy_engine_v062 import compare as compare_v062
from .legacy_engine_v063 import compare as compare_v063
from .legacy_engine_v064 import compare as compare_v064
from .legacy_engine_v065 import compare as compare_v065
from .legacy_engine_v066 import compare as compare_v066
from .legacy_engine_v067 import compare as compare_v067
from .check_scope import validate_check_variants, validate_annotation_origin, validate_reference_provenance, validate_annotation_provenance, validate_check_annotations
from .limits import MAX_BUNDLE_BYTES, validate_input_size
from .version import ENGINE_VERSION
from .timestamps import timestamp_key
from .allele_check import AlleleCheck, replay_allele_check, validate_saved_allele_check
from .historical import HistoricalImport, import_historical
from .models import InvestigationResult
from .ensembl import SourceRecord, parse_transcripts, validate_source_snapshot, validate_source_assembly
from .ncbi import ReferenceCheck, ReferenceCheckError, replay_reference_check
from .snpeff import SnpEffCheck, SnpEffCheckRequest, compare_snpeff, check_id, validate_execution_metadata
from .snpeff_databases import validate_database
from .storage import load_reference_check, load_source_record, load_snpeff_check, latest_allele_check

BUNDLE_VERSION = 2
COMPARATORS = {"0.5.0": compare_v050, "0.6.0": compare_v060, "0.6.1": compare_v061,
               "0.6.2": compare_v062, "0.6.3": compare_v063, "0.6.4": compare_v064,
               "0.6.5": compare_v065, "0.6.6": compare_v066, "0.6.7": compare_v067, ENGINE_VERSION: compare}


class BundleManifest(StrictModel):
    format: str
    version: int
    engine_version: str
    entries: dict[str, Any]
    sha256: dict[str, str]
    exported_at: str | None = None
    replayed_from_id: str | None = None


def _verify_source(source: SourceRecord) -> None:
    validate_source_assembly(source)
    if source.origin == "historical_artifact":
        if not source.artifact:
            raise ValueError("Historical source artifact is missing")
        artifact=source.artifact
        rebuilt=import_historical(HistoricalImport(query=source.query,raw_json=artifact["text"],
            source_release=artifact["source_release"],tool_version=artifact["tool_version"],
            generated_at=artifact["generated_at"],assembly_accession=source.assembly_accession,
            source_uri=artifact["source_uri"]))
        if source.model_dump(exclude={"retrieved_at"}) != rebuilt.model_dump(exclude={"retrieved_at"}):
            raise ValueError("Historical source does not match its preserved artifact and provenance")
        return
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
    derived = parse_transcripts(rows)
    if derived != source.transcripts:
        raise ValueError("Bundle transcript rows do not match the preserved response")
    expected_id = hashlib.sha256(json.dumps({"query": query.model_dump(), "release": source.releases,
        "assembly": source.assembly_accession, "raw": source.source_response_sha256,
        "retrieved_at": source.retrieved_at}, sort_keys=True).encode()).hexdigest()[:20]
    if source.id != expected_id:
        raise ValueError("Bundle source record ID does not match its contents")


def _verify_reference(source: SourceRecord, check: ReferenceCheck) -> None:
    try:
        expected = replay_reference_check(source, check.reference_fasta,
            check.contextual_response, check.hgvs_response, check.checked_at)
    except ReferenceCheckError as exc:
        raise ValueError(f"Bundle NCBI check cannot be replayed: {exc}") from exc
    if check != expected:
        raise ValueError("Bundle NCBI observations, metadata, or agreement flags do not match its preserved responses")


def _verify_snpeff(source: SourceRecord, check: SnpEffCheck) -> None:
    if hashlib.sha256(check.vcf_text.encode("utf-8")).hexdigest() != check.vcf_sha256:
        raise ValueError("Bundle SnpEff VCF hash does not match")
    expected_id = digest({"source": source.id, "vcf": check.vcf_text, "checked_at": check.checked_at})[:20]
    request = SnpEffCheckRequest(vcf_text=check.vcf_text,
        snpeff_version=check.snpeff_version, genome_database=check.genome_database,
        database_sha256=check.database_sha256)
    validate_required_text(request)
    replay = compare_snpeff(source, request)
    # Retain replay support for observations saved before declaration-aware IDs.
    valid_ids = {expected_id, check_id(source.id, request, check.checked_at)}
    if (check.id not in valid_ids or check.status != replay.status or check.matches != replay.matches or
            check.unmatched_ensembl != replay.unmatched_ensembl or check.unmatched_snpeff != replay.unmatched_snpeff or
            check.explanation != replay.explanation):
        raise ValueError("Bundle SnpEff check does not match a comparison replay")
    if check.execution:
        run = check.execution
        validate_execution_metadata(run)
        if ((run.capture_format == 'utf8_bytes' and run.stderr_sha256 is None) or
                (run.stderr_sha256 is not None and hashlib.sha256(run.stderr.encode('utf-8')).hexdigest() != run.stderr_sha256)):
            raise ValueError('SnpEff execution stderr does not match its preserved byte hash')
        if run.assembly_name is not None or run.assembly_accession is not None:
            expected = validate_database({"genome":check.genome_database,
                "assembly_name":run.assembly_name,"assembly_accession":run.assembly_accession})
            if source.assembly_accession != expected["assembly_accession"]:
                raise ValueError("SnpEff execution assembly does not match its source")
        q = source.query
        expected_vcf = ("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
                        f"{q.chromosome}\t{q.position}\t.\t{q.ref}\t{q.alt}\t.\tPASS\t.\n")
        if (run.input_vcf != expected_vcf or hashlib.sha256(run.input_vcf.encode()).hexdigest()!=run.input_vcf_sha256 or
                run.output_vcf_sha256!=check.vcf_sha256 or digest(run.database_files)!=run.database_sha256 or
                run.database_sha256!=check.database_sha256 or run.software_version[:100]!=check.snpeff_version):
            raise ValueError("SnpEff execution metadata does not match its preserved inputs and outputs")


def create_bundle(db_path, result: InvestigationResult) -> dict:
    # Older records remain readable, but their stored output belongs to an
    # earlier engine. Export a current replay so import can check every result.
    original_id = result.id
    original_result = result
    replay = compare(result.input)
    replayed_from_id = result.id if replay != result else None
    result = replay
    entries = {"investigation": result.model_dump(mode="json")}
    allele_check = latest_allele_check(db_path, original_id)
    if allele_check:
        try:
            validate_saved_allele_check(original_result, allele_check)
            allele_check = replay_allele_check(result, allele_check.observations, allele_check.checked_at)
        except (ReferenceCheckError, ValueError) as exc:
            raise ValueError(f"Saved allele check cannot be exported: {exc}") from exc
        entries["allele_check"] = allele_check.model_dump(mode="json")
    source_ids = {s.provenance.configuration.get("source_record_id") for s in result.input.snapshots} - {None}
    sources=[]
    for source_id in sorted(source_ids):
        source = load_source_record(db_path, source_id)
        if not source:
            raise ValueError("Linked source record is missing; the bundle cannot preserve its evidence")
        sources.append(source.model_dump(mode="json"))
    if len(sources)==1:
        entries["source_record"]=sources[0]
    elif sources:
        entries["source_records"]=sources
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
    bundle = {"format": "GenomeDebugger bundle", "version": BUNDLE_VERSION, "engine_version": ENGINE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "replayed_from_id": replayed_from_id,
            "entries": entries, "sha256": {key: digest(value) for key, value in entries.items()}}
    if len(canonical_json(bundle).encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds the 32 MB portability limit; split the investigation before exporting")
    verify_bundle(bundle)
    return bundle


def verify_bundle(bundle: dict, *, new_submission=True) -> tuple[InvestigationResult, list[SourceRecord], ReferenceCheck | None, SnpEffCheck | None, AlleleCheck | None]:
    BundleManifest.model_validate(bundle, strict=True)
    if (bundle.get("format") != "GenomeDebugger bundle" or bundle.get("version") != BUNDLE_VERSION or
            bundle.get("engine_version") not in COMPARATORS):
        raise ValueError("Unsupported bundle format or version")
    entries, hashes = bundle.get("entries"), bundle.get("sha256")
    allowed = {"investigation", "source_record", "source_records", "reference_check", "snpeff_check", "allele_check"}
    if (not isinstance(entries, dict) or not isinstance(hashes, dict) or
            "investigation" not in entries or not set(entries) <= allowed or set(entries) != set(hashes)):
        raise ValueError("Bundle entries and hashes do not match")
    for name, value in entries.items():
        if digest(value) != hashes[name]:
            raise ValueError(f"Bundle entry {name} failed its SHA-256 check")
    result = InvestigationResult.model_validate(entries["investigation"])
    if new_submission:
        validate_required_text(result.input)
        validate_input_size(result.input)
    rules = COMPARATORS[bundle["engine_version"]]
    original_unversioned = not new_submission and 'engine_version' not in entries['investigation']
    if original_unversioned:
        from .archived_restore import validate_unversioned
        validate_unversioned(entries['investigation'])
    elif result.engine_version != bundle["engine_version"] or result != rules(result.input):
        raise ValueError("Investigation result does not match a replay of its declared engine version")
    if "source_record" in entries and "source_records" in entries:
        raise ValueError("Bundle must use one source-record collection")
    raw_sources=[entries["source_record"]] if "source_record" in entries else entries.get("source_records",[])
    if not isinstance(raw_sources,list) or len(raw_sources)>2:
        raise ValueError("Bundle supports at most two source records")
    sources=[SourceRecord.model_validate(item) for item in raw_sources]
    source_map={item.id:item for item in sources}
    if len(source_map)!=len(sources):
        raise ValueError("Bundle source record IDs must be unique")
    check = ReferenceCheck.model_validate(entries["reference_check"]) if "reference_check" in entries else None
    snpeff = SnpEffCheck.model_validate(entries["snpeff_check"]) if "snpeff_check" in entries else None
    allele_check = AlleleCheck.model_validate(entries["allele_check"]) if "allele_check" in entries else None
    if allele_check:
        try:
            replayed_check = replay_allele_check(result, allele_check.observations, allele_check.checked_at)
        except ReferenceCheckError as exc:
            raise ValueError(f"Allele check cannot be replayed: {exc}") from exc
        if allele_check != replayed_check:
            raise ValueError("Allele check does not match its preserved reference observations")
    for record in [*sources, *([check] if check else []), *([snpeff] if snpeff else []), *([allele_check] if allele_check else [])]:
        timestamp_key(record.retrieved_at if isinstance(record, SourceRecord) else record.checked_at)
    for source in sources:
        _verify_source(source)
    if check:
        source=source_map.get(check.source_record_id)
        if source is None:
            raise ValueError("Bundle NCBI check requires its source record")
        _verify_reference(source, check)
    required_ids={s.provenance.configuration.get("source_record_id") for s in result.input.snapshots} - {None}
    if set(source_map)!=required_ids:
        raise ValueError("Bundle source records do not match investigation provenance")
    if any(s.provenance.input_sha256 != source_map[s.provenance.configuration["source_record_id"]].source_response_sha256
           for s in result.input.snapshots if s.provenance.configuration.get("source_record_id")):
        raise ValueError("Bundle source response hash does not match investigation provenance")
    for snapshot in result.input.snapshots:
        source_id = snapshot.provenance.configuration.get("source_record_id")
        if source_id:
            validate_source_snapshot(source_map[source_id], snapshot)
    if check and (check.source_record_id not in source_map or
                  not result.input.reference_check or check.id != result.input.reference_check.id):
        raise ValueError("Bundle reference check does not match its source or investigation")
    reference_summary = result.input.reference_check
    validate_reference_provenance(result.input)
    validate_annotation_provenance(result.input)
    if reference_summary and (not check or reference_summary.source_record_id != check.source_record_id or reference_summary.source_response_sha256 != check.source_response_sha256 or
        reference_summary.refseq_accession != check.refseq_accession or
        reference_summary.expected_reference != check.expected_reference or
        reference_summary.observed_reference != check.observed_reference or
        reference_summary.reference_matches != check.reference_matches or
        reference_summary.spdi_matches != check.spdi_matches or
        reference_summary.hgvs_matches != check.hgvs_matches or
        reference_summary.status != check.status):
        raise ValueError("Bundle NCBI check does not match its investigation summary")
    if check:
        validate_check_variants(result.input, source_map[check.source_record_id], "NCBI reference")
    if snpeff and (snpeff.source_record_id not in source_map or snpeff.source_response_sha256 != source_map[snpeff.source_record_id].source_response_sha256):
        raise ValueError("Bundle SnpEff check does not match its source record")
    annotation_summary = result.input.annotation_check
    if annotation_summary and (not snpeff or annotation_summary.id != snpeff.id or
        annotation_summary.source_record_id != snpeff.source_record_id or
        annotation_summary.source_response_sha256 != snpeff.source_response_sha256 or
        annotation_summary.vcf_sha256 != snpeff.vcf_sha256 or annotation_summary.status != snpeff.status or
        annotation_summary.matched_transcripts != len(snpeff.matches) or
        annotation_summary.snpeff_version != snpeff.snpeff_version or
        annotation_summary.genome_database != snpeff.genome_database or
        annotation_summary.database_sha256 != snpeff.database_sha256):
        raise ValueError("Bundle SnpEff check does not match its investigation summary")
    if snpeff and not annotation_summary:
        raise ValueError("Bundle includes a SnpEff check not linked by the investigation")
    if snpeff:
        validate_check_annotations(result.input, source_map[snpeff.source_record_id])
        validate_annotation_origin(result.input, snpeff)
        validate_check_variants(result.input, source_map[snpeff.source_record_id], "SnpEff annotation")
        _verify_snpeff(source_map[snpeff.source_record_id], snpeff)
    return result, sources, check, snpeff, allele_check
