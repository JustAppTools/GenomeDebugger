"""Regression coverage for the seven additional 0.6.1 audit findings."""
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, storage
from app.allele_check import AlleleCheck, SPDI, _validate_normalized_interval, replay_allele_check
from app.bundle import create_bundle, verify_bundle
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, comparison_input
from app.legacy_engine_v061 import compare as compare_v061
from app.models import AnnotationCheckSummary, InvestigationInput, ReferenceCheckSummary, VariantRecord
from app.ncbi import ReferenceCheckError, _manifest, fetch_reference_check
from app.regression import create_case
from app.snpeff import compare_snpeff
from test_ncbi import ncbi_transport
from test_snpeff import VCF, record, request

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures'


def checked_input(path, kind):
    source = record()
    storage.save_source_record(path, source)
    if kind == 'reference':
        with httpx.Client(transport=ncbi_transport()) as client:
            check = fetch_reference_check(source, client)
        storage.save_reference_check(path, check)
        summary = ReferenceCheckSummary.model_validate(check.model_dump(include=set(ReferenceCheckSummary.model_fields)))
    else:
        check = compare_snpeff(source, request())
        storage.save_snpeff_check(path, check)
        summary = AnnotationCheckSummary.model_validate({
            **{key: getattr(check, key) for key in AnnotationCheckSummary.model_fields if key != 'matched_transcripts'},
            'matched_transcripts': len(check.matches)})
    return comparison_input(source, CompareTranscripts(
        transcript_a=source.transcripts[0].transcript_id,
        transcript_b=source.transcripts[1].transcript_id), **{kind+'_check': summary})


@pytest.mark.parametrize('kind', ['reference', 'annotation'])
@pytest.mark.parametrize('field,value', [('assembly','GRCh37'), ('sequence_id','2'),
                                       ('position',6524706), ('alt','G')])
def test_checks_cannot_validate_a_transformed_variant(tmp_path, monkeypatch, kind, field, value):
    monkeypatch.setattr(main, 'DB', tmp_path/'source.db')
    payload = checked_input(main.DB, kind)
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    bundle = create_bundle(main.DB, compare(payload))
    raw = payload.model_dump(mode='json')
    for snapshot in raw['snapshots']:
        snapshot['provenance']['tool'] = 'Custom postprocessor'
        snapshot['variant'][field] = value
        if field == 'position':
            snapshot['variant']['reference_context'] = None
    assert api.post('/api/investigations', json=raw).status_code == 422
    result = compare(InvestigationInput.model_validate(raw))
    bundle['entries']['investigation'] = result.model_dump(mode='json')
    bundle['sha256']['investigation'] = digest(bundle['entries']['investigation'])
    with pytest.raises(ValueError, match='does not apply to the full variant'):
        verify_bundle(bundle)
    # The check is specific to the input allele. Explicit transformed outputs
    # can still cite the source after removing that inapplicable check.
    raw[kind+'_check'] = None
    assert api.post('/api/investigations', json=raw).status_code == 200


