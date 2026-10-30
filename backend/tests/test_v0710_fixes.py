"""Regression coverage for the eight findings in the 0.7.9 audit."""
import copy
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, SourceQuery, SourceRecord, comparison_input, fetch_record
from app.models import AnnotationCheckSummary
from app.ncbi import _sha, fetch_reference_check
from app.regression import create_case
from app.snpeff import SnpEffCheck, SnpEffCheckRequest, compare_snpeff, validate_execution_metadata
from test_ensembl import fixture_transport
from test_historical import request as historical_request
from test_ncbi import ncbi_transport
from test_regression import baseline
from test_snpeff import QUERY, record

ROOT = Path(__file__).resolve().parents[2]


def source_input(source, check=None):
    summary = None
    if check:
        summary = AnnotationCheckSummary(**check.model_dump(include=set(AnnotationCheckSummary.model_fields) - {'matched_transcripts'}),
                                         matched_transcripts=len(check.matches))
    return comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
                            transcript_b=source.transcripts[1].transcript_id), annotation_check=summary)


def matching_check(source):
    q = source.query
    ann = ','.join(f"{q.alt}|{'&'.join(row.consequence_terms)}|MODIFIER|G|{row.gene_id}|transcript|{row.transcript_id}"
                   for row in source.transcripts)
    return compare_snpeff(source, SnpEffCheckRequest(
        vcf_text=f'{q.chromosome}\t{q.position}\t.\t{q.ref}\t{q.alt}\t.\tPASS\tANN={ann}',
        snpeff_version='test', genome_database='test', database_sha256='a' * 64))


def bundle_for(source, payload, check=None):
    result = compare(payload)
    entries = {'investigation': result.model_dump(mode='json'), 'source_record': source.model_dump(mode='json')}
    if check:
        entries['snpeff_check'] = check.model_dump(mode='json')
    return {'format': 'GenomeDebugger bundle', 'version': 2, 'engine_version': result.engine_version,
            'entries': entries, 'sha256': {key: digest(value) for key, value in entries.items()}}


@pytest.mark.parametrize('endpoint', ['contextual', 'hgvs'])
@pytest.mark.parametrize('cached', [False, True])
def test_missing_notation_uses_provider_failure_and_preserves_valid_cache(tmp_path, monkeypatch, endpoint, cached):
    monkeypatch.setattr(main, 'DB', tmp_path / 'missing.db')
    source = record()
    storage.save_source_record(main.DB, source)
    if cached:
        with httpx.Client(transport=ncbi_transport()) as client:
            previous = fetch_reference_check(source, client)
        storage.save_reference_check(main.DB, previous)
    base = ncbi_transport()
    def handler(request):
        return httpx.Response(200, json={'data': {}}) if request.url.path.endswith('/' + endpoint) else base.handle_request(request)
    def fetch(source):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_reference_check(source, client)
    monkeypatch.setattr(main, 'fetch_reference_check', fetch)
    response = TestClient(main.app).post(f'/api/sources/ensembl/records/{source.id}/reference-check', json={'mode': 'fetch'})
    assert response.status_code == (200 if cached else 502)
    if cached:
        assert response.json()['access'] == 'cached_after_error'
        assert response.json()['check']['id'] == previous.id
        assert storage.latest_reference_check(main.DB, source.id) == previous
    else:
        assert storage.latest_reference_check(main.DB, source.id) is None


