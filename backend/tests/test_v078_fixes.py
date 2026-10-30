"""Regression coverage for the thirteen findings in the 0.7.7 audit."""
import copy
import json
import sqlite3
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, SourceError, comparison_input, fetch_record
from app.historical import import_historical
from app.legacy_engine_v064 import compare as compare_v064
from app.models import Annotation, InvestigationInput
from app.ncbi import fetch_reference_check
from app.regression import create_case, run_case
from app.version import ENGINE_VERSION
from test_historical import request as historical_request
from test_ncbi import ncbi_transport
from test_regression import baseline
from test_snpeff import QUERY, record


@pytest.mark.parametrize('historical', [False, True])
@pytest.mark.parametrize('key,value', [
    ('assembly_accession', 'GCA_000001405.14'),
    ('retrieved_at', '1999-01-01T00:00:00Z'),
    ('generated_at', '1999-01-01T00:00:00Z'),
    ('artifact_sha256', '0' * 64),
])
def test_source_metadata_must_match_in_api_candidates_and_bundles(tmp_path, monkeypatch, historical, key, value):
    monkeypatch.setattr(main, 'DB', tmp_path / 'sources.db')
    source = record()
    if historical:
        source = import_historical(historical_request(source))
    storage.save_source_record(main.DB, source)
    payload = comparison_input(source, CompareTranscripts(
        transcript_a=source.transcripts[0].transcript_id, transcript_b=source.transcripts[1].transcript_id))
    original = compare(payload)
    storage.save(main.DB, original)
    case = create_case(original, 'Source consistency')
    storage.save_case(main.DB, case)
    bundle = create_bundle(main.DB, original)
    payload = payload.model_copy(deep=True)
    for snapshot in payload.snapshots:
        snapshot.provenance.configuration[key] = value
    api = TestClient(main.app)
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 422 and key in response.text
    assert api.post(f'/api/regression-cases/{case.id}/runs', json={'candidate': payload.model_dump(mode='json')}).status_code == 422
    bundle['entries']['investigation'] = compare(payload).model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    assert api.post('/api/bundles/verify', json=bundle).status_code == 422
    assert api.post('/api/bundles/import', json=bundle).status_code == 422
    assert storage.load(main.DB, original.id) == original
    assert storage.load(main.DB, compare(payload).id) is None


@pytest.mark.parametrize('historical', [False, True])
def test_omitted_legacy_metadata_and_explicit_custom_outputs_remain_supported(tmp_path, monkeypatch, historical):
    monkeypatch.setattr(main, 'DB', tmp_path / 'legacy.db')
    source = record()
    if historical:
        source = import_historical(historical_request(source))
    storage.save_source_record(main.DB, source)
    payload = comparison_input(source, CompareTranscripts(
        transcript_a=source.transcripts[0].transcript_id, transcript_b=source.transcripts[1].transcript_id))
    for snapshot in payload.snapshots:
        for key in ('assembly_accession', 'retrieved_at', 'generated_at', 'artifact_sha256'):
            snapshot.provenance.configuration.pop(key, None)
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    verify_bundle(create_bundle(main.DB, compare(payload)))
    for snapshot in payload.snapshots:
        snapshot.provenance.tool = 'Custom transformed output'
        snapshot.provenance.configuration['retrieved_at'] = '1999-01-01T00:00:00Z'
        snapshot.annotation.consequence = 'missense_variant'
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    verify_bundle(create_bundle(main.DB, compare(payload)))


def test_reimport_returns_the_actual_preserved_capture_time(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'reimport.db')
    payload = historical_request(record()).model_dump(mode='json')
    api = TestClient(main.app)
    first = api.post('/api/sources/historical-vep', json=payload).json()
    second = api.post('/api/sources/historical-vep', json=payload).json()
    assert first == second
    assert api.get('/api/sources/ensembl/records/' + first['id']).json() == second


@pytest.mark.parametrize('key', ['consequence', 'priority.consequence'])
def test_configuration_order_is_exact_and_candidate_assertions_detect_its_change(tmp_path, monkeypatch, key):
    monkeypatch.setattr(main, 'DB', tmp_path / 'configuration.db')
    payload = baseline().input.model_copy(deep=True)
    payload.controlled_lookup = None
    payload.snapshots[1] = payload.snapshots[0].model_copy(deep=True)
    payload.snapshots[1].id = 'other'
    payload.snapshots[0].provenance.configuration = {key: 'high;moderate;low'}
    payload.snapshots[1].provenance.configuration = {key: 'low;moderate;high'}
    result = compare(payload)
    assert [(d.field, d.category) for d in result.differences] == [(f'configuration.{key}', 'configuration')]
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    candidate = payload.model_copy(deep=True)
    candidate.snapshots[0].provenance.configuration[key] = 'moderate;high;low'
    run = run_case(create_case(result, 'Ordered configuration'), candidate)
    assert run.status == 'failed'
    assert any(not check.passed and check.path == f'differences.configuration.{key}' for check in run.checks)
    verify_bundle(create_bundle(main.DB, result))


