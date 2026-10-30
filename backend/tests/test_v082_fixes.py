"""Regressions for all backend findings in the 0.8.1 audit."""
import csv
import io
import json
import sqlite3
from contextlib import closing
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import main, storage
from app.engine import compare, digest
from app.models import InvestigationInput
from app.manage import restore_backup, validate_restore
from app.workspace_lock import WorkspaceLock, WorkspaceInUseError
from app.tabular_import import REQUIRED
from app.bundle import verify_bundle
from app.legacy_engine_v065 import compare as compare_v065
from app.version import ENGINE_VERSION
from app.archives.mvp import engine as original_mvp
from app import legacy_unversioned_selection as original_selection

FIXTURE = Path(__file__).resolve().parents[2]/'fixtures/transcript-switch.json'

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'workspace.db')
    return TestClient(main.app,raise_server_exceptions=False)

def create(api):
    response=api.post('/api/investigations',json=json.loads(FIXTURE.read_text(encoding='utf-8')))
    assert response.status_code==200,response.text
    return response.json()

def table(rows):
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=[*REQUIRED,'context_start','reference_sequence']);writer.writeheader()
    for row in rows:
        writer.writerow({**dict(assembly='GRCh38',sequence_id='NC_000001.11',position=102,ref='C',alt='T',gene_id='G',tool='Tool',tool_version='1',source_name='Source',source_release='1',context_start=100,reference_sequence='GACGTACG'),**row})
    return output.getvalue()

def imported(api,a,b,name='A.csv'):
    response=api.post('/api/imports/tabular/preview',json={'title':'Row collections','files':[
        {'name':name,'text':table(a),'delimiter':','},{'name':'B.csv','text':table(b),'delimiter':','}]})
    assert response.status_code==200,response.text
    payload=response.json()['input']
    response=api.post('/api/investigations',json=payload)
    assert response.status_code==200,response.text
    return response.json()

def test_app_lifetime_lock_blocks_restore_and_another_owner_regardless_of_port(api,tmp_path):
    result=create(api);backup=tmp_path/'backup.db';storage.backup(main.DB,backup)
    with api:
        with pytest.raises(WorkspaceInUseError):restore_backup(backup,main.DB)
        with pytest.raises(WorkspaceInUseError):
            with WorkspaceLock(main.DB):pass
        assert api.get('/api/investigations/'+result['id']).json()==result
    # Closing the app releases the OS lock even though the lock file remains.
    assert restore_backup(backup,main.DB).is_file()
    with WorkspaceLock(main.DB):pass

@pytest.mark.parametrize('damage',['identity','hash','baseline_parent','baseline_name','run_parent','run_verdict','sequence'])
def test_semantically_inconsistent_restores_leave_destination_unchanged(api,tmp_path,damage):
    result=create(api)
    case=api.post(f"/api/investigations/{result['id']}/regression-cases",json={'name':'Pinned'}).json()
    run=api.post(f"/api/regression-cases/{case['id']}/runs",json={}).json()
    source=tmp_path/'bad.db';storage.backup(main.DB,source);before=main.DB.read_bytes()
    with closing(sqlite3.connect(source)) as db:
        if damage in ('identity','hash'):
            raw=json.loads(db.execute('SELECT result_json FROM investigations').fetchone()[0])
            if damage=='identity':raw['identity']['status']='rejected'
            else:raw['input_sha256']='0'*64
            db.execute('UPDATE investigations SET result_json=?',(json.dumps(raw),))
        elif damage=='baseline_parent':db.execute("UPDATE regression_cases SET source_investigation_id='missing'")
        elif damage=='baseline_name':db.execute("UPDATE regression_cases SET name='wrong'")
        elif damage=='run_parent':db.execute("UPDATE regression_runs SET case_id='missing'")
        elif damage=='sequence':db.execute('UPDATE investigation_order SET sequence=-1')
        else:
            run['status']='failed';db.execute('UPDATE regression_runs SET run_json=?',(json.dumps(run),))
        db.commit()
    with pytest.raises(ValueError):restore_backup(source,main.DB)
    assert main.DB.read_bytes()==before
    assert not list(tmp_path.glob('workspace-before-restore-*'))
    assert not list(tmp_path.glob('*.restore-*'))

@pytest.mark.parametrize('rules',[original_mvp,original_selection])
def test_unversioned_original_formats_restore_without_rewriting_and_reject_altered_verdicts(tmp_path,rules):
    data=json.loads(FIXTURE.read_text(encoding='utf-8'))
    legacy=rules.compare(rules.InvestigationInput.model_validate(data)).model_dump_json()
    source=tmp_path/'original.db'
    with closing(sqlite3.connect(source)) as db:
        db.execute('CREATE TABLE investigations(id TEXT PRIMARY KEY,title TEXT NOT NULL,result_json TEXT NOT NULL)')
        db.execute('INSERT INTO investigations VALUES(?,?,?)',(json.loads(legacy)['id'],data['title'],legacy));db.commit()
    target=tmp_path/'restored.db';restore_backup(source,target)
    with closing(sqlite3.connect(target)) as db:assert db.execute('SELECT result_json FROM investigations').fetchone()[0]==legacy
    corrupted=json.loads(legacy);corrupted['identity']['status']='rejected'
    with closing(sqlite3.connect(source)) as db:
        db.execute('UPDATE investigations SET result_json=?',(json.dumps(corrupted),));db.commit()
    with pytest.raises(ValueError):restore_backup(source,target)

