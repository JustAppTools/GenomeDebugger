import sqlite3
from pathlib import Path
from .models import InvestigationResult
from .regression import RegressionCase, RegressionRun
from .ensembl import SourceQuery, SourceRecord


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, title TEXT NOT NULL, result_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS regression_cases (id TEXT PRIMARY KEY, name TEXT NOT NULL, source_investigation_id TEXT NOT NULL, case_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS regression_runs (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, run_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS source_records (id TEXT PRIMARY KEY, source TEXT NOT NULL, query_key TEXT NOT NULL, retrieved_at TEXT NOT NULL, record_json TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS source_records_lookup ON source_records(source, query_key, retrieved_at)")


def _query_key(query: SourceQuery) -> str:
    return query.model_dump_json()


def save_source_record(path: Path, record: SourceRecord):
    initialize(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT OR IGNORE INTO source_records VALUES (?, ?, ?, ?, ?)",
                   (record.id, "ensembl_vep", _query_key(record.query), record.retrieved_at, record.model_dump_json()))


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
        db.execute("INSERT OR REPLACE INTO investigations VALUES (?, ?, ?)", (result.id, result.input.title, result.model_dump_json()))


def load(path: Path, id_: str) -> InvestigationResult | None:
    initialize(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT result_json FROM investigations WHERE id = ?", (id_,)).fetchone()
    return InvestigationResult.model_validate_json(row[0]) if row else None


def list_items(path: Path) -> list[dict]:
    initialize(path)
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT id, title FROM investigations ORDER BY rowid DESC LIMIT 100").fetchall()
    return [{"id": row[0], "title": row[1]} for row in rows]


def save_case(path: Path, case: RegressionCase):
    initialize(path)
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
