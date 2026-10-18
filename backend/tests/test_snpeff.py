import httpx
from fastapi.testclient import TestClient

from app import main
from app.ensembl import SourceQuery, fetch_record
from app.snpeff import SnpEffCheckRequest, compare_snpeff
from app.storage import save_source_record
from test_ensembl import fixture_transport

QUERY = SourceQuery(chromosome="1",position=6524705,ref="C",alt="T")
VCF = ("1\t6524705\t.\tC\tT\t.\tPASS\tANN="
       "T|3_prime_UTR_variant|MODIFIER|G|ENSG00000162408|transcript|ENST00000377705|protein_coding|,"
       "T|intron_variant|MODIFIER|G|ENSG00000162408|transcript|ENST00000400913|protein_coding|")


def record():
    with httpx.Client(transport=fixture_transport()) as client:
        return fetch_record(QUERY, client)


def request(text=VCF):
    return SnpEffCheckRequest(vcf_text=text,snpeff_version="5.2",genome_database="GRCh38.99",database_sha256="a"*64)


def test_matching_and_disagreeing_ann_terms():
    source = record()
    agreed = compare_snpeff(source, request())
    assert agreed.status == "agree" and len(agreed.matches) == 2
    assert len(agreed.vcf_sha256) == 64
    changed = compare_snpeff(source, request(VCF.replace("3_prime_UTR_variant","missense_variant")))
    assert changed.status == "disagree"
    no_match = compare_snpeff(source, request(VCF.replace("ENST00000377705","ENST-OTHER-1").replace("ENST00000400913","ENST-OTHER-2")))
    assert no_match.status == "unresolved"
    partial = compare_snpeff(source, request(VCF.split(",")[0]))
    assert partial.status == "unresolved" and partial.unmatched_ensembl


def test_ann_allele_guard_and_local_persistence(tmp_path, monkeypatch):
    source = record()
    monkeypatch.setattr(main,"DB",tmp_path/"test.db")
    save_source_record(main.DB,source)
    client = TestClient(main.app)
    path = f"/api/sources/ensembl/records/{source.id}/snpeff-check"
    assert client.post(path,json=request().model_dump()).json()["status"] == "agree"
    assert client.get(path).json()["status"] == "agree"
    assert client.post(path,json=request(VCF.replace("\tC\tT\t","\tC\tG\t")).model_dump()).status_code == 422
