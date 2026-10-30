"""Regression coverage for the 0.7.1 audit: linked checks and atomic baselines."""
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, comparison_input
from app.models import InvestigationInput, ReferenceCheckSummary
from app.ncbi import fetch_reference_check
from app.regression import create_case, run_case
from app.report import markdown_report
from test_ncbi import ncbi_transport
from test_snpeff import record

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/transcript-switch.json'


def reference_input(path):
    source = record()
    storage.save_source_record(path, source)
    with httpx.Client(transport=ncbi_transport(base='A')) as client:
        check = fetch_reference_check(source, client)
    storage.save_reference_check(path, check)
    summary = ReferenceCheckSummary.model_validate(check.model_dump(include=set(ReferenceCheckSummary.model_fields)))
    return comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id), reference_check=summary)


@pytest.mark.parametrize('side', [0, 1])
@pytest.mark.parametrize('key,value', [('reference_check_id', 'nonexistent-check'), ('reference_check_status', 'agree')])
def test_contradictory_reference_metadata_rejected_by_api_and_bundle(tmp_path, monkeypatch, side, key, value):
    monkeypatch.setattr(main, 'DB', tmp_path/'checks.db')
    payload = reference_input(main.DB)
    api = TestClient(main.app)
    result = compare(payload).model_copy(deep=True)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    bundle = create_bundle(main.DB, result)
    payload.snapshots[side].provenance.configuration[key] = value
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 422 and 'provenance contradicts' in response.text
    assert storage.load(main.DB, compare(payload).id) is None
    case = create_case(result, 'Reference provenance')
    storage.save_case(main.DB, case)
    assert api.post(f'/api/regression-cases/{case.id}/runs', json={'candidate':payload.model_dump(mode='json')}).status_code == 422
    bundle['entries']['investigation'] = compare(payload).model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    with pytest.raises(ValueError, match='provenance contradicts'):
        verify_bundle(bundle)
    assert api.post('/api/bundles/import', json=bundle).status_code == 422


def test_reference_report_uses_actual_summary_and_allows_missing_legacy_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'legacy.db')
    payload = reference_input(main.DB)
    check_id = payload.reference_check.id
    for snapshot in payload.snapshots:
        snapshot.provenance.configuration.pop('reference_check_id')
        snapshot.provenance.configuration.pop('reference_check_status')
    result = compare(payload)
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    verify_bundle(create_bundle(main.DB, result))
    assert f'Linked NCBI allele check: `{check_id}` (disagree)' in api.get(f'/api/investigations/{result.id}/report.md').text
    # Old saved data or unvalidated drafts can still contain contradictory flags.
    for snapshot in result.input.snapshots:
        snapshot.provenance.configuration.update(reference_check_id='nonexistent-check', reference_check_status='agree')
    report = markdown_report(result)
    assert f'Linked NCBI allele check: `{check_id}` (disagree)' in report
    assert 'Linked NCBI allele check: `nonexistent-check`' not in report


def test_dangling_reference_flags_cannot_claim_a_check(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'dangling.db')
    payload = reference_input(main.DB)
    payload.reference_check = None
    response = TestClient(main.app).post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 422 and 'provenance contradicts' in response.text
    assert 'Linked NCBI allele check:' not in markdown_report(compare(payload))


