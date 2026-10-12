"""Versioned assertions for replaying a discrepancy against the current engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from .engine import compare, digest
from .models import InvestigationInput, InvestigationResult, StrictModel


class RegressionCase(StrictModel):
    id: str
    name: str
    schema_version: Literal[1] = 1
    created_at: str
    source_investigation: InvestigationResult


class CreateRegressionCase(StrictModel):
    name: str = Field(min_length=1, max_length=200)


class RegressionRunRequest(StrictModel):
    candidate: InvestigationInput | None = None


class RegressionCheck(StrictModel):
    path: str
    expected: Any
    actual: Any
    passed: bool
    required: bool


class RegressionRun(StrictModel):
    id: str
    case_id: str
    created_at: str
    mode: Literal["pinned", "candidate"]
    status: Literal["passed", "failed"]
    baseline_input_sha256: str
    candidate_input_sha256: str
    checks: list[RegressionCheck]
    input_changes: list[str]
    actual: InvestigationResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_case(source: InvestigationResult, name: str) -> RegressionCase:
    return RegressionCase(id=uuid4().hex[:16], name=name, created_at=utc_now(), source_investigation=source.model_copy(deep=True))


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        return {key: item for k, v in value.items() for key, item in _flatten(v, f"{prefix}.{k}" if prefix else k).items()}
    if isinstance(value, list):
        return {key: item for index, item in enumerate(value) for key, item in _flatten(item, f"{prefix}[{index}]").items()}
    return {prefix: value}


def _differences(result: InvestigationResult) -> dict[str, dict]:
    return {d.field: {"category": d.category, "before": d.before, "after": d.after, "meaningful": d.meaningful} for d in result.differences}


def _findings(result: InvestigationResult) -> list[dict]:
    return sorted(
        ({"status": f.status, "cause": f.cause, "affected_fields": sorted(f.affected_fields)} for f in result.findings),
        key=lambda x: (x["cause"], x["status"], x["affected_fields"]),
    )


def _evidence(result: InvestigationResult) -> dict[str, str]:
    # Hash data and kind, not prose, so wording changes do not fail a replay.
    return {e.id: digest({"kind": e.kind, "data": e.data}) for e in result.evidence}


def run_case(case: RegressionCase, candidate: InvestigationInput | None = None) -> RegressionRun:
    baseline = case.source_investigation
    mode = "candidate" if candidate is not None else "pinned"
    supplied = candidate or baseline.input
    if candidate is not None:
        for index, (expected, actual) in enumerate(zip(baseline.input.snapshots, candidate.snapshots)):
            if expected.variant != actual.variant:
                raise ValueError(f"Candidate snapshot {index + 1} changes the tested variant; submit the same variant representation")
    actual_result = compare(supplied)
    checks: list[RegressionCheck] = []

    def check(path: str, expected: Any, actual: Any, required: bool = True):
        checks.append(RegressionCheck(path=path, expected=expected, actual=actual, passed=expected == actual, required=required))

    for index, (expected, actual) in enumerate(zip(baseline.input.snapshots, actual_result.input.snapshots)):
        left = _flatten(expected.annotation.model_dump(mode="json"))
        right = _flatten(actual.annotation.model_dump(mode="json"))
        for path in sorted(set(left) | set(right)):
            check(f"snapshots[{index}].annotation.{path}", left.get(path), right.get(path))
    check("identity.status", baseline.identity.status, actual_result.identity.status)
    expected_diffs, actual_diffs = _differences(baseline), _differences(actual_result)
    for field in sorted(set(expected_diffs) | set(actual_diffs)):
        check(f"differences.{field}", expected_diffs.get(field), actual_diffs.get(field))
    check("findings", _findings(baseline), _findings(actual_result))
    expected_evidence, actual_evidence = _evidence(baseline), _evidence(actual_result)
    for id_ in sorted(set(expected_evidence) | set(actual_evidence)):
        check(f"evidence.{id_}", expected_evidence.get(id_), actual_evidence.get(id_), required=(mode == "pinned"))

    old_input = _flatten(baseline.input.model_dump(mode="json"))
    new_input = _flatten(supplied.model_dump(mode="json"))
    input_changes = sorted(path for path in set(old_input) | set(new_input) if old_input.get(path) != new_input.get(path))
    status = "passed" if all(c.passed for c in checks if c.required) else "failed"
    return RegressionRun(
        id=uuid4().hex[:16], case_id=case.id, created_at=utc_now(), mode=mode,
        status=status, baseline_input_sha256=baseline.input_sha256,
        candidate_input_sha256=actual_result.input_sha256, checks=checks,
        input_changes=input_changes, actual=actual_result,
    )
