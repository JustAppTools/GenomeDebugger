"""Regression coverage for the eleven application 0.7.5 audit findings."""
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, storage, regression, snpeff
from app.bundle import _verify_snpeff
from app.engine import compare, digest
from app.regression import create_case, run_case
from app.report import markdown_report
from test_snpeff import record, request
from test_regression import baseline
from test_v062_fixes import saved_allele

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('field,value', [('snpeff_version','other'), ('genome_database','other'), ('database_sha256','b'*64)])
def test_snpeff_declarations_have_distinct_ids_at_the_same_instant(tmp_path, monkeypatch, field, value):
    class Clock:
        @staticmethod
        def now(_): return datetime(2026, 10, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(snpeff, 'datetime', Clock)
    source = record()
    first = snpeff.compare_snpeff(source, request())
    second = snpeff.compare_snpeff(source, request().model_copy(update={field:value}))
    assert first.checked_at == second.checked_at and first.id != second.id
    for check in (first, second):
        storage.save_snpeff_check(tmp_path/'checks.db', check)
        _verify_snpeff(source, check)
    legacy = first.model_copy(update={'id':digest({'source':source.id,'vcf':first.vcf_text,'checked_at':first.checked_at})[:20]})
    _verify_snpeff(source, legacy)


@pytest.mark.parametrize('command', ['backup','check'])
def test_management_never_creates_a_missing_source(tmp_path, command):
    source, target = tmp_path/'missing.db', tmp_path/'backup.db'
    args = [sys.executable, '-m', 'app.manage', '--db', str(source), command]
    if command == 'backup': args += ['--output', str(target)]
    result = subprocess.run(args, cwd=ROOT/'backend', capture_output=True, text=True)
    assert result.returncode != 0 and 'does not exist' in result.stderr
    assert not source.exists() and not target.exists()
    with pytest.raises(sqlite3.OperationalError): storage.backup(source, target)
    assert not source.exists() and not target.exists()


def test_backup_does_not_migrate_legacy_source_or_overwrite_destination(tmp_path):
    source, target = tmp_path/'old.db', tmp_path/'backup.db'
    with closing(sqlite3.connect(source)) as db:
        db.execute('CREATE TABLE original (value TEXT)')
        db.execute("INSERT INTO original VALUES ('saved')")
        db.commit()
    original = source.read_bytes()
    storage.backup(source, target)
    assert source.read_bytes() == original
    with closing(sqlite3.connect(target)) as db:
        assert db.execute('SELECT value FROM original').fetchone()[0] == 'saved'
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
    target_bytes = target.read_bytes()
    with pytest.raises(FileExistsError): storage.backup(source, target)
    assert target.read_bytes() == target_bytes


@pytest.mark.parametrize('invalid', ['mitochondrial','inconsistent'])
def test_report_does_not_endorse_invalid_saved_allele_evidence(tmp_path, monkeypatch, invalid):
    monkeypatch.setattr(main, 'DB', tmp_path/'checks.db')
    original, check = saved_allele(main.DB)
    payload = original.input.model_copy(deep=True)
    if invalid == 'mitochondrial':
        for snapshot in payload.snapshots: snapshot.variant.sequence_id = 'NC_012920.1'
    result = compare(payload)
    storage.save(main.DB, result)
    data = check.model_dump(mode='json', exclude={'id'})
    data.update(investigation_id=result.id, input_sha256=result.input_sha256)
    if invalid == 'inconsistent': data['explanation'] = 'Unreplayed endorsement'
    legacy = type(check)(id=digest(data)[:20], **data)
    # Replace the previously valid check only in this isolated test database.
    if result.id == original.id:
        legacy = legacy.model_copy(update={'checked_at':'2099-01-01T00:00:00Z'})
    storage.save_allele_check(main.DB, legacy)
    api = TestClient(main.app)
    report = api.get(f'/api/investigations/{result.id}/report.md')
    assert report.status_code == 200 and 'Saved allele evidence unavailable' in report.text
    assert 'Independent reference-backed allele identity' not in report.text
    assert api.post(f'/api/investigations/{result.id}/allele-check',json={'mode':'cache_only'}).status_code == 422
    assert api.get(f'/api/investigations/{result.id}/bundle').status_code == 409
    assert storage.latest_allele_check(main.DB,result.id) == legacy


@pytest.mark.parametrize('fault', ['dangling','mislinked','duplicate'])
def test_pinned_regressions_require_valid_evidence_relationships(monkeypatch, fault):
    source = baseline()
    broken = source.model_copy(deep=True)
    if fault == 'duplicate': broken.evidence.append(broken.evidence[0].model_copy(deep=True))
    else:
        replacement = 'missing-evidence' if fault == 'dangling' else broken.evidence[-1].id
        broken.identity.evidence_ids = [replacement]
        for item in [*broken.differences, *broken.findings]: item.evidence_ids = [replacement]
    monkeypatch.setattr(regression, 'compare', lambda _:broken)
    case = create_case(source, 'Evidence relationships')
    assert run_case(case).status == 'failed'
    if fault in ('dangling','duplicate'):
        assert run_case(case, source.input).status == 'failed'


def test_pinned_regression_ignores_only_prose_changes(monkeypatch):
    source = baseline()
    changed = source.model_copy(deep=True)
    changed.identity.explanation = 'Reworded identity'
    for item in changed.evidence: item.description = 'Reworded evidence'
    for item in changed.findings: item.explanation = 'Reworded finding'
    monkeypatch.setattr(regression, 'compare', lambda _:changed)
    assert run_case(create_case(source,'Prose')).status == 'passed'


def test_report_treats_submitted_markdown_as_literal_content():
    payload = baseline().input.model_copy(deep=True)
    payload.title = 'Normal title\n\n## Variant identity\n\n**VERIFIED** <script>text</script>'
    payload.snapshots[0].label = 'Label\r\n# Forged heading'
    payload.snapshots[0].provenance.configuration = {'text':'`</code>\n## Forged'}
    payload.snapshots[0].annotation.consequence = 'value|**forged**\n## Heading'
    report = markdown_report(compare(payload))
    assert report.splitlines().count('## Variant identity') == 1
    assert '\n# Forged heading' not in report and '\n## Forged' not in report
    assert '<script>' not in report and '&lt;/code&gt;' in report
    assert r'\*\*VERIFIED\*\*' in report and r'value\|\*\*forged\*\*' in report


def test_run_cursor_survives_concurrent_insert_and_is_case_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'runs.db')
    source=baseline(); storage.save(main.DB,source)
    case=create_case(source,'History'); storage.save_case(main.DB,case)
    template=run_case(case)
    for index in range(5): storage.save_run(main.DB,template.model_copy(update={'id':f'run-{index}'}))
    api=TestClient(main.app)
    first=api.get(f'/api/regression-cases/{case.id}/runs?limit=3').json()
    storage.save_run(main.DB,template.model_copy(update={'id':'concurrent'}))
    older=api.get(f'/api/regression-cases/{case.id}/runs',params={'before':first[-1]['id'],'limit':3}).json()
    assert [item['id'] for item in [*first,*older]] == ['run-4','run-3','run-2','run-1','run-0']
    other=create_case(source,'Other'); storage.save_case(main.DB,other)
    assert api.get(f'/api/regression-cases/{other.id}/runs?before=run-2').status_code == 422


