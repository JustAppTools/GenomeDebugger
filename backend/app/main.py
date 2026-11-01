import os
import hashlib
import ipaddress
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse, Response
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from .engine import compare
from .allele_check import fetch_allele_check, replay_allele_check, validate_saved_allele_check
from .limits import MAX_BUNDLE_BYTES, MAX_INPUT_BYTES, MAX_INPUT_DATA_BYTES, InputSizeError, validate_input_size
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
from .storage import list_investigation_page
from .check_scope import validate_check_variants, validate_annotation_origin, validate_reference_provenance, validate_annotation_provenance
from .ensembl import validate_source_snapshot, validate_source_assembly
from .version import APP_VERSION
from .admission import validate_required_text
from .ncbi import validate_saved_reference_check
from .snpeff import validate_execution_metadata
from .check_scope import validate_check_annotations
from .tabular_import import TabularPair, preview_pair
from .workspace import LibraryLabelUpdate, save_label, read_label, list_library, local_data, MAX_SQLITE_INTEGER
from typing import Literal
from .storage import backup
import tempfile
import io
import json
import zipfile
from pydantic import BaseModel, Field
from .identifier import IdentifierRequest, resolve_identifier
from contextlib import asynccontextmanager
from .workspace_lock import WorkspaceLock
from .hosting import PublicHosting, REQUEST_DATABASE, HostingCapacityError

BASE = Path(os.environ.get('GENOMEDEBUGGER_RESOURCES', str(Path(__file__).resolve().parents[2])))
DEMO = BASE / "fixtures" / "transcript-switch.json"
DB = Path(os.environ.get("GENOMEDEBUGGER_DB", str(BASE / "data" / "investigations.db")))
HOSTING = PublicHosting.from_environment()


def database():
    return REQUEST_DATABASE.get() or DB


@asynccontextmanager
async def workspace_lifespan(_app):
    # Public preview uses one process and request-scoped visitor databases.
    with WorkspaceLock(HOSTING.root / 'server' if HOSTING.enabled else DB):
        yield


app = FastAPI(title="GenomeDebugger", version=APP_VERSION, lifespan=workspace_lifespan, description="Compare genomic analysis results with preserved sources and optional independent checks")
TRUSTED_BROWSER_ORIGINS = frozenset({"http://localhost:5173", "http://127.0.0.1:5173"} |
    {origin.strip() for origin in os.environ.get("GENOMEDEBUGGER_ALLOWED_ORIGINS", "").split(",") if origin.strip()})
app.add_middleware(CORSMiddleware, allow_origins=list(TRUSTED_BROWSER_ORIGINS), allow_credentials=False, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError):
    # Rejected values can contain lone surrogates or overflowing numbers. Do not
    # echo raw input/context into a JSON response or expose entire submitted data.
    def safe_text(value, length=512):
        return str(value)[:length].encode("utf-8", errors="replace").decode("utf-8")
    details = [{"loc": [part if isinstance(part, int) else safe_text(part, 200)
                        for part in error.get("loc", ())[:20]],
                "msg": safe_text(error.get("msg", "Invalid value")),
                "type": safe_text(error.get("type", "value_error"), 100)}
               for error in exc.errors()[:50]]
    return JSONResponse(status_code=422, content={"detail": details})


@app.exception_handler(InputSizeError)
async def input_size_error(_request: Request, exc: InputSizeError):
    return JSONResponse(status_code=413, content={"detail": str(exc)})


