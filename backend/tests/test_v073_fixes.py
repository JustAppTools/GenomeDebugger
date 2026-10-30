"""Coverage for provenance, parsing, size, check selection and nuclear scope."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.allele_check import AlleleCheck, fetch_allele_check
from app.bundle import create_bundle, verify_bundle, _verify_snpeff
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, comparison_input
from app.historical import HistoricalImport, import_historical
from app.limits import InputSizeError
from app.models import InvestigationInput
from app.ncbi import ReferenceCheckError, fetch_reference_check
from app.report import markdown_report
from app.snpeff import compare_snpeff
from test_ncbi import ncbi_transport
from test_snpeff import record, request, VCF

FIXTURES = Path(__file__).resolve().parents[2]/'fixtures'


def historical(source):
    return import_historical(HistoricalImport(query=source.query, raw_json=json.dumps(source.source_response),
        source_release=110, tool_version='110', generated_at='2024-01-01T00:00:00Z',
        assembly_accession=source.assembly_accession, source_uri='Constructed historical test artifact'))


def source_input(source):
    return comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id))


@pytest.mark.parametrize('origin', ['current_api', 'historical_artifact'])
@pytest.mark.parametrize('side', [0, 1])
def test_wrong_source_origin_rejected_by_api_and_bundle(tmp_path, monkeypatch, origin, side):
    monkeypatch.setattr(main, 'DB', tmp_path/'origin.db')
    source = record()
    if origin == 'historical_artifact':source = historical(source)
    storage.save_source_record(main.DB, source)
    payload = source_input(source)
    bundle = create_bundle(main.DB, compare(payload))
    payload.snapshots[side].provenance.configuration['source_origin'] = 'historical_artifact' if origin == 'current_api' else 'current_api'
    api = TestClient(main.app)
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 422 and 'source origin contradicts' in response.text
    assert storage.list_items(main.DB) == []
    bundle['entries']['investigation'] = compare(payload).model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    with pytest.raises(ValueError, match='source origin contradicts'):verify_bundle(bundle)


def test_reports_use_preserved_origins_including_mixed_and_legacy_data(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'reports.db')
    current = record()
    old = historical(current)
    for source in (current, old):storage.save_source_record(main.DB, source)
    api = TestClient(main.app)
    for source, label in [(current,'CURRENT PUBLIC SOURCE'), (old,'PRESERVED HISTORICAL OUTPUT')]:
        payload = source_input(source)
        for snapshot in payload.snapshots:snapshot.provenance.configuration.pop('source_origin', None)
        response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
        assert response.status_code == 200
        assert label in api.get(f"/api/investigations/{response.json()['id']}/report.md").text
        # Already-saved contradictory legacy flags cannot override actual origins.
        for snapshot in payload.snapshots:snapshot.provenance.configuration['source_origin'] = 'historical_artifact' if source is current else 'current_api'
        assert label in markdown_report(compare(payload), sources=[source])
    payload = source_input(current)
    payload.snapshots[1] = source_input(old).snapshots[1]
    report = markdown_report(compare(payload), sources=[current, old])
    assert 'MIXED CURRENT AND HISTORICAL SOURCES' in report
    assert 'Historical dates' in report and 'current when retrieved' in report
    assert 'source provenance unavailable' in markdown_report(compare(payload))


@pytest.mark.parametrize('warning_first', [True, False])
def test_duplicate_ann_is_rejected_in_import_and_bundle_replay(tmp_path, monkeypatch, warning_first):
    monkeypatch.setattr(main, 'DB', tmp_path/'ann.db')
    source = record()
    storage.save_source_record(main.DB, source)
    warning = 'T|missense_variant|MODERATE|G|ENSG00000162408|transcript|ENST00000377705|||||||||WARNING_REF_DOES_NOT_MATCH_GENOME'
    prefix, matching = VCF.split('ANN=')
    values = [warning, matching] if warning_first else [matching, warning]
    text = prefix + ';'.join('ANN='+value for value in values)
    response = TestClient(main.app).post(f'/api/sources/ensembl/records/{source.id}/snpeff-check', json=request(text).model_dump())
    assert response.status_code == 422 and 'duplicate INFO tag ANN' in response.text
    assert storage.latest_snpeff_check(main.DB, source.id) is None
    check = compare_snpeff(source, request())
    check.vcf_text = text
    check.vcf_sha256 = hashlib.sha256(text.encode()).hexdigest()
    check.id = digest({'source':source.id,'vcf':text,'checked_at':check.checked_at})[:20]
    with pytest.raises(ValueError, match='duplicate INFO tag ANN'):_verify_snpeff(source, check)


def large_input(length=420):
    payload = json.loads((FIXTURES/'transcript-switch.json').read_text(encoding='utf-8'))
    payload['controlled_lookup'] = None
    for snapshot in payload['snapshots']:
        snapshot['annotations'] = [{'gene_id':'G','transcript_id':f'T{i}','consequence':'x'*length} for i in range(1000)]
    return payload


def test_default_expansion_round_trips_and_candidate_checks_remain_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'large.db')
    api = TestClient(main.app)
    raw = large_input()
    assert len(json.dumps(raw,separators=(',',':')).encode()) < 1_000_000
    created = api.post('/api/investigations', json=raw)
    assert created.status_code == 200
    result = created.json()
    assert len(json.dumps(result['input'],separators=(',',':')).encode()) > 1_000_000
    assert api.post('/api/investigations', json=result['input']).json() == result
    case = api.post(f"/api/investigations/{result['id']}/regression-cases", json={'name':'Expanded input'}).json()
    candidate = api.post(f"/api/regression-cases/{case['id']}/runs", json={'candidate':result['input']})
    assert candidate.status_code == 200 and candidate.json()['status'] == 'passed'
    bundle = api.get(f"/api/investigations/{result['id']}/bundle").json()
    assert api.post('/api/bundles/import', json=bundle).status_code == 200
    too_large = large_input(500)
    assert api.post('/api/investigations', json=too_large).status_code == 413
    assert api.post(f"/api/regression-cases/{case['id']}/runs", json={'candidate':too_large}).status_code == 413
    entry = compare(InvestigationInput.model_validate(too_large)).model_dump(mode='json')
    oversized = {'format':'GenomeDebugger bundle','version':2,'engine_version':entry['engine_version'],
                 'entries':{'investigation':entry},'sha256':{'investigation':digest(entry)}}
    with pytest.raises(InputSizeError):verify_bundle(oversized)
    assert api.post('/api/bundles/import', json=oversized).status_code == 413


@pytest.mark.parametrize('kind', ['reference', 'annotation'])
def test_explicit_check_selection_is_pinned_and_none_omits_cached_checks(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(main, 'DB', tmp_path/'selection.db')
    source = record()
    storage.save_source_record(main.DB, source)
    if kind == 'reference':
        with httpx.Client(transport=ncbi_transport()) as client:first = fetch_reference_check(source, client)
        with httpx.Client(transport=ncbi_transport(base='A')) as client:second = fetch_reference_check(source, client)
        writer = storage.save_reference_check
    else:
        first = compare_snpeff(source, request())
        second = compare_snpeff(source, request(VCF.replace('3_prime_UTR_variant','missense_variant')))
        writer = storage.save_snpeff_check
    for check in (first, second):writer(main.DB, check)
    api = TestClient(main.app)
    selectors = {'transcript_a':source.transcripts[0].transcript_id,'transcript_b':source.transcripts[1].transcript_id}
    url = f'/api/sources/ensembl/records/{source.id}/compare'
    explicit = {**selectors,'reference_check_id':None,'annotation_check_id':None}
    omitted = api.post(url, json=explicit).json()['input']
    assert omitted['reference_check'] is None and omitted['annotation_check'] is None
    pinned = api.post(url, json={**explicit,kind+'_check_id':first.id}).json()['input'][kind+'_check']
    assert pinned['id'] == first.id and pinned['status'] == 'agree'
    # Omitted fields retain the documented legacy latest-check API behavior.
    assert api.post(url, json=selectors).json()['input'][kind+'_check']['id'] == second.id
    assert api.post(url, json={**explicit,kind+'_check_id':'missing'}).status_code == 422
    another = record()
    storage.save_source_record(main.DB, another)
    other_url = f'/api/sources/ensembl/records/{another.id}/compare'
    assert api.post(other_url, json={**explicit,kind+'_check_id':first.id}).status_code == 422


@pytest.mark.parametrize('sequence', ['MT','NC_012920.1'])
def test_mitochondrial_targets_are_rejected_without_requests_and_during_replay(sequence, tmp_path, monkeypatch):
    payload = InvestigationInput.model_validate_json((FIXTURES/'transcript-switch.json').read_text(encoding='utf-8'))
    payload.synthetic = False
    payload.controlled_lookup = None
    for snapshot in payload.snapshots:
        snapshot.variant = snapshot.variant.model_copy(update={'sequence_id':sequence,'position':100,'ref':'A','alt':'G','reference_context':None})
    result = compare(payload)
    def unexpected(_):raise AssertionError('An unsupported target must not be transmitted')
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ReferenceCheckError, match='Mitochondrial'):fetch_allele_check(result, client)
    fixture = json.loads((FIXTURES/'ncbi-repeat-deletion-observation.json').read_text(encoding='utf-8'))
    entry = result.model_dump(mode='json')
    check = AlleleCheck.model_validate(fixture['check']).model_dump(mode='json')
    bundle = {'format':'GenomeDebugger bundle','version':2,'engine_version':result.engine_version,
        'entries':{'investigation':entry,'allele_check':check},
        'sha256':{'investigation':digest(entry),'allele_check':digest(check)}}
    with pytest.raises(ValueError, match='Mitochondrial'):verify_bundle(bundle)
    # An old out-of-scope cached record is preserved but cannot be presented as
    # a currently valid check by the cache-only API.
    monkeypatch.setattr(main, 'DB', tmp_path/'legacy-mt.db')
    saved = AlleleCheck.model_validate(check).model_copy(update={'investigation_id':result.id,'input_sha256':result.input_sha256})
    storage.save(main.DB, result)
    storage.save_allele_check(main.DB, saved)
    response = TestClient(main.app).post(f'/api/investigations/{result.id}/allele-check', json={'mode':'cache_only'})
    assert response.status_code == 422 and 'Mitochondrial' in response.text
