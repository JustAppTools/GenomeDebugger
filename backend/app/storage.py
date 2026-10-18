import sqlite3
import os
from contextlib import contextmanager
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


@contextmanager
def _connection(path: Path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def _guard_size(path: Path, incoming: str):
    try:
        limit_mb = int(os.environ.get("GENOMEDEBUGGER_MAX_DB_MB", "512"))
    except ValueError as exc:
        raise StorageLimitError("GENOMEDEBUGGER_MAX_DB_MB must be an integer") from exc
    if limit_mb < 10:
        raise StorageLimitError("GENOMEDEBUGGER_MAX_DB_MB must be at least 10")
    # SQLite reuses free pages after deletion; physical file size is not usage.
    used = 0
    if path.exists():
        with _connection(path) as db:
            pages = db.execute("PRAGMA page_count").fetchone()[0]
            free = db.execute("PRAGMA freelist_count").fetchone()[0]
            size = db.execute("PRAGMA page_size").fetchone()[0]
        used = (pages - free) * size
    if used + len(incoming.encode("utf-8")) > limit_mb * 1024 * 1024:
        raise StorageLimitError("Local database size limit reached; back up and manage saved records before adding more")


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(path) as db:
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


def _record_entry(record):
    payload = record.model_dump_json()
    if isinstance(record, InvestigationResult):
        return ("investigations", "result_json", record,
                (record.id, record.input.title, payload, datetime.now(timezone.utc).isoformat()))
    if isinstance(record, SourceRecord):
        source_kind = "ensembl_vep" if record.origin == "current_api" else "ensembl_vep_historical"
        return ("source_records", "record_json", record,
                (record.id, source_kind, _query_key(record.query), record.retrieved_at, payload))
    if isinstance(record, ReferenceCheck):
        return ("reference_checks", "check_json", record, (record.id, record.source_record_id, record.checked_at, payload))
    if isinstance(record, SnpEffCheck):
        return ("snpeff_checks", "check_json", record, (record.id, record.source_record_id, record.checked_at, payload))
    if isinstance(record, AlleleCheck):
        return ("allele_checks", "check_json", record, (record.id, record.investigation_id, record.checked_at, payload))
    raise TypeError("Unsupported immutable record")


def _same_record(existing, incoming):
    # Historical artifact identity covers original bytes and declared metadata;
    # re-importing those bytes can have a different local retrieval timestamp.
    if isinstance(incoming, SourceRecord) and incoming.origin == "historical_artifact":
        return existing.model_dump(exclude={"retrieved_at"}) == incoming.model_dump(exclude={"retrieved_at"})
    return existing == incoming


def _insert_entry(db, table, values):
    columns = "id, title, result_json, created_at" if table == "investigations" else None
    target = f"{table} ({columns})" if columns else table
    db.execute(f"INSERT INTO {target} VALUES ({', '.join('?' for _ in values)})", values)


def _save_records(path: Path, records):
    initialize(path)
    with _connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        pending = []
        for record in records:
            table, column, model, values = _record_entry(record)
            row = db.execute(f"SELECT {column} FROM {table} WHERE id = ?", (model.id,)).fetchone()
            if row:
                existing = type(model).model_validate_json(row[0])
                if not _same_record(existing, model):
                    raise RecordConflictError(f"Conflicting immutable {table} record: {model.id}")
            else:
                pending.append((table, model, values))
        if pending:
            _guard_size(path, "".join(model.model_dump_json() for _, model, _ in pending))
            for table, _, values in pending:
                _insert_entry(db, table, values)


def save_bundle_records(path: Path, result, sources, reference=None, snpeff=None, allele=None):
    records = [*sources, *([reference] if reference else []), *([snpeff] if snpeff else []),
               result, *([allele] if allele else [])]
    _save_records(path, records)


def save_snpeff_check(path: Path, check: SnpEffCheck):
    _save_records(path, [check])


def latest_snpeff_check(path: Path, source_record_id: str) -> SnpEffCheck | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT check_json FROM snpeff_checks WHERE source_record_id = ? ORDER BY checked_at DESC LIMIT 1",
                         (source_record_id,)).fetchone()
    return SnpEffCheck.model_validate_json(row[0]) if row else None


def load_snpeff_check(path: Path, id_: str) -> SnpEffCheck | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT check_json FROM snpeff_checks WHERE id = ?", (id_,)).fetchone()
    return SnpEffCheck.model_validate_json(row[0]) if row else None


def save_allele_check(path: Path, check: AlleleCheck):
    _save_records(path, [check])


def latest_allele_check(path: Path, investigation_id: str) -> AlleleCheck | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT check_json FROM allele_checks WHERE investigation_id = ? ORDER BY checked_at DESC LIMIT 1", (investigation_id,)).fetchone()
    return AlleleCheck.model_validate_json(row[0]) if row else None


def save_reference_check(path: Path, check: ReferenceCheck):
    _save_records(path, [check])