@pytest.mark.parametrize('endpoint,data', [
    ('contextual', {'seq_id': '', 'position': 6524704, 'deleted_sequence': 'C', 'inserted_sequence': 'T'}),
    ('contextual', {'seq_id': 'NC_000001.11', 'position': True, 'deleted_sequence': 'C', 'inserted_sequence': 'T'}),
    ('contextual', {'seq_id': 'NC_000001.11', 'position': -1, 'deleted_sequence': 'C', 'inserted_sequence': 'T'}),
    ('contextual', {'seq_id': 'NC_000001.11', 'position': 6524704, 'deleted_sequence': 'C', 'inserted_sequence': 'C'}),
    ('hgvs', {'hgvs': None}), ('hgvs', {'hgvs': ''}), ('hgvs', {'hgvs': 'not a genomic notation'}),
])
def test_invalid_notation_cannot_become_a_disagreement(tmp_path, monkeypatch, endpoint, data):
    monkeypatch.setattr(main, 'DB', tmp_path / 'invalid.db')
    source = record()
    storage.save_source_record(main.DB, source)
    base = ncbi_transport()
    def fetch(source):
        def handler(request):
            return httpx.Response(200, json={'data': data}) if request.url.path.endswith('/' + endpoint) else base.handle_request(request)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_reference_check(source, client)
    monkeypatch.setattr(main, 'fetch_reference_check', fetch)
    response = TestClient(main.app).post(f'/api/sources/ensembl/records/{source.id}/reference-check', json={'mode': 'fetch'})
    assert response.status_code == 502
    assert storage.latest_reference_check(main.DB, source.id) is None


def test_invalid_legacy_cache_stays_inspectable_but_cannot_replace_usable_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'legacy.db')
    source = record()
    storage.save_source_record(main.DB, source)
    with httpx.Client(transport=ncbi_transport()) as client:
        previous = fetch_reference_check(source, client)
    storage.save_reference_check(main.DB, previous)
    bad = previous.model_copy(deep=True)
    bad.checked_at = (datetime.fromisoformat(previous.checked_at) + timedelta(seconds=1)).isoformat()
    bad.contextual_response = {'data': {}}
    bad.contextual_response_sha256 = _sha(bad.contextual_response)
    bad.observed_spdi = None
    bad.spdi_matches = False
    bad.status = 'disagree'
    bad.id = _sha({'source_record_id': source.id, 'checked_at': bad.checked_at, 'fasta': bad.reference_fasta,
                   'contextual': bad.contextual_response, 'hgvs': bad.hgvs_response})[:20]
    storage.save_reference_check(main.DB, bad)
    api = TestClient(main.app)
    cached = api.post(f'/api/sources/ensembl/records/{source.id}/reference-check', json={'mode': 'cache_only'})
    assert cached.status_code == 200 and cached.json()['check']['id'] == previous.id
    selected = api.post(f'/api/sources/ensembl/records/{source.id}/compare', json={
        'transcript_a': source.transcripts[0].transcript_id, 'transcript_b': source.transcripts[1].transcript_id,
        'reference_check_id': bad.id})
    assert selected.status_code == 422
    assert api.get('/api/sources/reference-checks/' + bad.id).json() == bad.model_dump(mode='json')
    assert storage.latest_reference_check(main.DB, source.id) == bad


@pytest.mark.parametrize('change', ['consequence', 'gene_id', 'transcript_id', 'additional'])
def test_changed_custom_annotations_cannot_reuse_source_check_at_any_boundary(tmp_path, monkeypatch, change):
    monkeypatch.setattr(main, 'DB', tmp_path / 'annotations.db')
    source = record()
    check = matching_check(source)
    storage.save_source_record(main.DB, source)
    storage.save_snpeff_check(main.DB, check)
    original = compare(source_input(source, check))
    storage.save(main.DB, original)
    case = create_case(original, 'Check scope')
    storage.save_case(main.DB, case)
    payload = original.input.model_copy(deep=True)
    for snapshot in payload.snapshots:
        snapshot.provenance.tool = 'Custom transformed output'
    if change == 'additional':
        payload.snapshots[0].annotations[0].consequence = 'stop_gained'
    else:
        setattr(payload.snapshots[0].annotation, change, 'stop_gained' if change == 'consequence' else 'changed')
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 422
    assert api.post(f'/api/regression-cases/{case.id}/runs', json={'candidate': payload.model_dump(mode='json')}).status_code == 422
    bundle = bundle_for(source, payload, check)
    assert api.post('/api/bundles/verify', json=bundle).status_code == 422
    assert api.post('/api/bundles/import', json=bundle).status_code == 422
    assert len(storage.list_items(main.DB)) == 1
    assert storage.list_runs(main.DB, case.id) == []
    assert storage.load(main.DB, original.id) == original


