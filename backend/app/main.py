import os
import ipaddress
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from .engine import compare
from .allele_check import fetch_allele_check
from .limits import MAX_BUNDLE_BYTES, MAX_INPUT_BYTES
from .ensembl import PUBLIC_EXAMPLE, CompareTranscripts, SourceError, SourceLookup, SourceLookupResult, SourceRecord, comparison_input, fetch_record
from .models import AnnotationCheckSummary, InvestigationInput, InvestigationResult, ReferenceCheckSummary
from .ncbi import ReferenceCheck, ReferenceCheckError, ReferenceCheckRequest, ReferenceCheckResult, fetch_reference_check
from .regression import CreateRegressionCase, RegressionCase, RegressionRun, RegressionRunRequest, create_case, run_case
from .report import markdown_report
from .snpeff import SnpEffCheck, SnpEffCheckRequest, compare_snpeff
from .snpeff_runner import runtime_status, run_snpeff
from .historical import HistoricalImport, SourcePair, import_historical, comparison_pair
from .bundle import ENGINE_VERSION, create_bundle, verify_bundle
from .storage import list_items, load, save, save_case, load_case, list_cases, save_run, load_run, list_runs, save_source_record, load_source_record, latest_source_record, save_reference_check, latest_reference_check, load_reference_check, delete_investigation, initialize, StorageLimitError, RecordConflictError, save_snpeff_check, latest_snpeff_check
from .storage import save_allele_check, latest_allele_check
from .storage import list_source_records, save_bundle_records
from .storage import load_snpeff_check
from .storage import RecordMissingError
from .check_scope import validate_check_variants, validate_annotation_origin
from .ensembl import validate_source_snapshot
from .version import APP_VERSION

BASE = Path(__file__).resolve().parents[2]
DEMO = BASE / "fixtures" / "transcript-switch.json"
DB = Path(os.environ.get("GENOMEDEBUGGER_DB", str(BASE / "data" / "investigations.db")))
app = FastAPI(title="GenomeDebugger", version=APP_VERSION, description="Compare genomic analysis results with preserved sources and optional independent checks")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])


def validate_linked_checks(payload: InvestigationInput):
    for snapshot in payload.snapshots:
        source_id = snapshot.provenance.configuration.get("source_record_id")
        if source_id:
            source = load_source_record(DB, source_id)
            if source is None or snapshot.provenance.input_sha256 != source.source_response_sha256:
                raise ValueError("Snapshot requires its preserved source record and matching response hash")
            try:
                validate_source_snapshot(source, snapshot)
            except ValueError as exc:
                raise ValueError(f"{exc}. Restore the source output or identify transformed output as a custom tool.") from exc
    for label, summary, loader in (("NCBI reference", payload.reference_check, load_reference_check),
                                   ("SnpEff annotation", payload.annotation_check, load_snpeff_check)):
        if summary is None:
            continue
        check = loader(DB, summary.id)
        source = load_source_record(DB, summary.source_record_id)
        if check is None or source is None:
            raise ValueError(f"{label} summary requires its preserved source and check records")
        fields = set(type(summary).model_fields)
        observed = check.model_dump(include=fields)
        if isinstance(summary, AnnotationCheckSummary):
            observed["matched_transcripts"] = len(check.matches)
            validate_annotation_origin(payload, check)
        if type(summary).model_validate(observed) != summary or source.source_response_sha256 != summary.source_response_sha256:
            raise ValueError(f"{label} summary does not match its preserved check")
        validate_check_variants(payload, source, label)


@app.exception_handler(StorageLimitError)
async def storage_limit_error(_request: Request, exc: StorageLimitError):
    return JSONResponse(status_code=507, content={"detail": str(exc)})


