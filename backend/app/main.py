import os
import ipaddress
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from .engine import compare
from .ensembl import PUBLIC_EXAMPLE, CompareTranscripts, SourceError, SourceLookup, SourceLookupResult, SourceRecord, comparison_input, fetch_record
from .models import AnnotationCheckSummary, InvestigationInput, InvestigationResult, ReferenceCheckSummary
from .ncbi import ReferenceCheck, ReferenceCheckError, ReferenceCheckRequest, ReferenceCheckResult, fetch_reference_check
from .regression import CreateRegressionCase, RegressionCase, RegressionRun, RegressionRunRequest, create_case, run_case
from .report import markdown_report
from .snpeff import SnpEffCheck, SnpEffCheckRequest, compare_snpeff
from .bundle import ENGINE_VERSION, create_bundle, verify_bundle
from .storage import list_items, load, save, save_case, load_case, list_cases, save_run, load_run, list_runs, save_source_record, load_source_record, latest_source_record, save_reference_check, latest_reference_check, load_reference_check, delete_investigation, initialize, StorageLimitError, RecordConflictError, save_snpeff_check, latest_snpeff_check

BASE = Path(__file__).resolve().parents[2]
DEMO = BASE / "fixtures" / "transcript-switch.json"
DB = Path(os.environ.get("GENOMEDEBUGGER_DB", str(BASE / "data" / "investigations.db")))
app = FastAPI(title="GenomeDebugger", version=ENGINE_VERSION, description="Local genomic discrepancy investigation with optional Ensembl and NCBI checks and user supplied SnpEff output comparison")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])


@app.exception_handler(StorageLimitError)
async def storage_limit_error(_request: Request, exc: StorageLimitError):
    return JSONResponse(status_code=507, content={"detail": str(exc)})


@app.exception_handler(RecordConflictError)
async def record_conflict_error(_request: Request, exc: RecordConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


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
        limit = 1_000_000
        if int(request.headers.get("content-length", "0")) > limit:
            return JSONResponse(status_code=413, content={"detail": "Input exceeds 1 MB limit"})
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return JSONResponse(status_code=413, content={"detail": "Input exceeds 1 MB limit"})
            chunks.append(chunk)
        request._body = b"".join(chunks)
    return await call_next(request)


@app.get("/api/health")
def health():
    try:
        initialize(DB)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Local database unavailable") from exc
    return {"status": "ok", "version": ENGINE_VERSION}


@app.get("/api/sources/ensembl/example")
def ensembl_example():
    return PUBLIC_EXAMPLE


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
        result, source, check, snpeff = verify_bundle(payload)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"valid": True, "investigation_id": result.id, "has_source_record": source is not None, "has_reference_check": check is not None, "has_snpeff_check": snpeff is not None}


@app.post("/api/bundles/import")
def bundle_import(payload: dict):
    try:
        result, source, check, snpeff = verify_bundle(payload)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = load(DB, result.id)
    if existing is not None and existing != result:
        raise HTTPException(status_code=409, detail="An investigation with this input ID already has a different saved result")
    if source:
        save_source_record(DB, source)
    if check:
        save_reference_check(DB, check)
    if snpeff:
        save_snpeff_check(DB, snpeff)
    save(DB, result)
    return {"imported": result.id}


@app.get("/api/investigations/{id_}/report.md", response_class=PlainTextResponse)
def report(id_: str):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return markdown_report(result)


@app.post("/api/investigations/{id_}/regression-cases", response_model=RegressionCase)
def create_regression_case(id_: str, payload: CreateRegressionCase):
    source = load(DB, id_)
    if source is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    case = create_case(source, payload.name)
    save_case(DB, case)
    return case


@app.get("/api/regression-cases")
def regression_cases():
    return list_cases(DB)


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
        run = run_case(case, payload.candidate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_run(DB, run)
    return run


@app.get("/api/regression-cases/{id_}/runs")
def regression_runs(id_: str):
    if load_case(DB, id_) is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    return list_runs(DB, id_)


@app.get("/api/regression-runs/{id_}", response_model=RegressionRun)
def regression_run(id_: str):
    run = load_run(DB, id_)
    if run is None:
        raise HTTPException(status_code=404, detail="Regression run not found")
    return run
