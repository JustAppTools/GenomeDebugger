"""Local database backup and integrity commands.

Run from backend: python -m app.manage backup --output PATH
"""

import argparse
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

from .storage import backup, initialize, validate_schema
from .workspace_lock import WorkspaceLock

DEFAULT_DB = Path(os.environ.get("GENOMEDEBUGGER_DB", str(Path(__file__).resolve().parents[2] / "data" / "investigations.db")))


def validate_restore(path: Path):
    """Validate one consistent staged copy, never the live destination."""
    from .models import InvestigationResult
    from .regression import RegressionCase, RegressionRun, validate_saved_run
    from .ensembl import SourceRecord
    from .ncbi import ReferenceCheck, ReferenceCheckError
    from .snpeff import SnpEffCheck
    from .allele_check import AlleleCheck
    from .workspace import LibraryLabel
    from .bundle import verify_bundle, _verify_source, _verify_reference, _verify_snpeff
    from .engine import digest
    from .allele_check import validate_saved_allele_check
    from .timestamps import timestamp_key
    from .storage import _query_key
    import json
    with closing(sqlite3.connect(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup failed SQLite integrity validation')
        validate_schema(db, db.execute('PRAGMA user_version').fetchone()[0])
    # Upgrade only the staged copy. Older valid backups can omit tables that
    # later releases added without changing the original scientific JSON.
    initialize(path)
    models = {'investigations': ('result_json', InvestigationResult),
              'regression_cases': ('case_json', RegressionCase), 'regression_runs': ('run_json', RegressionRun),
              'source_records': ('record_json', SourceRecord), 'reference_checks': ('check_json', ReferenceCheck),
              'snpeff_checks': ('check_json', SnpEffCheck), 'allele_checks': ('check_json', AlleleCheck)}
    with closing(sqlite3.connect(path)) as db:
        def get(table, id_):
            column, model = models[table]
            row = db.execute(f'SELECT {column} FROM {table} WHERE id=?', (id_,)).fetchone()
            if row is None:
                raise ValueError(f'Backup is missing a linked {table} record: {id_}')
            return model.model_validate_json(row[0])

        def validate_investigation(result, original=None):
            entries = {'investigation': original if original is not None else result.model_dump(mode='json')}
            ids = {s.provenance.configuration.get('source_record_id') for s in result.input.snapshots} - {None}
            if ids:
                entries['source_records'] = [get('source_records', id_).model_dump(mode='json') for id_ in sorted(ids)]
            for summary, table, key in ((result.input.reference_check, 'reference_checks', 'reference_check'),
                                        (result.input.annotation_check, 'snpeff_checks', 'snpeff_check')):
                if summary:
                    entries[key] = get(table, summary.id).model_dump(mode='json')
            # Keep the original result/version. create_bundle intentionally
            # replays with the current engine and would conceal corruption here.
            verify_bundle({'format':'GenomeDebugger bundle', 'version':2, 'engine_version':result.engine_version,
                           'entries':entries, 'sha256':{key:digest(value) for key,value in entries.items()}},
                          new_submission=False)

        for table, (column, model) in models.items():
            for id_, raw in db.execute(f'SELECT id,{column} FROM {table}'):
                try:
                    record = model.model_validate_json(raw)
                    if record.id != id_:
                        raise ValueError('Record identifier disagrees with its stored key')
                    if table == 'investigations' and db.execute('SELECT title FROM investigations WHERE id=?',(id_,)).fetchone()[0] != record.input.title:
                        raise ValueError('Investigation title disagrees with its stored input')
                    if table == 'investigations':
                        validate_investigation(record, json.loads(raw))
                    elif table == 'regression_cases':
                        name, parent_id = db.execute('SELECT name,source_investigation_id FROM regression_cases WHERE id=?',(id_,)).fetchone()
                        if name != record.name or parent_id != record.source_investigation.id or get('investigations', parent_id) != record.source_investigation:
                            raise ValueError('Backup baseline metadata or parent is inconsistent')
                        timestamp_key(record.created_at)
                    elif table == 'regression_runs':
                        case_id = db.execute('SELECT case_id FROM regression_runs WHERE id=?',(id_,)).fetchone()[0]
                        case = get('regression_cases', case_id)
                        if (case_id != record.case_id or record.baseline_input_sha256 != case.source_investigation.input_sha256
                                or record.candidate_input_sha256 != record.actual.input_sha256
                                or (record.mode == 'pinned' and record.actual.input != case.source_investigation.input)):
                            raise ValueError('Backup regression run has inconsistent ownership or inputs')
                        validate_investigation(record.actual, json.loads(raw)['actual'])
                        validate_saved_run(case, record)
                        timestamp_key(record.created_at)
                    elif table == 'source_records':
                        source, query, retrieved = db.execute('SELECT source,query_key,retrieved_at FROM source_records WHERE id=?',(id_,)).fetchone()
                        expected_source = 'ensembl_vep' if record.origin == 'current_api' else 'ensembl_vep_historical'
                        if (source,query,retrieved) != (expected_source,_query_key(record.query),record.retrieved_at):
                            raise ValueError('Backup source index disagrees with its record')
                        timestamp_key(record.retrieved_at)
                        _verify_source(record)
                    else:
                        parent_column = 'investigation_id' if table == 'allele_checks' else 'source_record_id'
                        parent_id, checked = db.execute(f'SELECT {parent_column},checked_at FROM {table} WHERE id=?',(id_,)).fetchone()
                        if parent_id != getattr(record,parent_column) or checked != record.checked_at:
                            raise ValueError('Backup check index disagrees with its record')
                        timestamp_key(record.checked_at)
                        if table == 'allele_checks':
                            validate_saved_allele_check(get('investigations',parent_id), record)
                        else:
                            source = get('source_records',parent_id)
                            if record.source_response_sha256 != source.source_response_sha256:
                                raise ValueError('Backup check disagrees with its source fingerprint')
                            (_verify_reference if table == 'reference_checks' else _verify_snpeff)(source, record)
                except (ValueError, TypeError, KeyError, IndexError, ReferenceCheckError) as exc:
                    raise ValueError(f'Backup contains an unreadable or inconsistent {table} record: {id_}') from exc
        for id_, name, notes, tags, favorite, archived in db.execute('SELECT investigation_id,display_name,notes,tags,favorite,archived FROM investigation_labels'):
            if favorite not in (0,1) or archived not in (0,1):
                raise ValueError('Backup contains invalid library flags')
            LibraryLabel(display_name=name, notes=notes, tags=json.loads(tags), favorite=bool(favorite), archived=bool(archived)).checked()
            if not db.execute('SELECT 1 FROM investigations WHERE id=?',(id_,)).fetchone():
                raise ValueError('Backup contains a label without its investigation')
        order_ids = {row[0] for row in db.execute('SELECT investigation_id FROM investigation_order')}
        if any(type(row[0]) is not int or row[0] < 1 for row in db.execute('SELECT sequence FROM investigation_order')):
            raise ValueError('Backup contains invalid investigation sequence numbers')
        investigation_ids = {row[0] for row in db.execute('SELECT id FROM investigations')}
        if order_ids != investigation_ids:
            raise ValueError('Backup has inconsistent investigation ordering metadata')


def restore_backup(source: Path, destination: Path):
    with WorkspaceLock(destination):
        return _restore_backup_locked(source, destination)


def _restore_backup_locked(source: Path, destination: Path):
    """Validate a closed backup, preserve the destination, then atomically replace it."""
    source, destination = source.resolve(), destination.resolve()
    if source == destination:
        raise ValueError('Backup source must differ from the destination database')
    if not source.is_file():
        raise ValueError('Backup source does not exist')
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(destination) + suffix).exists():
            raise ValueError('Database journal files are present. Stop the application and resolve its active database state before restoring.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    staging = destination.with_name(destination.name + '.restore-' + uuid.uuid4().hex)
    try:
        backup(source, staging)
        validate_restore(staging)
        if destination.exists():
            previous = destination.with_name(destination.stem + '-before-restore-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.db')
            backup(destination, previous)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return previous


def main():
    parser = argparse.ArgumentParser(description="Manage the local GenomeDebugger SQLite database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup", help="Create a consistent SQLite backup")
    create.add_argument("--output", type=Path, required=True)
    commands.add_parser("check", help="Run SQLite integrity check and report database size")
    restore = commands.add_parser('restore', help='Restore a validated backup while the application is stopped; preserve the existing database first')
    restore.add_argument('--from-backup', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'restore':
        try:
            previous = restore_backup(args.from_backup, args.db)
        except (OSError, sqlite3.Error, ValueError) as exc:
            parser.error(f'Restore failed: {exc}')
        print(f'Restored {args.db.resolve()}')
        if previous:
            print(f'Previous database preserved at {previous}')
        return
    if not args.db.is_file():
        parser.error(f"Source database does not exist: {args.db}; check --db")
    if args.command == "backup":
        source, destination = args.db.resolve(), args.output.resolve()
        if source == destination:
            parser.error("Backup destination must differ from the database")
        if destination.exists():
            parser.error("Backup destination already exists; choose a new filename")
        try:
            backup(source, destination)
        except (OSError, sqlite3.Error) as exc:
            parser.error(f"Backup failed: {exc}")
        print(f"Backup saved to {destination}")
    else:
        try:
            with closing(sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                status = '; '.join(row[0] for row in db.execute("PRAGMA integrity_check"))
                version = db.execute("PRAGMA user_version").fetchone()[0]
        except (OSError, sqlite3.Error) as exc:
            parser.error(f"Integrity check failed: {exc}")
        if status != 'ok':
            parser.error(f"Integrity check failed: {status}")
        print(f"Integrity: {status}; schema version: {version}; size: {args.db.stat().st_size} bytes")


if __name__ == "__main__":
    main()