def test_case_save_crossing_deletion_does_not_leave_an_orphan(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'delete.db')
    result = compare(InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8')))
    storage.save(main.DB, result)
    entered, release = threading.Event(), threading.Event()
    original = main.create_case
    def delayed(*args):
        case = original(*args)
        entered.set()
        assert release.wait(10)
        return case
    monkeypatch.setattr(main, 'create_case', delayed)
    with TestClient(main.app) as api, ThreadPoolExecutor(1) as pool:
        future = pool.submit(api.post, f'/api/investigations/{result.id}/regression-cases', json={'name':'Late case'})
        try:
            assert entered.wait(10)
            assert api.delete(f'/api/investigations/{result.id}').status_code == 200
        finally:
            release.set()
        response = future.result(10)
        assert response.status_code == 404 and 'was not saved' in response.text
        assert storage.list_cases(main.DB) == []
        assert api.get(f'/api/investigations/{result.id}').status_code == 404


def test_case_and_run_require_matching_parents_and_are_immutable(tmp_path):
    path = tmp_path/'parents.db'
    result = compare(InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8')))
    case = create_case(result, 'Pinned case')
    with pytest.raises(storage.RecordMissingError):
        storage.save_case(path, case)
    storage.save(path, result)
    wrong = case.model_copy(deep=True)
    wrong.source_investigation.input_sha256 = '0'*64
    with pytest.raises(storage.RecordConflictError):
        storage.save_case(path, wrong)
    storage.save_case(path, case)
    storage.save_case(path, case)
    with pytest.raises(ValueError, match='pinned'):
        storage.delete_investigation(path, result.id)
    with pytest.raises(storage.RecordConflictError):
        storage.save_case(path, case.model_copy(update={'name':'Changed'}))
    run = run_case(case)
    with pytest.raises(storage.RecordMissingError):
        storage.save_run(path, run.model_copy(update={'case_id':'missing'}))
    with pytest.raises(storage.RecordConflictError):
        storage.save_run(path, run.model_copy(update={'baseline_input_sha256':'0'*64}))
    storage.save_run(path, run)
    storage.save_run(path, run)
    assert len(storage.list_runs(path, case.id)) == 1


def used_bytes(path):
    with closing(sqlite3.connect(path)) as db:
        return (db.execute('PRAGMA page_count').fetchone()[0] - db.execute('PRAGMA freelist_count').fetchone()[0]) * db.execute('PRAGMA page_size').fetchone()[0]


@pytest.mark.parametrize('kind', ['case', 'run'])
def test_concurrent_regression_saves_respect_quota(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(main, 'DB', tmp_path/'quota.db')
    monkeypatch.setenv('GENOMEDEBUGGER_MAX_DB_MB', '10')
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8'))
    payload.controlled_lookup = None
    for snapshot in payload.snapshots:
        snapshot.annotation.protein_consequence = 'X'*300000
    result = compare(payload)
    storage.save(main.DB, result)
    case = create_case(result, 'Concurrent baseline')
    if kind == 'case':
        url, body, incoming = f'/api/investigations/{result.id}/regression-cases', {'name':case.name}, case
    else:
        storage.save_case(main.DB, case)
        url, body, incoming = f'/api/regression-cases/{case.id}/runs', {}, run_case(case)
    limit = 10*1024*1024
    filler = limit - used_bytes(main.DB) - int(len(incoming.model_dump_json().encode())*1.6)
    assert filler > 0
    with closing(sqlite3.connect(main.DB)) as db:
        db.execute('CREATE TABLE audit_padding (data BLOB)')
        db.execute('INSERT INTO audit_padding VALUES (zeroblob(?))', (filler,))
        db.commit()
    started, release = threading.Event(), threading.Event()
    original = storage._guard_size
    def delayed(path, text, *args):
        original(path, text, *args)
        if not started.is_set():
            started.set()
            assert release.wait(10)
    monkeypatch.setattr(storage, '_guard_size', delayed)
    with TestClient(main.app) as api, ThreadPoolExecutor(2) as pool:
        first = pool.submit(api.post, url, json=body)
        try:
            assert started.wait(10)
            second = pool.submit(api.post, url, json=body)
            # Allow an unguarded second save to finish if it can. With the fix
            # it waits for the first write transaction before checking capacity.
            try:
                second.result(timeout=0.25)
            except TimeoutError:
                pass
        finally:
            release.set()
        assert sorted([first.result(10).status_code, second.result(10).status_code]) == [200, 507]
    assert used_bytes(main.DB) <= limit
    saved = storage.list_cases(main.DB) if kind == 'case' else storage.list_runs(main.DB, case.id)
    assert len(saved) == 1


def test_sqlite_growth_beyond_quota_rolls_back_the_whole_save(tmp_path, monkeypatch):
    path = tmp_path/'pages.db'
    monkeypatch.setenv('GENOMEDEBUGGER_MAX_DB_MB', '10')
    storage.initialize(path)
    limit = 10*1024*1024
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE audit_padding (data BLOB)')
        db.execute('INSERT INTO audit_padding VALUES (zeroblob(?))', (limit - used_bytes(path) - 30000,))
        db.execute('CREATE TRIGGER audit_growth AFTER INSERT ON investigations BEGIN '
                   'INSERT INTO audit_padding VALUES (zeroblob(50000)); END')
        db.commit()
    # Exercise real SQLite write amplification beyond the serialized record:
    # trigger growth must be counted and rolled back with the investigation.
    before = used_bytes(path)
    result = compare(InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8')))
    assert before + len(result.model_dump_json().encode()) < limit
    with pytest.raises(storage.StorageLimitError):
        storage.save(path, result)
    assert storage.list_items(path) == []
    assert used_bytes(path) == before
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM audit_padding').fetchone()[0] == 1