@app.exception_handler(RecordConflictError)
async def record_conflict_error(_request: Request, exc: RecordConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(RecordMissingError)
async def record_missing_error(_request: Request, exc: RecordMissingError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.middleware("http")
async def limit_input(request: Request, call_next):
    client_host = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local = client_host == "testclient"
    if not local:
        return JSONResponse(status_code=403, content={"detail": "GenomeDebugger accepts local connections only"})
    if request.method == "POST":
        limit = MAX_BUNDLE_BYTES if request.url.path in {"/api/bundles/verify", "/api/bundles/import"} else MAX_INPUT_BYTES
        detail = "Bundle exceeds 32 MB limit" if limit == MAX_BUNDLE_BYTES else "Input exceeds 1 MB limit"
        try:
            declared_size = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        if declared_size > limit:
            return JSONResponse(status_code=413, content={"detail": detail})
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return JSONResponse(status_code=413, content={"detail": detail})
            chunks.append(chunk)
        request._body = b"".join(chunks)
    return await call_next(request)


@app.get("/api/health")
def health():
    try:
        initialize(DB)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Local database unavailable") from exc
    return {"status": "ok", "version": ENGINE_VERSION, "app_version":APP_VERSION,
            "limits": {"input_bytes": MAX_INPUT_BYTES, "bundle_bytes": MAX_BUNDLE_BYTES}}


@app.get("/api/sources/ensembl/example")
def ensembl_example():
    return PUBLIC_EXAMPLE


@app.get("/api/tools/snpeff")
def snpeff_runtime():
    return runtime_status()


@app.get("/api/sources/records")
def preserved_sources(limit: int = Query(default=200, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return [{**record.model_dump(exclude={"source_response","artifact"}),
             "artifact":{key:value for key,value in record.artifact.items() if key!="text"} if record.artifact else None}
            for record in list_source_records(DB, limit, offset)]


@app.post("/api/sources/historical-vep",response_model=SourceRecord)
def historical_vep(payload: HistoricalImport):
    try:
        record=import_historical(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    save_source_record(DB,record)
    return record


@app.post("/api/sources/compare",response_model=InvestigationResult)
def compare_source_records(payload: SourcePair):
    left=load_source_record(DB,payload.source_a)
    right=load_source_record(DB,payload.source_b)
    if left is None or right is None:
        raise HTTPException(status_code=404,detail="Both preserved source records must exist")
    try:
        result=compare(comparison_pair(left,right,payload))
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    save(DB,result)
    return result


@app.post("/api/sources/ensembl/records/{id_}/snpeff-run",response_model=SnpEffCheck)
def snpeff_local_run(id_: str):
    record=load_source_record(DB,id_)
    if record is None:
        raise HTTPException(status_code=404,detail="Source record not found")
    try:
        check=run_snpeff(record)
    except (ValueError,OSError,KeyError) as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    save_snpeff_check(DB,check)
    return check


@app.post("/api/sources/ensembl/lookup", response_model=SourceLookupResult)
def ensembl_lookup(payload: SourceLookup):
    cached = latest_source_record(DB, payload.query)
    if payload.mode == "cache_only":
        if cached is None:
            raise HTTPException(status_code=404, detail="No local Ensembl record is cached for this variant")
        return SourceLookupResult(record=cached, access="cache")
    try:
        record = fetch_record(payload.query)
    except SourceError as exc:
        if cached is not None:
            return SourceLookupResult(record=cached, access="cached_after_error", warning=f"Live Ensembl fetch failed: {exc}. Showing the previously retrieved local record.")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    save_source_record(DB, record)
    return SourceLookupResult(record=record, access="fetched")


@app.get("/api/sources/ensembl/records/{id_}", response_model=SourceRecord)
def ensembl_record(id_: str):
    record = load_source_record(DB, id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    return record


@app.post("/api/sources/ensembl/records/{id_}/reference-check", response_model=ReferenceCheckResult)
def check_ensembl_reference(id_: str, payload: ReferenceCheckRequest):
    record = load_source_record(DB, id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    cached = latest_reference_check(DB, id_)
    if payload.mode == "cache_only":
        if cached is None:
            raise HTTPException(status_code=404, detail="No local NCBI check is cached for this source record")
        return ReferenceCheckResult(check=cached, access="cache")
    try:
        check = fetch_reference_check(record)
    except ReferenceCheckError as exc:
        if cached is not None:
            return ReferenceCheckResult(check=cached, access="cached_after_error", warning=f"Live NCBI check failed: {exc}. Showing the previous local check.")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    save_reference_check(DB, check)
    return ReferenceCheckResult(check=check, access="fetched")


@app.get("/api/sources/reference-checks/{id_}", response_model=ReferenceCheck)
def reference_check(id_: str):
    check = load_reference_check(DB, id_)
    if check is None:
        raise HTTPException(status_code=404, detail="Reference check not found")
    return check


@app.post("/api/sources/ensembl/records/{id_}/snpeff-check", response_model=SnpEffCheck)
def snpeff_check(id_: str, payload: SnpEffCheckRequest):
    record = load_source_record(DB, id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    try:
        check = compare_snpeff(record, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_snpeff_check(DB, check)
    return check


@app.get("/api/sources/ensembl/records/{id_}/snpeff-check", response_model=SnpEffCheck)
def saved_snpeff_check(id_: str):
    check = latest_snpeff_check(DB, id_)
    if check is None:
        raise HTTPException(status_code=404, detail="No SnpEff check saved for this record")
    return check


@app.post("/api/sources/ensembl/records/{id_}/compare", response_model=InvestigationResult)
def compare_ensembl_transcripts(id_: str, payload: CompareTranscripts):
    record = load_source_record(DB, id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    try:
        check = latest_reference_check(DB, id_)
        summary = ReferenceCheckSummary.model_validate(check.model_dump(include={
            "id", "source_record_id", "source_response_sha256", "refseq_accession",
            "expected_reference", "observed_reference", "reference_matches",
            "spdi_matches", "hgvs_matches", "status"})) if check else None
        annotation = latest_snpeff_check(DB, id_)
        annotation_summary = AnnotationCheckSummary(
            id=annotation.id, source_record_id=annotation.source_record_id,
            source_response_sha256=annotation.source_response_sha256, vcf_sha256=annotation.vcf_sha256,
            snpeff_version=annotation.snpeff_version, genome_database=annotation.genome_database,
            database_sha256=annotation.database_sha256, status=annotation.status,
            matched_transcripts=len(annotation.matches)) if annotation else None
        investigation_input = comparison_input(record, payload, summary, annotation_summary)
        if annotation:
            for snapshot in investigation_input.snapshots:
                snapshot.provenance.configuration["annotation_check_origin"] = "local_execution" if annotation.execution else "user_supplied"
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = compare(investigation_input)
    save(DB, result)
    return result


@app.get("/api/demos/transcript-switch", response_model=InvestigationInput)
def demo():
    return InvestigationInput.model_validate_json(DEMO.read_text(encoding="utf-8"))


@app.post("/api/investigations", response_model=InvestigationResult)
def create_investigation(payload: InvestigationInput):
    try:
        validate_linked_checks(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = compare(payload)
    save(DB, result)
    return result


@app.get("/api/investigations")
def investigations(q: str = Query(default="", max_length=200), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return list_items(DB, q, limit, offset)


@app.get("/api/investigations/{id_}", response_model=InvestigationResult)
def investigation(id_: str):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return result


@app.post("/api/investigations/{id_}/allele-check")
def check_investigation_alleles(id_: str, payload: ReferenceCheckRequest):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if payload.mode == "cache_only":
        check = latest_allele_check(DB, id_)
        if check is None:
            raise HTTPException(status_code=404, detail="No reference-backed allele check is saved for this investigation")
        return check
    try:
        check = fetch_allele_check(result)
    except (ReferenceCheckError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_allele_check(DB, check)
    return check


@app.delete("/api/investigations/{id_}")
def remove_investigation(id_: str):
    try:
        removed = delete_investigation(DB, id_)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"deleted": id_}


@app.get("/api/investigations/{id_}/bundle")
def investigation_bundle(id_: str):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        return create_bundle(DB, result)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/bundles/verify")
def bundle_verify(payload: dict):
    try:
        result, source, check, snpeff, allele_check = verify_bundle(payload)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"valid": True, "investigation_id": result.id, "has_source_record": bool(source), "has_reference_check": check is not None, "has_snpeff_check": snpeff is not None, "has_allele_check":allele_check is not None}


@app.post("/api/bundles/import")
def bundle_import(payload: dict):
    try:
        result, source, check, snpeff, allele_check = verify_bundle(payload)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_bundle_records(DB, result, source, check, snpeff, allele_check)
    return {"imported": result.id}


@app.get("/api/investigations/{id_}/report.md", response_class=PlainTextResponse)
def report(id_: str):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    annotation = load_snpeff_check(DB, result.input.annotation_check.id) if result.input.annotation_check else None
    return markdown_report(result, latest_allele_check(DB,result.id), annotation)


@app.post("/api/investigations/{id_}/regression-cases", response_model=RegressionCase)
def create_regression_case(id_: str, payload: CreateRegressionCase):
    source = load(DB, id_)
    if source is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    case = create_case(source, payload.name)
    save_case(DB, case)
    return case


@app.get("/api/regression-cases")
def regression_cases(source_investigation_id: str | None = Query(default=None, max_length=100),
                     limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    return list_cases(DB, source_investigation_id, limit, offset)


@app.get("/api/regression-cases/{id_}", response_model=RegressionCase)
def regression_case(id_: str):
    case = load_case(DB, id_)
    if case is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    return case


@app.post("/api/regression-cases/{id_}/runs", response_model=RegressionRun)
def run_regression_case(id_: str, payload: RegressionRunRequest):
    case = load_case(DB, id_)
    if case is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    try:
        if payload.candidate is not None:
            validate_linked_checks(payload.candidate)
        run = run_case(case, payload.candidate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_run(DB, run)
    return run


@app.get("/api/regression-cases/{id_}/runs")
def regression_runs(id_: str, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    if load_case(DB, id_) is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    return list_runs(DB, id_, limit, offset)


@app.get("/api/regression-runs/{id_}", response_model=RegressionRun)
def regression_run(id_: str):
    run = load_run(DB, id_)
    if run is None:
        raise HTTPException(status_code=404, detail="Regression run not found")
    return run
