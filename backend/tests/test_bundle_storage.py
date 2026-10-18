import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.engine import compare, digest
from app.ensembl import CompareTranscripts, SourceQuery, comparison_input, fetch_record
from app.models import InvestigationInput, InvestigationResult, ReferenceCheckSummary
from app.storage import backup, StorageLimitError, RecordConflictError, save, save_source_record, save_reference_check
from app.bundle import create_bundle, verify_bundle
from app.legacy_engine_v050 import compare as compare_v050
from app.ncbi import fetch_reference_check
from test_ensembl import fixture_transport
from test_ncbi import ncbi_transport

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "transcript-switch.json"


def test_bundle_export_verify_import_and_tamper(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "first.db")
    client = TestClient(main.app)
    result = client.post("/api/investigations", json=json.loads(FIXTURE.read_text())).json()
    bundle = client.get(f"/api/investigations/{result['id']}/bundle").json()
    assert client.post("/api/bundles/verify", json=bundle).json()["valid"]
    changed = json.loads(json.dumps(bundle))
    changed["entries"]["investigation"]["input"]["title"] = "tampered"
    assert client.post("/api/bundles/verify", json=changed).status_code == 422
    changed = json.loads(json.dumps(bundle))
    changed["entries"]["investigation"]["findings"][0]["explanation"] = "Tampered scientific conclusion"
    changed["sha256"]["investigation"] = digest(changed["entries"]["investigation"])
    assert client.post("/api/bundles/verify", json=changed).status_code == 422
    monkeypatch.setattr(main, "DB", tmp_path / "second.db")
    assert client.post("/api/bundles/import", json=bundle).json()["imported"] == result["id"]
    assert client.get(f"/api/investigations/{result['id']}").json() == result
    assert client.get("/api/investigations", params={"q":"Synthetic", "limit":1}).json()[0]["id"] == result["id"]
    assert client.delete(f"/api/investigations/{result['id']}").status_code == 200
    assert client.get(f"/api/investigations/{result['id']}").status_code == 404


def test_old_database_migrates_and_backup_is_restorable(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as db:
        db.execute("CREATE TABLE investigations (id TEXT PRIMARY KEY, title TEXT NOT NULL, result_json TEXT NOT NULL)")
    monkeypatch.setattr(main, "DB", old)
    client = TestClient(main.app)
    result = client.post("/api/investigations", json=json.loads(FIXTURE.read_text())).json()
    with sqlite3.connect(old) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT created_at FROM investigations WHERE id = ?", (result["id"],)).fetchone()[0]
    restored = tmp_path / "backups" / "backup.db"
    backup(old, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT COUNT(*) FROM investigations").fetchone()[0] == 1


def test_storage_capacity_failure_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "small.db")
    monkeypatch.setattr("app.storage._guard_size", lambda *_: (_ for _ in ()).throw(StorageLimitError("Storage is full")))
    response = TestClient(main.app).post("/api/investigations", json=json.loads(FIXTURE.read_text()))
    assert response.status_code == 507
    assert response.json()["detail"] == "Storage is full"


def test_legacy_record_bundle_exports_current_replay(tmp_path):
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text())
    current = compare(payload)
    old_json = current.model_dump(mode="json")
    old_json["input"].pop("annotation_check")
    old_json["input"].pop("meaningful_overrides")
    for snapshot in old_json["input"]["snapshots"]:
        snapshot.pop("annotations")
    old_json["input_sha256"] = digest(old_json["input"])
    old_json["id"] = old_json["input_sha256"][:16]
    legacy = InvestigationResult.model_validate(old_json)
    bundle = create_bundle(tmp_path / "empty.db", legacy)
    restored, *_ = verify_bundle(bundle)
    assert bundle["replayed_from_id"] == legacy.id
    assert restored == compare(legacy.input)


def test_saved_result_cannot_be_replaced_by_same_id(tmp_path):
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text())
    result = compare(payload)
    path = tmp_path / "immutable.db"
    save(path, result)
    altered = result.model_copy(deep=True)
    altered.findings[0].explanation = "Different conclusion"
    try:
        save(path, altered)
    except RecordConflictError:
        pass
    else:
        raise AssertionError("Conflicting result replaced the saved record")


