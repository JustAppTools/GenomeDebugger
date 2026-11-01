import sqlite3
import os
from contextlib import contextmanager, closing, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from .models import InvestigationResult
from .regression import RegressionCase, RegressionRun
from .ensembl import SourceQuery, SourceRecord
from .ncbi import ReferenceCheck, ReferenceCheckError
from .snpeff import SnpEffCheck
from .allele_check import AlleleCheck
from .timestamps import timestamp_key, legacy_timestamp_key
from .hosting import REQUEST_HOSTING


class StorageLimitError(Exception):
    pass


class RecordConflictError(Exception):
    pass


class RecordMissingError(Exception):
    pass


@contextmanager
def _connection(path: Path):
    settings = REQUEST_HOSTING.get()
    with settings.quota_lock if settings else nullcontext():
        if settings and settings.admit(path.parent.name) != path:
            raise ValueError('Invalid request database')
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        db.create_function("timestamp_key", 1, legacy_timestamp_key, deterministic=True)
        db.create_function('unicode_casefold', 1, lambda value: value.casefold(), deterministic=True)
        try:
            before = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0] if settings else 0
            with db:
                yield db
                if settings:
                    settings.guard_allocation(path, db, before)
        finally:
            db.close()


def max_database_bytes():
    try:
        limit_mb = int(os.environ.get("GENOMEDEBUGGER_MAX_DB_MB", "512"))
    except ValueError as exc:
        raise StorageLimitError("GENOMEDEBUGGER_MAX_DB_MB must be an integer") from exc
    if limit_mb < 10:
        raise StorageLimitError("GENOMEDEBUGGER_MAX_DB_MB must be at least 10")
    return limit_mb * 1024 * 1024


DATABASE_COLUMNS = {
    'investigations': {'id','title','result_json','created_at'},
    'regression_cases': {'id','name','source_investigation_id','case_json'},
    'regression_runs': {'id','case_id','run_json'},
    'source_records': {'id','source','query_key','retrieved_at','record_json'},
    'reference_checks': {'id','source_record_id','checked_at','check_json'},
    'snpeff_checks': {'id','source_record_id','checked_at','check_json'},
    'allele_checks': {'id','investigation_id','checked_at','check_json'},
    'investigation_order': {'sequence','investigation_id'},
    'investigation_labels': {'investigation_id','display_name','notes','tags','favorite','archived'},
}


def validate_schema(db, version):
    if version not in (0, 1, 2, 3):
        raise sqlite3.DatabaseError('Unsupported GenomeDebugger database schema')
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = set(DATABASE_COLUMNS) if version == 3 else {'investigations'}
    if version == 2:
        required.add('investigation_order')
    if not required <= tables:
        raise sqlite3.DatabaseError('GenomeDebugger database is missing required tables')
    for table in tables & DATABASE_COLUMNS.keys():
        fields = DATABASE_COLUMNS[table] - ({'created_at'} if table == 'investigations' and version == 0 else set())
        info = list(db.execute(f'PRAGMA table_info({table})'))
        columns = {row[1] for row in info}
        if not fields <= columns:
            raise sqlite3.DatabaseError(f'GenomeDebugger table {table} has an incompatible schema')
        primary = tuple(row[1] for row in sorted(info, key=lambda row: row[5]) if row[5])
        expected = ('sequence',) if table == 'investigation_order' else ('investigation_id',) if table == 'investigation_labels' else ('id',)
        if primary != expected:
            raise sqlite3.DatabaseError(f'GenomeDebugger table {table} is missing its required primary key')
        for row in info:
            if row[1] not in fields:
                continue
            expected_type = 'INTEGER' if row[1] in ('sequence', 'favorite', 'archived') else 'TEXT'
            if row[2].upper() != expected_type or (row[1] not in (*expected, 'created_at') and not row[3]):
                raise sqlite3.DatabaseError(f'GenomeDebugger table {table} has incompatible column constraints')
        if table == 'investigation_order':
            unique = [tuple(r[2] for r in db.execute('SELECT * FROM pragma_index_info(?)', (index[1],)))
                      for index in db.execute(f'PRAGMA index_list({table})') if index[2] and not index[4]]
            sql = db.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?', (table,)).fetchone()[0]
            if ('investigation_id',) not in unique or 'AUTOINCREMENT' not in sql.upper():
                raise sqlite3.DatabaseError('GenomeDebugger ordering table is missing its sequence or uniqueness constraints')


