import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.allele_check import AlleleCheck, fetch_allele_check, replay_allele_check
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.models import InvestigationInput
from app.ncbi import ReferenceCheckError
from app.storage import save, save_allele_check
from app.version import ENGINE_VERSION

FIXTURE = json.loads((Path(__file__).resolve().parents[2]/'fixtures/ncbi-repeat-deletion-observation.json').read_text())


def result():
    return compare(InvestigationInput.model_validate(FIXTURE['input']))


def transport(mismatch=False):
    saved = AlleleCheck.model_validate(FIXTURE['check'])
    urls = {}
    for observation in saved.observations:
        urls[observation.reference_uri] = observation.reference_fasta.replace('\nCC', '\nAA') if mismatch else observation.reference_fasta
        urls[observation.contextual_uri] = observation.contextual_response
        urls[observation.hgvs_uri] = observation.hgvs_response
    def handler(request):
        data=urls[str(request.url)]
        if mismatch and not isinstance(data,str):
            raise AssertionError('Normalization requested despite reference mismatch')
        return httpx.Response(200,text=data) if isinstance(data,str) else httpx.Response(200,json=data)
    return httpx.MockTransport(handler)


def test_preserved_public_repeat_deletion_normalizes_to_same_allele():
    with httpx.Client(transport=transport()) as client:
        check=fetch_allele_check(result(),client)
    assert check.status=='agree'
    assert [o.normalized.text() for o in check.observations]==['NC_000001.11:10003:CCC:CC']*2
    assert replay_allele_check(result(),check.observations,check.checked_at)==check


def test_reference_mismatch_skips_normalization():
    with httpx.Client(transport=transport(mismatch=True)) as client:
        check=fetch_allele_check(result(),client)
    assert check.status=='disagree'
    assert all(not o.reference_matches and o.normalized is None for o in check.observations)


def test_synthetic_and_cross_assembly_are_not_transmitted():
    sample=result()
    sample.input.synthetic=True
    with pytest.raises(ReferenceCheckError,match='Synthetic'):
        fetch_allele_check(sample)
    sample.input.synthetic=False
    sample.input.snapshots[0].variant.assembly='GRCh37'
    with pytest.raises(ReferenceCheckError,match='GRCh38'):
        fetch_allele_check(sample)


def test_allele_check_survives_bundle_and_cache_round_trip(tmp_path,monkeypatch):
    sample=result()
    with httpx.Client(transport=transport()) as client:
        check=fetch_allele_check(sample,client)
    monkeypatch.setattr(main,'DB',tmp_path/'first.db')
    save(main.DB,sample);save_allele_check(main.DB,check)
    api=TestClient(main.app)
    response=api.post(f'/api/investigations/{sample.id}/allele-check',json={'mode':'cache_only'})
    assert response.json()['status']=='agree'
    bundle=create_bundle(main.DB,sample)
    assert verify_bundle(bundle)[4]==check
    monkeypatch.setattr(main,'DB',tmp_path/'second.db')
    assert api.post('/api/bundles/import',json=bundle).status_code==200
    assert api.post(f'/api/investigations/{sample.id}/allele-check',json={'mode':'cache_only'}).json()['id']==check.id
    report=api.get(f'/api/investigations/{sample.id}/report.md')
    assert report.status_code==200 and 'NC_000001.11:10003:CCC:CC' in report.text
    assert f'Engine version: `{ENGINE_VERSION}`' in report.text
    bundle['entries']['allele_check']['observations'][0]['normalized']['position']+=1
    bundle['sha256']['allele_check']=digest(bundle['entries']['allele_check'])
    with pytest.raises(ValueError,match='preserved reference'):
        verify_bundle(bundle)
