import copy
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, comparison_input
from app.legacy_engine_v060 import compare as compare_v060
from app.models import AnnotationCheckSummary, InvestigationInput, ClinicalAssertion, VariantRecord
from app.allele_check import AlleleCheck
from app.ncbi import fetch_reference_check
import httpx
from test_ncbi import ncbi_transport
from app.regression import create_case
from app.snpeff import compare_snpeff
from app.version import ENGINE_VERSION
from test_snpeff import record, request

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/transcript-switch.json'


def source_bundle(path, annotation=False):
    source = record()
    storage.save_source_record(path, source)
    summary = None
    if annotation:
        check = compare_snpeff(source, request())
        storage.save_snpeff_check(path, check)
        summary = AnnotationCheckSummary(**{key:getattr(check,key) for key in (
            'id','source_record_id','source_response_sha256','vcf_sha256','snpeff_version',
            'genome_database','database_sha256','status')}, matched_transcripts=len(check.matches))
    result = compare(comparison_input(source, CompareTranscripts(
        transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id), annotation_check=summary))
    return create_bundle(path, result)


def replace_input(bundle, payload):
    bundle['entries']['investigation'] = compare(InvestigationInput.model_validate(payload)).model_dump(mode='json')
    bundle['sha256'] = {key:digest(value) for key,value in bundle['entries'].items()}


@pytest.mark.parametrize('change', ['consequence','variant','extra_row','missing_row','provenance'])
def test_bundle_rejects_source_snapshot_contradictions(tmp_path, change):
    bundle = source_bundle(tmp_path/'origin.db')
    payload = copy.deepcopy(bundle['entries']['investigation']['input'])
    snapshot = payload['snapshots'][0]
    if change == 'consequence':snapshot['annotation']['consequence'] = 'stop_gained'
    if change == 'variant':snapshot['variant']['alt'] = 'G'
    if change == 'extra_row':snapshot['annotations'][0]['gene_id'] = 'WRONG-GENE'
    if change == 'missing_row':snapshot['annotations'] = []
    if change == 'provenance':snapshot['provenance']['tool_version'] = 'invented'
    replace_input(bundle, payload)
    with pytest.raises(ValueError,match='VEP snapshot'):
        verify_bundle(bundle)


def test_explicit_custom_postprocessor_can_cite_source_as_input(tmp_path):
    bundle = source_bundle(tmp_path/'origin.db')
    payload = copy.deepcopy(bundle['entries']['investigation']['input'])
    payload['snapshots'][0]['provenance']['tool'] = 'Custom postprocessor'
    payload['snapshots'][0]['annotation']['consequence'] = 'stop_gained'
    replace_input(bundle, payload)
    assert verify_bundle(bundle)[0].input.snapshots[0].provenance.tool == 'Custom postprocessor'


def test_snpeff_explanation_cannot_contradict_replayed_outcome(tmp_path):
    bundle = source_bundle(tmp_path/'origin.db', annotation=True)
    bundle['entries']['snpeff_check']['explanation'] = 'Every matched transcript DISAGREES.'
    bundle['sha256']['snpeff_check'] = digest(bundle['entries']['snpeff_check'])
    with pytest.raises(ValueError,match='SnpEff check'):
        verify_bundle(bundle)


def test_import_conflict_is_rejected_before_any_new_record_is_saved(tmp_path, monkeypatch):
    bundle = source_bundle(tmp_path/'origin.db', annotation=True)
    changed = copy.deepcopy(bundle)
    changed['entries']['snpeff_check']['snpeff_version'] = 'DIFFERENT-VERSION'
    payload = changed['entries']['investigation']['input']
    payload['annotation_check']['snpeff_version'] = 'DIFFERENT-VERSION'
    replace_input(changed, payload)
    verify_bundle(changed)  # Individually consistent; conflicts with existing saved bytes.
    monkeypatch.setattr(main,'DB',tmp_path/'import.db')
    api = TestClient(main.app)
    assert api.post('/api/bundles/import',json=bundle).status_code == 200
    response = api.post('/api/bundles/import',json=changed)
    assert response.status_code == 409
    assert storage.load(main.DB,changed['entries']['investigation']['id']) is None
    original = storage.load(main.DB,bundle['entries']['investigation']['id'])
    verify_bundle(create_bundle(main.DB,original))
    # Re-importing identical records needs no new capacity.
    monkeypatch.setattr(storage,'_guard_size',lambda *_: (_ for _ in ()).throw(storage.StorageLimitError('full')))
    assert api.post('/api/bundles/import',json=bundle).status_code == 200