def validate_linked_checks(payload: InvestigationInput):
    validate_required_text(payload)
    validate_reference_provenance(payload)
    validate_annotation_provenance(payload)
    for snapshot in payload.snapshots:
        source_id = snapshot.provenance.configuration.get("source_record_id")
        if source_id:
            source = load_source_record(database(), source_id)
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
        check = loader(database(), summary.id)
        source = load_source_record(database(), summary.source_record_id)
        if check is None or source is None:
            raise ValueError(f"{label} summary requires its preserved source and check records")
        fields = set(type(summary).model_fields)
        observed = check.model_dump(include=fields)
        if isinstance(summary, AnnotationCheckSummary):
            observed["matched_transcripts"] = len(check.matches)
            validate_annotation_origin(payload, check)
            validate_check_annotations(payload, source)
            if check.execution:
                validate_execution_metadata(check.execution)
        else:
            try:
                validate_saved_reference_check(source, check)
            except ReferenceCheckError as exc:
                raise ValueError(str(exc)) from exc
        if type(summary).model_validate(observed) != summary or source.source_response_sha256 != summary.source_response_sha256:
            raise ValueError(f"{label} summary does not match its preserved check")
        validate_check_variants(payload, source, label)


@app.exception_handler(StorageLimitError)
async def storage_limit_error(_request: Request, exc: StorageLimitError):
    return JSONResponse(status_code=507, content={"detail": str(exc)})


@app.exception_handler(HostingCapacityError)
async def hosting_capacity_error(_request: Request, _exc: HostingCapacityError):
    return JSONResponse({'detail': 'The free preview is at capacity. Download or delete existing work, or try again later.'},
                        status_code=503, headers={'Cache-Control':'no-store','Retry-After':'60'})