@pytest.mark.parametrize('kind', ['reference','annotation'])
def test_preserved_checks_allow_pinned_aliases_and_reject_missing_evidence(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(main, 'DB', tmp_path/'source.db')
    payload = checked_input(main.DB, kind)
    for snapshot in payload.snapshots:
        snapshot.variant.assembly = 'GCF_000001405.40'
        snapshot.variant.sequence_id = 'NC_000001.11'
        snapshot.provenance.tool = 'Custom postprocessor'
    api = TestClient(main.app)
    assert api.post('/api/investigations', json=payload.model_dump(mode='json')).status_code == 200
    verify_bundle(create_bundle(main.DB, compare(payload)))
    monkeypatch.setattr(main, 'DB', tmp_path/'empty.db')
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 422 and 'preserved source and check' in response.text


@pytest.mark.parametrize('warning', ['WARNING_REF_DOES_NOT_MATCH_GENOME', 'ERROR_CHROMOSOME_NOT_FOUND'])
def test_non_transcript_ann_warnings_invalidate_the_record(tmp_path, monkeypatch, warning):
    source = record()
    fields = ['T','intergenic_region','MODIFIER','','','intergenic_region','','','','','','','','','',warning]
    bad = request(VCF+','+'|'.join(fields))
    with pytest.raises(ValueError, match='warning|error'):
        compare_snpeff(source, bad)
    monkeypatch.setattr(main, 'DB', tmp_path/'source.db')
    storage.save_source_record(main.DB, source)
    response = TestClient(main.app).post(f'/api/sources/ensembl/records/{source.id}/snpeff-check', json=bad.model_dump())
    assert response.status_code == 422
    fields[-1] = ''
    assert compare_snpeff(source, request(VCF+','+'|'.join(fields))).status == 'agree'


def promoted_input():
    payload = InvestigationInput.model_validate_json((FIXTURES/'transcript-switch.json').read_text())
    payload.controlled_lookup = None
    first = payload.snapshots[0]
    second = payload.snapshots[1]
    second.variant = first.variant.model_copy(deep=True)
    second.annotation = first.annotation.model_copy(deep=True)
    alternate = first.variant.model_copy(update={'position':104, 'ref':'T', 'alt':'G'})
    row = first.annotation.model_copy(update={'transcript_id':'SECOND', 'consequence':'intron_variant'})
    first.variant_records = [VariantRecord(variant=alternate, annotations=[row])]
    second.variant_records = [VariantRecord(variant=first.variant.model_copy(deep=True),
                                            annotations=[first.annotation.model_copy(deep=True)])]
    second.variant = alternate.model_copy(deep=True)
    second.annotation = row.model_copy(deep=True)
    return payload


def test_primary_promotion_matches_complete_collections_and_scopes_drift():
    payload = promoted_input()
    assert not any(d.field.endswith('.presence') for d in compare(payload).differences)
    payload.snapshots[1].variant_records[0].annotations[0].consequence = 'stop_gained'
    scoped = [d for d in compare(payload).differences if d.field.startswith('variant_records[')]
    assert len(scoped) == 1 and scoped[0].field.endswith('.consequence')
    assert scoped[0].before == 'missense_variant' and scoped[0].after == 'stop_gained'
    payload.snapshots[1].variant_records = []
    missing = [d for d in compare(payload).differences if d.field.endswith('.presence')]
    assert len(missing) == 1 and missing[0].before == 'present' and missing[0].after is None


def test_v061_promoted_collection_archive_uses_frozen_rules(tmp_path):
    payload = promoted_input()
    old = compare_v061(payload)
    assert len([d for d in old.differences if d.field.endswith('.presence')]) == 2
    entry = old.model_dump(mode='json')
    bundle = {'format':'GenomeDebugger bundle', 'version':2, 'engine_version':'0.6.1',
              'entries':{'investigation':entry}, 'sha256':{'investigation':digest(entry)}}
    assert verify_bundle(bundle)[0] == old
    current = verify_bundle(create_bundle(tmp_path/'archive.db', old))[0]
    assert current.id != old.id and current.input_sha256 == old.input_sha256
    assert not any(d.field.endswith('.presence') for d in current.differences)


def saved_allele(path):
    fixture = json.loads((FIXTURES/'ncbi-repeat-deletion-observation.json').read_text())
    result = compare(InvestigationInput.model_validate(fixture['input']))
    captured = AlleleCheck.model_validate(fixture['check'])
    check = replay_allele_check(result, captured.observations, captured.checked_at)
    storage.save(path, result)
    storage.save_allele_check(path, check)
    return result, check


def test_delete_removes_owned_checks_and_keeps_shared_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'delete.db')
    result, check = saved_allele(main.DB)
    source = record()
    storage.save_source_record(main.DB, source)
    api = TestClient(main.app)
    assert api.delete(f'/api/investigations/{result.id}').status_code == 200
    assert storage.load(main.DB, result.id) is None
    assert storage.latest_allele_check(main.DB, result.id) is None
    assert storage.load_source_record(main.DB, source.id) == source
    assert api.delete(f'/api/investigations/{result.id}').status_code == 404


def test_delete_is_atomic_and_pinned_investigations_keep_checks(tmp_path):
    path = tmp_path/'atomic.db'
    result, check = saved_allele(path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER block_delete BEFORE DELETE ON investigations BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(sqlite3.IntegrityError):
        storage.delete_investigation(path, result.id)
    assert storage.load(path, result.id) == result
    assert storage.latest_allele_check(path, result.id) == check
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER block_delete')
    storage.save_case(path, create_case(result, 'Protected baseline'))
    with pytest.raises(ValueError, match='pinned'):
        storage.delete_investigation(path, result.id)
    assert storage.latest_allele_check(path, result.id) == check


def test_impossible_spdi_is_rejected_by_replay_and_bundle_api(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'allele.db')
    result, check = saved_allele(main.DB)
    bundle = create_bundle(main.DB, result)
    for observation in check.observations:
        observation.contextual_response['data']['position'] = 10**12
    with pytest.raises(ReferenceCheckError, match='chromosome length'):
        replay_allele_check(result, check.observations, check.checked_at)
    for observation in bundle['entries']['allele_check']['observations']:
        observation['contextual_response']['data']['position'] = 10**12
        observation['normalized']['position'] = 10**12
    bundle['sha256']['allele_check'] = digest(bundle['entries']['allele_check'])
    api = TestClient(main.app)
    for operation in ('verify','import'):
        assert api.post('/api/bundles/'+operation, json=bundle).status_code == 422


@pytest.mark.parametrize('offset,deleted,valid', [(0,'',True),(-1,'C',True),(0,'C',False),
                                               (1,'',False),(-1,'CC',False)])
def test_spdi_sequence_end_boundaries(offset, deleted, valid):
    chromosome = _manifest()['chromosomes']['1']
    allele = SPDI(seq_id=chromosome['refseq_accession'], position=chromosome['length']+offset,
                  deleted_sequence=deleted, inserted_sequence='A')
    if valid:
        _validate_normalized_interval(allele)
    else:
        with pytest.raises(ReferenceCheckError, match='chromosome length'):
            _validate_normalized_interval(allele)
