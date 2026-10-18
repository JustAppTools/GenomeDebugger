"""Reviewed database/build combinations supported by the local runner."""

SUPPORTED_DATABASES = {
    "GRCh38.mane.1.0.ensembl": {
        "assembly_name": "GRCh38",
        "assembly_accession": "GCA_000001405.29",
    },
}


def validate_database(manifest: dict) -> dict:
    expected = SUPPORTED_DATABASES.get(manifest.get("genome"))
    if expected is None:
        raise ValueError("Unsupported SnpEff database/build; install a reviewed GRCh38 database")
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("SnpEff assembly metadata is missing or does not match its supported database")
    return expected
