import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.engine import digest
from app.ensembl import SourceRecord
from app.snpeff import SnpEffCheck
from app.snpeff_runner import run_snpeff
from app.bundle import _verify_snpeff
from test_snpeff import record,VCF


def install_fixture(tmp_path,monkeypatch):
    paths={}
    for key in ('java','jar','config'):
        path=tmp_path/key;path.write_bytes(key.encode());paths[key]=str(path)
        paths[key+'_sha256']=hashlib.sha256(key.encode()).hexdigest()
    base=tmp_path/'data'/'fixture'
    base.mkdir(parents=True);(base/'snpEffectPredictor.bin').write_bytes(b'database')
    paths.update(data_dir=str(base.parent),genome='fixture',snpeff_version='fixture-version',
                 database_files={'snpEffectPredictor.bin':hashlib.sha256(b'database').hexdigest()})
    manifest=tmp_path/'runtime.json';manifest.write_text(json.dumps(paths))
    monkeypatch.setenv('GENOMEDEBUGGER_SNPEFF_MANIFEST',str(manifest))
    return paths


def test_local_runner_checks_artifacts_and_records_execution(tmp_path,monkeypatch):
    paths=install_fixture(tmp_path,monkeypatch)
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        assert '-nodownload' in command and '-noLog' in command and '-noStats' in command
        assert Path(command[-1]).is_file()
        return SimpleNamespace(returncode=0,stdout=VCF,stderr='')
    monkeypatch.setattr('app.snpeff_runner.subprocess.run',run)
    source=record()
    check=run_snpeff(source)
    assert check.execution and check.execution.database_sha256==digest(paths['database_files'])
    _verify_snpeff(source,check)
    assert len(calls)==1
    Path(paths['jar']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='jar artifact changed'):
        run_snpeff(record())
    assert len(calls)==1


def test_preserved_real_local_run_has_consistent_output_provenance():
    fixture=json.loads((Path(__file__).resolve().parents[2]/'fixtures/snpeff-mane-public-run.json').read_text())
    check=SnpEffCheck.model_validate(fixture['check'])
    _verify_snpeff(SourceRecord.model_validate(fixture['source']),check)
    assert check.execution and check.execution.software_version.startswith('SnpEff')
    assert check.status=='unresolved'  # Transcript-version differences are not silently stripped.