def test_custom_metadata_and_protein_changes_keep_compatible_term_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'compatible.db')
    source = record()
    check = matching_check(source)
    storage.save_source_record(main.DB, source)
    storage.save_snpeff_check(main.DB, check)
    payload = source_input(source, check)
    for snapshot in payload.snapshots:
        snapshot.provenance.tool = 'Custom transformed output'
        snapshot.annotation.protein_consequence = 'declared separately'
    response = TestClient(main.app).post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 200, response.text
    verify_bundle(create_bundle(main.DB, compare(payload)))


def test_edited_output_with_detached_annotation_check_can_be_saved_and_exported(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'detached.db')
    source = record()
    check = matching_check(source)
    storage.save_source_record(main.DB, source)
    storage.save_snpeff_check(main.DB, check)
    payload = source_input(source, check)
    payload.annotation_check = None
    for snapshot in payload.snapshots:
        snapshot.provenance.tool = 'Custom transformed output'
        snapshot.annotation.consequence = 'stop_gained'
        for key in ('annotation_check_id', 'annotation_check_status', 'annotation_check_origin'):
            snapshot.provenance.configuration.pop(key, None)
    api = TestClient(main.app)
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 200, response.text
    bundle = api.get('/api/investigations/' + response.json()['id'] + '/bundle')
    assert bundle.status_code == 200
    assert 'snpeff_check' not in bundle.json()['entries']
    assert api.post('/api/bundles/verify', json=bundle.json()).status_code == 200


@pytest.mark.parametrize('field,value', [
    ('started_at', 'not-a-date'), ('started_at', '2026-10-20T12:00:00'),
    ('elapsed_seconds', -5), ('command', []), ('command', ['   ']), ('command', ['java', '\x00']),
    ('java_sha256', 'not-a-hash'), ('jar_sha256', 'a' * 63), ('config_sha256', 'G' * 64),
    ('database_files', {'snpEffectPredictor.bin': 'not-a-hash'}),
])
def test_execution_metadata_formats_rejected_atomically(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(main, 'DB', tmp_path / 'execution.db')
    fixture = json.loads((ROOT / 'fixtures/snpeff-mane-public-run.json').read_text(encoding='utf-8'))
    source = SourceRecord.model_validate(fixture['source'])
    check = SnpEffCheck.model_validate(fixture['check'])
    check.execution = check.execution.model_copy(update={field: value})
    bundle = bundle_for(source, source_input(source, check), check)
    api = TestClient(main.app)
    for route in ('verify', 'import'):
        response = api.post('/api/bundles/' + route, json=bundle)
        assert response.status_code == 422, response.text
    assert storage.list_items(main.DB) == []
    assert storage.list_source_records(main.DB) == []


def test_legacy_execution_formats_remain_verifiable_without_rewriting_saved_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'execution-legacy.db')
    fixture = json.loads((ROOT / 'fixtures/snpeff-mane-public-run.json').read_text(encoding='utf-8'))
    source = SourceRecord.model_validate(fixture['source'])
    check = SnpEffCheck.model_validate(fixture['check'])
    assert check.execution.capture_format == 'legacy_text'
    validate_execution_metadata(check.execution)
    storage.save_source_record(main.DB, source)
    storage.save_snpeff_check(main.DB, check)
    with closing(sqlite3.connect(main.DB)) as db:
        old = db.execute('SELECT check_json FROM snpeff_checks WHERE id=?', (check.id,)).fetchone()[0]
    verify_bundle(create_bundle(main.DB, compare(source_input(source, check))))
    with closing(sqlite3.connect(main.DB)) as db:
        assert db.execute('SELECT check_json FROM snpeff_checks WHERE id=?', (check.id,)).fetchone()[0] == old


