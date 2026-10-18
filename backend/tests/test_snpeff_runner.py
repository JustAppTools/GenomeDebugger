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
    genome='GRCh38.mane.1.0.ensembl'
    base=tmp_path/'data'/genome
    base.mkdir(parents=True);(base/'snpEffectPredictor.bin').write_bytes(b'database')
    paths.update(data_dir=str(base.parent),genome=genome,snpeff_version='fixture-version',
                 assembly_name='GRCh38',assembly_accession='GCA_000001405.29',
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
        calls[-1] += (Path(command[-1]).read_bytes(),)
        return SimpleNamespace(returncode=0,stdout=VCF,stderr='')
    monkeypatch.setattr('app.snpeff_runner.subprocess.run',run)
    source=record()
    check=run_snpeff(source)
    assert check.execution and check.execution.database_sha256==digest(paths['database_files'])
    assert calls[0][2] == check.execution.input_vcf.encode('utf-8')
    assert hashlib.sha256(calls[0][2]).hexdigest() == check.execution.input_vcf_sha256
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


@pytest.mark.parametrize('change', ['database','manifest_assembly','missing_metadata','source_assembly'])
def test_wrong_or_unknown_database_build_never_executes(tmp_path,monkeypatch,change):
    paths=install_fixture(tmp_path,monkeypatch)
    source=record()
    if change=='database':paths['genome']='GRCh37.test'
    if change=='manifest_assembly':paths['assembly_name']='GRCh37'
    if change=='missing_metadata':paths.pop('assembly_accession')
    if change=='source_assembly':source.assembly_accession='GCA_000001405.14'
    (tmp_path/'runtime.json').write_text(json.dumps(paths))
    calls=[]
    monkeypatch.setattr('app.snpeff_runner.subprocess.run',lambda *a,**kw:calls.append(a))
    with pytest.raises(ValueError,match='assembly|database/build'):
        run_snpeff(source)
    assert calls==[]
