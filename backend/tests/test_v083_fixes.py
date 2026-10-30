"""Corrected-behavior regressions for the 0.8.2 audit."""
import asyncio
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from app import main, storage
from app.bundle import verify_bundle
from app.engine import compare, digest
from app.manage import restore_backup
from app.models import InvestigationInput
from app.regression import create_case, run_case, RegressionRun
from app import legacy_engine_v050, legacy_engine_v063, legacy_engine_v066
from app import legacy_regression_v050, legacy_regression_v063, legacy_regression_v063_linked, legacy_regression_v066

FIXTURE=Path(__file__).resolve().parents[2]/'fixtures/transcript-switch.json'

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'workspace.db')
    return TestClient(main.app,raise_server_exceptions=False)

def payload():
    return InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8'))

def failed_run(api):
    baseline=api.post('/api/investigations',json=payload().model_dump(mode='json')).json()
    case=api.post(f"/api/investigations/{baseline['id']}/regression-cases",json={'name':'Expected predictions'}).json()
    candidate=deepcopy(baseline['input']);candidate['snapshots'][0]['annotation']['consequence']='stop_gained'
    run=api.post(f"/api/regression-cases/{case['id']}/runs",json={'candidate':candidate}).json()
    assert run['status']=='failed'
    return run

@pytest.mark.parametrize('damage',['empty','omit','required','values','path','changes','version'])
def test_forged_regression_assertions_reject_restore_without_touching_destination(api,tmp_path,damage):
    run=failed_run(api);source=tmp_path/'altered.db';storage.backup(main.DB,source)
    before=main.DB.read_bytes()
    if damage=='empty':run['checks']=[]
    elif damage=='omit':run['checks']=[check for check in run['checks'] if check['passed']]
    elif damage=='required':
        for check in run['checks']:check['required']=False
    elif damage=='values':
        for check in run['checks']:check.update(expected=check['actual'],passed=True)
    elif damage=='path':run['checks'][0]['path']='unrelated.assertion'
    elif damage=='changes':run['input_changes']=[]
    else:run.pop('assertion_version')
    run['status']='passed' if all(c['passed'] for c in run['checks'] if c['required']) else 'failed'
    with closing(sqlite3.connect(source)) as db:
        db.execute('UPDATE regression_runs SET run_json=? WHERE id=?',(json.dumps(run),run['id']));db.commit()
    with pytest.raises(ValueError):restore_backup(source,main.DB)
    assert main.DB.read_bytes()==before
    assert not list(tmp_path.glob('*.restore-*'))

def test_valid_failed_candidate_keeps_its_verdict_after_restore(api,tmp_path):
    run=failed_run(api);source=tmp_path/'valid.db';storage.backup(main.DB,source)
    target=tmp_path/'restored.db';restore_backup(source,target)
    assert storage.load_run(target,run['id']).status=='failed'

@pytest.mark.parametrize('engine,rules',[
    (legacy_engine_v050,legacy_regression_v050),
    (legacy_engine_v063,legacy_regression_v063),
    (legacy_engine_v063,legacy_regression_v063_linked),
    (legacy_engine_v066,legacy_regression_v066),
])
@pytest.mark.parametrize('candidate',[False,True])
def test_historical_regression_rules_restore_without_rewriting(tmp_path,engine,rules,candidate):
    source=tmp_path/'original.db';baseline=engine.compare(payload())
    case=create_case(baseline,'Historical baseline')
    supplied=payload()
    if candidate:supplied.snapshots[0].annotation.consequence='stop_gained'
    actual=engine.compare(supplied)
    run=rules.run_case(case,supplied if candidate else None,_actual_result=actual)
    storage.save(source,baseline);storage.save_case(source,case)
    storage.save_run(source,RegressionRun.model_validate(run.model_dump(mode='json')))
    original=run.model_dump_json()
    with closing(sqlite3.connect(source)) as db:
        db.execute('UPDATE regression_runs SET run_json=?',(original,));db.commit()
    target=tmp_path/'restored.db';restore_backup(source,target)
    with closing(sqlite3.connect(target)) as db:assert db.execute('SELECT run_json FROM regression_runs').fetchone()[0]==original

