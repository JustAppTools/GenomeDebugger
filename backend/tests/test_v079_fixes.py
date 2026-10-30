"""Regression coverage for the eight findings in the application 0.7.8 audit."""
import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage, snpeff_runner
from app.bundle import _verify_snpeff, create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, SourceRecord, comparison_input, fetch_record
from app.json_text import parse_json
from app.models import AnnotationCheckSummary
from app.ncbi import fetch_reference_check
from app.unicode_text import MAX_JSON_DEPTH
from test_ensembl import fixture_transport
from test_historical import request as historical_request
from test_ncbi import ncbi_transport
from test_regression import baseline
from test_snpeff import QUERY, VCF, record
from test_snpeff_runner import install_fixture

ROOT = Path(__file__).resolve().parents[2]


def source_bundle(source):
    payload = comparison_input(source, CompareTranscripts(
        transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id))
    result = compare(payload)
    entries = {'investigation': result.model_dump(mode='json'), 'source_record': source.model_dump(mode='json')}
    return {'format': 'GenomeDebugger bundle', 'version': 2, 'engine_version': result.engine_version,
        'entries': entries, 'sha256': {key: digest(value) for key, value in entries.items()}}


@pytest.mark.parametrize('name', ['GRCh37', 'GRCh38.p0', ''])
def test_contradictory_source_envelope_cannot_verify_or_enter_cache(tmp_path, monkeypatch, name):
    monkeypatch.setattr(main, 'DB', tmp_path / 'assembly.db')
    bundle = source_bundle(record())
    bundle['entries']['source_record']['assembly_name'] = name
    bundle['sha256']['source_record'] = digest(bundle['entries']['source_record'])
    api = TestClient(main.app)
    for route in ('verify', 'import'):
        response = api.post('/api/bundles/' + route, json=bundle)
        assert response.status_code == 422 and 'assembly' in response.text.lower()
    assert storage.list_source_records(main.DB) == []
    assert storage.list_items(main.DB) == []


@pytest.mark.parametrize('name', ['GRCh38', 'GRCh38.p14'])
def test_supported_base_and_patch_names_keep_valid_bundles_compatible(tmp_path, monkeypatch, name):
    monkeypatch.setattr(main, 'DB', tmp_path / 'valid.db')
    source = record()
    source.assembly_name = name
    bundle = source_bundle(source)
    api = TestClient(main.app)
    assert api.post('/api/bundles/verify', json=bundle).status_code == 200
    assert api.post('/api/bundles/import', json=bundle).status_code == 200
    cached = api.post('/api/sources/ensembl/lookup', json={'query': source.query.model_dump(), 'mode': 'cache_only'})
    assert cached.status_code == 200 and cached.json()['record']['assembly_name'] == name
    exported = api.get('/api/investigations/' + bundle['entries']['investigation']['id'] + '/bundle')
    assert exported.status_code == 200
    verify_bundle(exported.json())


def test_invalid_legacy_cache_is_not_used_but_is_not_rewritten(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'legacy.db')
    invalid = record()
    invalid.assembly_name = 'GRCh37'
    storage.save_source_record(main.DB, invalid)  # Simulate an older admitted record.
    api = TestClient(main.app)
    response = api.post('/api/sources/ensembl/lookup', json={'query': invalid.query.model_dump(), 'mode': 'cache_only'})
    assert response.status_code == 422 and 'Cached source metadata is inconsistent' in response.text
    valid = record()
    monkeypatch.setattr(main, 'fetch_record', lambda _: valid)
    response = api.post('/api/sources/ensembl/lookup', json={'query': invalid.query.model_dump(), 'mode': 'fetch'})
    assert response.status_code == 200 and response.json()['access'] == 'fetched'
    assert response.json()['record']['id'] == valid.id
    assert storage.load_source_record(main.DB, invalid.id) == invalid


@pytest.mark.parametrize('cached', [False, True])
def test_live_assembly_contradiction_is_a_provider_error_with_safe_fallback(tmp_path, monkeypatch, cached):
    monkeypatch.setattr(main, 'DB', tmp_path / 'provider.db')
    source = record()
    if cached: storage.save_source_record(main.DB, source)
    base = fixture_transport()
    def handler(request):
        response = base.handle_request(request)
        if request.url.path == '/info/assembly/human':
            body = response.json()
            body['assembly_name'] = 'GRCh37'
            return httpx.Response(200, json=body)
        return response
    def fetch(query):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_record(query, client)
    monkeypatch.setattr(main, 'fetch_record', fetch)
    response = TestClient(main.app).post('/api/sources/ensembl/lookup', json={'query': source.query.model_dump(), 'mode': 'fetch'})
    assert response.status_code == (200 if cached else 502)
    if cached:
        assert response.json()['access'] == 'cached_after_error'
        assert response.json()['record']['id'] == source.id
    assert len(storage.list_source_records(main.DB)) == int(cached)


