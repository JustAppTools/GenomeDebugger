"""Versioned assertions for replaying a discrepancy against the current engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator
from .admission import require_text

from .engine import compare, digest, row_key, canonical_consequence
from .models import InvestigationInput, InvestigationResult, StrictModel, variant_key


class RegressionCase(StrictModel):
    id: str
    name: str
    schema_version: Literal[1] = 1
    created_at: str
    source_investigation: InvestigationResult


class CreateRegressionCase(StrictModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        require_text(value, 'Test name')
        return value


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
    assertion_version: Literal['0.6.7','0.6.8'] | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_case(source: InvestigationResult, name: str) -> RegressionCase:
    return RegressionCase(id=uuid4().hex[:16], name=name, created_at=utc_now(), source_investigation=source.model_copy(deep=True))


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {prefix: {}}
        return {key: item for k, v in value.items() for key, item in _flatten(v, f"{prefix}.{k}" if prefix else k).items()}
    if isinstance(value, list):
        if not value:
            return {prefix: []}
        return {key: item for index, item in enumerate(value) for key, item in _flatten(item, f"{prefix}[{index}]").items()}
    return {prefix: value}


def _differences(result: InvestigationResult) -> dict[str, dict]:
    def value(difference, text):
        return canonical_consequence(text) if text is not None and difference.category == 'annotation' and (difference.field == 'consequence' or difference.field.endswith('.consequence')) else text
    return {d.field: {"category": d.category, "before": value(d, d.before), "after": value(d, d.after), "meaningful": d.meaningful} for d in result.differences}


def _annotation_output(row) -> dict:
    data = row.model_dump(mode='json')
    data['consequence'] = canonical_consequence(data['consequence'])
    return data


def _findings(result: InvestigationResult) -> list[dict]:
    return sorted(
        ({"status": f.status, "cause": f.cause, "affected_fields": sorted(f.affected_fields)} for f in result.findings),
        key=lambda x: (x["cause"], x["status"], x["affected_fields"]),
    )


def _evidence(result: InvestigationResult) -> dict[str, str]:
    # Hash data and kind, not prose, so wording changes do not fail a replay.
    return {e.id: digest({"kind": e.kind, "data": e.data}) for e in result.evidence}


def _links(result: InvestigationResult) -> dict:
    return {"identity": sorted(result.identity.evidence_ids),
            "differences": {d.field: sorted(d.evidence_ids) for d in result.differences},
            "findings": sorted([{"cause": f.cause, "status": f.status,
                "affected_fields": sorted(f.affected_fields), "evidence_ids": sorted(f.evidence_ids)}
                for f in result.findings], key=lambda value: digest(value))}


def run_case(case: RegressionCase, candidate: InvestigationInput | None = None, *, _actual_result: InvestigationResult | None = None) -> RegressionRun:
    baseline = case.source_investigation
    mode = "candidate" if candidate is not None else "pinned"
    supplied = candidate or baseline.input
    if candidate is not None:
        for index, (expected, actual) in enumerate(zip(baseline.input.snapshots, candidate.snapshots)):
            if expected.variant != actual.variant:
                raise ValueError(f"Candidate snapshot {index + 1} changes the tested variant; submit the same variant representation")
            expected_variants = {variant_key(row.variant) for row in expected.variant_records}
            actual_variants = {variant_key(row.variant) for row in actual.variant_records}
            if expected_variants != actual_variants:
                raise ValueError(f"Candidate snapshot {index + 1} changes the tested additional variants")
    actual_result = _actual_result if _actual_result is not None else compare(supplied)
    checks: list[RegressionCheck] = []

    def check(path: str, expected: Any, actual: Any, required: bool = True):
        checks.append(RegressionCheck(path=path, expected=expected, actual=actual, passed=expected == actual, required=required))

    for index, (expected, actual) in enumerate(zip(baseline.input.snapshots, actual_result.input.snapshots)):
        left = _flatten(_annotation_output(expected.annotation))
        right = _flatten(_annotation_output(actual.annotation))
        for path in sorted(set(left) | set(right)):
            check(f"snapshots[{index}].annotation.{path}", left.get(path), right.get(path))
        # Assert absolute outputs as well as their A/B differences. Shared drift
        # in both analyses must fail even when the discrepancy itself is stable.
        def collection_outputs(snapshot):
            return {
                "annotations": [_annotation_output(row) for row in sorted(snapshot.annotations, key=row_key)],
                "variant_records": [{"variant": record.variant.model_dump(mode="json"),
                    "annotations": [_annotation_output(row) for row in sorted(record.annotations, key=row_key)]}
                    for record in sorted(snapshot.variant_records, key=lambda record: variant_key(record.variant))],
            }
        left = _flatten(collection_outputs(expected))
        right = _flatten(collection_outputs(actual))
        for path in sorted(set(left) | set(right)):
            check(f"snapshots[{index}].{path}", left.get(path), right.get(path))
    check("identity.status", baseline.identity.status, actual_result.identity.status)
    expected_diffs, actual_diffs = _differences(baseline), _differences(actual_result)
    for field in sorted(set(expected_diffs) | set(actual_diffs)):
        check(f"differences.{field}", expected_diffs.get(field), actual_diffs.get(field))
    check("findings", _findings(baseline), _findings(actual_result))
    ids = [item.id for item in actual_result.evidence]
    references = [*actual_result.identity.evidence_ids,
                  *(id_ for item in actual_result.differences for id_ in item.evidence_ids),
                  *(id_ for item in actual_result.findings for id_ in item.evidence_ids)]
    check("evidence.references", [], sorted(set(references) - set(ids)))
    check("evidence.unique_ids", len(ids), len(set(ids)))
    if mode == 'pinned':
        check("evidence.relationships", _links(baseline), _links(actual_result))
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
        input_changes=input_changes, actual=actual_result, assertion_version='0.6.8',
    )


def validate_saved_run(case: RegressionCase, record: RegressionRun):
    """Rebuild the complete assertions, without recalculating historical results."""
    from . import legacy_regression_v050, legacy_regression_v063, legacy_regression_v063_linked
    from . import legacy_regression_v064, legacy_regression_v066, legacy_regression_v067
    versions = {'0.5.0': [legacy_regression_v050], '0.6.0': [legacy_regression_v063],
                '0.6.1': [legacy_regression_v063], '0.6.2': [legacy_regression_v063],
                # Evidence-link assertions shipped without changing comparator
                # 0.6.3. Both complete historical layouts are supported.
                '0.6.3': [legacy_regression_v063, legacy_regression_v063_linked],
                '0.6.4': [legacy_regression_v064], '0.6.5': [legacy_regression_v066],
                '0.6.6': [legacy_regression_v066]}
    if record.actual.engine_version == '0.6.8' and record.assertion_version == '0.6.8':
        evaluators = [run_case]
    elif record.actual.engine_version == '0.6.7' and record.assertion_version == '0.6.7':
        evaluators = [legacy_regression_v067.run_case]
    elif record.assertion_version is None and record.actual.engine_version in versions:
        evaluators = [rules.run_case for rules in versions[record.actual.engine_version]]
    else:
        raise ValueError('Unsupported saved regression assertion version')
    for evaluator in evaluators:
        rebuilt = evaluator(case, record.actual.input if record.mode == 'candidate' else None,
                            _actual_result=record.actual)
        if ([check.model_dump(mode='json') for check in record.checks] ==
                [check.model_dump(mode='json') for check in rebuilt.checks]
                and record.input_changes == rebuilt.input_changes and record.status == rebuilt.status):
            return
    raise ValueError('Saved regression assertions disagree with the baseline and candidate')
