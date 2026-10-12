import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.engine import compare
from app.models import InvestigationInput
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