def test_additional_output_finding_links_only_its_affected_fields():
    payload = baseline().input.model_copy(deep=True)
    payload.controlled_lookup = None
    payload.snapshots[1].annotation = payload.snapshots[0].annotation.model_copy(deep=True)
    for index, snapshot in enumerate(payload.snapshots):
        snapshot.annotations = [Annotation(gene_id='GENE-DEMO-1', transcript_id='TX-EXTRA',
            consequence='intron_variant', protein_consequence=f'p.Change{index}')]
    result = compare(payload)
    finding = next(f for f in result.findings if f.cause == 'unexplained change')
    assert finding.affected_fields == ['annotations[GENE-DEMO-1|TX-EXTRA||].protein_consequence']
    evidence = {item.id: item for item in result.evidence}
    assert [evidence[id_].data['field'] for id_ in finding.evidence_ids] == finding.affected_fields


@pytest.mark.parametrize('number', ['1e400', '-1e400', 'NaN', 'Infinity', '-Infinity'])
def test_historical_nonfinite_numbers_are_rejected_before_storage(tmp_path, monkeypatch, number):
    monkeypatch.setattr(main, 'DB', tmp_path / 'numbers.db')
    source = record()
    payload = historical_request(source).model_dump(mode='json')
    raw = copy.deepcopy(source.source_response)
    payload['raw_json'] = json.dumps(raw)[:-1] + ',"extension":' + number + '}'
    response = TestClient(main.app, raise_server_exceptions=False).post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 422 and 'finite' in response.text
    assert storage.list_source_records(main.DB) == []


def test_finite_numeric_metadata_preserves_artifact_and_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'finite.db')
    source = record()
    payload = historical_request(source).model_dump(mode='json')
    raw = copy.deepcopy(source.source_response)
    raw['extension'] = {'number': 1e30, 'small': 1e-30, 'integer': 123456789012345678901234567890}
    payload['raw_json'] = json.dumps(raw)
    api = TestClient(main.app)
    response = api.post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['artifact']['text'] == payload['raw_json']
    assert saved['source_response']['extension'] == raw['extension']
    compared = api.post('/api/sources/compare', json={'source_a': saved['id'], 'source_b': saved['id'],
        'transcript_a': source.transcripts[0].transcript_id, 'transcript_b': source.transcripts[1].transcript_id})
    assert compared.status_code == 200
    bundle = api.get('/api/investigations/' + compared.json()['id'] + '/bundle')
    assert bundle.status_code == 200, bundle.text
    assert api.post('/api/bundles/verify', json=bundle.json()).status_code == 200


