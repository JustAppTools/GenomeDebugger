import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path
from .models import InvestigationResult
from .regression import RegressionCase, RegressionRun
from .ensembl import SourceQuery, SourceRecord
from .ncbi import ReferenceCheck
from .snpeff import SnpEffCheck
from .allele_check import AlleleCheck


class StorageLimitError(Exception):
    pass


class RecordConflictError(Exception):
    pass


def _guard_size(path: Path, incoming: str):
    try:
        limit_mb = int(os.environ.get("GENOMEDEBUGGER_MAX_DB_MB", "512"))
    except ValueError as exc:
        raise StorageLimitError("GENOMEDEBUGGER_MAX_DB_MB must be an integer") from exc
    if limit_mb < 10:
        raise StorageLimitError("GENOMEDEBUGGER_MAX_DB_MB must be at least 10")
    wal = path.with_name(path.name + "-wal")
    used = (path.stat().st_size if path.exists() else 0) + (wal.stat().st_size if wal.exists() else 0)
    if used + len(incoming.encode("utf-8")) > limit_mb * 1024 * 1024:
        raise StorageLimitError("Local database size limit reached; back up and manage saved records before adding more")


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, title TEXT NOT NULL, result_json TEXT NOT NULL)")
        if db.execute("PRAGMA user_version").fetchone()[0] < 1:
            columns = {row[1] for row in db.execute("PRAGMA table_info(investigations)")}
            if "created_at" not in columns:
                db.execute("ALTER TABLE investigations ADD COLUMN created_at TEXT")
            db.execute("PRAGMA user_version = 1")
        db.execute("CREATE INDEX IF NOT EXISTS investigations_created ON investigations(created_at)")
        db.execute("CREATE TABLE IF NOT EXISTS regression_cases (id TEXT PRIMARY KEY, name TEXT NOT NULL, source_investigation_id TEXT NOT NULL, case_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS regression_runs (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, run_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS source_records (id TEXT PRIMARY KEY, source TEXT NOT NULL, query_key TEXT NOT NULL, retrieved_at TEXT NOT NULL, record_json TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS source_records_lookup ON source_records(source, query_key, retrieved_at)")
        db.execute("CREATE TABLE IF NOT EXISTS reference_checks (id TEXT PRIMARY KEY, source_record_id TEXT NOT NULL, checked_at TEXT NOT NULL, check_json TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS reference_checks_lookup ON reference_checks(source_record_id, checked_at)")
        db.execute("CREATE TABLE IF NOT EXISTS snpeff_checks (id TEXT PRIMARY KEY, source_record_id TEXT NOT NULL, checked_at TEXT NOT NULL, check_json TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS snpeff_checks_lookup ON snpeff_checks(source_record_id, checked_at)")
        db.execute("CREATE TABLE IF NOT EXISTS allele_checks (id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL, checked_at TEXT NOT NULL, check_json TEXT NOT NULL)")


def save_snpeff_check(path: Path, check: SnpEffCheck):
    initialize(path)
    _guard_size(path, check.model_dump_json())
    with sqlite3.connect(path) as db:
        db.execute("INSERT OR IGNORE INTO snpeff_checks VALUES (?, ?, ?, ?)",
                   (check.id, check.source_record_id, check.checked_at, check.model_dump_json()))


def latest_snpeff_check(path: Path, source_record_id: str) -> SnpEffCheck | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT check_json FROM snpeff_checks WHERE source_record_id = ? ORDER BY checked_at DESC LIMIT 1",
                         (source_record_id,)).fetchone()
    return SnpEffCheck.model_validate_json(row[0]) if row else None


def load_snpeff_check(path: Path, id_: str) -> SnpEffCheck | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT check_json FROM snpeff_checks WHERE id = ?", (id_,)).fetchone()
    return SnpEffCheck.model_validate_json(row[0]) if row else None


def save_allele_check(path: Path, check: AlleleCheck):
    initialize(path)
    _guard_size(path, check.model_dump_json())
    with sqlite3.connect(path) as db:
        db.execute("INSERT OR IGNORE INTO allele_checks VALUES (?, ?, ?, ?)",
                   (check.id, check.investigation_id, check.checked_at, check.model_dump_json()))


def latest_allele_check(path: Path, investigation_id: str) -> AlleleCheck | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT check_json FROM allele_checks WHERE investigation_id = ? ORDER BY checked_at DESC LIMIT 1", (investigation_id,)).fetchone()
    return AlleleCheck.model_validate_json(row[0]) if row else None


def save_reference_check(path: Path, check: ReferenceCheck):
    initialize(path)
    _guard_size(path, check.model_dump_json())
    with sqlite3.connect(path) as db:
        db.execute("INSERT OR IGNORE INTO reference_checks VALUES (?, ?, ?, ?)",
                   (check.id, check.source_record_id, check.checked_at, check.model_dump_json()))


def latest_reference_check(path: Path, source_record_id: str) -> ReferenceCheck | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT check_json FROM reference_checks WHERE source_record_id = ? ORDER BY checked_at DESC LIMIT 1",
                         (source_record_id,)).fetchone()
    return ReferenceCheck.model_validate_json(row[0]) if row else None


