"""Local database backup and integrity commands.

Run from backend: python -m app.manage backup --output PATH
"""

import argparse
import os
import sqlite3
from pathlib import Path

from .storage import backup, initialize

DEFAULT_DB = Path(os.environ.get("GENOMEDEBUGGER_DB", str(Path(__file__).resolve().parents[2] / "data" / "investigations.db")))


def main():
    parser = argparse.ArgumentParser(description="Manage the local GenomeDebugger SQLite database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup", help="Create a consistent SQLite backup")
    create.add_argument("--output", type=Path, required=True)
    commands.add_parser("check", help="Run SQLite integrity check and report database size")
    args = parser.parse_args()
    if args.command == "backup":
        source, destination = args.db.resolve(), args.output.resolve()
        if source == destination:
            parser.error("Backup destination must differ from the database")
        if destination.exists():
            parser.error("Backup destination already exists; choose a new filename")
        backup(source, destination)
        print(f"Backup saved to {destination}")
    else:
        initialize(args.db)
        with sqlite3.connect(args.db) as db:
            status = db.execute("PRAGMA integrity_check").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
        print(f"Integrity: {status}; schema version: {version}; size: {args.db.stat().st_size} bytes")


if __name__ == "__main__":
    main()
