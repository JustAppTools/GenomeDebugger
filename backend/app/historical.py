"""Preserve explicitly supplied historical VEP output and its declared provenance."""

from datetime import datetime, timezone
import hashlib
import json

from pydantic import Field

from .engine import digest
from .ensembl import SourceQuery, SourceRecord, parse_transcripts, snapshot_from_record
from .models import InvestigationInput, StrictModel
from .json_text import parse_json
from .admission import validate_required_text


class HistoricalImport(StrictModel):
    query: SourceQuery
    raw_json: str = Field(min_length=1,max_length=250_000)
    source_release: int = Field(ge=1, strict=True)
    tool_version: str = Field(min_length=1,max_length=100)
    generated_at: datetime
    assembly_accession: str = Field(pattern=r"^GC[AF]_\d+\.\d+$")
    source_uri: str = Field(min_length=1,max_length=2000)


class SourcePair(StrictModel):
    source_a: str
    source_b: str
    transcript_a: str
    transcript_b: str
    title: str = Field(default="Preserved source comparison",min_length=1,max_length=200)


def historical_id(query: SourceQuery, artifact: dict, assembly_accession: str) -> str:
    return digest({"origin":"historical_artifact","query":query.model_dump(),"artifact":artifact,
                   "assembly_accession":assembly_accession})[:20]


def import_historical(payload: HistoricalImport) -> SourceRecord:
    validate_required_text(payload)
    if payload.generated_at.tzinfo is None:
        raise ValueError("Historical generation time must include a timezone")
    if payload.generated_at > datetime.now(timezone.utc):
        raise ValueError("Historical generation time cannot be in the future")
    # Keep the original UTF-8 text (including an optional BOM) for hashing.
    body=parse_json(payload.raw_json.removeprefix('\ufeff'))
    if isinstance(body,list):
        if len(body)!=1:
            raise ValueError("Import one VEP variant record at a time")
        body=body[0]
    q=payload.query
    if (not isinstance(body,dict) or body.get("assembly_name")!="GRCh38" or
        any(type(body.get(key)) is not int for key in ('start', 'end')) or
        body.get("seq_region_name")!=q.chromosome or body.get("start")!=q.position or
        body.get("end")!=q.position or body.get("allele_string")!=f"{q.ref}/{q.alt}"):
        raise ValueError("Historical VEP artifact does not match the declared GRCh38 SNV query")
    parsed = parse_transcripts(body.get("transcript_consequences"))
    artifact={"text":payload.raw_json,"sha256":hashlib.sha256(payload.raw_json.encode()).hexdigest(),
              "tool_version":payload.tool_version,"source_release":payload.source_release,
              "generated_at":payload.generated_at.isoformat(),"source_uri":payload.source_uri}
    raw_hash=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return SourceRecord(id=historical_id(q,artifact,payload.assembly_accession),query=q,
        retrieved_at=datetime.now(timezone.utc).isoformat(),source_uri=payload.source_uri,
        sequence_uri="not retrieved; historical artifact reference is unverified",
        release_uri=payload.source_uri,assembly_uri=payload.source_uri,releases=[payload.source_release],
        assembly_name="GRCh38",assembly_accession=payload.assembly_accession,reference_base=q.ref,
        source_response_sha256=raw_hash,source_response=body,transcripts=parsed,
        origin="historical_artifact",artifact=artifact)


def comparison_pair(left: SourceRecord, right: SourceRecord, selection: SourcePair) -> InvestigationInput:
    return InvestigationInput(title=selection.title,synthetic=False,snapshots=[
        snapshot_from_record(left,selection.transcript_a,'a'),snapshot_from_record(right,selection.transcript_b,'b')])