def load_reference_check(path: Path, id_: str) -> ReferenceCheck | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT check_json FROM reference_checks WHERE id = ?", (id_,)).fetchone()
    return ReferenceCheck.model_validate_json(row[0]) if row else None


def _query_key(query: SourceQuery) -> str:
    return query.model_dump_json()


def save_source_record(path: Path, record: SourceRecord):
    initialize(path)
    _guard_size(path, record.model_dump_json())
    with sqlite3.connect(path) as db:
        db.execute("INSERT OR IGNORE INTO source_records VALUES (?, ?, ?, ?, ?)",
                   (record.id, "ensembl_vep" if record.origin == "current_api" else "ensembl_vep_historical",
                    _query_key(record.query), record.retrieved_at, record.model_dump_json()))


def list_source_records(path: Path) -> list[SourceRecord]:
    initialize(path)
    with sqlite3.connect(path) as db:
        rows=db.execute("SELECT record_json FROM source_records ORDER BY retrieved_at DESC LIMIT 200").fetchall()
    return [SourceRecord.model_validate_json(row[0]) for row in rows]


def load_source_record(path: Path, id_: str) -> SourceRecord | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT record_json FROM source_records WHERE id = ?", (id_,)).fetchone()
    return SourceRecord.model_validate_json(row[0]) if row else None


def latest_source_record(path: Path, query: SourceQuery) -> SourceRecord | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT record_json FROM source_records WHERE source = ? AND query_key = ? ORDER BY retrieved_at DESC LIMIT 1",
                         ("ensembl_vep", _query_key(query))).fetchone()
    return SourceRecord.model_validate_json(row[0]) if row else None


def save(path: Path, result: InvestigationResult):
    initialize(path)
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT result_json FROM investigations WHERE id = ?", (result.id,)).fetchone()
        if existing:
            if InvestigationResult.model_validate_json(existing[0]) != result:
                raise RecordConflictError("An investigation with this input ID already has a different saved result")
            return
        _guard_size(path, result.model_dump_json())
        db.execute("INSERT INTO investigations (id, title, result_json, created_at) VALUES (?, ?, ?, ?)",
                   (result.id, result.input.title, result.model_dump_json(), datetime.now(timezone.utc).isoformat()))


def load(path: Path, id_: str) -> InvestigationResult | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT result_json FROM investigations WHERE id = ?", (id_,)).fetchone()
    return InvestigationResult.model_validate_json(row[0]) if row else None


def list_items(path: Path, query: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    initialize(path)
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT id, title, created_at FROM investigations WHERE title LIKE ? OR id LIKE ? "
                          "ORDER BY rowid DESC LIMIT ? OFFSET ?", (f"%{query}%", f"%{query}%", limit, offset)).fetchall()
    return [{"id": row[0], "title": row[1], "created_at": row[2]} for row in rows]


def delete_investigation(path: Path, id_: str) -> bool:
    initialize(path)
    with sqlite3.connect(path) as db:
        if db.execute("SELECT 1 FROM regression_cases WHERE source_investigation_id = ?", (id_,)).fetchone():
            raise ValueError("This investigation has a pinned regression case and cannot be deleted")
        return db.execute("DELETE FROM investigations WHERE id = ?", (id_,)).rowcount > 0


def backup(path: Path, destination: Path):
    initialize(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as source, sqlite3.connect(destination) as target:
        source.backup(target)


def save_case(path: Path, case: RegressionCase):
    initialize(path)
    _guard_size(path, case.model_dump_json())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO regression_cases VALUES (?, ?, ?, ?)", (case.id, case.name, case.source_investigation.id, case.model_dump_json()))


def load_case(path: Path, id_: str) -> RegressionCase | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT case_json FROM regression_cases WHERE id = ?", (id_,)).fetchone()
    return RegressionCase.model_validate_json(row[0]) if row else None


def list_cases(path: Path) -> list[dict]:
    initialize(path)
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT id, name, source_investigation_id FROM regression_cases ORDER BY rowid DESC LIMIT 100").fetchall()
    return [{"id": row[0], "name": row[1], "source_investigation_id": row[2]} for row in rows]


def save_run(path: Path, run: RegressionRun):
    initialize(path)
    _guard_size(path, run.model_dump_json())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO regression_runs VALUES (?, ?, ?)", (run.id, run.case_id, run.model_dump_json()))


def load_run(path: Path, id_: str) -> RegressionRun | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT run_json FROM regression_runs WHERE id = ?", (id_,)).fetchone()
    return RegressionRun.model_validate_json(row[0]) if row else None


def list_runs(path: Path, case_id: str) -> list[dict]:
    initialize(path)
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT run_json FROM regression_runs WHERE case_id = ? ORDER BY rowid DESC LIMIT 100", (case_id,)).fetchall()
    return [{"id": run.id, "created_at": run.created_at, "mode": run.mode, "status": run.status} for row in rows if (run := RegressionRun.model_validate_json(row[0]))]
