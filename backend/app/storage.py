import json
import sqlite3
from pathlib import Path
from .models import InvestigationResult


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, title TEXT NOT NULL, result_json TEXT NOT NULL)")


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
