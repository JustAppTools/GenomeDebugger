import httpx
from fastapi.testclient import TestClient

from app import main
from app.ensembl import CompareTranscripts, SourceQuery, comparison_input, fetch_record
from app.ncbi import ReferenceCheck, ReferenceCheckError, fetch_reference_check
from app.engine import compare
from app.models import ReferenceCheckSummary
from app.storage import save_source_record
from test_ensembl import fixture_transport


def source_record():
    with httpx.Client(transport=fixture_transport()) as client:
        return fetch_record(SourceQuery(chromosome="1", position=6524705, ref="C", alt="T"), client)


def ncbi_transport(base="C"):
    def handler(request):
        path = request.url.path
        if path.endswith("/efetch.fcgi"):
            return httpx.Response(200, text=f">NC_000001.11:6524705-6524705 Homo sapiens chromosome 1, GRCh38.p14 Primary Assembly\n{base}\n")
        if path.endswith("/contextual"):
            return httpx.Response(200, json={"data": {"seq_id": "NC_000001.11", "position": 6524704,
                                                      "deleted_sequence": "C", "inserted_sequence": "T"}})
        if path.endswith("/hgvs"):
            return httpx.Response(200, json={"data": {"hgvs": "NC_000001.11:g.6524705C>T"}})
        raise AssertionError(path)
    return httpx.MockTransport(handler)


def test_ncbi_pinned_reference_spdi_and_hgvs_agree():
    with httpx.Client(transport=ncbi_transport()) as client:
        check = fetch_reference_check(source_record(), client)
    assert check.status == "agree"
    assert check.refseq_accession == "NC_000001.11"
    assert check.expected_spdi == "NC_000001.11:6524704:C:T"
    assert check.expected_hgvs == "NC_000001.11:g.6524705C>T"
    assert all((check.reference_matches, check.spdi_matches, check.hgvs_matches))
    assert len(check.assembly_report_sha256) == 64
    legacy = check.model_dump(exclude={"representation_checked"})
    assert ReferenceCheck.model_validate(legacy).representation_checked


def test_independent_reference_disagreement_is_preserved():
    record = source_record()
    with httpx.Client(transport=ncbi_transport(base="A")) as client:
        check = fetch_reference_check(record, client)
    assert check.status == "disagree"
    assert check.observed_reference == "A"
    assert not check.reference_matches
    assert not check.representation_checked
    assert check.contextual_response is None and check.hgvs_response is None
    assert not check.spdi_matches and not check.hgvs_matches
    summary = ReferenceCheckSummary.model_validate(check.model_dump(include=set(ReferenceCheckSummary.model_fields)))
    payload = comparison_input(record, CompareTranscripts(transcript_a="ENST00000377705", transcript_b="ENST00000400913"), summary)
    result = compare(payload)
    assert result.identity.status == "unresolved"
    assert result.findings[0].cause == "independent allele disagreement"
    assert "reference-check" in result.identity.evidence_ids


def test_pinned_mapping_rejects_other_assembly():
    source = source_record().model_copy(update={"assembly_accession": "GCA_unsupported"})
    with httpx.Client(transport=ncbi_transport()) as client:
        try:
            fetch_reference_check(source, client)
        except ReferenceCheckError as exc:
            assert "pinned NCBI mapping" in str(exc)
        else:
            raise AssertionError("unsupported assembly was mapped")
    mitochondrial = source_record().model_copy(update={"query": SourceQuery(chromosome="MT", position=1, ref="C", alt="T")})
    with httpx.Client(transport=ncbi_transport()) as client:
        try:
            fetch_reference_check(mitochondrial, client)
        except ReferenceCheckError as exc:
            assert "Mitochondrial HGVS" in str(exc)
        else:
            raise AssertionError("mitochondrial notation was accepted")


def test_reference_check_cache_and_comparison_link(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "test.db")
    source = source_record()
    save_source_record(main.DB, source)
    calls = []
    def fake_fetch(record):
        calls.append(record.id)
        if len(calls) > 1:
            raise ReferenceCheckError("NCBI request failed: ReadTimeout")
        with httpx.Client(transport=ncbi_transport()) as client:
            return fetch_reference_check(record, client)
    monkeypatch.setattr(main, "fetch_reference_check", fake_fetch)
    client = TestClient(main.app)
    url = f"/api/sources/ensembl/records/{source.id}/reference-check"
    assert client.post(url, json={"mode": "cache_only"}).status_code == 404
    assert calls == []
    fetched = client.post(url, json={"mode": "fetch"})
    assert fetched.status_code == 200 and fetched.json()["access"] == "fetched"
    check_id = fetched.json()["check"]["id"]
    assert client.get(f"/api/sources/reference-checks/{check_id}").status_code == 200
    assert client.post(url, json={"mode": "cache_only"}).json()["access"] == "cache"
    assert len(calls) == 1
    fallback = client.post(url, json={"mode": "fetch"})
    assert fallback.status_code == 200 and fallback.json()["access"] == "cached_after_error"
    compared = client.post(f"/api/sources/ensembl/records/{source.id}/compare",
                           json={"transcript_a": "ENST00000377705", "transcript_b": "ENST00000400913"})
    assert compared.status_code == 200
    config = compared.json()["input"]["snapshots"][0]["provenance"]["configuration"]
    assert config["reference_check_id"] == check_id
    assert config["reference_check_status"] == "agree"
    report = client.get(f"/api/investigations/{compared.json()['id']}/report.md")
    assert check_id in report.text
    assert "does not validate VEP consequences" in report.text
