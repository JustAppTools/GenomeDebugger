"""Regression coverage for the application 0.7.6 audit and replay compatibility."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.legacy_engine_v063 import compare as compare_v063
from app.models import Annotation
from app.regression import create_case, run_case
from app.version import ENGINE_VERSION
from test_regression import baseline
from test_snpeff import record
from test_snpeff_runner import install_fixture


def test_protein_finding_links_to_affected_output_and_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'evidence.db')
    payload=baseline().input.model_copy(deep=True)
    payload.controlled_lookup=None
    payload.snapshots[1].annotation.consequence=payload.snapshots[0].annotation.consequence
    response=TestClient(main.app).post('/api/investigations',json=payload.model_dump(mode='json'))
    assert response.status_code==200
    result=response.json()
    finding=next(item for item in result['findings'] if item['cause']=='transcript selection')
    linked={item['data']['field'] for item in result['evidence'] if item['id'] in finding['evidence_ids']}
    assert finding['affected_fields']==['protein_consequence']
    assert linked=={'protein_consequence','transcript_id'}


def test_historical_term_order_does_not_become_an_effect_change(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'terms.db')
    source=record()
    raw=copy.deepcopy(source.source_response)
    terms=['intron_variant','non_coding_transcript_variant']
    api=TestClient(main.app)
    sources=[]
    for order in (terms,list(reversed(terms))):
        raw['transcript_consequences'][0]['consequence_terms']=order
        artifact=json.dumps([raw],indent=2)
        response=api.post('/api/sources/historical-vep',json={'query':source.query.model_dump(),
            'raw_json':artifact,'source_release':110,'tool_version':'audit-fixture',
            'generated_at':'2024-01-01T12:00:00Z','assembly_accession':source.assembly_accession,'source_uri':'audit fixture'})
        assert response.status_code==200,response.text
        assert response.json()['artifact']['text']==artifact
        sources.append(response.json())
    response=api.post('/api/sources/compare',json={'source_a':sources[0]['id'],'source_b':sources[1]['id'],
        'transcript_a':source.transcripts[0].transcript_id,'transcript_b':source.transcripts[0].transcript_id})
    assert response.status_code==200
    result=response.json()
    assert not any(item['field']=='consequence' or item['field'].endswith('.consequence') for item in result['differences'])
    assert result['input']['snapshots'][0]['annotation']['consequence']!=';'.join(reversed(terms))
    assert result['input']['snapshots'][1]['annotation']['consequence']==';'.join(reversed(terms))
    verify_bundle(create_bundle(main.DB,storage.load(main.DB,result['id'])))


def test_candidate_term_order_is_semantic_but_input_drift_remains_visible():
    payload=baseline().input.model_copy(deep=True);payload.controlled_lookup=None
    for index,snapshot in enumerate(payload.snapshots):
        snapshot.annotation.consequence='a;b' if index==0 else 'c;d'
        snapshot.annotations=[Annotation(gene_id='OTHER',transcript_id='OTHER',consequence='e;f')]
    case=create_case(compare(payload),'Term order')
    candidate=payload.model_copy(deep=True)
    for snapshot in candidate.snapshots:
        snapshot.annotation.consequence=';'.join(reversed(snapshot.annotation.consequence.split(';')))
        snapshot.annotations[0].consequence='f;e'
    result=run_case(case,candidate)
    assert result.status=='passed'
    assert 'snapshots[0].annotation.consequence' in result.input_changes
    # Unrelated user metadata must stay byte-sensitive even when its key ends
    # with "consequence"; only actual annotation outputs use set semantics.
    candidate.snapshots[0].provenance.configuration['custom.consequence']='b;a'
    assert 'snapshots[0].provenance.configuration.custom.consequence' in run_case(case,candidate).input_changes


def test_archived_v063_rules_verify_and_export_as_separate_current_replay(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'archive.db')
    payload=baseline().input.model_copy(deep=True);payload.controlled_lookup=None
    payload.snapshots[1].annotation.consequence=payload.snapshots[0].annotation.consequence
    original=compare_v063(payload)
    assert original.engine_version=='0.6.3'
    entries={'investigation':original.model_dump(mode='json')}
    bundle={'format':'GenomeDebugger bundle','version':2,'engine_version':'0.6.3',
            'entries':entries,'sha256':{key:digest(value) for key,value in entries.items()}}
    assert verify_bundle(bundle)[0]==original
    api=TestClient(main.app)
    assert api.post('/api/bundles/import',json=bundle).status_code==200
    exported=api.get(f'/api/investigations/{original.id}/bundle').json()
    assert exported['engine_version']==ENGINE_VERSION
    assert exported['replayed_from_id']==original.id
    assert exported['entries']['investigation']['id']!=original.id
    verify_bundle(exported)
    assert storage.load(main.DB,original.id)==original


@pytest.mark.parametrize('field',['value','key','override'])
def test_nested_unicode_is_rejected_as_bounded_validation_error(tmp_path,monkeypatch,field):
    monkeypatch.setattr(main,'DB',tmp_path/'unicode.db')
    raw=baseline().input.model_dump(mode='json')
    if field=='value':raw['snapshots'][0]['provenance']['configuration']['test']='\ud800'
    elif field=='key':raw['snapshots'][0]['provenance']['configuration']['\udfff']='valid'
    else:raw['meaningful_overrides']['\ud800']=False
    response=TestClient(main.app,raise_server_exceptions=False).post('/api/investigations',content=json.dumps(raw),headers={'content-type':'application/json'})
    assert response.status_code==422 and 'invalid Unicode' in response.text
    assert len(response.content)<1500
    assert storage.list_items(main.DB)==[]


def test_invalid_unicode_in_raw_historical_extensions_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'unicode.db')
    source=record();raw=copy.deepcopy(source.source_response);raw['extra_metadata']='\ud800'
    response=TestClient(main.app,raise_server_exceptions=False).post('/api/sources/historical-vep',json={
        'query':source.query.model_dump(),'raw_json':json.dumps([raw]),'source_release':110,'tool_version':'audit',
        'generated_at':'2024-01-01T12:00:00Z','assembly_accession':source.assembly_accession,'source_uri':'audit'})
    assert response.status_code==422 and 'invalid Unicode' in response.text
    assert storage.list_source_records(main.DB)==[]


def test_valid_unicode_metadata_round_trips(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'unicode.db')
    raw=baseline().input.model_dump(mode='json')
    raw['snapshots'][0]['provenance']['configuration']['label']='Genome 🧬 é'
    response=TestClient(main.app).post('/api/investigations',content=json.dumps(raw),headers={'content-type':'application/json'})
    assert response.status_code==200
    assert response.json()['input']['snapshots'][0]['provenance']['configuration']['label']=='Genome 🧬 é'


@pytest.mark.parametrize('bad',[[],42,None,{'genome':None},{'genome':[]},'text'])
def test_wrong_manifest_roots_and_genomes_report_unconfigured(tmp_path,monkeypatch,bad):
    path=tmp_path/'runtime.json';path.write_text(json.dumps(bad),encoding='utf-8')
    monkeypatch.setenv('GENOMEDEBUGGER_SNPEFF_MANIFEST',str(path))
    response=TestClient(main.app,raise_server_exceptions=False).get('/api/tools/snpeff')
    assert response.status_code==200
    assert response.json()['configured'] is False
    assert response.json()['detail']


@pytest.mark.parametrize('field,bad',[('java',None),('jar_sha256',42),('database_files',[]),('database_files',{'file':None}),('snpeff_version',[]),('sources',None)])
def test_wrong_manifest_field_types_never_execute(tmp_path,monkeypatch,field,bad):
    manifest=install_fixture(tmp_path,monkeypatch);manifest[field]=bad
    (tmp_path/'runtime.json').write_text(json.dumps(manifest),encoding='utf-8')
    monkeypatch.setattr(main,'DB',tmp_path/'checks.db')
    source=record();storage.save_source_record(main.DB,source)
    calls=[]
    monkeypatch.setattr('app.snpeff_runner.subprocess.run',lambda *args,**kwargs:calls.append(args))
    api=TestClient(main.app,raise_server_exceptions=False)
    assert api.get('/api/tools/snpeff').json()['configured'] is False
    assert api.post(f'/api/sources/ensembl/records/{source.id}/snpeff-run').status_code==422
    assert calls==[]


def test_library_cursor_survives_insertions_anchor_deletion_and_back_navigation(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'pages.db')
    api=TestClient(main.app)
    raw=baseline().input.model_dump(mode='json')
    ids=[]
    for i in range(5):
        response=api.post('/api/investigations',json={**raw,'title':f'Page_{i}'})
        assert response.status_code==200;ids.append(response.json()['id'])
    first=api.get('/api/investigations/page',params={'q':'Page_','limit':3}).json()
    assert [item['id'] for item in first['items']]==ids[:1:-1]
    inserted=api.post('/api/investigations',json={**raw,'title':'Page_new'}).json()['id']
    assert api.delete('/api/investigations/'+first['items'][-1]['id']).status_code==200
    second=api.get('/api/investigations/page',params={'q':'Page_','limit':3,'before':first['next_before'],'ceiling':first['ceiling']}).json()
    assert [item['id'] for item in second['items']]==list(reversed(ids[:2]))
    assert second['next_before'] is None
    back=api.get('/api/investigations/page',params={'q':'Page_','limit':3,'ceiling':first['ceiling']}).json()
    assert inserted not in {item['id'] for item in back['items']}
    assert len({item['id'] for item in [*first['items'],*second['items']]})==5
    assert api.get('/api/investigations/page',params={'before':-1}).status_code==422