def test_bundle_rejects_rehashed_source_record_with_changed_reference(tmp_path):
    query = SourceQuery(chromosome="1", position=6524705, ref="C", alt="T")
    with httpx.Client(transport=fixture_transport()) as client:
        source = fetch_record(query, client)
    path = tmp_path / "source.db"
    save_source_record(path, source)
    result = compare(comparison_input(source, CompareTranscripts(
        transcript_a="ENST00000377705", transcript_b="ENST00000400913")))
    bundle = create_bundle(path, result)
    bundle["entries"]["source_record"]["reference_base"] = "A"
    bundle["sha256"]["source_record"] = digest(bundle["entries"]["source_record"])
    try:
        verify_bundle(bundle)
    except ValueError:
        pass
    else:
        raise AssertionError("Changed source record passed replay checks")


@pytest.mark.parametrize("field,value", [
    ("observed_spdi", "contradicts-the-response"), ("observed_hgvs", "incorrect"),
    ("spdi_matches", False), ("status", "disagree"), ("expected_spdi", "incorrect"),
    ("refseq_accession", "NC_000002.12"), ("assembly_report_sha256", "0" * 64),
])
def test_bundle_replays_every_ncbi_observation(tmp_path, field, value):
    with httpx.Client(transport=fixture_transport()) as client:
        source = fetch_record(SourceQuery(chromosome="1", position=6524705, ref="C", alt="T"), client)
    with httpx.Client(transport=ncbi_transport()) as client:
        check = fetch_reference_check(source, client)
    path = tmp_path / "reference.db"
    save_source_record(path, source)
    save_reference_check(path, check)
    summary = ReferenceCheckSummary.model_validate(check.model_dump(include=set(ReferenceCheckSummary.model_fields)))
    result = compare(comparison_input(source, CompareTranscripts(
        transcript_a="ENST00000377705", transcript_b="ENST00000400913"), summary))
    bundle = create_bundle(path, result)
    verify_bundle(bundle)
    bundle["entries"]["reference_check"][field] = value
    bundle["sha256"]["reference_check"] = digest(bundle["entries"]["reference_check"])
    with pytest.raises(ValueError, match="NCBI"):
        verify_bundle(bundle)


def test_archived_v050_bundle_remains_verifiable_and_has_separate_record_id(tmp_path):
    payload = InvestigationInput.model_validate_json(FIXTURE.read_text())
    legacy = compare_v050(payload)
    entry = legacy.model_dump(mode="json")
    entry.pop("engine_version")  # Original 0.5.0 exports did not include this field.
    bundle = {"format":"GenomeDebugger bundle", "version":2, "engine_version":"0.5.0",
              "entries":{"investigation":entry}, "sha256":{"investigation":digest(entry)}}
    verified, *_ = verify_bundle(bundle)
    current = compare(payload)
    assert current.id != verified.id and current.input_sha256 == verified.input_sha256
    save(tmp_path / "versions.db", verified)
    save(tmp_path / "versions.db", current)
    bundle["entries"]["investigation"]["findings"][0]["explanation"] = "tampered"
    bundle["sha256"]["investigation"] = digest(bundle["entries"]["investigation"])
    with pytest.raises(ValueError, match="replay"):
        verify_bundle(bundle)


def test_large_export_is_importable_while_input_limit_stays_one_mb(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "large.db")
    client = TestClient(main.app)
    data = json.loads(FIXTURE.read_text())
    for side, snapshot in enumerate(data["snapshots"]):
        snapshot["annotations"] = [{"gene_id":"BIG", "transcript_id":f"T{i}",
            "consequence":("A" if side == 0 else "B") * 500} for i in range(500)]
    assert len(json.dumps(data).encode()) < 1_000_000
    response = client.post("/api/investigations", json=data)
    assert response.status_code == 200
    bundle = client.get(f"/api/investigations/{response.json()['id']}/bundle")
    assert len(bundle.content) > 1_000_000
    assert client.post("/api/bundles/verify", content=bundle.content, headers={"Content-Type":"application/json"}).status_code == 200
    monkeypatch.setattr(main, "DB", tmp_path / "imported.db")
    assert client.post("/api/bundles/import", content=bundle.content, headers={"Content-Type":"application/json"}).status_code == 200
    assert client.post("/api/investigations", content=b' ' * 1_000_001).status_code == 413
