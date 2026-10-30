"""Offline scope, chronological selection, and readable report regressions."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.allele_check import AlleleCheck, replay_allele_check
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, comparison_input
from app.models import AnnotationCheckSummary, InvestigationInput
from app.ncbi import ReferenceCheckError, fetch_reference_check
from app.report import markdown_report
from app.snpeff import compare_snpeff
from app.timestamps import timestamp_key
from test_ncbi import ncbi_transport
from test_snpeff import record, request, VCF

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures'
EARLY = '2024-01-01T12:00:00+10:00'
LATER = '2024-01-01T03:00:00+00:00'


def test_synthetic_allele_check_rejected_offline_and_legacy_records_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'scope.db')
    captured = json.loads((FIXTURES/'ncbi-repeat-deletion-observation.json').read_text(encoding='utf-8'))
    captured['input']['synthetic'] = True
    result = compare(InvestigationInput.model_validate(captured['input']))
    old = AlleleCheck.model_validate(captured['check'])
    with pytest.raises(ReferenceCheckError, match='Synthetic'):
        replay_allele_check(result, old.observations, old.checked_at)
    data = old.model_dump(mode='json', exclude={'id'})
    data.update(investigation_id=result.id, input_sha256=result.input_sha256)
    legacy = AlleleCheck(id=digest(data)[:20], **data)
    entries = {'investigation':result.model_dump(mode='json'), 'allele_check':legacy.model_dump(mode='json')}
    bundle = {'format':'GenomeDebugger bundle','version':2,'engine_version':result.engine_version,
              'entries':entries,'sha256':{key:digest(value) for key,value in entries.items()}}
    api = TestClient(main.app)
    for endpoint in ('verify','import'):
        response = api.post('/api/bundles/'+endpoint, json=bundle)
        assert response.status_code == 422 and 'Synthetic' in response.text
    assert storage.list_items(main.DB) == []
    # Simulate an already-saved record from the audited version.
    storage.save(main.DB, result)
    storage.save_allele_check(main.DB, legacy)
    response = api.post(f'/api/investigations/{result.id}/allele-check', json={'mode':'cache_only'})
    assert response.status_code == 422 and 'Synthetic' in response.text
    export = api.get(f'/api/investigations/{result.id}/bundle')
    assert export.status_code == 409 and 'Synthetic' in export.text
    report = api.get(f'/api/investigations/{result.id}/report.md')
    assert report.status_code == 200 and 'outside scope' in report.text
    assert 'Independent reference-backed allele identity' not in report.text
    assert storage.latest_allele_check(main.DB, result.id) == legacy


@pytest.mark.parametrize('kind', ['source', 'reference', 'annotation', 'allele'])
def test_latest_records_follow_actual_time_and_preserve_original_bytes(tmp_path, kind):
    db = tmp_path/'time.db'
    source = record()
    if kind == 'source':source.retrieved_at='2000-01-01T00:00:00Z'
    storage.save_source_record(db, source)
    if kind == 'source':
        original = source
        field = 'retrieved_at'
        writer = storage.save_source_record
        latest = lambda:storage.latest_source_record(db, source.query)
    elif kind == 'reference':
        with httpx.Client(transport=ncbi_transport()) as client:original=fetch_reference_check(source,client)
        field = 'checked_at'
        writer = storage.save_reference_check
        latest = lambda:storage.latest_reference_check(db, source.id)
    elif kind == 'annotation':
        original = compare_snpeff(source,request())
        field = 'checked_at'
        writer = storage.save_snpeff_check
        latest = lambda:storage.latest_snpeff_check(db, source.id)
    else:
        captured=json.loads((FIXTURES/'ncbi-repeat-deletion-observation.json').read_text(encoding='utf-8'))
        original=AlleleCheck.model_validate(captured['check'])
        parent=compare(InvestigationInput.model_validate(captured['input']))
        storage.save(db,parent.model_copy(update={'id':original.investigation_id}))
        field='checked_at'
        writer=storage.save_allele_check
        latest=lambda:storage.latest_allele_check(db,original.investigation_id)
    expected=[]
    for id_,date in [('early',EARLY),('later',LATER),('tie','2024-01-01T13:00:00+10:00')]:
        value=original.model_copy(update={'id':id_,field:date})
        writer(db,value);expected.append(value)
        assert latest() == value
    # UTC text is computed only during ordering; immutable JSON is unchanged.
    with closing(sqlite3.connect(db)) as connection:
        table,column=('source_records','record_json') if kind=='source' else (
            'snpeff_checks' if kind=='annotation' else 'reference_checks' if kind=='reference' else 'allele_checks','check_json')
        assert json.loads(connection.execute(f'SELECT {column} FROM {table} WHERE id=?',('later',)).fetchone()[0])[field] == LATER
        # Legacy invalid dates sort after valid dates, without being deleted.
        legacy=expected[-1].model_copy(update={'id':'legacy',field:'not-a-date'})
        connection.execute(f'UPDATE {table} SET id=?, {field}=?, {column}=? WHERE id=?',
                           ('legacy','not-a-date',legacy.model_dump_json(),'early'))
        connection.commit()
    assert latest() == expected[-1]
    if kind=='source':
        assert [r.id for r in storage.list_source_records(db,limit=2)] == ['tie','later']
        assert storage.load_source_record(db,'legacy') == legacy


def test_imported_offset_checks_select_the_later_disagreement(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'dates.db')
    source=record();storage.save_source_record(main.DB,source)
    api=TestClient(main.app)
    for date,vcf in [(EARLY,VCF),(LATER,VCF.replace('3_prime_UTR_variant','stop_gained'))]:
        check=compare_snpeff(source,request(vcf));check.checked_at=date
        check.id=digest({'source':source.id,'vcf':check.vcf_text,'checked_at':date})[:20]
        storage.save_snpeff_check(main.DB,check)
        summary=AnnotationCheckSummary.model_validate({**check.model_dump(include=set(AnnotationCheckSummary.model_fields)-{'matched_transcripts'}),'matched_transcripts':len(check.matches)})
        payload=comparison_input(source,CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
            transcript_b=source.transcripts[1].transcript_id),annotation_check=summary)
        bundle=create_bundle(main.DB,compare(payload))
        assert api.post('/api/bundles/import',json=bundle).status_code == 200
    selected=api.get(f'/api/sources/ensembl/records/{source.id}/snpeff-check').json()
    assert selected['status']=='disagree' and selected['checked_at']==LATER


@pytest.mark.parametrize('date', ['2024-01-01', '2024-01-01T12:00:00', 'not-a-date'])
def test_invalid_or_naive_new_record_timestamps_rejected(tmp_path, date):
    source=record()
    with pytest.raises(ValueError,match='timestamp'):storage.save_source_record(tmp_path/'bad.db',source.model_copy(update={'retrieved_at':date}))
    storage.save_source_record(tmp_path/'valid.db',source)
    payload=comparison_input(source,CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id))
    bundle=create_bundle(tmp_path/'valid.db',compare(payload))
    # Keep the invalid source ID consistent to reach timestamp admission checks.
    source.retrieved_at=date
    source.id=hashlib.sha256(json.dumps({'query':source.query.model_dump(),'release':source.releases,
        'assembly':source.assembly_accession,'raw':source.source_response_sha256,'retrieved_at':date},sort_keys=True).encode()).hexdigest()[:20]
    payload=comparison_input(source,CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id))
    bundle['entries']['source_record']=source.model_dump(mode='json')
    bundle['entries']['investigation']=compare(payload).model_dump(mode='json')
    bundle['sha256']={key:digest(value) for key,value in bundle['entries'].items()}
    with pytest.raises(ValueError,match='timestamp'):verify_bundle(bundle)


def test_report_labels_dates_and_overridden_outputs_as_not_important():
    payload=InvestigationInput.model_validate_json((FIXTURES/'transcript-switch.json').read_text(encoding='utf-8'))
    payload.controlled_lookup=None
    for snapshot,date in zip(payload.snapshots,['2024-01-01','2025-01-01']):
        from app.models import ClinicalAssertion
        snapshot.annotation.clinical=ClinicalAssertion(framework='F',condition_id='C',classification='unchanged',assertion_date=date)
    payload.meaningful_overrides={'consequence':False}
    report=markdown_report(compare(payload))
    assert 'Important by comparison rules' in report and 'representation only' not in report
    assert '| clinical.assertion_date | 2024-01-01 | 2025-01-01 | no |' in report
    assert any(line.startswith('| consequence |') and '| no |' in line for line in report.splitlines())
