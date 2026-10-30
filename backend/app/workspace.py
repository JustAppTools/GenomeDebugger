"""Mutable library organization is separate from immutable scientific results."""
import json
import base64
import binascii
from pathlib import Path
from datetime import date
from .timestamps import timestamp_key
from pydantic import Field
from .engine import digest
from .models import StrictModel
from .storage import _connection, _guard_size, _search_pattern, initialize, RecordMissingError, RecordConflictError, max_database_bytes

MAX_SQLITE_INTEGER = 9223372036854775807


class LibraryLabel(StrictModel):
    display_name: str = Field(default='', max_length=150)
    notes: str = Field(default='', max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    favorite: bool = False
    archived: bool = False

    def checked(self):
        if any(not tag.strip() or len(tag) > 50 for tag in self.tags):
            raise ValueError('Use nonblank tags of at most 50 characters')
        return self


class LibraryLabelUpdate(LibraryLabel):
    expected_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    expected_details_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


def label_revision(label: LibraryLabel):
    return digest(label.model_dump())


def details_revision(label: LibraryLabel):
    return digest(label.model_dump(include={'display_name','notes','tags'}))


def _read_label(db, id_):
    row = db.execute("SELECT i.id,i.title,i.created_at,COALESCE(l.display_name,''),COALESCE(l.notes,''),COALESCE(l.tags,'[]'),COALESCE(l.favorite,0),COALESCE(l.archived,0) FROM investigations i LEFT JOIN investigation_labels l ON l.investigation_id=i.id WHERE i.id=?", (id_,)).fetchone()
    if row is None:
        raise RecordMissingError('Comparison no longer exists')
    id_, title, created, name, notes, tags, favorite, archived = row
    label = LibraryLabel(display_name=name, notes=notes, tags=json.loads(tags), favorite=bool(favorite), archived=bool(archived)).checked()
    return {'id': id_, 'title': title, 'created_at': created, **label.model_dump(), 'label_revision': label_revision(label), 'details_revision':details_revision(label)}


def read_label(path: Path, id_: str):
    initialize(path)
    with _connection(path) as db:
        return _read_label(db, id_)


def save_label(path: Path, id_: str, label: LibraryLabelUpdate):
    label.checked()
    initialize(path)
    with _connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        current = _read_label(db, id_)
        if label.expected_revision is not None and label.expected_revision != current['label_revision']:
            raise RecordConflictError('Saved details changed in another tab. Your edits are still here. Cancel editing and refresh records before trying again.')
        if label.expected_details_revision is not None and label.expected_details_revision != current['details_revision']:
            raise RecordConflictError('Saved details changed in another tab. Your edits are still here. Cancel editing and refresh records before trying again.')
        changed = label.model_dump(include=label.model_fields_set - {'expected_revision','expected_details_revision'})
        merged = LibraryLabel(**{**{key: current[key] for key in LibraryLabel.model_fields}, **changed}).checked()
        db.execute('INSERT INTO investigation_labels VALUES (?,?,?,?,?,?) ON CONFLICT(investigation_id) DO UPDATE SET display_name=excluded.display_name,notes=excluded.notes,tags=excluded.tags,favorite=excluded.favorite,archived=excluded.archived',
                   (id_, merged.display_name, merged.notes, json.dumps(merged.tags, ensure_ascii=False), int(merged.favorite), int(merged.archived)))
        _guard_size(path, '', db)
        result = _read_label(db, id_)
    return result


def list_library(path: Path, q='', view='active', favorite=False, source='', since='', sort='newest', offset=0, limit=50, cursor='', ceiling=None, since_instant=''):
    if ceiling is not None and (type(ceiling) is not int or not 0 <= ceiling <= MAX_SQLITE_INTEGER):
        raise ValueError('Invalid library page ceiling')
    initialize(path)
    if since:
        date.fromisoformat(since)
    boundary = timestamp_key(since_instant or since+'T00:00:00+00:00') if since_instant or since else None
    pattern = _search_pattern(q)
    point = None
    if cursor:
        try:
            point = json.loads(base64.b64decode(cursor.encode('ascii'), altchars=b'-_', validate=True))
            if (not isinstance(point, dict) or set(point) != {'sequence','name','sort','ceiling'} or
                    type(point['sequence']) is not int or type(point['ceiling']) is not int or
                    not isinstance(point['name'], str) or point['sort'] != sort or
                    not 0 < point['sequence'] <= point['ceiling'] <= MAX_SQLITE_INTEGER or
                    (ceiling is not None and ceiling != point['ceiling'])):
                raise ValueError('Invalid library cursor')
            point['name'].encode('utf-8', errors='strict')
            if len(point['name']) > 600:
                raise ValueError('Invalid library name cursor')
            ceiling = point['ceiling']
        except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
            raise ValueError('Invalid library cursor; refresh this filtered view') from exc
    with _connection(path) as db:
        if ceiling is None:
            ceiling = db.execute('SELECT COALESCE(MAX(sequence),0) FROM investigation_order').fetchone()[0]
        where = " WHERE (unicode_casefold(i.title || ' ' || i.id || ' ' || COALESCE(l.display_name,'') || ' ' || COALESCE(l.notes,'') || ' ' || COALESCE(l.tags,'')) LIKE ? ESCAPE '\\')"
        args = [pattern]
        where += ' AND o.sequence <= ?'
        args.append(ceiling)
        if view != 'all':
            where += ' AND COALESCE(l.archived,0)=?'
            args.append(int(view == 'archived'))
        if favorite:
            where += ' AND COALESCE(l.favorite,0)=1'
        if source:
            where += " AND unicode_casefold(json_extract(i.result_json,'$.input.snapshots[0].provenance.source_name') || ' ' || json_extract(i.result_json,'$.input.snapshots[1].provenance.source_name')) LIKE ? ESCAPE '\\'"
            args.append(_search_pattern(source))
        if boundary:
            where += ' AND timestamp_key(i.created_at) >= ?'
            args.append(boundary)
        base = ' FROM investigations i JOIN investigation_order o ON o.investigation_id=i.id LEFT JOIN investigation_labels l ON l.investigation_id=i.id'
        total = db.execute('SELECT COUNT(*)' + base + where, args).fetchone()[0]
        name = "unicode_casefold(CASE WHEN COALESCE(l.display_name,'')='' THEN i.title ELSE l.display_name END)"
        ordering = {'newest':'o.sequence DESC', 'oldest':'o.sequence ASC', 'name':name + ', o.sequence DESC'}[sort]
        if point:
            if sort == 'name':
                where += f' AND ({name} > ? OR ({name} = ? AND o.sequence < ?))'
                args.extend([point['name'],point['name'],point['sequence']])
            else:
                where += ' AND o.sequence ' + ('<' if sort == 'newest' else '>') + ' ?'
                args.append(point['sequence'])
        # Project only display fields in SQLite. A page must not deserialize up
        # to 100 complete investigations and all their preserved source text.
        paths = ['$.input.snapshots[0].variant.'+field for field in ('assembly','sequence_id','position','ref','alt')]
        paths += ['$.input.snapshots[0].provenance.source_name','$.input.snapshots[1].provenance.source_name',
                  '$.input.snapshots[0].provenance.tool','$.input.snapshots[0].provenance.tool_version',
                  '$.input.snapshots[1].provenance.tool','$.input.snapshots[1].provenance.tool_version',
                  '$.input.synthetic','$.identity.status']
        summary = 'json_extract(i.result_json,' + ','.join("'"+path+"'" for path in paths) + ')'
        rows = db.execute("SELECT i.id,i.title,i.created_at," + summary + ",json_array_length(i.result_json,'$.differences'),COALESCE(l.display_name,''),COALESCE(l.notes,''),COALESCE(l.tags,'[]'),COALESCE(l.favorite,0),COALESCE(l.archived,0),o.sequence," + name + base + where + ' ORDER BY ' + ordering + ' LIMIT ? OFFSET ?', (*args, limit+1, 0 if point else offset)).fetchall()
    items = []
    has_more = len(rows) > limit
    rows = rows[:limit]
    for id_, title, created, summary, differences, name, notes, tags, pinned, archived, _, _ in rows:
        assembly, accession, position, ref, alt, source_a, source_b, tool_a, version_a, tool_b, version_b, synthetic, identity = json.loads(summary)
        label = LibraryLabel(display_name=name, notes=notes, tags=json.loads(tags), favorite=bool(pinned), archived=bool(archived))
        items.append(dict(id=id_, title=title, created_at=created, **label.model_dump(), label_revision=label_revision(label), details_revision=details_revision(label),
                          variant=f'{assembly} {accession}:{position} {ref}>{alt}',
                          sources=[source_a,source_b], tools=[f'{tool_a} {version_a}',f'{tool_b} {version_b}'],
                          synthetic=bool(synthetic), identity_status=identity, difference_count=differences))
    next_cursor = None
    if has_more and rows:
        next_cursor = base64.urlsafe_b64encode(json.dumps({'sequence':rows[-1][-2],'name':rows[-1][-1] if sort=='name' else '', 'sort':sort,'ceiling':ceiling}, ensure_ascii=False, separators=(',',':')).encode()).decode()
    return {'items': items, 'total': total, 'offset': offset, 'has_more': has_more, 'next_cursor':next_cursor, 'ceiling':ceiling}


def local_data(path: Path):
    initialize(path)
    with _connection(path) as db:
        counts = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in
                  ('investigations','regression_cases','regression_runs','source_records','reference_checks','snpeff_checks','allele_checks')}
        used = (db.execute('PRAGMA page_count').fetchone()[0] - db.execute('PRAGMA freelist_count').fetchone()[0]) * db.execute('PRAGMA page_size').fetchone()[0]
    return {'database_path': str(path.resolve()), 'used_bytes': used, 'file_bytes': path.stat().st_size, 'max_db_bytes':max_database_bytes(), 'schema_version': 3, 'counts': counts}