def test_archived_065_bundle_still_verifies_and_new_comparisons_get_a_separate_identity():
    payload=InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8'))
    old=compare_v065(payload);new=compare(payload)
    entries={'investigation':old.model_dump(mode='json')}
    assert verify_bundle({'format':'GenomeDebugger bundle','version':2,'engine_version':'0.6.5','entries':entries,'sha256':{'investigation':digest(entries['investigation'])}})[0]==old
    assert old.engine_version=='0.6.5' and new.engine_version==ENGINE_VERSION and old.id!=new.id

def test_flag_update_does_not_bypass_a_details_conflict_and_unrelated_flags_do_not_conflict(api):
    result=create(api);url=f"/api/workspace/library/{result['id']}/label"
    loaded=api.get(url).json()
    newer=api.post(url,json={'notes':'Other tab saved this'}).json()
    flagged=api.post(url,json={'favorite':True}).json()
    assert flagged['details_revision']==newer['details_revision']!=loaded['details_revision']
    assert api.post(url,json={'notes':'Stale editor','expected_details_revision':loaded['details_revision']}).status_code==409
    response=api.post(url,json={'notes':'Current editor','expected_details_revision':newer['details_revision']})
    assert response.status_code==200 and response.json()['favorite'] is True

def test_new_tabular_annotation_is_only_a_row_addition_not_a_selection_or_effect_change(api):
    old={'transcript_id':'T2','consequence':'intron_variant'}
    result=imported(api,[old],[old,{'transcript_id':'T1','consequence':'missense_variant'}])
    scientific=[d for d in result['differences'] if d['category']=='annotation']
    assert len(scientific)==1 and scientific[0]['field'].endswith('annotations[G|T1||].presence')
    assert not any(f['cause']=='transcript selection' for f in result['findings'])

def test_new_tabular_variant_does_not_compare_two_different_overview_anchors(api):
    old={'position':104,'ref':'T','alt':'G','transcript_id':'T2','consequence':'intron_variant'}
    extra={'transcript_id':'T1','consequence':'missense_variant'}
    result=imported(api,[old],[extra,old])
    scientific=[d for d in result['differences'] if d['meaningful']]
    assert len(scientific)==1 and scientific[0]['category']=='variant' and scientific[0]['field'].endswith('.presence')
    assert result['identity']['status']=='unresolved' and 'sets differ' in result['identity']['explanation']

@pytest.mark.parametrize('unverified',['rejected','unresolved'])
def test_transcript_causes_require_established_common_identity(api,unverified):
    data=json.loads(FIXTURE.read_text(encoding='utf-8'));data['controlled_lookup']=None
    if unverified=='rejected':data['snapshots'][1]['variant']['alt']='G'
    else:data['snapshots'][1]['variant']['reference_context']=None
    result=api.post('/api/investigations',json=data).json()
    assert result['identity']['status']==unverified
    assert not any(f['cause']=='transcript selection' for f in result['findings'])
    assert not any(f['status']=='verified' for f in result['findings'])

def test_source_hash_and_location_changes_are_visible_as_provenance(api):
    data=json.loads(FIXTURE.read_text(encoding='utf-8'));data['controlled_lookup']=None
    data['snapshots'][1]['annotation']=deepcopy(data['snapshots'][0]['annotation'])
    for snapshot,letter in zip(data['snapshots'],'ab'):
        snapshot['provenance']['input_sha256']=letter*64;snapshot['provenance']['source_uri']='https://example.invalid/'+letter
    result=api.post('/api/investigations',json=data).json()
    assert {d['field'] for d in result['differences']} >= {'source_uri','input_sha256'}
    assert all(d['category']=='provenance' and not d['meaningful'] for d in result['differences'] if d['field'] in ('source_uri','input_sha256'))

def test_long_original_filename_is_kept_while_only_its_display_label_is_bounded(api):
    name='x'*147+'.csv'
    result=imported(api,[{'transcript_id':'T','consequence':'intron_variant'}],[{'transcript_id':'T','consequence':'intron_variant'}],name)
    snapshot=result['input']['snapshots'][0]
    assert snapshot['provenance']['configuration']['import_filename']==name
    assert len(snapshot['label'])==150
    bundle=api.get(f"/api/investigations/{result['id']}/bundle").json()
    assert api.post('/api/bundles/verify',json=bundle).status_code==200

@pytest.mark.parametrize('instant,expected',[('2026-10-28T05:00:00Z',0),('2026-10-27T15:00:00Z',1),('2026-10-28T02:00:00Z',1),('2026-11-01T05:00:00Z',0),('2026-11-02T06:00:00Z',0)])
def test_filter_compares_explicit_local_midnight_as_an_instant(api,instant,expected):
    result=create(api)
    with closing(sqlite3.connect(main.DB)) as db:
        db.execute('UPDATE investigations SET created_at=?',('2026-10-28T02:00:00+00:00',));db.commit()
    response=api.get('/api/workspace/library',params={'since_instant':instant})
    assert response.status_code==200 and response.json()['total']==expected
    assert api.get('/api/workspace/library',params={'since':'2026-99-99'}).status_code==422
    assert api.get('/api/workspace/library',params={'since_instant':'bad'}).status_code==422

def test_every_offset_endpoint_rejects_overflow(api):
    result=create(api);case=api.post(f"/api/investigations/{result['id']}/regression-cases",json={'name':'Baseline'}).json()
    for path in ['/api/investigations','/api/sources/records','/api/regression-cases',f"/api/regression-cases/{case['id']}/runs"]:
        assert api.get(path,params={'offset':2**63}).status_code==422