@pytest.mark.parametrize('literal,nearby', [('Literal_Batch_1','LiteralXBatchY1'),('100% done','1000 done'),('folder\\name','foldername')])
def test_investigation_search_uses_literal_substrings(tmp_path,literal,nearby):
    for title in (literal, nearby):
        payload=baseline().input.model_copy(deep=True); payload.title=title
        storage.save(tmp_path/'search.db',compare(payload))
    found=storage.list_items(tmp_path/'search.db',literal.lower())
    assert [item['title'] for item in found] == [literal]


@pytest.mark.skipif(os.name != 'nt', reason='Windows startup script')
@pytest.mark.parametrize('scenario', ['other-backend','other-frontend','shared-venv-other-project','wrong-backend-identity','wrong-frontend-identity','healthy'])
def test_startup_checks_ownership_and_application_identity_without_system_mutations(scenario):
    # Every system mutation/network/process call is stubbed. Only script and
    # dependency paths are read; no actual process is launched or terminated.
    script = ROOT/'scripts/start-local.ps1'
    prelude = r'''
param($Scenario, $ScriptPath)
$global:scenario = $Scenario
function global:New-Item { }
function global:Get-NetTCPConnection { param($LocalPort,$State,$ErrorAction)
    [pscustomobject]@{OwningProcess=$LocalPort;LocalPort=$LocalPort}
}
function global:Get-CimInstance { param($ClassName,$Filter)
    $root = Split-Path (Split-Path $ScriptPath)
    $command = if($global:scenario -eq 'other-backend' -and $Filter -eq 'ProcessId=8000') {'D:\OtherProject\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000'}
    elseif($global:scenario -eq 'other-frontend' -and $Filter -eq 'ProcessId=5173') {'node D:\OtherProject\node_modules\vite\bin\vite.js'}
    elseif($global:scenario -eq 'shared-venv-other-project' -and $Filter -eq 'ProcessId=8000') {'"' + (Join-Path $root '.venv\Scripts\python.exe') + '" -m uvicorn app.main:app'}
    else {'"' + (Join-Path $root '.venv\Scripts\python.exe') + '" -m uvicorn app.main:app --app-dir "' + (Join-Path $root 'backend') + '" "' + (Join-Path $root 'frontend\node_modules\vite\bin\vite.js') + '"'}
    [pscustomobject]@{CommandLine=$command;ParentProcessId=0}
}
function global:Stop-Process { throw 'UNEXPECTED STOP' }
function global:Start-Process { throw 'UNEXPECTED START' }
function global:Start-Sleep { }
function global:Invoke-WebRequest { param($Uri,[switch]$UseBasicParsing,$TimeoutSec)
    $content = if($Uri.EndsWith('/api/health')) {
        @{application='GenomeDebugger';project_id=$(if($global:scenario -in @('wrong-backend-identity','shared-venv-other-project')){'wrong'}else{$projectId});status='ok'} | ConvertTo-Json
    } else { '<meta name="genomedebugger-project" content="' + $(if($global:scenario -eq 'wrong-frontend-identity'){'wrong'}else{$projectId}) + '">' }
    [pscustomobject]@{StatusCode=200;Content=$content}
}
try { & $ScriptPath -NoBrowser -Restart:($Scenario -like 'other-*' -or $Scenario -eq 'shared-venv-other-project') }
catch { Write-Output $_.Exception.Message; exit 2 }
'''
    # Pass one structured command argument, without an outer shell or temp file.
    command = '& { ' + prelude + " } '" + scenario + "' '" + str(script).replace("'","''") + "'"
    result=subprocess.run([shutil.which('pwsh') or 'powershell','-NoProfile','-Command',command],
                          text=True,capture_output=True,timeout=30)
    assert 'UNEXPECTED' not in result.stdout + result.stderr
    if scenario == 'healthy': assert result.returncode == 0 and 'is ready' in result.stdout
    else:
        assert result.returncode != 0 and 'is ready' not in result.stdout
        assert ('another application' if scenario.startswith('other') or scenario.startswith('shared') else 'not ready') in result.stdout