def latest_reference_check(path: Path, source_record_id: str) -> ReferenceCheck | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT check_json FROM reference_checks WHERE source_record_id = ? ORDER BY checked_at DESC LIMIT 1",
                         (source_record_id,)).fetchone()
    return ReferenceCheck.model_validate_json(row[0]) if row else None


def load_reference_check(path: Path, id_: str) -> ReferenceCheck | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT check_json FROM reference_checks WHERE id = ?", (id_,)).fetchone()
    return ReferenceCheck.model_validate_json(row[0]) if row else None


def _query_key(query: SourceQuery) -> str:
    return query.model_dump_json()


def save_source_record(path: Path, record: SourceRecord):
    _save_records(path, [record])


def list_source_records(path: Path, limit: int = 200, offset: int = 0) -> list[SourceRecord]:
    initialize(path)
    with _connection(path) as db:
        rows=db.execute("SELECT record_json FROM source_records ORDER BY retrieved_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [SourceRecord.model_validate_json(row[0]) for row in rows]


def load_source_record(path: Path, id_: str) -> SourceRecord | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT record_json FROM source_records WHERE id = ?", (id_,)).fetchone()
    return SourceRecord.model_validate_json(row[0]) if row else None


def latest_source_record(path: Path, query: SourceQuery) -> SourceRecord | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT record_json FROM source_records WHERE source = ? AND query_key = ? ORDER BY retrieved_at DESC LIMIT 1",
                         ("ensembl_vep", _query_key(query))).fetchone()
    return SourceRecord.model_validate_json(row[0]) if row else None


def save(path: Path, result: InvestigationResult):
    _save_records(path, [result])


def load(path: Path, id_: str) -> InvestigationResult | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT result_json FROM investigations WHERE id = ?", (id_,)).fetchone()
    return InvestigationResult.model_validate_json(row[0]) if row else None


def list_items(path: Path, query: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    initialize(path)
    with _connection(path) as db:
        rows = db.execute("SELECT id, title, created_at FROM investigations WHERE title LIKE ? OR id LIKE ? "
                          "ORDER BY rowid DESC LIMIT ? OFFSET ?", (f"%{query}%", f"%{query}%", limit, offset)).fetchall()
    return [{"id": row[0], "title": row[1], "created_at": row[2]} for row in rows]


def delete_investigation(path: Path, id_: str) -> bool:
    initialize(path)
    with _connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM regression_cases WHERE source_investigation_id = ?", (id_,)).fetchone():
            raise ValueError("This investigation has a pinned regression case and cannot be deleted")
        if not db.execute("SELECT 1 FROM investigations WHERE id = ?", (id_,)).fetchone():
            return False
        db.execute("DELETE FROM allele_checks WHERE investigation_id = ?", (id_,))
        db.execute("DELETE FROM investigations WHERE id = ?", (id_,))
        return True


def backup(path: Path, destination: Path):
    initialize(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _connection(path) as source, _connection(destination) as target:
        source.backup(target)


def save_case(path: Path, case: RegressionCase):
    initialize(path)
    _guard_size(path, case.model_dump_json())
    with _connection(path) as db:
        db.execute("INSERT INTO regression_cases VALUES (?, ?, ?, ?)", (case.id, case.name, case.source_investigation.id, case.model_dump_json()))


def load_case(path: Path, id_: str) -> RegressionCase | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT case_json FROM regression_cases WHERE id = ?", (id_,)).fetchone()
    return RegressionCase.model_validate_json(row[0]) if row else None


def list_cases(path: Path, source_investigation_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    initialize(path)
    with _connection(path) as db:
        rows = db.execute("SELECT id, name, source_investigation_id FROM regression_cases "
                          "WHERE (? IS NULL OR source_investigation_id = ?) ORDER BY rowid DESC LIMIT ? OFFSET ?",
                          (source_investigation_id, source_investigation_id, limit, offset)).fetchall()
    return [{"id": row[0], "name": row[1], "source_investigation_id": row[2]} for row in rows]


def save_run(path: Path, run: RegressionRun):
    initialize(path)
    _guard_size(path, run.model_dump_json())
    with _connection(path) as db:
        db.execute("INSERT INTO regression_runs VALUES (?, ?, ?)", (run.id, run.case_id, run.model_dump_json()))


def load_run(path: Path, id_: str) -> RegressionRun | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT run_json FROM regression_runs WHERE id = ?", (id_,)).fetchone()
    return RegressionRun.model_validate_json(row[0]) if row else None


def list_runs(path: Path, case_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    initialize(path)
    with _connection(path) as db:
        rows = db.execute("SELECT run_json FROM regression_runs WHERE case_id = ? ORDER BY rowid DESC LIMIT ? OFFSET ?", (case_id, limit, offset)).fetchall()
    return [{"id": run.id, "created_at": run.created_at, "mode": run.mode, "status": run.status} for row in rows if (run := RegressionRun.model_validate_json(row[0]))]