def test_expanded_release_metadata_is_preserved_comparable_and_portable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'releases.db')
    releases = list(range(80, 121))
    base = fixture_transport()
    def handler(request):
        return httpx.Response(200, json={'releases': releases}) if request.url.path == '/info/data' else base.handle_request(request)
    def fetch(query):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_record(query, client)
    monkeypatch.setattr(main, 'fetch_record', fetch)
    api = TestClient(main.app)
    fetched = api.post('/api/sources/ensembl/lookup', json={'query': QUERY.model_dump(), 'mode': 'fetch'})
    assert fetched.status_code == 200
    source = SourceRecord.model_validate(fetched.json()['record'])
    result = api.post(f'/api/sources/ensembl/records/{source.id}/compare', json={
        'transcript_a': source.transcripts[0].transcript_id, 'transcript_b': source.transcripts[1].transcript_id})
    assert result.status_code == 200, result.text
    assert result.json()['input']['snapshots'][0]['provenance']['source_release'] == 'reported 41 releases (see source record)'
    exported = api.get('/api/investigations/' + result.json()['id'] + '/bundle')
    assert exported.status_code == 200
    assert exported.json()['entries']['source_record']['releases'] == releases
    assert api.post('/api/bundles/verify', json=exported.json()).status_code == 200
    cached = api.post('/api/sources/ensembl/lookup', json={'query': QUERY.model_dump(), 'mode': 'cache_only'})
    assert cached.json()['record']['releases'] == releases


@pytest.mark.parametrize('field', ['position', 'context_start', 'extra_position', 'source_position', 'historical_release'])
@pytest.mark.parametrize('boolean', [True, False])
def test_boolean_coordinates_and_counts_are_rejected_without_saving(tmp_path, monkeypatch, field, boolean):
    monkeypatch.setattr(main, 'DB', tmp_path / 'numbers.db')
    payload = baseline().input.model_dump(mode='json')
    route = '/api/investigations'
    if field == 'source_position':
        payload = {'query': {**QUERY.model_dump(), 'position': boolean}, 'mode': 'cache_only'}
        route = '/api/sources/ensembl/lookup'
    elif field == 'historical_release':
        payload = historical_request(record()).model_dump(mode='json')
        payload['source_release'] = boolean
        route = '/api/sources/historical-vep'
    elif field == 'position':
        payload['snapshots'][0]['variant']['position'] = boolean
    elif field == 'context_start':
        payload['snapshots'][0]['variant']['reference_context']['start'] = boolean
    else:
        payload['snapshots'][0]['variant_records'] = [{'variant': {**payload['snapshots'][0]['variant'], 'position': boolean},
                                                      'annotations': [payload['snapshots'][0]['annotation']]}]
    response = TestClient(main.app).post(route, json=payload)
    assert response.status_code == 422
    assert storage.list_items(main.DB) == []
    assert storage.list_source_records(main.DB) == []


@pytest.mark.parametrize('field', ['start', 'end'])
def test_boolean_provider_coordinates_cannot_pass_numeric_equality(tmp_path, monkeypatch, field):
    monkeypatch.setattr(main, 'DB', tmp_path / 'provider-numbers.db')
    source = record()
    raw = copy.deepcopy(source.source_response)
    raw.update(start=1, end=1)
    raw[field] = True
    query = SourceQuery(chromosome='1', position=1, ref='C', alt='T')
    base = fixture_transport()
    def handler(request):
        return httpx.Response(200, json=[raw]) if request.url.path.startswith('/vep/') else base.handle_request(request)
    def fetch(query):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return fetch_record(query, client)
    monkeypatch.setattr(main, 'fetch_record', fetch)
    api = TestClient(main.app)
    assert api.post('/api/sources/ensembl/lookup', json={'query': query.model_dump(), 'mode': 'fetch'}).status_code == 502
    payload = historical_request(source).model_dump(mode='json')
    payload.update(query=query.model_dump(), raw_json=json.dumps(raw))
    assert api.post('/api/sources/historical-vep', json=payload).status_code == 422
    assert storage.list_source_records(main.DB) == []


