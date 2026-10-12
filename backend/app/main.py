import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from .engine import compare
from .models import InvestigationInput, InvestigationResult
from .report import markdown_report
from .storage import list_items, load, save

BASE = Path(__file__).resolve().parents[2]
DEMO = BASE / "fixtures" / "transcript-switch.json"
DB = Path(os.environ.get("GENOMEDEBUGGER_DB", str(BASE / "data" / "investigations.db")))
app = FastAPI(title="GenomeDebugger", version="0.1.0", description="Offline genomic discrepancy investigation")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware("http")
async def limit_input(request: Request, call_next):
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
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/demos/transcript-switch", response_model=InvestigationInput)
def demo():
    return InvestigationInput.model_validate_json(DEMO.read_text(encoding="utf-8"))


@app.post("/api/investigations", response_model=InvestigationResult)
def create_investigation(payload: InvestigationInput):
    result = compare(payload)
    save(DB, result)
    return result


@app.get("/api/investigations")
def investigations():
    return list_items(DB)


@app.get("/api/investigations/{id_}", response_model=InvestigationResult)
def investigation(id_: str):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return result


@app.get("/api/investigations/{id_}/report.md", response_class=PlainTextResponse)
def report(id_: str):
    result = load(DB, id_)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return markdown_report(result)