def test_import_rolls_back_all_records_on_mid_transaction_failure(tmp_path, monkeypatch):
    bundle = source_bundle(tmp_path/'origin.db', annotation=True)
    monkeypatch.setattr(main,'DB',tmp_path/'import.db')
    insert = storage._insert_entry
    calls = []
    def fail_after_second_write(db, table, values):
        insert(db,table,values)
        calls.append(table)
        if len(calls) == 2:raise storage.StorageLimitError('Storage full')
    monkeypatch.setattr(storage,'_insert_entry',fail_after_second_write)
    assert TestClient(main.app).post('/api/bundles/import',json=bundle).status_code == 507
    with sqlite3.connect(main.DB) as db:
        for table in ('source_records','snpeff_checks','investigations','reference_checks','allele_checks'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_deleted_pages_are_reused_under_storage_budget(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOMEDEBUGGER_MAX_DB_MB','10')
    path = tmp_path/'quota.db'
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    for side,snapshot in enumerate(data['snapshots']):
        snapshot['annotations'] = [{'gene_id':'BIG','transcript_id':f'T{i}',
            'consequence':('A' if side == 0 else 'B')*500} for i in range(500)]
    saved = []
    for i in range(20):
        data['title'] = f'Quota record {i}'
        result = compare(InvestigationInput.model_validate(data))
        try:storage.save(path,result);saved.append(result.id)
        except storage.StorageLimitError:break
    else:pytest.fail('Expected budget to be reached')
    for id_ in saved:storage.delete_investigation(path,id_)
    storage.save(path,result)
    assert storage.load(path,result.id) == result


@pytest.mark.parametrize('field,value', [('engine_version',[]),('engine_version',{}),('engine_version',None),
    ('version','2'),('version',2.0),('entries',[]),('sha256',[]),('exported_at',[])])
def test_bad_bundle_manifest_returns_validation_error(tmp_path,monkeypatch,field,value):
    sample = compare(InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8')))
    bundle = create_bundle(tmp_path/'origin.db',sample)
    bundle[field] = value
    monkeypatch.setattr(main,'DB',tmp_path/'target.db')
    api = TestClient(main.app,raise_server_exceptions=False)
    for endpoint in ('verify','import'):
        assert api.post('/api/bundles/'+endpoint,json=bundle).status_code == 422


def test_v060_archive_uses_frozen_rules_and_exports_separate_current_result(tmp_path):
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8'))
    for index,snapshot in enumerate(payload.snapshots):
        snapshot.annotation.clinical=ClinicalAssertion(framework='ACMG',condition_id='MONDO:1',
            classification='uncertain',assertion_date=f'202{index+3}-01-01')
    old = compare_v060(payload)
    assert not any(d.field.endswith('assertion_date') for d in old.differences)
    entry = old.model_dump(mode='json')
    bundle = {'format':'GenomeDebugger bundle','version':2,'engine_version':'0.6.0',
        'entries':{'investigation':entry},'sha256':{'investigation':digest(entry)}}
    assert verify_bundle(bundle)[0] == old
    exported = create_bundle(tmp_path/'archive.db',old)
    current = verify_bundle(exported)[0]
    assert current.engine_version == ENGINE_VERSION and current.id != old.id
    assert current.input_sha256 == old.input_sha256
    assert any(d.field.endswith('assertion_date') for d in current.differences)


def test_dates_are_compared_for_primary_additional_and_other_variant_rows():
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8'))
    for index,snapshot in enumerate(payload.snapshots):
        row = payload.snapshots[0].annotation.model_copy(deep=True)
        row.clinical = ClinicalAssertion(framework='ACMG',condition_id='MONDO:1',classification='uncertain',
                                        assertion_date=f'202{index+3}-01-01')
        snapshot.annotation = row
        snapshot.annotations = [row.model_copy(update={'transcript_id':'EXTRA'})]
        snapshot.variant_records = [VariantRecord(variant=snapshot.variant.model_copy(update={
            'position':200,'reference_context':None}),annotations=[row.model_copy(deep=True)])]
        snapshot.variant = payload.snapshots[0].variant.model_copy(deep=True)
        # Both additional variants have identical exact representations.
        snapshot.variant_records[0].variant = snapshot.variant.model_copy(update={'position':200,'reference_context':None})
    # Align padded primary alleles and additional variant representations.
    payload.snapshots[1].variant_records[0].variant = payload.snapshots[0].variant_records[0].variant.model_copy(deep=True)
    result = compare(payload)
    dates = [d for d in result.differences if d.field.endswith('assertion_date')]
    assert len(dates) == 3 and all(d.category == 'clinical_metadata' and not d.meaningful for d in dates)


def test_generated_long_difference_path_accepts_override():
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8'))
    for index,snapshot in enumerate(payload.snapshots):
        snapshot.annotations = [snapshot.annotation.model_copy(update={
            'gene_id':'G'*100,'transcript_id':'T'*100,'consequence':str(index)})]
    field = max((d.field for d in compare(payload).differences),key=len)
    assert len(field) > 200
    raw = payload.model_dump(mode='json');raw['meaningful_overrides'] = {field:False}
    result = compare(InvestigationInput.model_validate(raw))
    assert not next(d for d in result.differences if d.field == field).meaningful


def test_case_discovery_filters_before_pagination(tmp_path,monkeypatch):
    sample = compare(InvestigationInput.model_validate_json(FIXTURE.read_text(encoding='utf-8')))
    other = compare(sample.input.model_copy(update={'title':'Other investigation'}))
    monkeypatch.setattr(main,'DB',tmp_path/'cases.db')
    original = create_case(sample,'Original baseline');storage.save_case(main.DB,original)
    for i in range(100):storage.save_case(main.DB,create_case(other,f'Newer baseline {i}'))
    api = TestClient(main.app)
    found = api.get('/api/regression-cases',params={'source_investigation_id':sample.id}).json()
    assert [item['id'] for item in found] == [original.id]
    older = api.get('/api/regression-cases',params={'offset':100}).json()
    assert [item['id'] for item in older] == [original.id]


@pytest.mark.parametrize('kind', ['source','reference','allele'])
def test_immutable_artifact_conflicts_never_replace_existing_bytes(tmp_path,kind):
    path=tmp_path/'immutable.db'
    if kind=='source':
        artifact=record();writer=storage.save_source_record;loader=storage.load_source_record
        changed=artifact.model_copy(update={'source_uri':'different'})
    elif kind=='reference':
        with httpx.Client(transport=ncbi_transport()) as client:artifact=fetch_reference_check(record(),client)
        writer=storage.save_reference_check;loader=storage.load_reference_check
        changed=artifact.model_copy(update={'checked_at':'changed'})
    else:
        captured=json.loads((FIXTURE.parent/'ncbi-repeat-deletion-observation.json').read_text(encoding='utf-8'))
        artifact=AlleleCheck.model_validate(captured['check']);writer=storage.save_allele_check
        parent=compare(InvestigationInput.model_validate(captured['input']))
        storage.save(path,parent.model_copy(update={'id':artifact.investigation_id}))
        changed=artifact.model_copy(update={'checked_at':'changed'})
        loader=lambda path,_:storage.latest_allele_check(path,artifact.investigation_id)
    writer(path,artifact)
    with pytest.raises(storage.RecordConflictError):writer(path,changed)
    assert loader(path,artifact.id)==artifact


def test_legacy_selected_vep_snapshot_keeps_its_equivalent_release_label(tmp_path):
    bundle=source_bundle(tmp_path/'legacy.db')
    payload=bundle['entries']['investigation']['input']
    for snapshot in payload['snapshots']:
        snapshot['provenance']['configuration'].pop('source_annotation_scope')
        snapshot['provenance']['source_release']='Ensembl 116'
        snapshot['annotations']=[]
    replace_input(bundle,payload)
    assert verify_bundle(bundle)[0].input.snapshots[0].provenance.source_release=='Ensembl 116'
