import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.engine import compare
from app.models import Annotation, InvestigationInput, VariantRecord
from app.regression import create_case, run_case


FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "transcript-switch.json"


def baseline():
    return compare(InvestigationInput.model_validate_json(FIXTURE.read_text(encoding="utf-8")))


def test_pinned_case_passes_and_keeps_original_record():
    source = baseline()
    case = create_case(source, "Transcript switch")
    run = run_case(case)
    assert run.mode == "pinned"
    assert run.status == "passed"
    assert all(check.passed for check in run.checks)
    assert run.input_changes == []
    assert case.source_investigation.input_sha256 == source.input_sha256
    source.input.snapshots[0].annotation.consequence = "later edit"
    assert case.source_investigation.input.snapshots[0].annotation.consequence == "missense_variant"


def test_changed_candidate_consequence_fails_with_specific_checks():
    case = create_case(baseline(), "Transcript switch")
    candidate = case.source_investigation.input.model_copy(deep=True)
    candidate.snapshots[1].annotation.consequence = "synonymous_variant"
    run = run_case(case, candidate)
    assert run.status == "failed"
    assert run.mode == "candidate"
    assert any(c.path == "snapshots[1].annotation.consequence" and not c.passed for c in run.checks)
    assert any(c.path == "findings" and not c.passed for c in run.checks)
    assert any(path.endswith("annotation.consequence") for path in run.input_changes)


def test_metadata_only_pipeline_version_change_passes_and_is_recorded():
    case = create_case(baseline(), "Transcript switch")
    candidate = case.source_investigation.input.model_copy(deep=True)
    for snapshot in candidate.snapshots:
        snapshot.provenance.tool_version = "2.0"
    run = run_case(case, candidate)
    assert run.status == "passed"
    assert any(path.endswith("provenance.tool_version") for path in run.input_changes)
    assert run.baseline_input_sha256 != run.candidate_input_sha256


def test_changed_lookup_evidence_is_flagged_without_failing_same_outputs():
    case = create_case(baseline(), "Transcript switch")
    candidate = case.source_investigation.input.model_copy(deep=True)
    candidate.controlled_lookup.description = "Revised table documentation"
    run = run_case(case, candidate)
    assert run.status == "passed"
    assert any(c.path == "evidence.controlled-lookup" and not c.passed and not c.required for c in run.checks)


def test_candidate_cannot_change_tested_allele():
    case = create_case(baseline(), "Transcript switch")
    candidate = case.source_investigation.input.model_copy(deep=True)
    candidate.snapshots[0].variant.alt = "AG"
    with pytest.raises(ValueError, match="tested variant"):
        run_case(case, candidate)


def test_candidate_cannot_change_additional_tested_variant():
    source = baseline()
    extra = {"variant":{"assembly":"GRCh38","sequence_id":"NC_000001.11","position":104,
                        "ref":"T","alt":"G","reference_context":{"start":100,"sequence":"GACGTACG"}},
             "annotations":[{"gene_id":"GENE2","transcript_id":"TX2","consequence":"intron_variant"}]}
    for snapshot in source.input.snapshots:
        snapshot.variant_records = [VariantRecord.model_validate(extra)]
    case = create_case(compare(source.input), "Additional variant")
    candidate = case.source_investigation.input.model_copy(deep=True)
    candidate.snapshots[1].variant_records[0].variant.position = 105
    with pytest.raises(ValueError, match="additional variants"):
        run_case(case, candidate)


def test_case_and_run_api_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    client = TestClient(main.app)
    demo = client.get("/api/demos/transcript-switch").json()
    investigation = client.post("/api/investigations", json=demo).json()
    create = client.post(f"/api/investigations/{investigation['id']}/regression-cases", json={"name": "Expected transcript effect"})
    assert create.status_code == 200
    case = create.json()
    assert client.get(f"/api/regression-cases/{case['id']}").json() == case
    assert client.get("/api/regression-cases").json()[0]["id"] == case["id"]
    pinned = client.post(f"/api/regression-cases/{case['id']}/runs", json={})
    assert pinned.status_code == 200 and pinned.json()["status"] == "passed"
    candidate = json.loads(json.dumps(demo))
    candidate["snapshots"][1]["annotation"]["consequence"] = "synonymous_variant"
    failed = client.post(f"/api/regression-cases/{case['id']}/runs", json={"candidate": candidate})
    assert failed.status_code == 200 and failed.json()["status"] == "failed"
    assert client.get(f"/api/regression-runs/{failed.json()['id']}").json() == failed.json()
    assert len(client.get(f"/api/regression-cases/{case['id']}/runs").json()) == 2
    candidate["snapshots"][0]["variant"]["alt"] = "AG"
    assert client.post(f"/api/regression-cases/{case['id']}/runs", json={"candidate": candidate}).status_code == 422


@pytest.mark.parametrize("group", ["annotations", "variant_records"])
def test_shared_annotation_drift_fails_even_when_discrepancy_is_unchanged(group):
    payload = baseline().input
    annotation = Annotation(gene_id="G2", transcript_id="T2", consequence="intron_variant")
    for snapshot in payload.snapshots:
        if group == "annotations":
            snapshot.annotations = [annotation.model_copy(deep=True)]
        else:
            snapshot.variant_records = [VariantRecord(variant={"assembly":"GRCh38", "sequence_id":"NC_000001.11",
                "position":104, "ref":"T", "alt":"G", "reference_context":{"start":100,"sequence":"GACGTACG"}},
                annotations=[annotation.model_copy(deep=True)])]
    case = create_case(compare(payload), "Shared drift")
    candidate = payload.model_copy(deep=True)
    for snapshot in candidate.snapshots:
        row = snapshot.annotations[0] if group == "annotations" else snapshot.variant_records[0].annotations[0]
        row.consequence = "missense_variant"
    run = run_case(case, candidate)
    assert run.status == "failed"
    assert any(not check.passed and group in check.path and check.path.endswith("consequence")
               for check in run.checks)
    assert not any(not check.passed for check in run.checks if check.path.startswith("differences."))


def test_annotation_order_does_not_fail_candidate():
    payload = baseline().input
    for snapshot in payload.snapshots:
        snapshot.annotations = [Annotation(gene_id="G2", transcript_id=tid, consequence="intron_variant") for tid in ("T2", "T3")]
    case = create_case(compare(payload), "Annotation order")
    candidate = payload.model_copy(deep=True)
    for snapshot in candidate.snapshots:
        snapshot.annotations.reverse()
    assert run_case(case, candidate).status == "passed"
