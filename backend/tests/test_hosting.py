"""Public-free deployment isolation, cookie security, and local compatibility."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from app import main
from app.hosting import COOKIE, PublicHosting, REQUEST_DATABASE

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/transcript-switch.json'


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    settings = PublicHosting(enabled=True, origin='https://genomedebugger.example', secret=b'synthetic-test-key-' * 3, root=tmp_path/'visitors')
    monkeypatch.setattr(main, 'HOSTING', settings)
    monkeypatch.setattr(main, 'DB', tmp_path/'untouched-local.db')
    def client():
        return TestClient(main.app, base_url=settings.origin, raise_server_exceptions=False)
    return settings, client


def create(client, title='Private visitor input'):
    payload = json.loads(FIXTURE.read_text(encoding='utf-8'))
    payload['title'] = title
    response = client.post('/api/investigations', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_public_visitors_cannot_read_update_delete_or_export_each_others_records(hosted):
    settings, client = hosted
    a, b = client(), client()
    result = create(a)
    identifier = result['id']
    assert b.get('/api/investigations').json() == []
    for path in [f'/api/investigations/{identifier}', f'/api/investigations/{identifier}/report.md',
                 f'/api/investigations/{identifier}/bundle', f'/api/workspace/library/{identifier}/label']:
        assert b.get(path).status_code == 404
    assert b.post(f'/api/workspace/library/{identifier}/label', json={'notes':'Intrusion'}).status_code == 404
    assert b.delete(f'/api/investigations/{identifier}').status_code == 404
    assert b.post('/api/workspace/export', json={'ids':[identifier]}).status_code == 404
    assert b.post(f'/api/investigations/{identifier}/regression-cases', json={'name':'Intrusion'}).status_code == 404
    assert a.get(f'/api/investigations/{identifier}').status_code == 200
    assert not main.DB.exists()
    assert len(list(settings.root.glob('*/investigations.db'))) == 2


def test_deterministic_scientific_ids_do_not_share_notes_or_baselines(hosted):
    _, client = hosted
    a, b = client(), client()
    first = create(a); second = create(b)
    assert first['id'] == second['id']
    a.post(f"/api/workspace/library/{first['id']}/label", json={'notes':'Visitor A private notes'})
    assert b.get(f"/api/workspace/library/{second['id']}/label").json()['notes'] == ''
    case = a.post(f"/api/investigations/{first['id']}/regression-cases",json={'name':'A only'}).json()
    run = a.post(f"/api/regression-cases/{case['id']}/runs",json={}).json()
    assert b.get(f"/api/regression-cases/{case['id']}").status_code == 404
    assert b.get(f"/api/regression-runs/{run['id']}").status_code == 404


def test_browser_cookie_is_secure_signed_and_never_put_in_the_response_body(hosted):
    settings, client = hosted
    response = client().get('/api/health')
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie and 'Path=/' in cookie
    assert 'Domain=' not in cookie
    token = response.cookies.get(COOKIE)
    assert settings.identify(token) and token not in response.text
    assert response.headers['cache-control'] == 'no-store' and 'Cookie' in response.headers['vary']
    assert response.json()['hosted'] is True and response.json()['storage'] == 'temporary'


@pytest.mark.parametrize('cookie',['../other','a'*64+'.'+'0'*64, 'a'*64+'.'+'é'*64, 'x'*2000])
def test_invalid_cookie_gets_a_new_workspace_without_server_errors(hosted,cookie):
    settings, client = hosted
    browser = client()
    response = browser.get('/api/health',headers=[(b'Cookie',f'{COOKIE}={cookie}'.encode('latin-1'))])
    assert response.status_code == 200
    assert settings.identify(response.cookies.get(COOKIE))
    assert not (settings.root/('a'*64)).exists()


def test_copying_only_an_identifier_cannot_impersonate_another_visitor(hosted):
    settings, client = hosted
    a, b = client(), client()
    result = create(a)
    identifier = settings.identify(a.cookies.get(COOKIE))
    response = b.get('/api/investigations',headers={'Cookie':f'{COOKIE}={identifier}.{"0"*64}'})
    assert response.status_code == 200 and response.json() == []
    assert b.get(f"/api/investigations/{result['id']}").status_code == 404


@pytest.mark.parametrize('origin',['https://other.example','http://localhost:5173','null'])
def test_public_mode_rejects_foreign_browser_writes(hosted,origin):
    _, client = hosted
    browser = client();browser.get('/api/health')
    response = browser.post('/api/investigations',headers={'Origin':origin},json=json.loads(FIXTURE.read_text(encoding='utf-8')))
    assert response.status_code == 403
    assert browser.get('/api/investigations').json() == []


def test_public_host_tls_and_minimal_probe(hosted):
    _, client = hosted
    browser = client()
    assert browser.get('/api/health',headers={'Host':'other.example'}).status_code == 400
    with TestClient(main.app,base_url='http://genomedebugger.example') as insecure:
        assert insecure.get('/api/health').status_code == 400
        response = insecure.get('/healthz')
        assert response.status_code == 200 and response.json() == {'status':'ok'}
        assert COOKIE not in response.cookies


def test_browser_exports_and_imports_its_own_comparison_to_another_workspace(hosted):
    _, client = hosted
    a, b = client(), client()
    result = create(a)
    response = a.get(f"/api/investigations/{result['id']}/bundle")
    assert response.status_code == 200
    imported = b.post('/api/bundles/import',content=response.content,headers={'Content-Type':'application/json'})
    assert imported.status_code == 200
    assert b.get(f"/api/investigations/{imported.json()['imported']}").status_code == 200
    info = a.get('/api/workspace/data').json()
    assert info['database_path'] == 'Temporary workspace for this browser'
    assert info['hosted'] is True and info['desktop_mode'] is False
    assert a.get('/api/workspace/backup').content.startswith(b'SQLite format 3')


def test_threaded_request_contexts_do_not_leak_into_another_browser(hosted):
    _, client = hosted
    browsers = [client() for _ in range(4)]
    for browser in browsers:browser.get('/api/health')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda pair:create(pair[1],f'Visitor {pair[0]}'),enumerate(browsers)))
    for index,browser in enumerate(browsers):
        assert [row['id'] for row in browser.get('/api/investigations').json()] == [results[index]['id']]
    assert REQUEST_DATABASE.get() is None


def test_public_mode_cannot_stop_the_server_or_execute_a_local_tool(hosted,monkeypatch):
    _, client = hosted
    def forbidden(*_args,**_kwargs):raise AssertionError('Public server attempted local execution')
    monkeypatch.setattr(main,'run_snpeff',forbidden)
    browser = client()
    assert browser.post('/api/workspace/stop').status_code == 404
    assert browser.get('/api/tools/snpeff').json()['configured'] is False
    assert browser.post('/api/sources/ensembl/records/anything/snpeff-run').status_code == 409


def test_capacity_keeps_existing_visitors_readable_and_does_not_evict_active_work(hosted):
    settings, client = hosted
    settings.max_workspaces = 1
    a, b = client(), client()
    result = create(a)
    assert b.get('/api/health').status_code == 503
    assert a.get(f"/api/investigations/{result['id']}").status_code == 200
    settings.total_bytes = 1
    assert a.post('/api/investigations',json=result['input']).status_code == 503
    assert a.get('/api/workspace/backup').status_code == 200


def test_expiry_only_removes_inactive_owned_directories(hosted,tmp_path):
    settings, client = hosted
    a, b = client(), client();create(a);create(b)
    first = settings.identify(a.cookies.get(COOKIE));second = settings.identify(b.cookies.get(COOKIE))
    outside = tmp_path/'preserve-me';outside.mkdir();(outside/'notes.txt').write_text('Keep',encoding='utf-8')
    for identifier in (first,second):os.utime(settings.root/identifier,(0,0))
    settings.active[first] = 1;settings.last_cleanup = 0
    settings.cleanup(time.time())
    assert (settings.root/first).exists() and not (settings.root/second).exists()
    assert (outside/'notes.txt').read_text(encoding='utf-8') == 'Keep'


@pytest.mark.parametrize('origin',['http://example.com','https://example.com/path','https://name:pass@example.com','https://example.com?x=1'])
def test_hosted_configuration_fails_closed_for_bad_origins(monkeypatch,origin):
    monkeypatch.setenv('GENOMEDEBUGGER_DEPLOYMENT','public-free')
    monkeypatch.setenv('GENOMEDEBUGGER_PUBLIC_ORIGIN',origin)
    monkeypatch.setenv('GENOMEDEBUGGER_SESSION_SECRET','x'*64)
    with pytest.raises(ValueError):PublicHosting.from_environment()


def test_hosted_configuration_requires_a_secret_and_local_is_default(monkeypatch):
    monkeypatch.delenv('GENOMEDEBUGGER_DEPLOYMENT',raising=False)
    assert PublicHosting.from_environment().enabled is False
    monkeypatch.setenv('GENOMEDEBUGGER_DEPLOYMENT','public-free')
    monkeypatch.setenv('GENOMEDEBUGGER_PUBLIC_ORIGIN','https://genomedebugger.example')
    monkeypatch.setenv('GENOMEDEBUGGER_SESSION_SECRET','short')
    with pytest.raises(ValueError):PublicHosting.from_environment()
