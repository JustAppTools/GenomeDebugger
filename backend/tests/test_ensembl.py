import httpx
from fastapi.testclient import TestClient

from app import main
from app.ensembl import SourceError, SourceQuery, comparison_input, fetch_record
from app.engine import compare
from app.report import markdown_report


QUERY = SourceQuery(chromosome="1", position=6524705, ref="C", alt="T")


def fixture_transport(ref="C"):
    def handler(request):
        path = request.url.path
        if path == "/info/data":
            body = {"releases": [116]}
        elif path == "/info/assembly/human":
            body = {"assembly_name": "GRCh38.p14", "default_coord_system_version": "GRCh38", "assembly_accession": "GCA_000001405.29"}
        elif path.startswith("/sequence/region/human/"):
            body = {"seq": ref}
        elif path.startswith("/vep/human/region/"):
            body = [{"assembly_name": "GRCh38", "seq_region_name": "1", "start": 6524705, "end": 6524705,
                     "allele_string": "C/T", "transcript_consequences": [
                         {"transcript_id": "ENST00000377705", "gene_id": "ENSG00000162408", "consequence_terms": ["3_prime_UTR_variant"], "biotype": "protein_coding"},
                         {"transcript_id": "ENST00000400913", "gene_id": "ENSG00000162408", "consequence_terms": ["intron_variant"], "biotype": "protein_coding"}] }]
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


def test_documented_snv_is_validated_and_transcripts_can_be_compared():
    with httpx.Client(transport=fixture_transport()) as client:
        record = fetch_record(QUERY, client)
    assert record.assembly_accession == "GCA_000001405.29"
    assert record.releases == [116]
    assert record.reference_base == "C"
    assert len(record.source_response_sha256) == 64
    from app.ensembl import CompareTranscripts
    payload = comparison_input(record, CompareTranscripts(transcript_a="ENST00000377705", transcript_b="ENST00000400913"))
    result = compare(payload)
    assert result.identity.status == "verified"
    assert any(d.field == "consequence" for d in result.differences)
    assert result.findings[0].status == "possible"
    assert payload.snapshots[0].provenance.source_uri == record.source_uri
    report = markdown_report(result)
    assert "Data type: CURRENT PUBLIC SOURCE" in report
    assert record.source_response_sha256 in report
    assert "do not establish historical causation" in report


def test_reference_mismatch_stops_before_vep_request():
    with httpx.Client(transport=fixture_transport(ref="A")) as client:
        try:
            fetch_record(QUERY, client)
        except SourceError as exc:
            assert "Reference allele" in str(exc)
        else:
            raise AssertionError("wrong reference was accepted")


def test_cache_only_and_live_failure_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    calls = []
    def fake_fetch(query):
        calls.append(query)
        if len(calls) > 1:
            raise SourceError("Ensembl request failed: ReadTimeout")
        with httpx.Client(transport=fixture_transport()) as client:
            return fetch_record(query, client)
    monkeypatch.setattr(main, "fetch_record", fake_fetch)
    client = TestClient(main.app)
    body = {"query": QUERY.model_dump(), "mode": "cache_only"}
    assert client.post("/api/sources/ensembl/lookup", json=body).status_code == 404
    assert calls == []
    body["mode"] = "fetch"
    fetched = client.post("/api/sources/ensembl/lookup", json=body)
    assert fetched.status_code == 200 and fetched.json()["access"] == "fetched"
    record_id = fetched.json()["record"]["id"]
    assert client.get(f"/api/sources/ensembl/records/{record_id}").status_code == 200
    body["mode"] = "cache_only"
    assert client.post("/api/sources/ensembl/lookup", json=body).json()["access"] == "cache"
    assert len(calls) == 1
    body["mode"] = "fetch"
    fallback = client.post("/api/sources/ensembl/lookup", json=body)
    assert fallback.status_code == 200 and fallback.json()["access"] == "cached_after_error"
    assert "previously retrieved" in fallback.json()["warning"]
    compared = client.post(f"/api/sources/ensembl/records/{record_id}/compare", json={"transcript_a": "ENST00000377705", "transcript_b": "ENST00000400913"})
    assert compared.status_code == 200
    assert compared.json()["findings"][0]["status"] == "possible"


def test_invalid_source_query_is_rejected_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    client = TestClient(main.app)
    for bad in ({"chromosome": "../evil", "position": 1, "ref": "C", "alt": "T"},
                {"chromosome": "1", "position": 6524705, "ref": "C", "alt": "C"},
                {"chromosome": "1", "position": 6524705, "ref": "CC", "alt": "T"}):
        assert client.post("/api/sources/ensembl/lookup", json={"query": bad, "mode": "fetch"}).status_code == 422
