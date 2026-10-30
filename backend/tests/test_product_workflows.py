import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient
from app import main, storage
from app.identifier import resolve_identifier
from app.manage import restore_backup
from app.tabular_import import REQUIRED

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/transcript-switch.json'


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'workspace.db')
    return TestClient(main.app)


def table(rows=None, delimiter=','):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(REQUIRED), delimiter=delimiter)
    writer.writeheader()
    base = dict(assembly='GRCh38', sequence_id='NC_000001.11', position='102', ref='C', alt='T',
                gene_id='G', transcript_id='TX.1', consequence='missense_variant', tool='Declared tool',
                tool_version='1', source_name='Declared source', source_release='1')
    for patch in rows or [{}]:
        writer.writerow({**base, **patch})
    return output.getvalue()


def preview(api, first=None, second=None):
    return api.post('/api/imports/tabular/preview', json={'title':'Imported comparison', 'files':[
        {'name':'A.csv', 'text':first or table(), 'delimiter':','},
        {'name':'B.csv', 'text':second or table([{'consequence':'intron_variant'}]), 'delimiter':','}]})


def test_preview_preserves_original_text_and_requires_explicit_save(api):
    raw = table([{'source_name':'Source, with Unicode β'}])
    response = preview(api, first=raw)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['files'][0]['rows'] == 1
    snapshot = body['input']['snapshots'][0]
    assert snapshot['provenance']['configuration']['original_utf8'] == raw
    assert snapshot['provenance']['input_sha256'] == hashlib.sha256(raw.encode()).hexdigest()
    assert api.get('/api/investigations').json() == []
    result = api.post('/api/investigations', json=body['input'])
    assert result.status_code == 200, result.text
    assert result.json()['identity']['status'] == 'unresolved'
    bundle = api.get(f"/api/investigations/{result.json()['id']}/bundle").json()
    assert api.post('/api/bundles/verify', json=bundle).status_code == 200


@pytest.mark.parametrize('patch', [{'assembly':''}, {'position':'0'}, {'position':'1.0'}, {'ref':'N'}, {'alt':'C'}])
def test_import_never_guesses_missing_or_unsupported_values(api, patch):
    response = preview(api, first=table([patch]))
    assert response.status_code == 422
    assert api.get('/api/investigations').json() == []


def test_multi_variant_import_matches_rows_explicitly_and_rejects_conflicts(api):
    raw = table([{}, {'position':'103','transcript_id':'TX.2'}])
    response = preview(api, first=raw, second=raw)
    assert response.status_code == 200
    assert response.json()['files'][0]['variants'] == 2
    assert len(response.json()['input']['snapshots'][0]['variant_records']) == 1
    conflict = preview(api, first=table([{}, {'tool_version':'2','transcript_id':'TX.2'}]))
    assert conflict.status_code == 422 and 'consistent' in conflict.text
    duplicate = preview(api, first=table([{}, {}]))
    assert duplicate.status_code == 422 and 'unique' in duplicate.text


def test_library_labels_archive_and_search_never_change_scientific_bytes(api):
    result = api.post('/api/investigations', json=json.loads(FIXTURE.read_text())).json()
    id_ = result['id']
    before = api.get('/api/investigations/'+id_).content
    label = dict(display_name='Review β', notes='Follow up with producing analyst', tags=['β','release'], favorite=True, archived=True)
    assert api.post(f'/api/workspace/library/{id_}/label', json=label).status_code == 200
    assert api.get('/api/workspace/library').json()['total'] == 0
    found = api.get('/api/workspace/library', params={'view':'archived','q':'β','favorite':True}).json()
    assert found['total'] == 1 and found['items'][0]['display_name'] == 'Review β'
    assert api.get('/api/investigations/'+id_).content == before
    assert api.post(f'/api/workspace/library/{id_}/label', json={**label,'archived':False}).status_code == 200
    assert api.get('/api/workspace/library').json()['total'] == 1
    assert api.post('/api/workspace/library/missing/label', json=label).status_code == 404


