"""Execute the locally pinned SnpEff installation without a shell or downloads."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

from .engine import digest
from .ensembl import SourceRecord
from .snpeff import SnpEffCheck, SnpEffCheckRequest, SnpEffExecution, compare_snpeff
from .snpeff_databases import validate_database

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2]/"tools/snpeff/runtime.json"
_run_lock = threading.Lock()


def file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def _manifest() -> dict:
    path=Path(os.environ.get("GENOMEDEBUGGER_SNPEFF_MANIFEST",str(DEFAULT_MANIFEST)))
    if not path.is_file():
        raise ValueError("No pinned SnpEff runtime is installed. Run scripts/setup_snpeff.py first.")
    manifest=json.loads(path.read_text())
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}",manifest.get("genome","")):
        raise ValueError("Pinned SnpEff database name is invalid")
    validate_database(manifest)
    return manifest


def runtime_status() -> dict:
    try:
        manifest=_manifest()
        return {"configured":True,"genome":manifest["genome"],"software_version":manifest["snpeff_version"],
                "jar_sha256":manifest["jar_sha256"],"database_sha256":digest(manifest["database_files"]),
                "detail":"Artifacts will be rehashed and verified before and after each local run."}
    except (OSError,ValueError,KeyError) as exc:
        return {"configured":False,"detail":str(exc)}


def _verify_artifacts(manifest: dict) -> dict[str,str]:
    for key in ("java","jar","config"):
        path=Path(manifest[key])
        if not path.is_file() or file_sha(path)!=manifest[f"{key}_sha256"]:
            raise ValueError(f"Pinned SnpEff {key} artifact changed or is missing")
    base=(Path(manifest["data_dir"])/manifest["genome"]).resolve()
    files={}
    for path in sorted(base.rglob('*')):
        if path.is_file():
            if not path.resolve().is_relative_to(base):
                raise ValueError("SnpEff database contains a file outside its pinned directory")
            files[path.relative_to(base).as_posix()]=file_sha(path)
    if not files or files!=manifest["database_files"]:
        raise ValueError("Pinned SnpEff database files changed or are missing")
    return files


def run_snpeff(record: SourceRecord) -> SnpEffCheck:
    if not _run_lock.acquire(blocking=False):
        raise ValueError("Another SnpEff run is active; wait for it to finish")
    try:
        manifest=_manifest()
        expected = validate_database(manifest)
        if (record.assembly_accession != expected["assembly_accession"] or
                record.assembly_name not in {expected["assembly_name"], "GRCh38.p14"}):
            raise ValueError("Source assembly does not match the pinned SnpEff database assembly")
        files=_verify_artifacts(manifest)
        q=record.query
        vcf=("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
             f"{q.chromosome}\t{q.position}\t.\t{q.ref}\t{q.alt}\t.\tPASS\t.\n")
        started_at=datetime.now(timezone.utc).isoformat()
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix="genomedebugger-snpeff-") as directory:
            input_file=Path(directory)/"input.vcf"
            input_bytes = vcf.encode('utf-8')
            input_file.write_bytes(input_bytes)
            input_sha256 = file_sha(input_file)
            command=[manifest["java"],"-Xmx4g","-jar",Path(manifest["jar"]).as_posix(),"ann","-c",Path(manifest["config"]).as_posix(),
                     "-dataDir",Path(os.path.relpath(manifest["data_dir"],Path(manifest["config"]).parent)).as_posix(),
                     "-noLog","-nodownload","-noStats",manifest["genome"],input_file.as_posix()]
            try:
                completed=subprocess.run(command,cwd=directory,capture_output=True,text=True,encoding='utf-8',
                                         errors='replace',timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except subprocess.TimeoutExpired as exc:
                raise ValueError("SnpEff exceeded the two minute local run limit") from exc
        if completed.returncode:
            raise ValueError(f"SnpEff failed ({completed.returncode}): {completed.stderr[-2000:]}")
        if len(completed.stdout.encode())>500_000 or len(completed.stderr.encode())>1_000_000:
            raise ValueError("SnpEff output exceeded the single-variant output limit")
        _verify_artifacts(manifest)
        database_hash=digest(files)
        check=compare_snpeff(record,SnpEffCheckRequest(vcf_text=completed.stdout,
            snpeff_version=manifest["snpeff_version"][:100],genome_database=manifest["genome"],database_sha256=database_hash))
        check.execution=SnpEffExecution(started_at=started_at,elapsed_seconds=round(time.monotonic()-started,3),
            command=command,java_sha256=manifest["java_sha256"],jar_sha256=manifest["jar_sha256"],
            config_sha256=manifest["config_sha256"],database_files=files,database_sha256=database_hash,
            input_vcf=vcf,input_vcf_sha256=input_sha256,
            output_vcf_sha256=check.vcf_sha256,stderr=completed.stderr,software_version=manifest["snpeff_version"])
        check.execution.artifact_sources=manifest.get("sources",{})
        check.execution.assembly_name=expected["assembly_name"]
        check.execution.assembly_accession=expected["assembly_accession"]
        return check
    finally:
        _run_lock.release()