@pytest.mark.parametrize('depth', [MAX_JSON_DEPTH + 1, 1100])
def test_json_depth_errors_are_bounded_validation_failures(depth):
    text = '[' * depth + '0' + ']' * depth
    with pytest.raises(ValueError, match='JSON nesting'):
        parse_json(text)
    parse_json('[' * MAX_JSON_DEPTH + '0' + ']' * MAX_JSON_DEPTH)


@pytest.mark.parametrize('depth', [70, 1100])
def test_historical_depth_errors_do_not_save_partial_records(tmp_path, monkeypatch, depth):
    monkeypatch.setattr(main, 'DB', tmp_path / 'historical.db')
    source = record()
    payload = historical_request(source).model_dump(mode='json')
    payload['raw_json'] = json.dumps(source.source_response)[:-1] + ',"extension":' + '[' * depth + '0' + ']' * depth + '}'
    response = TestClient(main.app, raise_server_exceptions=False).post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 422 and 'JSON nesting' in response.text
    assert len(response.content) < 1000
    assert storage.list_source_records(main.DB) == []


def test_supported_nested_metadata_survives_model_and_bundle_envelopes(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'nested.db')
    source = record()
    raw = copy.deepcopy(source.source_response)
    value = {'label': 'nested finite metadata 🧬'}
    for _ in range(59): value = [value]
    raw['extension'] = value
    payload = historical_request(source).model_dump(mode='json')
    payload['raw_json'] = json.dumps(raw)
    api = TestClient(main.app)
    response = api.post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 200, response.text
    source_id = response.json()['id']
    compared = api.post('/api/sources/compare', json={'source_a': source_id, 'source_b': source_id,
        'transcript_a': source.transcripts[0].transcript_id, 'transcript_b': source.transcripts[1].transcript_id})
    assert compared.status_code == 200
    bundle = api.get('/api/investigations/' + compared.json()['id'] + '/bundle')
    assert bundle.status_code == 200, bundle.text
    assert api.post('/api/bundles/verify', json=bundle.json()).status_code == 200
    assert api.post('/api/bundles/import', json=bundle.json()).status_code == 200


@pytest.mark.parametrize('cached', [False, True])
def test_ensembl_parser_depth_failure_uses_provider_fallback(tmp_path, monkeypatch, cached):
    monkeypatch.setattr(main, 'DB', tmp_path / 'ensembl.db')
    source = record()
    if cached: storage.save_source_record(main.DB, source)
    raw = '[' + json.dumps(source.source_response)[:-1] + ',"extension":' + '[' * 1100 + '0' + ']' * 1100 + '}]'
    base = fixture_transport()
    def handler(request):
        if request.url.path.startswith('/vep/'):
            return httpx.Response(200, content=raw.encode(), headers={'content-type': 'application/json'})
        return base.handle_request(request)
    def fetch(query):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_record(query, client)
    monkeypatch.setattr(main, 'fetch_record', fetch)
    response = TestClient(main.app, raise_server_exceptions=False).post('/api/sources/ensembl/lookup',
        json={'query': source.query.model_dump(), 'mode': 'fetch'})
    assert response.status_code == (200 if cached else 502)
    if cached:
        assert response.json()['access'] == 'cached_after_error'
        assert response.json()['record']['id'] == source.id


@pytest.mark.parametrize('cached', [False, True])
def test_ncbi_parser_depth_failure_uses_provider_fallback(tmp_path, monkeypatch, cached):
    monkeypatch.setattr(main, 'DB', tmp_path / 'ncbi.db')
    source = record()
    storage.save_source_record(main.DB, source)
    if cached:
        with httpx.Client(transport=ncbi_transport()) as client:
            previous = fetch_reference_check(source, client)
        storage.save_reference_check(main.DB, previous)
    base = ncbi_transport()
    def handler(request):
        response = base.handle_request(request)
        if request.url.path.endswith('/hgvs'):
            raw = json.dumps(response.json())[:-1] + ',"extension":' + '[' * 1100 + '0' + ']' * 1100 + '}'
            return httpx.Response(200, content=raw.encode(), headers={'content-type': 'application/json'})
        return response
    def fetch(record):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_reference_check(record, client)
    monkeypatch.setattr(main, 'fetch_reference_check', fetch)
    response = TestClient(main.app, raise_server_exceptions=False).post(
        f'/api/sources/ensembl/records/{source.id}/reference-check', json={'mode': 'fetch'})
    assert response.status_code == (200 if cached else 502)
    if cached:
        assert response.json()['access'] == 'cached_after_error'
        assert response.json()['check']['id'] == previous.id


def test_initialized_reads_succeed_while_a_write_transaction_is_held(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'concurrent.db')
    seed = baseline()
    storage.save(main.DB, seed)
    payload = seed.input.model_copy(deep=True)
    payload.title = 'Pending concurrent save'
    expected = compare(payload)
    entered, release = threading.Event(), threading.Event()
    original = storage._insert_entry
    def held(db, table, values):
        if table == 'investigations' and values[0] == expected.id:
            entered.set()
            assert release.wait(10)
        original(db, table, values)
    monkeypatch.setattr(storage, '_insert_entry', held)
    with TestClient(main.app) as api, ThreadPoolExecutor(3) as pool:
        pending = pool.submit(api.post, '/api/investigations', json=payload.model_dump(mode='json'))
        assert entered.wait(5)
        try:
            health = pool.submit(api.get, '/api/health')
            page = pool.submit(api.get, '/api/investigations/page')
            assert health.result(2).status_code == 200
            response = page.result(2)
            assert response.status_code == 200
            assert [item['id'] for item in response.json()['items']] == [seed.id]
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(5).status_code == 200
        assert len(api.get('/api/investigations/page').json()['items']) == 2


