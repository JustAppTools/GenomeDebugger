"""Regression coverage for the six 0.6.2 audit findings."""
import copy
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, SourceError, SourceRecord, comparison_input, fetch_record
from app.historical import HistoricalImport, import_historical
from app.legacy_engine_v062 import compare as compare_v062
from app.models import AnnotationCheckSummary
from app.report import markdown_report
from app.snpeff import SnpEffCheck
from test_ensembl import QUERY, fixture_transport
from test_snpeff import record
from test_v062_fixes import checked_input, saved_allele

FIXTURES = Path(__file__).resolve().parents[2]/'fixtures'


@pytest.mark.parametrize('local', [False, True])
def test_execution_origin_must_match_actual_preserved_check(tmp_path, monkeypatch, local):
    monkeypatch.setattr(main, 'DB', tmp_path/'origin.db')
    if local:
        fixture = json.loads((FIXTURES/'snpeff-mane-public-run.json').read_text())
        source = SourceRecord.model_validate(fixture['source'])
        check = SnpEffCheck.model_validate(fixture['check'])
        storage.save_source_record(main.DB, source)
        storage.save_snpeff_check(main.DB, check)
        summary = AnnotationCheckSummary.model_validate({
            **check.model_dump(include=set(AnnotationCheckSummary.model_fields)), 'matched_transcripts':len(check.matches)})
        payload = comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
            transcript_b=source.transcripts[1].transcript_id), annotation_check=summary)
    else:
        payload = checked_input(main.DB, 'annotation')
        check = storage.load_snpeff_check(main.DB, payload.annotation_check.id)
    for snapshot in payload.snapshots:
        snapshot.provenance.configuration['annotation_check_origin'] = 'local_execution' if local else 'user_supplied'
    api = TestClient(main.app)
    valid = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert valid.status_code == 200
    bundle = create_bundle(main.DB, compare(payload))
    report = markdown_report(compare(payload), annotation_check=check)
    assert ('preserved execution record;' in report) == local
    assert ('user-supplied output' in report) != local
    for snapshot in payload.snapshots:
        snapshot.provenance.configuration['annotation_check_origin'] = 'user_supplied' if local else 'local_execution'
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 422 and 'origin contradicts' in response.text
    result = compare(payload)
    assert storage.load(main.DB, result.id) is None
    # Pure comparator wording remains neutral even for untrusted draft metadata.
    assert 'Preserved local SnpEff run' not in next(e.description for e in result.evidence if e.id == 'annotation-check')
    bundle['entries']['investigation'] = result.model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    with pytest.raises(ValueError, match='origin contradicts'):
        verify_bundle(bundle)


def test_valid_v062_archive_and_missing_legacy_origin_still_replay(tmp_path):
    path = tmp_path/'legacy.db'
    payload = checked_input(path, 'annotation')
    old = compare_v062(payload)
    bundle = create_bundle(path, compare(payload))
    bundle['engine_version'] = '0.6.2'
    bundle['entries']['investigation'] = old.model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    assert verify_bundle(bundle)[0] == old
    exported = verify_bundle(create_bundle(path, old))[0]
    assert exported.id != old.id and exported.input_sha256 == old.input_sha256
    check = storage.load_snpeff_check(path, payload.annotation_check.id)
    for snapshot in old.input.snapshots:
        snapshot.provenance.configuration['annotation_check_origin'] = 'local_execution'
    # Reports for old saved data derive origin from the check, not old flags.
    report = markdown_report(old, annotation_check=check)
    assert 'recorded local execution' not in report and 'user-supplied output' in report


BAD_ROWS = [None, {'transcript_id':'LOST','consequence_terms':['stop_gained']},
    {'gene_id':'G','consequence_terms':['stop_gained']},
    {'transcript_id':'LOST','gene_id':'G','consequence_terms':[]},
    {'transcript_id':'LOST','gene_id':'G','consequence_terms':['']},
    {'transcript_id':'LOST','gene_id':'G','consequence_terms':[None]}]