def test_database_download_and_selected_bundle_export_are_restorable(api, tmp_path):
    result = api.post('/api/investigations', json=json.loads(FIXTURE.read_text())).json()
    response = api.get('/api/workspace/backup')
    assert response.status_code == 200
    downloaded = tmp_path / 'downloaded.db'
    downloaded.write_bytes(response.content)
    with closing(sqlite3.connect(downloaded)) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT id FROM investigations').fetchone()[0] == result['id']
    archive = api.post('/api/workspace/export', json={'ids':[result['id']]} )
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_:
        bundle = json.loads(zip_.read(zip_.namelist()[0]))
    assert api.post('/api/bundles/verify', json=bundle).status_code == 200
    target = tmp_path / 'restored.db'
    restore_backup(downloaded, target)
    assert storage.load(target, result['id']) is not None
    old_copy = restore_backup(downloaded, target)
    assert old_copy.is_file()
    corrupt = tmp_path / 'corrupt.db'; corrupt.write_bytes(b'not sqlite')
    with pytest.raises((ValueError, sqlite3.Error)):
        restore_backup(corrupt, target)
    assert storage.load(target, result['id']) is not None


def test_new_examples_keep_scientific_uncertainty(api):
    matching = api.get('/api/demos/matching').json()
    result = api.post('/api/investigations', json=matching).json()
    assert result['differences'] == []
    assert matching['synthetic'] and matching['controlled_lookup'] is None
    uncertain = api.get('/api/demos/uncertain').json()
    result = api.post('/api/investigations', json=uncertain).json()
    assert result['identity']['status'] == 'unresolved'
    assert not any(f['status']=='verified' for f in result['findings'])


def test_identifier_resolution_previews_every_supported_allele_without_selecting():
    raw = [{'assembly_name':'GRCh38','start':123,'end':123,'strand':1,'seq_region_name':'1','allele_string':'C/A/T'},
           {'assembly_name':'GRCh37','start':120,'end':120,'strand':1,'seq_region_name':'1','allele_string':'C/T'},
           {'assembly_name':'GRCh38','start':123,'end':123,'strand':-1,'seq_region_name':'1','allele_string':'C/T'}]
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=raw))) as client:
        result = resolve_identifier('rs56116432', client)
    assert [q['alt'] for q in result['choices']] == ['A','T']
    assert result['unsupported_records'] == 2 and result['response'] == raw
    assert 'selected' not in result
    with pytest.raises(ValueError):
        resolve_identifier('BRCA1')


def test_new_schema_migration_preserves_result_and_creates_only_organization_table(api):
    result = api.post('/api/investigations', json=json.loads(FIXTURE.read_text())).json()
    data = api.get('/api/workspace/data').json()
    assert data['schema_version'] == 3 and data['counts']['investigations'] == 1
    with closing(sqlite3.connect(main.DB)) as db:
        before = db.execute('SELECT result_json FROM investigations').fetchone()[0]
        db.execute('DROP TABLE investigation_labels'); db.execute('PRAGMA user_version=2'); db.commit()
    storage.initialize(main.DB)
    with closing(sqlite3.connect(main.DB)) as db:
        assert db.execute('SELECT result_json FROM investigations').fetchone()[0] == before
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3


@pytest.mark.parametrize('sort',['newest','oldest','name'])
def test_library_cursor_does_not_skip_records_after_deletion_or_include_new_insertions(api,sort):
    original = json.loads(FIXTURE.read_text())
    ids=[]
    for index in range(4):
        ids.append(api.post('/api/investigations',json={**original,'title':f'Record {index}'}).json()['id'])
    first=api.get('/api/workspace/library',params={'limit':2,'sort':sort}).json()
    assert len(first['items'])==2 and first['next_cursor']
    removed=first['items'][0]['id']
    assert api.delete('/api/investigations/'+removed).status_code==200
    new=api.post('/api/investigations',json={**original,'title':'New insertion'}).json()['id']
    second=api.get('/api/workspace/library',params={'limit':2,'sort':sort,'cursor':first['next_cursor']}).json()
    assert new not in {item['id'] for item in second['items']}
    assert {item['id'] for item in first['items']+second['items']}==set(ids)
    assert len(second['items'])==2
    assert api.get('/api/workspace/library',params={'cursor':'not-a-cursor'}).status_code==422