def test_concurrent_cold_initialization_and_migration_remain_atomic(tmp_path):
    path = tmp_path / 'cold.db'
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: storage.initialize(path), range(12)))
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT COUNT(*) FROM investigation_order').fetchone()[0] == 0
    storage.save(path, baseline())
    assert len(storage.list_items(path)) == 1


def capture_bytes(monkeypatch, stdout, stderr):
    original = subprocess.run
    code = 'import sys;sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]));sys.stderr.buffer.write(bytes.fromhex(sys.argv[2]))'
    def run(_command, **kwargs):
        return original([sys.executable, '-c', code, stdout.hex(), stderr.hex()], **kwargs)
    monkeypatch.setattr(snpeff_runner.subprocess, 'run', run)


@pytest.mark.parametrize('ending', ['\n', '\r\n'])
def test_runner_preserves_exact_stdout_and_diagnostic_bytes(tmp_path, monkeypatch, ending):
    install_fixture(tmp_path, monkeypatch)
    source = record()
    stdout = ('##known output' + ending + VCF + ending).encode('utf-8')
    stderr = ('Diagnostics 🧬' + ending).encode('utf-8')
    capture_bytes(monkeypatch, stdout, stderr)
    check = snpeff_runner.run_snpeff(source)
    assert check.status == 'agree'
    assert check.vcf_text.encode('utf-8') == stdout
    assert check.execution.capture_format == 'utf8_bytes'
    assert check.vcf_sha256 == check.execution.output_vcf_sha256 == hashlib.sha256(stdout).hexdigest()
    assert check.execution.stderr.encode('utf-8') == stderr
    assert check.execution.stderr_sha256 == hashlib.sha256(stderr).hexdigest()
    _verify_snpeff(source, check)
    changed = check.model_copy(deep=True)
    changed.execution.stderr += 'changed'
    with pytest.raises(ValueError, match='stderr'):
        _verify_snpeff(source, changed)


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_invalid_runner_utf8_is_rejected_without_saving_a_check(tmp_path, monkeypatch, stream):
    install_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(main, 'DB', tmp_path / 'runner.db')
    source = record()
    storage.save_source_record(main.DB, source)
    stdout = VCF.encode('utf-8')
    stderr = b''
    if stream == 'stdout': stdout = b'##bad\xff\n' + stdout
    else: stderr = b'bad\xff'
    capture_bytes(monkeypatch, stdout, stderr)
    response = TestClient(main.app).post(f'/api/sources/ensembl/records/{source.id}/snpeff-run')
    assert response.status_code == 422 and 'valid UTF-8' in response.text
    assert storage.latest_snpeff_check(main.DB, source.id) is None


def test_legacy_execution_records_verify_and_import_without_rewriting_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'legacy-execution.db')
    fixture = json.loads((ROOT / 'fixtures/snpeff-mane-public-run.json').read_text(encoding='utf-8'))
    source = SourceRecord.model_validate(fixture['source'])
    raw_check = copy.deepcopy(fixture['check'])
    raw_check['execution'].pop('capture_format', None)
    raw_check['execution'].pop('stderr_sha256', None)
    original = json.dumps(raw_check)
    storage.save_source_record(main.DB, source)
    with closing(sqlite3.connect(main.DB)) as db:
        db.execute('INSERT INTO snpeff_checks VALUES (?,?,?,?)',
            (raw_check['id'], source.id, raw_check['checked_at'], original))
        db.commit()
    check = storage.load_snpeff_check(main.DB, raw_check['id'])
    assert check.execution.capture_format == 'legacy_text'
    assert check.execution.stderr_sha256 is None
    _verify_snpeff(source, check)
    fields = set(AnnotationCheckSummary.model_fields) - {'matched_transcripts'}
    summary = AnnotationCheckSummary.model_validate({**check.model_dump(include=fields), 'matched_transcripts': len(check.matches)})
    payload = comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id), annotation_check=summary)
    bundle = create_bundle(main.DB, compare(payload))
    bundle['entries']['snpeff_check'] = raw_check
    bundle['sha256']['snpeff_check'] = digest(raw_check)
    api = TestClient(main.app)
    assert api.post('/api/bundles/verify', json=bundle).status_code == 200
    assert api.post('/api/bundles/import', json=bundle).status_code == 200
    with closing(sqlite3.connect(main.DB)) as db:
        assert db.execute('SELECT check_json FROM snpeff_checks WHERE id=?', (check.id,)).fetchone()[0] == original