@pytest.mark.parametrize('table,definition',[
    ('investigation_labels',"investigation_id TEXT,display_name TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',tags TEXT NOT NULL DEFAULT '[]',favorite INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0"),
    ('investigation_labels',"investigation_id TEXT PRIMARY KEY,display_name TEXT,notes TEXT NOT NULL,tags TEXT NOT NULL,favorite INTEGER NOT NULL,archived INTEGER NOT NULL"),
    ('investigation_labels',"investigation_id TEXT PRIMARY KEY,display_name TEXT NOT NULL,notes TEXT NOT NULL,tags TEXT NOT NULL,favorite TEXT NOT NULL,archived INTEGER NOT NULL"),
    ('investigation_order','sequence INTEGER PRIMARY KEY AUTOINCREMENT,investigation_id TEXT NOT NULL'),
    ('investigation_order','sequence INTEGER PRIMARY KEY,investigation_id TEXT NOT NULL UNIQUE'),
])
def test_missing_database_constraints_reject_restore(api,tmp_path,table,definition):
    api.post('/api/investigations',json=payload().model_dump(mode='json'))
    source=tmp_path/'broken.db';storage.backup(main.DB,source);before=main.DB.read_bytes()
    with closing(sqlite3.connect(source)) as db:
        db.execute(f'ALTER TABLE {table} RENAME TO old_table')
        db.execute(f'CREATE TABLE {table}({definition})')
        db.execute(f'INSERT INTO {table} SELECT * FROM old_table');db.execute('DROP TABLE old_table');db.commit()
    with pytest.raises(sqlite3.DatabaseError):restore_backup(source,main.DB)
    assert main.DB.read_bytes()==before

@pytest.mark.parametrize('fail',[False,True])
def test_backup_temp_copy_is_removed_after_success_or_transport_error(api,fail):
    api.post('/api/investigations',json=payload().model_dump(mode='json'))
    response=main.workspace_backup();destination=Path(response.path)
    chunks=[]
    async def receive():return {'type':'http.disconnect'}
    async def send(message):
        if message['type']=='http.response.body':
            if fail:raise OSError('Injected failing transport')
            chunks.append(message.get('body',b''))
    async def run():await response({'type':'http','method':'GET','headers':[],'asgi':{'version':'3.0','spec_version':'2.4'}},receive,send)
    if fail:
        with pytest.raises(OSError):asyncio.run(run())
    else:
        asyncio.run(run());assert b''.join(chunks).startswith(b'SQLite format 3')
    assert not destination.exists() and not destination.parent.exists()

@pytest.mark.parametrize('left,right',[
    ('intron_variant&splice_region_variant','splice_region_variant&intron_variant'),
    ('intron_variant,splice_region_variant','splice_region_variant;intron_variant'),
    ('intron_variant&intron_variant','intron_variant'),
])
def test_compound_consequence_order_does_not_create_output_changes(left,right):
    supplied=payload();supplied.controlled_lookup=None
    supplied.snapshots[1]=supplied.snapshots[0].model_copy(deep=True)
    supplied.snapshots[1].id='B'
    supplied.snapshots[0].annotation.consequence=left
    supplied.snapshots[1].annotation.consequence=right
    assert not compare(supplied).differences

def test_066_archived_comparison_remains_verifiable_with_original_term_rules():
    supplied=payload();supplied.controlled_lookup=None
    supplied.snapshots[1]=supplied.snapshots[0].model_copy(deep=True);supplied.snapshots[1].id='B'
    supplied.snapshots[0].annotation.consequence='intron_variant&splice_region_variant'
    supplied.snapshots[1].annotation.consequence='splice_region_variant&intron_variant'
    old=legacy_engine_v066.compare(supplied);new=compare(supplied)
    assert old.differences and not new.differences and old.id!=new.id
    entries={'investigation':old.model_dump(mode='json')}
    assert verify_bundle({'format':'GenomeDebugger bundle','version':2,'engine_version':'0.6.6','entries':entries,'sha256':{'investigation':digest(entries['investigation'])}})[0]==old

def test_new_regression_accepts_order_only_compound_changes():
    supplied=payload();supplied.controlled_lookup=None
    for snapshot in supplied.snapshots:snapshot.annotation.consequence='intron_variant&splice_region_variant'
    case=create_case(compare(supplied),'Term sets')
    for snapshot in supplied.snapshots:snapshot.annotation.consequence='splice_region_variant&intron_variant'
    assert run_case(case,supplied).status=='passed'