@pytest.mark.parametrize('bad', BAD_ROWS)
def test_current_and_historical_adapters_reject_every_malformed_row(tmp_path, monkeypatch, bad):
    base = fixture_transport()
    def handler(req):
        response = base.handle_request(req)
        if req.url.path.startswith('/vep/'):
            body = response.json()
            body[0]['transcript_consequences'].append(bad)
            return httpx.Response(200, json=body)
        return response
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError, match='row 3 is malformed'):
            fetch_record(QUERY, client)
    source = record()
    raw = copy.deepcopy(source.source_response)
    raw['transcript_consequences'].append(bad)
    request = HistoricalImport(query=source.query, raw_json=json.dumps(raw), source_release=110,
        tool_version='110', generated_at='2024-01-01T00:00:00Z', assembly_accession=source.assembly_accession,
        source_uri='Constructed malformed audit fixture')
    with pytest.raises(ValueError, match='row 3 is malformed'):
        import_historical(request)
    monkeypatch.setattr(main, 'DB', tmp_path/'import.db')
    assert TestClient(main.app).post('/api/sources/historical-vep', json=request.model_dump(mode='json')).status_code == 422
    assert storage.list_source_records(main.DB) == []


def test_bundle_cannot_relabel_filtered_source_as_complete(tmp_path):
    source = record()
    storage.save_source_record(tmp_path/'source.db', source)
    payload = comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id))
    bundle = create_bundle(tmp_path/'source.db', compare(payload))
    entry = bundle['entries']['source_record']
    entry['source_response']['transcript_consequences'].append(BAD_ROWS[1])
    entry['source_response_sha256'] = hashlib.sha256(json.dumps(entry['source_response'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for snapshot in payload.snapshots:
        snapshot.provenance.input_sha256 = entry['source_response_sha256']
    bundle['entries']['investigation'] = compare(payload).model_dump(mode='json')
    bundle['sha256'] = {key:digest(value) for key,value in bundle['entries'].items()}
    with pytest.raises(ValueError, match='row 3 is malformed'):
        verify_bundle(bundle)
    stale = SourceRecord.model_validate(entry)
    with pytest.raises(ValueError, match='row 3 is malformed'):
        comparison_input(stale, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
            transcript_b=source.transcripts[1].transcript_id))


@pytest.mark.parametrize('change', ['consequence','missing_row','provenance'])
def test_source_claims_are_validated_before_persistence(tmp_path, monkeypatch, change):
    monkeypatch.setattr(main, 'DB', tmp_path/'source.db')
    source = record()
    storage.save_source_record(main.DB, source)
    payload = comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id))
    raw = payload.model_dump(mode='json')
    if change == 'consequence':raw['snapshots'][0]['annotation']['consequence'] = 'stop_gained'
    elif change == 'missing_row':raw['snapshots'][0]['annotations'] = []
    else:raw['snapshots'][0]['provenance']['tool_version'] = 'Invented version'
    api = TestClient(main.app)
    response = api.post('/api/investigations', json=raw)
    assert response.status_code == 422 and 'custom tool' in response.text
    assert storage.list_items(main.DB) == []
    raw['snapshots'][0]['provenance']['tool'] = 'Custom postprocessor'
    accepted = api.post('/api/investigations', json=raw)
    assert accepted.status_code == 200
    bundle = api.get(f"/api/investigations/{accepted.json()['id']}/bundle")
    assert bundle.status_code == 200
    assert api.post('/api/bundles/verify', json=bundle.json()).status_code == 200


def test_late_allele_response_cannot_restore_deleted_investigation_data(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'race.db')
    result, check = saved_allele(main.DB)
    started, release = threading.Event(), threading.Event()
    def delayed(_):
        started.set()
        assert release.wait(10)
        return check.model_copy(update={'id':'late-response'})
    monkeypatch.setattr(main, 'fetch_allele_check', delayed)
    api = TestClient(main.app)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda:api.post(f'/api/investigations/{result.id}/allele-check', json={'mode':'fetch'}))
        try:
            assert started.wait(10)
            assert api.delete(f'/api/investigations/{result.id}').status_code == 200
        finally:
            release.set()
        response = future.result(timeout=10)
    assert response.status_code == 404 and 'was not saved' in response.text
    assert storage.load(main.DB, result.id) is None
    assert storage.latest_allele_check(main.DB, result.id) is None


def test_owned_check_requires_parent_and_matching_input_in_same_transaction(tmp_path):
    result, check = saved_allele(tmp_path/'origin.db')
    target = tmp_path/'target.db'
    with pytest.raises(storage.RecordMissingError):
        storage.save_allele_check(target, check)
    with pytest.raises(storage.RecordConflictError):
        storage.save_bundle_records(target, result, [], allele=check.model_copy(update={'input_sha256':'0'*64}))
    assert storage.load(target, result.id) is None
    storage.save_bundle_records(target, result, [], allele=check)
    assert storage.latest_allele_check(target, result.id) == check
