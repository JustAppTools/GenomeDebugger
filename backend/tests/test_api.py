import json
from pathlib import Path
from fastapi.testclient import TestClient
from app import main


def test_demo_compare_store_and_export(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    client = TestClient(main.app)
    assert client.get("/api/health").json()["status"] == "ok"
    demo = client.get("/api/demos/transcript-switch")
    assert demo.status_code == 200
    result = client.post("/api/investigations", json=demo.json())
    assert result.status_code == 200
    body = result.json()
    assert body["identity"]["status"] == "verified"
    assert any(f["status"] == "verified" for f in body["findings"])
    assert client.get(f"/api/investigations/{body['id']}").json() == body
    assert client.get("/api/investigations").json()[0]["id"] == body["id"]
    report = client.get(f"/api/investigations/{body['id']}/report.md")
    assert report.status_code == 200
    assert "SYNTHETIC DEMONSTRATION" in report.text
    assert "controlled-lookup" in report.text


def test_api_rejects_bad_schema_and_missing_record(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    client = TestClient(main.app)
    assert client.post("/api/investigations", json={"title": "x", "snapshots": []}).status_code == 422
    assert client.get("/api/investigations/no-such-id").status_code == 404
    assert client.post("/api/investigations", content=b" " * 1_000_001, headers={"content-type": "application/json"}).status_code == 413
