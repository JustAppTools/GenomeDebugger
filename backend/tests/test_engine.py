import json
from copy import deepcopy
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.engine import compare, identity, simple_edit
from app.models import InvestigationInput, Variant

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "transcript-switch.json"


def sample():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(data):
    return compare(InvestigationInput.model_validate(data))


def test_equivalent_padded_substitutions_and_controlled_root_cause():
    result = run(sample())
    assert result.identity.status == "verified"
    assert result.identity.normalized_a == result.identity.normalized_b
    assert any(f.status == "verified" and f.cause == "transcript selection" for f in result.findings)
    replay = next(e for e in result.evidence if e.id == "controlled-lookup")
    assert replay.data["matches"] is True
    assert all(d.meaningful is False for d in result.differences if d.category == "representation")


def test_changed_assembly_does_not_establish_identity_or_cause():
    data = sample()
    data["snapshots"][1]["variant"]["assembly"] = "GRCh37"
    result = run(data)
    assert result.identity.status == "unresolved"
    assert not any(f.status == "verified" for f in result.findings)


def test_source_release_change_is_only_possible_cause():
    data = sample()
    data["snapshots"][1]["provenance"]["source_release"] = "2026-demo-2"
    result = run(data)
    assert not any(f.status == "verified" for f in result.findings)
    assert any(f.cause == "source release" and f.status == "possible" for f in result.findings)


def test_condition_mismatch_blocks_classification_comparison():
    data = sample()
    data["snapshots"][0]["annotation"]["clinical"] = {"framework": "germline", "condition_id": "MONDO:0000001", "classification": "Pathogenic"}
    data["snapshots"][1]["annotation"]["clinical"] = {"framework": "germline", "condition_id": "MONDO:0000002", "classification": "Benign"}
    result = run(data)
    assert not any(d.field == "clinical.classification" for d in result.differences)
    assert any(f.cause == "clinical assertion comparability" for f in result.findings)


def test_multiple_changes_are_not_claimed_as_one_verified_cause():
    data = sample()
    data["snapshots"][1]["provenance"]["tool_version"] = "2.0"
    data["snapshots"][1]["provenance"]["source_release"] = "release-2"
    result = run(data)
    assert not any(f.status == "verified" for f in result.findings)
    assert {"tool_version", "source_release", "transcript_id", "consequence"}.issubset({d.field for d in result.differences})


def test_missing_controlled_lookup_leaves_transcript_cause_possible():
    data = sample()
    data.pop("controlled_lookup")
    result = run(data)
    assert any(f.cause == "transcript selection" and f.status == "possible" for f in result.findings)
    assert not any(f.status == "verified" for f in result.findings)


def test_malformed_and_incomplete_input_rejected():
    data = sample()
    data["snapshots"][0]["variant"]["ref"] = "TT"
    with pytest.raises(ValidationError, match="ref does not match"):
        InvestigationInput.model_validate(data)
    data = sample()
    del data["snapshots"][0]["provenance"]
    with pytest.raises(ValidationError):
        InvestigationInput.model_validate(data)


def test_identity_symmetry_and_trim_idempotence():
    data = sample()
    a = Variant.model_validate(data["snapshots"][0]["variant"])
    b = Variant.model_validate(data["snapshots"][1]["variant"])
    assert identity(a,b).status == identity(b,a).status
    pos, ref, alt = simple_edit(a)
    trimmed = a.model_copy(update={"position": pos, "ref": ref, "alt": alt})
    assert simple_edit(trimmed) == (pos, ref, alt)


def test_indel_in_repeat_is_unresolved():
    data = sample()
    for snapshot in data["snapshots"]:
        snapshot["variant"] = {"assembly": "GRCh38", "sequence_id": "NC_000001.11", "position": 101, "ref": "AA", "alt": "A", "reference_context": {"start": 100, "sequence": "AAAAAA"}}
    assert run(data).identity.status == "unresolved"


def test_lookup_must_match_observations_and_allele():
    data = sample()
    data["controlled_lookup"]["rows"][0]["consequence"] = "synonymous_variant"
    assert not any(f.status == "verified" for f in run(data).findings)
    data = sample()
    data["controlled_lookup"]["variant"]["alt"] = "G"
    assert not any(f.status == "verified" for f in run(data).findings)
