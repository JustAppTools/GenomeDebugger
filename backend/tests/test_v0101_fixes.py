"""Consequence parsing, historical replay and lossless readable reports."""
import json
from pathlib import Path

import pytest

from app import legacy_engine_v067, legacy_regression_v067
from app.bundle import verify_bundle
from app.engine import compare, digest
from app.models import InvestigationInput
from app.regression import create_case, run_case, validate_saved_run, RegressionRun
from app.report import markdown_report


def supplied():
    value=InvestigationInput.model_validate_json((Path(__file__).resolve().parents[2]/'fixtures/transcript-switch.json').read_text())
    value.controlled_lookup=None
    value.snapshots[1]=value.snapshots[0].model_copy(deep=True)
    value.snapshots[1].id='B'
    return value


@pytest.mark.parametrize('left,right',[
    ('missense_variant; synonymous_variant','synonymous_variant&missense_variant'),
    (' intron_variant ,splice_region_variant ','splice_region_variant;intron_variant'),
    ('missense_variant; missense_variant','missense_variant'),
])
def test_term_whitespace_and_order_do_not_create_output_changes(left,right):
    value=supplied()
    value.snapshots[0].annotation.consequence=left
    value.snapshots[1].annotation.consequence=right
    assert not compare(value).differences
    case=create_case(compare(value),'Whitespace-insensitive consequences')
    assert run_case(case).status == 'passed'


def test_067_bundles_and_regression_assertions_retain_original_term_rules():
    value=supplied()
    value.snapshots[0].annotation.consequence='missense_variant; synonymous_variant'
    value.snapshots[1].annotation.consequence='synonymous_variant&missense_variant'
    old=legacy_engine_v067.compare(value)
    current=compare(value)
    assert old.engine_version == '0.6.7' and old.differences
    assert current.engine_version == '0.6.8' and not current.differences and current.id != old.id
    entries={'investigation':old.model_dump(mode='json')}
    bundle={'format':'GenomeDebugger bundle','version':2,'engine_version':'0.6.7','entries':entries,'sha256':{'investigation':digest(entries['investigation'])}}
    assert verify_bundle(bundle)[0] == old
    case=create_case(old,'Archived whitespace behavior')
    saved=RegressionRun.model_validate(legacy_regression_v067.run_case(case).model_dump(mode='json'))
    assert saved.actual.engine_version == saved.assertion_version == '0.6.7'
    validate_saved_run(case,saved)
    assert json.loads(old.model_dump_json()) == entries['investigation']


def test_markdown_carries_clinical_scope_for_every_annotation_location():
    from app.models import ClinicalAssertion, VariantRecord
    value=supplied()
    for i,snapshot in enumerate(value.snapshots):
        snapshot.annotation.clinical=ClinicalAssertion(framework='AUDIT_FRAMEWORK',condition_id='AUDIT_CONDITION_42',classification=['classification A','classification B'][i])
        extra=snapshot.annotation.model_copy(deep=True);extra.transcript_id='extra'
        snapshot.annotations=[extra]
        variant=snapshot.variant.model_copy(deep=True);variant.position+=10;variant.reference_context=None
        snapshot.variant_records=[VariantRecord(variant=variant,annotations=[extra])]
    report=markdown_report(compare(value))
    assert report.count('framework AUDIT_FRAMEWORK; condition AUDIT_CONDITION_42') == 6
    assert 'classification classification A' in report and 'classification classification B' in report


def test_markdown_distinguishes_missing_empty_and_whitespace_values():
    value=supplied()
    value.snapshots[0].annotation.protein_consequence=''
    value.snapshots[1].annotation.protein_consequence=' \t '
    report=markdown_report(compare(value))
    assert '| Empty text | Whitespace only |' in report
    value.snapshots[0].annotation.protein_consequence=None
    assert '| Not provided | Whitespace only |' in markdown_report(compare(value))