@pytest.mark.parametrize('fault', ['rows', 'transcript', 'gene', 'terms'])
def test_unusable_transcript_data_is_rejected_on_historical_and_current_admission(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(main, 'DB', tmp_path / 'limits.db')
    source = record()
    raw = copy.deepcopy(source.source_response)
    if fault == 'rows':
        raw['transcript_consequences'] = [dict(raw['transcript_consequences'][0], transcript_id=f'TX{i:04d}') for i in range(1002)]
    elif fault == 'transcript': raw['transcript_consequences'][0]['transcript_id'] = 'T' * 101
    elif fault == 'gene': raw['transcript_consequences'][0]['gene_id'] = 'G' * 101
    else: raw['transcript_consequences'][0]['consequence_terms'] = ['a' * 250, 'b' * 250]
    payload = historical_request(source).model_dump(mode='json')
    payload['raw_json'] = json.dumps(raw, separators=(',', ':'))
    assert len(payload['raw_json'].encode()) < 250000
    response = TestClient(main.app).post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 422
    assert storage.list_source_records(main.DB) == []
    from test_ensembl import fixture_transport
    base = fixture_transport()
    def upstream(request):
        if request.url.path.startswith('/vep/'):
            return httpx.Response(200, json=[raw])
        return base.handle_request(request)
    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        with pytest.raises(SourceError): fetch_record(QUERY, client)


def test_maximum_supported_transcript_set_can_be_compared_and_exported(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'maximum.db')
    source = record()
    raw = copy.deepcopy(source.source_response)
    raw['transcript_consequences'] = [dict(raw['transcript_consequences'][0], transcript_id=f'TX{i:04d}') for i in range(1001)]
    payload = historical_request(source).model_dump(mode='json')
    payload['raw_json'] = json.dumps(raw, separators=(',', ':'))
    api = TestClient(main.app)
    response = api.post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 200, response.text
    source_id = response.json()['id']
    response = api.post('/api/sources/compare', json={'source_a': source_id, 'source_b': source_id,
        'transcript_a': 'TX0000', 'transcript_b': 'TX0001'})
    assert response.status_code == 200, response.text
    assert len(response.json()['input']['snapshots'][0]['annotations']) == 1000
    assert api.get('/api/investigations/' + response.json()['id'] + '/bundle').status_code == 200


@pytest.mark.parametrize('cached', [False, True])
@pytest.mark.parametrize('bad', ['unicode', 'number'])
def test_invalid_ncbi_json_uses_provider_error_and_available_cache(tmp_path, monkeypatch, cached, bad):
    monkeypatch.setattr(main, 'DB', tmp_path / 'ncbi.db')
    source = record()
    storage.save_source_record(main.DB, source)
    if cached:
        with httpx.Client(transport=ncbi_transport()) as client:
            previous = fetch_reference_check(source, client)
        storage.save_reference_check(main.DB, previous)
    base = ncbi_transport()
    def upstream(request):
        response = base.handle_request(request)
        if request.url.path.endswith('/hgvs'):
            body = response.json()
            body['extension'] = '\ud800' if bad == 'unicode' else float('inf')
            return httpx.Response(200, content=json.dumps(body).encode(), headers={'content-type': 'application/json'})
        return response
    def fetch(source):
        with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
            return fetch_reference_check(source, client)
    monkeypatch.setattr(main, 'fetch_reference_check', fetch)
    response = TestClient(main.app, raise_server_exceptions=False).post(
        f'/api/sources/ensembl/records/{source.id}/reference-check', json={'mode': 'fetch'})
    assert response.status_code == (200 if cached else 502)
    if cached:
        assert response.json()['access'] == 'cached_after_error'
        assert response.json()['check']['id'] == previous.id
    else:
        assert 'NCBI returned invalid' in response.json()['detail']


def small_input(index):
    snapshot = {'id': 'a', 'label': 'x', 'variant': {'assembly': 'GRCh38', 'sequence_id': '1',
        'position': 1, 'ref': 'A', 'alt': 'T', 'reference_context': {'start': 1, 'sequence': 'A'}},
        'annotation': {'gene_id': 'G', 'transcript_id': 'T', 'consequence': 'intron_variant'},
        'provenance': {'tool': 'x', 'tool_version': 'x', 'source_name': 'x', 'source_release': 'x'}}
    return InvestigationInput.model_validate({'title': f'Cell reuse {index:05d}',
        'snapshots': [snapshot, dict(snapshot, id='b')]})


def allocation(path):
    with closing(sqlite3.connect(path)) as db:
        return (db.execute('PRAGMA page_count').fetchone()[0] - db.execute('PRAGMA freelist_count').fetchone()[0]) * db.execute('PRAGMA page_size').fetchone()[0]


def test_quota_allows_reusing_cells_without_allocating_new_pages(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOMEDEBUGGER_MAX_DB_MB', '10')
    monkeypatch.setattr(main, 'DB', tmp_path / 'cells.db')
    results = [compare(small_input(i)) for i in range(20)]
    storage._save_records(main.DB, results)
    limit = 10 * 1024 * 1024
    with closing(sqlite3.connect(main.DB)) as db:
        db.execute('CREATE TABLE padding (data BLOB)')
        size = limit - allocation(main.DB) - 100000
        db.execute('INSERT INTO padding VALUES (zeroblob(?))', (size,))
        db.commit()
        for _ in range(6):
            delta = limit - allocation(main.DB)
            if not delta: break
            size += delta
            db.execute('UPDATE padding SET data=zeroblob(?)', (size,))
            db.commit()
    assert allocation(main.DB) == limit
    api = TestClient(main.app)
    for result in reversed(results[-4:]):
        assert api.delete('/api/investigations/' + result.id).status_code == 200
        after_delete = allocation(main.DB)
        response = api.post('/api/investigations', json=result.input.model_dump(mode='json'))
        assert response.status_code == 200, response.text
        assert allocation(main.DB) <= limit
        if after_delete == limit:
            assert allocation(main.DB) == limit
            break
    else:
        pytest.fail('Fixture did not exercise a deletion that frees cells without a whole page')


@pytest.mark.parametrize('version', [0, 1])
def test_existing_records_migrate_without_rewriting_bytes_or_reusing_cursors(tmp_path, monkeypatch, version):
    path = tmp_path / 'old.db'
    originals = [compare_v064(small_input(i)) for i in range(3)]
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE investigations (id TEXT PRIMARY KEY, title TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT)')
        for rowid, result in zip((3, 8, 12), originals):
            db.execute('INSERT INTO investigations (rowid,id,title,result_json,created_at) VALUES (?,?,?,?,?)',
                (rowid, result.id, result.input.title, result.model_dump_json(), '2026-01-01T00:00:00Z'))
        db.execute(f'PRAGMA user_version = {version}')
        db.commit()
    monkeypatch.setattr(main, 'DB', path)
    api = TestClient(main.app)
    first = api.get('/api/investigations/page', params={'limit': 2}).json()
    assert first['ceiling'] == 12
    for result in originals: assert storage.load(path, result.id) == result
    with closing(sqlite3.connect(path)) as db:
        for result in originals:
            assert db.execute('SELECT result_json,created_at FROM investigations WHERE id=?', (result.id,)).fetchone() == (result.model_dump_json(), '2026-01-01T00:00:00Z')
    assert api.delete('/api/investigations/' + originals[-1].id).status_code == 200
    new = api.post('/api/investigations', json=small_input(20).model_dump(mode='json')).json()
    old_page = api.get('/api/investigations/page', params={'limit': 2, 'ceiling': first['ceiling']}).json()
    assert new['id'] not in {row['id'] for row in old_page['items']}
    assert api.get('/api/investigations/page').json()['ceiling'] > first['ceiling']
    for row in api.get('/api/investigations').json(): assert api.delete('/api/investigations/' + row['id']).status_code == 200
    newer = api.post('/api/investigations', json=small_input(21).model_dump(mode='json')).json()
    assert api.get('/api/investigations/page').json()['ceiling'] > first['ceiling']
    assert api.get('/api/investigations/page', params={'ceiling': first['ceiling']}).json()['items'] == []
    assert storage.load(path, newer['id']) is not None


def test_unicode_casefold_search_remains_literal_and_paginated(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'search.db')
    api = TestClient(main.app)
    names = ['Café export', 'CAFÉ export', 'Straße export', 'STRASSE export', 'Café_100% export', 'CAFÉx100y export']
    for i, name in enumerate(names):
        raw = small_input(i).model_dump(mode='json')
        raw['title'] = name
        assert api.post('/api/investigations', json=raw).status_code == 200
    assert {row['title'] for row in api.get('/api/investigations', params={'q': 'café'}).json()} == {names[i] for i in (0, 1, 4, 5)}
    first = api.get('/api/investigations/page', params={'q': 'straße', 'limit': 1}).json()
    second = api.get('/api/investigations/page', params={'q': 'straße', 'limit': 1, 'ceiling': first['ceiling'], 'before': first['next_before']}).json()
    assert {row['title'] for row in first['items'] + second['items']} == set(names[2:4])
    assert [row['title'] for row in api.get('/api/investigations/page', params={'q': 'CAFÉ_100%'}).json()['items']] == [names[4]]


def test_frozen_v064_bundle_replays_and_exports_as_separate_current_result(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'archive.db')
    payload = baseline().input.model_copy(deep=True)
    payload.controlled_lookup = None
    payload.snapshots[1] = payload.snapshots[0].model_copy(deep=True)
    payload.snapshots[1].id = 'b'
    payload.snapshots[0].provenance.configuration['consequence'] = 'a;b'
    payload.snapshots[1].provenance.configuration['consequence'] = 'b;a'
    original = compare_v064(payload)
    assert original.engine_version == '0.6.4' and not original.differences
    entries = {'investigation': original.model_dump(mode='json')}
    bundle = {'format': 'GenomeDebugger bundle', 'version': 2, 'engine_version': '0.6.4',
        'entries': entries, 'sha256': {key: digest(value) for key, value in entries.items()}}
    assert verify_bundle(bundle)[0] == original
    api = TestClient(main.app)
    assert api.post('/api/bundles/import', json=bundle).status_code == 200
    exported = api.get('/api/investigations/' + original.id + '/bundle').json()
    assert exported['engine_version'] == ENGINE_VERSION
    assert exported['replayed_from_id'] == original.id
    assert exported['entries']['investigation']['differences'][0]['field'] == 'configuration.consequence'
    assert exported['entries']['investigation']['id'] != original.id
    verify_bundle(exported)
    assert storage.load(main.DB, original.id) == original
