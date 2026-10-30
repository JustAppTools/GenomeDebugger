"""Application boundary regressions: origin policy, check links, safe errors."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.regression import create_case
from test_v062_fixes import checked_input

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures'


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'boundaries.db')
    return TestClient(main.app, base_url='http://127.0.0.1:8000')


def demo():
    return json.loads((FIXTURES / 'transcript-switch.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://untrusted.example'}, {'Origin': 'null'},
    {'Origin': 'http://127.0.0.1:5199'}, {'Sec-Fetch-Site': 'cross-site'},
    {'Sec-Fetch-Site': 'same-site'},
])
def test_untrusted_browser_mutations_are_rejected_before_side_effects(api, monkeypatch, headers):
    response = api.post('/api/investigations', content=json.dumps(demo()).encode(), headers=headers)
    assert response.status_code == 403
    assert storage.list_items(main.DB) == []
    def unexpected_fetch(*args, **kwargs):
        pytest.fail('Untrusted browser triggered an upstream request')
    monkeypatch.setattr(main, 'fetch_record', unexpected_fetch)
    assert api.post('/api/sources/ensembl/lookup', json={
        'query': {'chromosome':'1','position':6524705,'ref':'C','alt':'T'}, 'mode':'fetch'}, headers=headers).status_code == 403
    # Deletion is also rejected, even with otherwise valid saved data.
    saved = api.post('/api/investigations', json=demo()).json()
    assert api.delete(f"/api/investigations/{saved['id']}", headers=headers).status_code == 403
    assert storage.load(main.DB, saved['id']) is not None


@pytest.mark.parametrize('host', ['untrusted.example:8000', 'localhost.untrusted.example', 'testserver', '['])
def test_untrusted_hosts_are_rejected_for_reads_and_writes(api, host):
    # A real loopback TCP peer must not receive TestClient's host exception.
    with TestClient(main.app, base_url='http://127.0.0.1:8000', client=('127.0.0.1', 10000)) as client:
        assert client.get('/api/health', headers={'Host':host}).status_code == 400
        assert client.post('/api/investigations', json=demo(), headers={'Host':host}).status_code == 400
    assert storage.list_items(main.DB) == []


@pytest.mark.parametrize('host', ['localhost:8000', '[::1]:8000'])
def test_loopback_hosts_allow_local_api_clients(api, host):
    # Avoid TestClient's IPv6 URL splitter; pass the actual Host to the ASGI app.
    with TestClient(main.app, base_url='http://127.0.0.1:8000', client=('::1', 10000)) as client:
        assert client.post('/api/investigations', json=demo(), headers={'Host':host}).status_code == 200


@pytest.mark.parametrize('origin', [None, 'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000'])
def test_cli_trusted_frontend_and_same_origin_docs_can_save(api, origin):
    headers = {'Origin':origin} if origin else {}
    response = api.post('/api/investigations', json=demo(), headers=headers)
    assert response.status_code == 200
    assert storage.load(main.DB, response.json()['id']) is not None


@pytest.mark.parametrize('field,value', [
    ('annotation_check_id', 'nonexistent-check'), ('annotation_check_status', 'disagree'),
    ('annotation_check_origin', 'local_execution'),
])
@pytest.mark.parametrize('linked', [True, False])
def test_snpeff_claims_are_checked_in_create_candidate_and_bundle(api, field, value, linked):
    payload = checked_input(main.DB, 'annotation')
    assert payload.annotation_check.status == 'agree'
    result = compare(payload)
    storage.save(main.DB, result)
    case = create_case(result, 'Consistent SnpEff baseline')
    storage.save_case(main.DB, case)
    bundle = create_bundle(main.DB, result)
    if not linked:
        payload.annotation_check = None
        bundle['entries'].pop('snpeff_check')
        bundle['sha256'].pop('snpeff_check')
        for snapshot in payload.snapshots:
            for key in ('annotation_check_id', 'annotation_check_status', 'annotation_check_origin'):
                snapshot.provenance.configuration.pop(key, None)
    payload.snapshots[1].provenance.configuration[field] = value
    invalid = payload.model_dump(mode='json')
    assert api.post('/api/investigations', json=invalid).status_code == 422
    assert api.post(f'/api/regression-cases/{case.id}/runs', json={'candidate':invalid}).status_code == 422
    bundle['entries']['investigation'] = compare(payload).model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    with pytest.raises(ValueError, match='SnpEff'):verify_bundle(bundle)
    assert api.post('/api/bundles/import', json=bundle).status_code == 422
    assert len(storage.list_items(main.DB)) == 1
    assert storage.list_runs(main.DB, case.id) == []


def test_snpeff_missing_legacy_flags_remain_compatible(api):
    payload = checked_input(main.DB, 'annotation')
    for snapshot in payload.snapshots:
        for key in ('annotation_check_id', 'annotation_check_status', 'annotation_check_origin'):
            snapshot.provenance.configuration.pop(key, None)
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 200
    bundle = api.get(f"/api/investigations/{response.json()['id']}/bundle").json()
    assert api.post('/api/bundles/verify', json=bundle).status_code == 200


@pytest.mark.parametrize('kind', ['surrogate', 'overflow', 'nan'])
@pytest.mark.parametrize('route', ['investigation', 'candidate', 'historical'])
def test_invalid_values_return_safe_field_errors(api, kind, route):
    payload = demo()
    if kind == 'surrogate':payload['title'] = 'bad\ud800'
    if kind == 'nan':payload['snapshots'][0]['variant']['position'] = float('nan')
    body = json.dumps(payload)
    if kind == 'overflow':body = body.replace('"position": 101', '"position": 1e999', 1)
    url = '/api/investigations'
    if route == 'candidate':
        result = api.post(url, json=demo()).json()
        case = api.post(f"/api/investigations/{result['id']}/regression-cases", json={'name':'Error rendering'}).json()
        url = f"/api/regression-cases/{case['id']}/runs"
        body = '{"candidate":' + body + '}'
    elif route == 'historical':
        url = '/api/sources/historical-vep'
        body = '{"tool_version":"bad\\ud800"}' if kind == 'surrogate' else '{"source_release":1e999}' if kind == 'overflow' else '{"source_release":NaN}'
    response = api.post(url, content=body.encode(), headers={'Content-Type':'application/json'})
    assert response.status_code == 422
    details = response.json()['detail']
    assert details and all(set(error) == {'loc','msg','type'} for error in details)
    assert all(error['loc'] and error['msg'] for error in details)
    assert len(response.content) < 30_000


def test_validation_details_are_bounded(api):
    payload = demo()
    payload.update({f'extra{i}': 'private contents' for i in range(100)})
    response = api.post('/api/investigations', json=payload)
    assert response.status_code == 422 and len(response.json()['detail']) == 50
    assert 'private contents' not in response.text