def _guard_size(path: Path, incoming: str, connection=None):
    limit_bytes = max_database_bytes()
    # SQLite reuses free pages after deletion; physical file size is not usage.
    used = 0
    def used_bytes(db):
        pages = db.execute("PRAGMA page_count").fetchone()[0]
        free = db.execute("PRAGMA freelist_count").fetchone()[0]
        size = db.execute("PRAGMA page_size").fetchone()[0]
        return (pages - free) * size
    if connection is not None:
        used = used_bytes(connection)
    elif path.exists():
        with _connection(path) as db:
            used = used_bytes(db)
    if used + len(incoming.encode("utf-8")) > limit_bytes:
        raise StorageLimitError("Local database size limit reached; back up and manage saved records before adding more")


def initialize(path: Path):
    with _connection(path) as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version >= 3:
            validate_schema(db, version)
            return
        db.execute('BEGIN IMMEDIATE')
        # Another initializer may have finished while this connection waited.
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version >= 3:
            validate_schema(db, version)
            return
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
        if db.execute('PRAGMA user_version').fetchone()[0] < 2:
            db.execute('CREATE TABLE investigation_order (sequence INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id TEXT NOT NULL UNIQUE)')
            db.execute('INSERT INTO investigation_order (sequence, investigation_id) SELECT rowid, id FROM investigations ORDER BY rowid')
            db.execute('PRAGMA user_version = 2')
        db.execute('CREATE TABLE IF NOT EXISTS investigation_labels (investigation_id TEXT PRIMARY KEY, display_name TEXT NOT NULL DEFAULT \'\', notes TEXT NOT NULL DEFAULT \'\', tags TEXT NOT NULL DEFAULT \'[]\', favorite INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0)')
        db.execute('PRAGMA user_version = 3')
        validate_schema(db, 3)


def _record_entry(record):
    if isinstance(record, SourceRecord):
        timestamp_key(record.retrieved_at)
    elif isinstance(record, (ReferenceCheck, SnpEffCheck, AlleleCheck)):
        timestamp_key(record.checked_at)
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
    if isinstance(record, RegressionCase):
        return ("regression_cases", "case_json", record,
                (record.id, record.name, record.source_investigation.id, payload))
    if isinstance(record, RegressionRun):
        return ("regression_runs", "run_json", record, (record.id, record.case_id, payload))
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
    if table == 'investigations':
        db.execute('INSERT INTO investigation_order (investigation_id) VALUES (?)', (values[0],))


def _save_records(path: Path, records):
    initialize(path)
    with _connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        parents = {record.id: record for record in records if isinstance(record, InvestigationResult)}
        cases = {record.id: record for record in records if isinstance(record, RegressionCase)}
        for record in records:
            if isinstance(record, RegressionCase):
                parent = parents.get(record.source_investigation.id)
                if parent is None:
                    row = db.execute("SELECT result_json FROM investigations WHERE id = ?",
                                     (record.source_investigation.id,)).fetchone()
                    if row is None:
                        raise RecordMissingError("Investigation no longer exists; regression case was not saved")
                    parent = InvestigationResult.model_validate_json(row[0])
                if parent != record.source_investigation:
                    raise RecordConflictError("Regression baseline does not match its saved investigation")
            if isinstance(record, RegressionRun):
                case = cases.get(record.case_id)
                if case is None:
                    row = db.execute("SELECT case_json FROM regression_cases WHERE id = ?", (record.case_id,)).fetchone()
                    if row is None:
                        raise RecordMissingError("Regression case no longer exists; run was not saved")
                    case = RegressionCase.model_validate_json(row[0])
                if case.source_investigation.input_sha256 != record.baseline_input_sha256:
                    raise RecordConflictError("Regression run baseline hash does not match its saved case")
            if isinstance(record, AlleleCheck):
                parent = parents.get(record.investigation_id)
                if parent is None:
                    row = db.execute("SELECT result_json FROM investigations WHERE id = ?",
                                     (record.investigation_id,)).fetchone()
                    if row is None:
                        raise RecordMissingError("Investigation no longer exists; allele check was not saved")
                    parent = InvestigationResult.model_validate_json(row[0])
                if parent.input_sha256 != record.input_sha256:
                    raise RecordConflictError("Allele check input hash does not match its investigation")
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
            # Existing pages may contain reusable cells, even with no freelist
            # pages. Reserve by actual allocation, not serialized input length.
            _guard_size(path, '', db)
            for table, _, values in pending:
                _insert_entry(db, table, values)
            # Account for actual SQLite pages and indexes before committing.
            # Raising here rolls back the entire write, including batch imports.
            _guard_size(path, "", db)