@app.exception_handler(RecordConflictError)
async def record_conflict_error(_request: Request, exc: RecordConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(RecordMissingError)
async def record_missing_error(_request: Request, exc: RecordMissingError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.middleware("http")
async def limit_input(request: Request, call_next):
    if HOSTING.enabled:
        return await HOSTING.handle(request, lambda req: bounded_call(req, call_next, {HOSTING.origin}))
    client_host = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local = client_host == "testclient"
    if not local:
        return JSONResponse(status_code=403, content={"detail": "GenomeDebugger accepts local connections only"})
    hostname = None
    try:
        hostname = request.url.hostname
        trusted_host = hostname == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        trusted_host = hostname == "localhost"
    # TestClient's conventional host is never accepted from a real TCP peer.
    if not trusted_host and not (client_host == "testclient" and hostname == "testserver"):
        return JSONResponse(status_code=400, content={"detail": "Untrusted Host header"})
    return await bounded_call(request, call_next, TRUSTED_BROWSER_ORIGINS)


async def bounded_call(request, call_next, origins):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        same_origin = str(request.base_url).rstrip("/")
        if ((origin is not None and origin not in origins and origin != same_origin) or
                (origin is None and request.headers.get("sec-fetch-site") in {"cross-site", "same-site"})):
            return JSONResponse(status_code=403, content={"detail": "Browser origin is not trusted"})
    if request.method == "POST":
        limit = MAX_BUNDLE_BYTES if request.url.path in {"/api/bundles/verify", "/api/bundles/import"} else MAX_INPUT_BYTES
        detail = "Bundle exceeds 32 MB limit" if limit == MAX_BUNDLE_BYTES else "Input exceeds 2 MB request limit"
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


@app.get("/healthz")
def readiness():
    return {"status": "ok"}


@app.get("/api/health")
def health():
    try:
        initialize(database())
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Local database unavailable") from exc
    return {"application": "GenomeDebugger", "project_id": hashlib.sha256(str(BASE.resolve()).lower().encode("utf-8")).hexdigest(),
            "status": "ok", "version": ENGINE_VERSION, "app_version":APP_VERSION,
            **HOSTING.metadata(),
            "limits": {"input_bytes": MAX_INPUT_BYTES, "input_data_bytes": MAX_INPUT_DATA_BYTES, "bundle_bytes": MAX_BUNDLE_BYTES}}


@app.post('/api/imports/tabular/preview')
def preview_tabular(payload: TabularPair):
    try:
        preview = preview_pair(payload)
        validate_input_size(preview['input'])
        return preview
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/sources/ensembl/example")
def ensembl_example():
    return PUBLIC_EXAMPLE


@app.get('/api/workspace/data')
def workspace_data():
    details = local_data(database())
    if HOSTING.enabled:
        details['database_path'] = 'Temporary workspace for this browser'
    return {**details, **HOSTING.metadata(), 'app_version': APP_VERSION, 'engine_version': ENGINE_VERSION,
            'desktop_mode': getattr(app.state, 'desktop_server', None) is not None}


@app.post('/api/workspace/stop')
def stop_desktop():
    if HOSTING.enabled:
        raise HTTPException(status_code=404, detail='Not available in the public preview')
    server = getattr(app.state, 'desktop_server', None)
    if server is None:
        raise HTTPException(status_code=409, detail='Use Stop GenomeDebugger.cmd to stop development services')
    return JSONResponse({'stopping':True}, background=BackgroundTask(setattr, server, 'should_exit', True))


@app.post('/api/sources/resolve-identifier')
def identifier_preview(payload: IdentifierRequest):
    try:
        return resolve_identifier(payload.identifier)
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/api/workspace/backup')
def workspace_backup():
    initialize(database())
    folder = Path(tempfile.mkdtemp(prefix='genomedebugger-backup-'))
    destination = folder / 'genomedebugger-backup.db'
    def cleanup():
        destination.unlink(missing_ok=True)
        folder.rmdir()
    try:
        backup(database(), destination)
    except Exception:
        cleanup()
        raise
    class BackupResponse(FileResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                cleanup()
    return BackupResponse(destination, media_type='application/vnd.sqlite3', filename='genomedebugger-backup.db')


@app.get('/api/workspace/library')
def workspace_library(q: str = Query(default='', max_length=200), view: Literal['active','archived','all'] = 'active',
                      favorite: bool = False, source: str = Query(default='', max_length=100),
                      since: str = Query(default='', pattern=r'^(?:|\d{4}-\d{2}-\d{2})$'),
                      sort: Literal['newest','oldest','name'] = 'newest', offset: int = Query(default=0, ge=0, le=MAX_SQLITE_INTEGER), limit: int = Query(default=50, ge=1, le=100),
                      cursor: str = Query(default='', max_length=4096), ceiling: int | None = Query(default=None, ge=0, le=MAX_SQLITE_INTEGER),
                      since_instant: str = Query(default='', max_length=64)):
    try:
        return list_library(database(), q, view, favorite, source, since, sort, offset, limit, cursor, ceiling, since_instant)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/api/workspace/library/{id_}/label')
def workspace_label_details(id_: str):
    return read_label(database(), id_)


@app.post('/api/workspace/library/{id_}/label')
def workspace_label(id_: str, payload: LibraryLabelUpdate):
    try:
        return save_label(database(), id_, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class SelectedExports(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=20)


@app.post('/api/workspace/export')
def export_selected(payload: SelectedExports):
    output = io.BytesIO()
    size = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for index, id_ in enumerate(dict.fromkeys(payload.ids)):
            result = load(database(), id_)
            if result is None:
                raise HTTPException(status_code=404, detail='A selected comparison is no longer available')
            try:
                bundle = create_bundle(database(), result)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raw = json.dumps(bundle, ensure_ascii=False).encode('utf-8')
            size += len(raw)
            if size > MAX_BUNDLE_BYTES:
                raise HTTPException(status_code=413, detail='Selected export exceeds 32 MB; select fewer comparisons')
            archive.writestr(f'comparison-{index+1}-bundle.json', raw)
    return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition':'attachment; filename="genomedebugger-selected-bundles.zip"'})


@app.get("/api/tools/snpeff")
def snpeff_runtime():
    if HOSTING.enabled:
        return {'configured': False, 'detail': 'The public preview supports supplied SnpEff output. Run a pinned SnpEff installation with the local app.'}
    return runtime_status()


@app.get("/api/sources/records")
def preserved_sources(limit: int = Query(default=200, ge=1, le=500), offset: int = Query(default=0, ge=0, le=MAX_SQLITE_INTEGER)):
    return [{**record.model_dump(exclude={"source_response","artifact"}),
             "artifact":{key:value for key,value in record.artifact.items() if key!="text"} if record.artifact else None}
            for record in list_source_records(database(), limit, offset)]


@app.post("/api/sources/historical-vep",response_model=SourceRecord)
def historical_vep(payload: HistoricalImport):
    try:
        record=import_historical(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    save_source_record(database(),record)
    # Re-importing the same artifact retains its original local capture time.
    return load_source_record(database(), record.id)


@app.post("/api/sources/compare",response_model=InvestigationResult)
def compare_source_records(payload: SourcePair):
    left=load_source_record(database(),payload.source_a)
    right=load_source_record(database(),payload.source_b)
    if left is None or right is None:
        raise HTTPException(status_code=404,detail="Both preserved source records must exist")
    try:
        investigation_input = comparison_pair(left,right,payload)
        validate_required_text(investigation_input)
        validate_input_size(investigation_input)
        result=compare(investigation_input)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    save(database(),result)
    return result


@app.post("/api/sources/ensembl/records/{id_}/snpeff-run",response_model=SnpEffCheck)
def snpeff_local_run(id_: str):
    if HOSTING.enabled:
        raise HTTPException(status_code=409, detail='Use supplied SnpEff output or run SnpEff with the local app')
    record=load_source_record(database(),id_)
    if record is None:
        raise HTTPException(status_code=404,detail="Source record not found")
    try:
        check=run_snpeff(record)
    except (ValueError,OSError,KeyError) as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    save_snpeff_check(database(),check)
    return check


@app.post("/api/sources/ensembl/lookup", response_model=SourceLookupResult)
def ensembl_lookup(payload: SourceLookup):
    cached = latest_source_record(database(), payload.query)
    if cached is not None:
        try:
            validate_source_assembly(cached)
        except ValueError as exc:
            if payload.mode == 'cache_only':
                raise HTTPException(status_code=422, detail=f'Cached source metadata is inconsistent: {exc}. Fetch a new capture.') from exc
            cached = None
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
    save_source_record(database(), record)
    return SourceLookupResult(record=record, access="fetched")


@app.get("/api/sources/ensembl/records/{id_}", response_model=SourceRecord)
def ensembl_record(id_: str):
    record = load_source_record(database(), id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    return record


@app.post("/api/sources/ensembl/records/{id_}/reference-check", response_model=ReferenceCheckResult)
def check_ensembl_reference(id_: str, payload: ReferenceCheckRequest):
    record = load_source_record(database(), id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    cached = latest_reference_check(database(), id_, validate=lambda check: validate_saved_reference_check(record, check))
    if payload.mode == "cache_only":
        if cached is None:
            raise HTTPException(status_code=404, detail="No usable local NCBI check is cached for this source record")
        return ReferenceCheckResult(check=cached, access="cache")
    try:
        check = fetch_reference_check(record)
    except ReferenceCheckError as exc:
        if cached is not None:
            return ReferenceCheckResult(check=cached, access="cached_after_error", warning=f"Live NCBI check failed: {exc}. Showing the previous local check.")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    save_reference_check(database(), check)
    return ReferenceCheckResult(check=check, access="fetched")


@app.get("/api/sources/reference-checks/{id_}", response_model=ReferenceCheck)
def reference_check(id_: str):
    check = load_reference_check(database(), id_)
    if check is None:
        raise HTTPException(status_code=404, detail="Reference check not found")
    return check


@app.post("/api/sources/ensembl/records/{id_}/snpeff-check", response_model=SnpEffCheck)
def snpeff_check(id_: str, payload: SnpEffCheckRequest):
    record = load_source_record(database(), id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    try:
        validate_required_text(payload)
        check = compare_snpeff(record, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_snpeff_check(database(), check)
    return check


@app.get("/api/sources/ensembl/records/{id_}/snpeff-check", response_model=SnpEffCheck)
def saved_snpeff_check(id_: str):
    check = latest_snpeff_check(database(), id_)
    if check is None:
        raise HTTPException(status_code=404, detail="No SnpEff check saved for this record")
    if check.execution:
        try:
            validate_execution_metadata(check.execution)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f'Saved execution metadata is invalid: {exc}') from exc
    return check


@app.post("/api/sources/ensembl/records/{id_}/compare", response_model=InvestigationResult)
def compare_ensembl_transcripts(id_: str, payload: CompareTranscripts):
    record = load_source_record(database(), id_)
    if record is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    try:
        if "reference_check_id" in payload.model_fields_set:
            check = load_reference_check(database(), payload.reference_check_id) if payload.reference_check_id else None
            if payload.reference_check_id and (check is None or check.source_record_id != id_):
                raise ValueError("Selected NCBI check is missing or belongs to a different source record")
        else:
            check = latest_reference_check(database(), id_, validate=lambda check: validate_saved_reference_check(record, check))
        if check:
            try:
                validate_saved_reference_check(record, check)
            except ReferenceCheckError as exc:
                raise ValueError(str(exc)) from exc
        summary = ReferenceCheckSummary.model_validate(check.model_dump(include={
            "id", "source_record_id", "source_response_sha256", "refseq_accession",
            "expected_reference", "observed_reference", "reference_matches",
            "spdi_matches", "hgvs_matches", "status"})) if check else None
        if "annotation_check_id" in payload.model_fields_set:
            annotation = load_snpeff_check(database(), payload.annotation_check_id) if payload.annotation_check_id else None
            if payload.annotation_check_id and (annotation is None or annotation.source_record_id != id_):
                raise ValueError("Selected SnpEff check is missing or belongs to a different source record")
        else:
            annotation = latest_snpeff_check(database(), id_)
        if annotation and annotation.execution:
            validate_execution_metadata(annotation.execution)
        annotation_summary = AnnotationCheckSummary(
            id=annotation.id, source_record_id=annotation.source_record_id,
            source_response_sha256=annotation.source_response_sha256, vcf_sha256=annotation.vcf_sha256,
            snpeff_version=annotation.snpeff_version, genome_database=annotation.genome_database,
            database_sha256=annotation.database_sha256, status=annotation.status,
            matched_transcripts=len(annotation.matches)) if annotation else None
        investigation_input = comparison_input(record, payload, summary, annotation_summary)
        validate_required_text(investigation_input)
        if annotation:
            for snapshot in investigation_input.snapshots:
                snapshot.provenance.configuration["annotation_check_origin"] = "local_execution" if annotation.execution else "user_supplied"
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    validate_input_size(investigation_input)
    result = compare(investigation_input)
    save(database(), result)
    return result


@app.get("/api/demos/transcript-switch", response_model=InvestigationInput)
def demo():
    return InvestigationInput.model_validate_json(DEMO.read_text(encoding="utf-8"))


@app.get('/api/demos/{kind}', response_model=InvestigationInput)
def teaching_case(kind: Literal['matching','uncertain']):
    payload = InvestigationInput.model_validate_json(DEMO.read_text(encoding='utf-8'))
    payload.controlled_lookup = None
    if kind == 'matching':
        payload.title = 'Teaching example: matching outputs'
        second = payload.snapshots[0].model_copy(deep=True)
        second.id = 'matching-B'
        second.label = 'Analysis B — matching reported output'
        payload.snapshots[1] = second
    else:
        payload.title = 'Teaching example: insufficient reference evidence'
        for snapshot in payload.snapshots:
            snapshot.variant.reference_context = None
    return payload


@app.post("/api/investigations", response_model=InvestigationResult)
def create_investigation(payload: InvestigationInput):
    validate_input_size(payload)
    try:
        validate_linked_checks(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = compare(payload)
    save(database(), result)
    return result


@app.get("/api/investigations")
def investigations(q: str = Query(default="", max_length=200), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0, le=MAX_SQLITE_INTEGER)):
    return list_items(database(), q, limit, offset)


@app.get('/api/investigations/page')
def investigation_page(q: str = Query(default='', max_length=200), limit: int = Query(default=100, ge=1, le=500),
                       before: int | None = Query(default=None, ge=1, le=9223372036854775807),
                       ceiling: int | None = Query(default=None, ge=0, le=9223372036854775807)):
    return list_investigation_page(database(), q, limit, before, ceiling)


@app.get("/api/investigations/{id_}", response_model=InvestigationResult)
def investigation(id_: str):
    result = load(database(), id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return result


@app.post("/api/investigations/{id_}/allele-check")
def check_investigation_alleles(id_: str, payload: ReferenceCheckRequest):
    result = load(database(), id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if payload.mode == "cache_only":
        check = latest_allele_check(database(), id_)
        if check is None:
            raise HTTPException(status_code=404, detail="No reference-backed allele check is saved for this investigation")
        try:
            validate_saved_allele_check(result, check)
        except (ReferenceCheckError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return check
    try:
        check = fetch_allele_check(result)
    except (ReferenceCheckError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_allele_check(database(), check)
    return check


@app.delete("/api/investigations/{id_}")
def remove_investigation(id_: str):
    try:
        removed = delete_investigation(database(), id_)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"deleted": id_}


@app.get("/api/investigations/{id_}/bundle")
def investigation_bundle(id_: str):
    result = load(database(), id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        return create_bundle(database(), result)
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
    save_bundle_records(database(), result, source, check, snpeff, allele_check)
    return {"imported": result.id}


@app.get("/api/investigations/{id_}/report.md", response_class=PlainTextResponse)
def report(id_: str):
    result = load(database(), id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    annotation = load_snpeff_check(database(), result.input.annotation_check.id) if result.input.annotation_check else None
    source_ids = {s.provenance.configuration.get("source_record_id") for s in result.input.snapshots} - {None}
    sources = [source for source_id in source_ids if (source := load_source_record(database(), source_id)) is not None]
    return markdown_report(result, latest_allele_check(database(),result.id), annotation, sources)


@app.post("/api/investigations/{id_}/regression-cases", response_model=RegressionCase)
def create_regression_case(id_: str, payload: CreateRegressionCase):
    source = load(database(), id_)
    if source is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    case = create_case(source, payload.name)
    save_case(database(), case)
    return case


@app.get("/api/regression-cases")
def regression_cases(source_investigation_id: str | None = Query(default=None, max_length=100),
                     limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0, le=MAX_SQLITE_INTEGER)):
    return list_cases(database(), source_investigation_id, limit, offset)


@app.get("/api/regression-cases/{id_}", response_model=RegressionCase)
def regression_case(id_: str):
    case = load_case(database(), id_)
    if case is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    return case


@app.post("/api/regression-cases/{id_}/runs", response_model=RegressionRun)
def run_regression_case(id_: str, payload: RegressionRunRequest):
    case = load_case(database(), id_)
    if case is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    if payload.candidate is not None:
        validate_input_size(payload.candidate)
    try:
        if payload.candidate is not None:
            validate_linked_checks(payload.candidate)
        run = run_case(case, payload.candidate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_run(database(), run)
    return run


@app.get("/api/regression-cases/{id_}/runs")
def regression_runs(id_: str, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0, le=MAX_SQLITE_INTEGER),
                    before: str | None = None):
    if load_case(database(), id_) is None:
        raise HTTPException(status_code=404, detail="Regression case not found")
    try:
        return list_runs(database(), id_, limit, offset, before)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/regression-runs/{id_}", response_model=RegressionRun)
def regression_run(id_: str):
    run = load_run(database(), id_)
    if run is None:
        raise HTTPException(status_code=404, detail="Regression run not found")
    return run


# The portable desktop build serves its compiled UI from the same loopback origin.
# Development keeps the existing Vite setup and API behavior.
if os.environ.get('GENOMEDEBUGGER_STATIC_DIR'):
    from fastapi.staticfiles import StaticFiles
    app.mount('/', StaticFiles(directory=os.environ['GENOMEDEBUGGER_STATIC_DIR'], html=True), name='desktop-ui')
