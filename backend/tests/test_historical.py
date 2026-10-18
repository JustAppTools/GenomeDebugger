import copy
import hashlib
import json
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.bundle import create_bundle,verify_bundle
from app.engine import compare,digest
from app.ensembl import SourceQuery,fetch_record
from app.historical import HistoricalImport,SourcePair,comparison_pair,import_historical
from app.storage import latest_source_record,save_source_record
from test_ensembl import fixture_transport


def current():
    with httpx.Client(transport=fixture_transport()) as client:
        return fetch_record(SourceQuery(chromosome='1',position=6524705,ref='C',alt='T'),client)


def request(record):
    # Synthetic historical metadata exercises import mechanics, not a biological historical claim.
    raw=copy.deepcopy(record.source_response)
    raw['transcript_consequences'][0]['consequence_terms']=['missense_variant']
    return HistoricalImport(query=record.query,raw_json=json.dumps([raw],indent=2),source_release=110,
        tool_version='110-test-fixture',generated_at='2024-01-01T12:00:00Z',
        assembly_accession=record.assembly_accession,source_uri='test fixture: historical output')


def test_historical_import_preserves_raw_bytes_and_stays_out_of_current_cache(tmp_path):
    live=current();payload=request(live);old=import_historical(payload)
    assert old.origin=='historical_artifact' and old.artifact['text']==payload.raw_json
    save_source_record(tmp_path/'cache.db',old)
    assert latest_source_record(tmp_path/'cache.db',live.query) is None
    save_source_record(tmp_path/'cache.db',live)
    assert latest_source_record(tmp_path/'cache.db',live.query).id==live.id
    payload.raw_json='\ufeff'+payload.raw_json
    bom=import_historical(payload)
    assert bom.artifact['text'].startswith('\ufeff')
    assert bom.artifact['sha256']==hashlib.sha256(payload.raw_json.encode('utf-8')).hexdigest()


def test_two_source_comparison_and_bundle_round_trip(tmp_path,monkeypatch):
    live=current();old=import_historical(request(live))
    selection=SourcePair(source_a=old.id,source_b=live.id,
        transcript_a=old.transcripts[0].transcript_id,transcript_b=live.transcripts[0].transcript_id)
    result=compare(comparison_pair(old,live,selection))
    assert result.identity.status=='unresolved'
    assert any(d.field=='consequence' for d in result.differences)
    assert not any(f.status=='verified' for f in result.findings)
    path=tmp_path/'source.db'
    for record in (old,live):save_source_record(path,record)
    bundle=create_bundle(path,result)
    assert len(bundle['entries']['source_records'])==2
    assert verify_bundle(bundle)[0]==result
    monkeypatch.setattr(main,'DB',tmp_path/'imported.db')
    client=TestClient(main.app)
    assert client.post('/api/bundles/import',json=bundle).status_code==200
    assert len(client.get('/api/sources/records').json())==2
    forged=bundle['entries']['source_records'][0]
    if forged['origin']!='historical_artifact':forged=bundle['entries']['source_records'][1]
    forged['artifact']['generated_at']='2020-01-01T00:00:00Z'
    bundle['sha256']['source_records']=digest(bundle['entries']['source_records'])
    with pytest.raises(ValueError,match='Historical'):
        verify_bundle(bundle)


def test_historical_api_import_and_replay(tmp_path,monkeypatch):
    live=current()
    monkeypatch.setattr(main,'DB',tmp_path/'api.db')
    save_source_record(main.DB,live)
    client=TestClient(main.app)
    response=client.post('/api/sources/historical-vep',json=request(live).model_dump(mode='json'))
    assert response.status_code==200
    old=response.json()
    result=client.post('/api/sources/compare',json={'source_a':old['id'],'source_b':live.id,
        'transcript_a':old['transcripts'][0]['transcript_id'],'transcript_b':live.transcripts[0].transcript_id})
    assert result.status_code==200
    assert result.json()['input']['snapshots'][0]['provenance']['tool_version']=='110-test-fixture'


@pytest.mark.parametrize('date',['2024-01-01T00:00:00','2099-01-01T00:00:00Z'])
def test_historical_import_rejects_ambiguous_or_future_dates(date):
    payload=request(current()).model_copy(update={'generated_at':datetime.fromisoformat(date)})
    with pytest.raises(ValueError):import_historical(payload)