def save_bundle_records(path: Path, result, sources, reference=None, snpeff=None, allele=None):
    records = [*sources, *([reference] if reference else []), *([snpeff] if snpeff else []),
               result, *([allele] if allele else [])]
    _save_records(path, records)


def save_snpeff_check(path: Path, check: SnpEffCheck):
    _save_records(path, [check])


def latest_snpeff_check(path: Path, source_record_id: str) -> SnpEffCheck | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT check_json FROM snpeff_checks WHERE source_record_id = ? ORDER BY timestamp_key(checked_at) DESC, rowid DESC LIMIT 1",
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
        row = db.execute("SELECT check_json FROM allele_checks WHERE investigation_id = ? ORDER BY timestamp_key(checked_at) DESC, rowid DESC LIMIT 1", (investigation_id,)).fetchone()
    return AlleleCheck.model_validate_json(row[0]) if row else None


def save_reference_check(path: Path, check: ReferenceCheck):
    _save_records(path, [check])


def latest_reference_check(path: Path, source_record_id: str, *, validate=None) -> ReferenceCheck | None:
    initialize(path)
    with _connection(path) as db:
        rows = db.execute("SELECT check_json FROM reference_checks WHERE source_record_id = ? ORDER BY timestamp_key(checked_at) DESC, rowid DESC",
                          (source_record_id,))
        for (raw,) in rows:
            try:
                check = ReferenceCheck.model_validate_json(raw)
                if validate is not None:
                    validate(check)
                return check
            except (ValueError, ReferenceCheckError):
                if validate is None:
                    raise
    return None


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
        rows=db.execute("SELECT record_json FROM source_records ORDER BY timestamp_key(retrieved_at) DESC, rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [SourceRecord.model_validate_json(row[0]) for row in rows]


def load_source_record(path: Path, id_: str) -> SourceRecord | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT record_json FROM source_records WHERE id = ?", (id_,)).fetchone()
    return SourceRecord.model_validate_json(row[0]) if row else None


def latest_source_record(path: Path, query: SourceQuery) -> SourceRecord | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT record_json FROM source_records WHERE source = ? AND query_key = ? ORDER BY timestamp_key(retrieved_at) DESC, rowid DESC LIMIT 1",
                         ("ensembl_vep", _query_key(query))).fetchone()
    return SourceRecord.model_validate_json(row[0]) if row else None


def save(path: Path, result: InvestigationResult):
    _save_records(path, [result])


def load(path: Path, id_: str) -> InvestigationResult | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT result_json FROM investigations WHERE id = ?", (id_,)).fetchone()
    return InvestigationResult.model_validate_json(row[0]) if row else None


