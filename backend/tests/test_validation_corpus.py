import json
from pathlib import Path

import pytest

from app.engine import identity
from app.models import Variant

CASES = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "identity-validation-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_curated_identity_case(case):
    a, b = Variant.model_validate(case["a"]), Variant.model_validate(case["b"])
    assert identity(a,b).status == case["expected"]
    assert identity(b,a).status == case["expected"]