@pytest.mark.parametrize('path', ['title', 'label', 'gene_id', 'transcript_id', 'tool', 'tool_version', 'source_name', 'source_release'])
@pytest.mark.parametrize('blank', ['   ', '\t\n\u00a0\ufeff'])
def test_required_text_rejects_whitespace_on_api_candidate_and_bundle_admission(tmp_path, monkeypatch, path, blank):
    monkeypatch.setattr(main, 'DB', tmp_path / 'text.db')
    original = baseline()
    storage.save(main.DB, original)
    case = create_case(original, 'Whitespace admission')
    storage.save_case(main.DB, case)
    payload = original.input.model_copy(deep=True)
    if path == 'title': payload.title = blank
    elif path == 'label': payload.snapshots[0].label = blank
    elif path in ('gene_id', 'transcript_id'): setattr(payload.snapshots[0].annotation, path, blank)
    else: setattr(payload.snapshots[0].provenance, path, blank)
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 422
    assert api.post(f'/api/regression-cases/{case.id}/runs', json={'candidate': payload.model_dump(mode='json')}).status_code == 422
    result = compare(payload)
    entries = {'investigation': result.model_dump(mode='json')}
    bundle = {'format': 'GenomeDebugger bundle', 'version': 2, 'engine_version': result.engine_version,
              'entries': entries, 'sha256': {key: digest(value) for key, value in entries.items()}}
    assert api.post('/api/bundles/import', json=bundle).status_code == 422
    assert len(storage.list_items(main.DB)) == 1


def test_valid_spaces_preserved_and_older_blank_records_stay_inspectable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'saved.db')
    payload = baseline().input.model_copy(deep=True)
    payload.title = '  Valid name with spaces  '
    api = TestClient(main.app)
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 200 and response.json()['input']['title'] == payload.title
    id_ = response.json()['id']
    assert api.post(f'/api/investigations/{id_}/regression-cases', json={'name': ' \t\ufeff'}).status_code == 422
    saved = api.post(f'/api/investigations/{id_}/regression-cases', json={'name': ' Valid baseline '})
    assert saved.status_code == 200 and saved.json()['name'] == ' Valid baseline '
    legacy = payload.model_copy(deep=True)
    legacy.title = '   '
    old = compare(legacy)
    storage.save(main.DB, old)
    assert api.get('/api/investigations/' + old.id).status_code == 200
    assert api.get('/api/investigations/' + old.id + '/report.md').status_code == 200
    assert storage.load(main.DB, old.id) == old


@pytest.mark.parametrize('field', ['tool_version', 'source_uri'])
def test_historical_required_metadata_cannot_bypass_nonblank_validation(tmp_path, monkeypatch, field):
    monkeypatch.setattr(main, 'DB', tmp_path / 'historical-text.db')
    payload = historical_request(record()).model_dump(mode='json')
    payload[field] = ' \t\ufeff'
    response = TestClient(main.app).post('/api/sources/historical-vep', json=payload)
    assert response.status_code == 422 and field in response.text
    assert storage.list_source_records(main.DB) == []


@pytest.mark.parametrize('field', ['snpeff_version', 'genome_database'])
def test_supplied_check_declaration_cannot_store_blank_names(tmp_path, monkeypatch, field):
    monkeypatch.setattr(main, 'DB', tmp_path / 'check-text.db')
    source = record()
    storage.save_source_record(main.DB, source)
    check = matching_check(source)
    payload = {key: getattr(check, key) for key in SnpEffCheckRequest.model_fields}
    payload[field] = '   '
    response = TestClient(main.app).post(f'/api/sources/ensembl/records/{source.id}/snpeff-check', json=payload)
    assert response.status_code == 422 and field in response.text
    assert storage.latest_snpeff_check(main.DB, source.id) is None


def test_generated_source_comparison_cannot_store_a_blank_title(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'source-text.db')
    source = record()
    storage.save_source_record(main.DB, source)
    response = TestClient(main.app).post('/api/sources/compare', json={
        'source_a': source.id, 'source_b': source.id, 'transcript_a': source.transcripts[0].transcript_id,
        'transcript_b': source.transcripts[1].transcript_id, 'title': '   '})
    assert response.status_code == 422
    assert storage.list_items(main.DB) == []