def _search_pattern(query: str) -> str:
    return '%' + query.casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def list_items(path: Path, query: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    initialize(path)
    pattern = _search_pattern(query)
    with _connection(path) as db:
        rows = db.execute("SELECT i.id, i.title, i.created_at,COALESCE(l.display_name,''),COALESCE(l.archived,0) FROM investigations i JOIN investigation_order o ON o.investigation_id=i.id LEFT JOIN investigation_labels l ON l.investigation_id=i.id "
                          "WHERE unicode_casefold(i.title) LIKE ? ESCAPE '\\' OR unicode_casefold(i.id) LIKE ? ESCAPE '\\' "
                          "ORDER BY o.sequence DESC LIMIT ? OFFSET ?", (pattern, pattern, limit, offset)).fetchall()
    return [{"id": row[0], "title": row[1], "created_at": row[2],
             **({'display_name':row[3]} if row[3] else {}), **({'archived':True} if row[4] else {})} for row in rows]


def list_investigation_page(path: Path, query: str = '', limit: int = 100,
                            before: int | None = None, ceiling: int | None = None) -> dict:
    initialize(path)
    pattern = _search_pattern(query)
    with _connection(path) as db:
        if ceiling is None:
            ceiling = db.execute('SELECT COALESCE(MAX(sequence), 0) FROM investigation_order').fetchone()[0]
        rows = db.execute("SELECT i.id, i.title, i.created_at, o.sequence FROM investigations i JOIN investigation_order o ON o.investigation_id=i.id "
            "WHERE (unicode_casefold(i.title) LIKE ? ESCAPE '\\' OR unicode_casefold(i.id) LIKE ? ESCAPE '\\') "
            "AND o.sequence <= ? AND (? IS NULL OR o.sequence < ?) ORDER BY o.sequence DESC LIMIT ?",
            (pattern, pattern, ceiling, before, before, limit + 1)).fetchall()
    visible = rows[:limit]
    return {'items': [{'id':row[0], 'title':row[1], 'created_at':row[2]} for row in visible],
            'ceiling':ceiling, 'next_before':visible[-1][3] if len(rows) > limit else None}


def delete_investigation(path: Path, id_: str) -> bool:
    initialize(path)
    with _connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM regression_cases WHERE source_investigation_id = ?", (id_,)).fetchone():
            raise ValueError("This investigation has a pinned regression case and cannot be deleted")
        if not db.execute("SELECT 1 FROM investigations WHERE id = ?", (id_,)).fetchone():
            return False
        db.execute("DELETE FROM allele_checks WHERE investigation_id = ?", (id_,))
        db.execute('DELETE FROM investigation_labels WHERE investigation_id = ?', (id_,))
        db.execute('DELETE FROM investigation_order WHERE investigation_id = ?', (id_,))
        db.execute("DELETE FROM investigations WHERE id = ?", (id_,))
        if REQUEST_HOSTING.get():
            db.commit()
            try:
                db.execute('VACUUM')
            except sqlite3.Error:
                # Deletion is already durable. Remaining free pages can still
                # be reused even if temporary space for compaction is absent.
                pass
        return True


def backup(path: Path, destination: Path):
    # mode=ro cannot create a missing source or migrate an existing schema.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as source:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb'):
            pass
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)


def save_case(path: Path, case: RegressionCase):
    _save_records(path, [case])


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
    _save_records(path, [run])


def load_run(path: Path, id_: str) -> RegressionRun | None:
    initialize(path)
    with _connection(path) as db:
        row = db.execute("SELECT run_json FROM regression_runs WHERE id = ?", (id_,)).fetchone()
    return RegressionRun.model_validate_json(row[0]) if row else None


def list_runs(path: Path, case_id: str, limit: int = 100, offset: int = 0, before: str | None = None) -> list[dict]:
    initialize(path)
    with _connection(path) as db:
        anchor = None
        if before is not None:
            row = db.execute("SELECT rowid FROM regression_runs WHERE id = ? AND case_id = ?", (before, case_id)).fetchone()
            if row is None:
                raise ValueError("History continuation run does not belong to this case")
            anchor = row[0]
        rows = db.execute("SELECT run_json FROM regression_runs WHERE case_id = ? AND (? IS NULL OR rowid < ?) "
                          "ORDER BY rowid DESC LIMIT ? OFFSET ?", (case_id, anchor, anchor, limit, offset)).fetchall()
    return [{"id": run.id, "created_at": run.created_at, "mode": run.mode, "status": run.status} for row in rows if (run := RegressionRun.model_validate_json(row[0]))]
