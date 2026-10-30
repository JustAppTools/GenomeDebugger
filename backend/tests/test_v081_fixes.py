"""Regression coverage for the twelve findings in the 0.8.0 audit."""
import base64
import csv
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import main, storage
from app.manage import restore_backup
from app.tabular_import import REQUIRED

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/transcript-switch.json'


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'workspace.db')
    return TestClient(main.app, raise_server_exceptions=False)


def create(api, title='Regression input'):
    data=json.loads(FIXTURE.read_text());data['title']=title
    response=api.post('/api/investigations',json=data)
    assert response.status_code==200,response.text
    return response.json()


def table(rows):
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=[*REQUIRED,'context_start','reference_sequence']);writer.writeheader()
    for row in rows:
        writer.writerow({**dict(assembly='GRCh38',sequence_id='NC_000001.11',position='102',ref='C',alt='T',gene_id='G',tool='Tool',tool_version='1',source_name='Source',source_release='1',context_start='100',reference_sequence='GACGTACG'),**row})
    return output.getvalue()


@pytest.mark.parametrize('multiple_variants',[False,True])
def test_csv_row_order_does_not_select_a_different_scientific_annotation(api,multiple_variants):
    rows=[{'transcript_id':'T2','consequence':'intron_variant'},{'transcript_id':'T1','consequence':'missense_variant'}]
    if multiple_variants:
        rows.append({'position':'104','ref':'T','alt':'G','transcript_id':'T3','consequence':'intron_variant'})
    files=[{'name':'A.csv','text':table(rows),'delimiter':','},{'name':'B.csv','text':table(list(reversed(rows))),'delimiter':','}]
    preview=api.post('/api/imports/tabular/preview',json={'title':'Reordered copies','files':files})
    assert preview.status_code==200,preview.text
    payload=preview.json()['input']
    for snapshot,file in zip(payload['snapshots'],files):
        assert snapshot['provenance']['configuration']['original_utf8']==file['text']
        assert snapshot['provenance']['input_sha256']==hashlib.sha256(file['text'].encode()).hexdigest()
    result=api.post('/api/investigations',json=payload).json()
    assert not any(d['meaningful'] for d in result['differences'])
    assert not any(f['cause']=='transcript selection' for f in result['findings'])
    bundle=api.get(f"/api/investigations/{result['id']}/bundle").json()
    assert api.post('/api/bundles/verify',json=bundle).status_code==200


def test_tabular_bom_is_retained_and_hashed_as_original_utf8(api):
    text='\ufeff'+table([{'transcript_id':'T1','consequence':'intron_variant'}])
    response=api.post('/api/imports/tabular/preview',json={'title':'BOM','files':[{'name':name,'text':text,'delimiter':','} for name in ['A.csv','B.csv']]})
    assert response.status_code==200,response.text
    for snapshot in response.json()['input']['snapshots']:
        assert snapshot['provenance']['configuration']['original_utf8']==text
        assert snapshot['provenance']['input_sha256']==hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize('damage',['wrong_table','missing_table','bad_json','wrong_id','bad_label'])
def test_invalid_restore_cannot_replace_destination_or_create_a_false_success(api,tmp_path,damage):
    result=create(api);target=main.DB
    before=target.read_bytes();source=tmp_path/'bad-backup.db'
    storage.backup(target,source)
    with closing(sqlite3.connect(source)) as db:
        if damage=='wrong_table':
            db.execute('DROP TABLE investigations');db.execute('CREATE TABLE investigations (unexpected TEXT)')
        elif damage=='missing_table':db.execute('DROP TABLE source_records')
        elif damage=='bad_json':db.execute("UPDATE investigations SET result_json='{}'")
        elif damage=='wrong_id':db.execute("UPDATE investigations SET id='wrong'")
        elif damage=='bad_label':db.execute("INSERT INTO investigation_labels VALUES (?,'','','[]',4,0)",(result['id'],))
        db.commit()
    with pytest.raises((ValueError,sqlite3.Error)):
        restore_backup(source,target)
    assert target.read_bytes()==before
    assert not list(tmp_path.glob('workspace-before-restore-*'))
    assert not list(tmp_path.glob('*.restore-*'))
    assert api.get('/api/health').status_code==200
    assert api.get('/api/investigations/'+result['id']).json()==result


def test_health_does_not_trust_a_version_number_without_the_required_schema(api):
    with closing(sqlite3.connect(main.DB)) as db:
        db.execute('CREATE TABLE investigations (unexpected TEXT)');db.execute('PRAGMA user_version=3');db.commit()
    assert api.get('/api/health').status_code==503


def test_restore_migrates_a_valid_legacy_backup_without_rewriting_its_result(api,tmp_path):
    result=create(api);raw=storage.load(main.DB,result['id']).model_dump_json()
    source=tmp_path/'legacy.db'
    with closing(sqlite3.connect(source)) as db:
        db.execute('CREATE TABLE investigations (id TEXT PRIMARY KEY,title TEXT NOT NULL,result_json TEXT NOT NULL)')
        db.execute('INSERT INTO investigations VALUES (?,?,?)',(result['id'],result['input']['title'],raw));db.commit()
    target=tmp_path/'restored.db'
    assert restore_backup(source,target) is None
    with closing(sqlite3.connect(target)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
        assert db.execute('SELECT result_json FROM investigations').fetchone()[0]==raw
    with closing(sqlite3.connect(source)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==0


def test_flag_updates_preserve_other_clients_notes_and_edit_conflicts_are_explicit(api):
    result=create(api);id_=result['id'];url=f'/api/workspace/library/{id_}/label'
    original=api.get(url).json()
    saved=api.post(url,json={'notes':'New notes','display_name':'Named','expected_revision':original['label_revision']})
    assert saved.status_code==200
    for flag in ['favorite','archived']:
        changed=api.post(url,json={flag:True})
        assert changed.status_code==200
        assert changed.json()['notes']=='New notes' and changed.json()['display_name']=='Named'
    conflict=api.post(url,json={'notes':'Stale notes','expected_revision':original['label_revision']})
    assert conflict.status_code==409 and 'another tab' in conflict.text
    current=api.get(url).json()
    assert current['notes']=='New notes' and current['favorite'] and current['archived']
    assert api.get('/api/investigations/'+id_).json()==result


@pytest.mark.parametrize('sorting',['newest','oldest','name'])
def test_long_unicode_names_round_trip_through_a_full_library_page(api,sorting):
    long='🧬'*200
    titles=['Older',long,*[f'Record {i:02d}' for i in range(49)]] if sorting=='newest' else [*[f'Record {i:02d}' for i in range(49)],long,'\U0010ffff']
    ids={create(api,title)['id'] for title in titles}
    page=api.get('/api/workspace/library',params={'sort':sorting}).json()
    assert len(page['items'])==50 and page['items'][-1]['title']==long
    assert len(page['next_cursor'])<=4096
    following=api.get('/api/workspace/library',params={'sort':sorting,'cursor':page['next_cursor']})
    assert following.status_code==200,following.text
    assert {row['id'] for row in page['items']+following.json()['items']}==ids


@pytest.mark.parametrize('field',['ceiling','offset'])
def test_library_rejects_integer_overflow_in_query_numbers(api,field):
    assert api.get('/api/workspace/library',params={field:2**63}).status_code==422


@pytest.mark.parametrize('point',[{'sequence':1,'ceiling':2**63},{'sequence':2**63,'ceiling':2**63},{'sequence':True,'ceiling':1}])
def test_library_rejects_overflow_or_boolean_cursor_numbers(api,point):
    cursor=base64.urlsafe_b64encode(json.dumps({'name':'','sort':'newest',**point}).encode()).decode()
    assert api.get('/api/workspace/library',params={'cursor':cursor}).status_code==422
