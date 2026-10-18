import hashlib
import json
from urllib.parse import quote
from .models import (
    Difference, Evidence, Finding, IdentityResult, InvestigationInput,
    InvestigationResult, Variant, variant_key,
)
from .version import ENGINE_VERSION


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def row_key(row) -> tuple[str, str, str, str]:
    clinical = row.clinical
    return (row.gene_id, row.transcript_id, clinical.framework if clinical else "",
            clinical.condition_id if clinical else "")


def row_label(key: tuple) -> str:
    # Escape structural punctuation in field paths; match with tuples, not text.
    return "|".join(quote(str(part), safe="._-") for part in key)


def simple_edit(variant: Variant) -> tuple[int, str, str]:
    """Trim shared flanks only. This is not repeat-aware normalization."""
    pos, ref, alt = variant.position, variant.ref, variant.alt
    while ref and alt and ref[0] == alt[0]:
        pos += 1
        ref, alt = ref[1:], alt[1:]
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    return pos, ref, alt


def identity(a: Variant, b: Variant) -> IdentityResult:
    if a.assembly != b.assembly or a.sequence_id != b.sequence_id:
        return IdentityResult(status="unresolved", explanation="Assembly or sequence accession differs; no validated liftover is available.", evidence_ids=["identity-inputs"])
    if not a.reference_context or not b.reference_context:
        return IdentityResult(status="unresolved", explanation="Reference context is missing; submitted coordinates alone do not establish biological equivalence.", evidence_ids=["identity-inputs"])
    ca, cb = a.reference_context, b.reference_context
    if ca.start != cb.start or ca.sequence != cb.sequence:
        return IdentityResult(status="unresolved", explanation="Reference contexts differ; this MVP cannot validate that they describe the same sequence.", evidence_ids=["identity-inputs"])
    ea, eb = simple_edit(a), simple_edit(b)
    fmt = lambda e: f"{a.sequence_id}:{e[0]}:{e[1] or '-'}>{e[2] or '-'}"
    if len(ea[1]) != len(ea[2]) or len(eb[1]) != len(eb[2]):
        def edited_sequence(variant: Variant) -> str:
            offset = variant.position - ca.start
            return ca.sequence[:offset] + variant.alt + ca.sequence[offset + len(variant.ref):]
        equivalent = edited_sequence(a) == edited_sequence(b)
        return IdentityResult(status="unresolved" if equivalent else "rejected",
                              explanation="Applying both edits to the identical supplied reference context "
                              + ("produces the same local sequence, but this does not establish reference-backed indel equivalence." if equivalent else "produces different local sequences.")
                              + " The supplied context is not independently authenticated against an assembly.",
                              normalized_a=fmt(ea), normalized_b=fmt(eb), evidence_ids=["identity-inputs"])
    return IdentityResult(
        status="verified" if ea == eb else "rejected",
        explanation="Both alleles match the same supplied reference context; trimmed substitution edits " + ("match." if ea == eb else "differ."),
        normalized_a=fmt(ea), normalized_b=fmt(eb), evidence_ids=["identity-inputs"],
    )


def compare(payload: InvestigationInput) -> InvestigationResult:
    a, b = payload.snapshots
    raw = payload.model_dump(mode="json")
    evidence = [Evidence(id="identity-inputs", kind="input", description="Assembly, sequence accession, reference context, and submitted alleles", data={"a": a.variant.model_dump(), "b": b.variant.model_dump()})]
    ident = identity(a.variant, b.variant)
    reference_check = payload.reference_check
    annotation_check = payload.annotation_check
    if reference_check:
        evidence.append(Evidence(id="reference-check", kind="external_reference_observation",
                                 description="Submitted NCBI reference and notation check linked to this source record",
                                 data=reference_check.model_dump()))
        if reference_check.status == "disagree":
            ident = ident.model_copy(update={
                "status": "unresolved",
                "explanation": "A linked NCBI reference or notation check disagrees with the Ensembl source record; cross-source allele identity remains unresolved.",
                "evidence_ids": [*ident.evidence_ids, "reference-check"],
            })
    if annotation_check:
        local_run = all(s.provenance.configuration.get("annotation_check_origin") == "local_execution" for s in (a,b))
        evidence.append(Evidence(id="annotation-check", kind="independent_annotation_output",
                                 description=("Preserved local SnpEff run compared with VEP transcripts; execution artifacts are recorded in the linked check" if local_run else "User-supplied SnpEff ANN output compared with preserved VEP transcripts; provenance is user declared"),
                                 data=annotation_check.model_dump()))
    differences: list[Difference] = []

    def add(field, before, after, category="annotation", meaningful=True):
        if before == after:
            return
        eid = f"diff-{len(differences)+1}"
        rule = payload.meaningful_overrides.get(field)
        if rule is not None:
            meaningful = rule
        data = {"field": field, "a": before, "b": after, "snapshot_ids": [a.id, b.id]}
        if rule is not None:
            data["meaningful_override"] = rule
        evidence.append(Evidence(id=eid, kind="field_comparison", description=f"Observed {field} values in the two supplied snapshots", data=data))
        differences.append(Difference(field=field, category=category, before=before, after=after, meaningful=meaningful, evidence_ids=[eid]))

    add("assembly", a.variant.assembly, b.variant.assembly, "identity")
    add("sequence_id", a.variant.sequence_id, b.variant.sequence_id, "identity")
    add("position", str(a.variant.position), str(b.variant.position), "representation", ident.status != "verified")
    add("ref", a.variant.ref, b.variant.ref, "representation", ident.status != "verified")
    add("alt", a.variant.alt, b.variant.alt, "representation", ident.status != "verified")
    add("gene_id", a.annotation.gene_id, b.annotation.gene_id)
    add("transcript_id", a.annotation.transcript_id, b.annotation.transcript_id)
    add("consequence", a.annotation.consequence, b.annotation.consequence)
    add("protein_consequence", a.annotation.protein_consequence, b.annotation.protein_consequence)
    # Selection is compared above; full row sets include the selected row so a
    # different selector does not turn an existing transcript into a missing row.
    rows_a = {row_key(row): row for row in (a.annotation, *a.annotations)} if a.annotations or b.annotations else {}
    rows_b = {row_key(row): row for row in (b.annotation, *b.annotations)} if a.annotations or b.annotations else {}
    for key in sorted(rows_a.keys() | rows_b.keys()):
        left, right = rows_a.get(key), rows_b.get(key)
        label = row_label(key)
        if key == row_key(a.annotation) == row_key(b.annotation):
            continue  # Primary fields already have a comparison and evidence.
        if left is None or right is None:
            add(f"annotations[{label}].presence", "present" if left else None, "present" if right else None)
            continue
        add(f"annotations[{label}].consequence", left.consequence, right.consequence)
        add(f"annotations[{label}].protein_consequence", left.protein_consequence, right.protein_consequence)
        if left.clinical and right.clinical:
            add(f"annotations[{label}].clinical.classification", left.clinical.classification, right.clinical.classification, "clinical")
            add(f"annotations[{label}].clinical.review_status", left.clinical.review_status, right.clinical.review_status, "clinical")
    extra_identity_issues: list[str] = []
    variant_rows_a = {variant_key(row.variant): row for row in a.variant_records}
    variant_rows_b = {variant_key(row.variant): row for row in b.variant_records}
    for variant_id in sorted(variant_rows_a.keys() | variant_rows_b.keys()):
        left, right = variant_rows_a.get(variant_id), variant_rows_b.get(variant_id)
        label = f"variant_records[{quote(variant_id[0], safe='._-')}|{quote(variant_id[1], safe='._-')}:{variant_id[2]}:{variant_id[3]}>{variant_id[4]}]"
        if left is None or right is None:
            add(f"{label}.presence", "present" if left else None, "present" if right else None, "variant")
            continue
        local_identity = identity(left.variant, right.variant)
        identity_eid = f"variant-record-{len(evidence)+1}"
        evidence.append(Evidence(id=identity_eid, kind="input",
                                 description=f"Additional variant identity within supplied contexts: {label}",
                                 data={"a": left.variant.model_dump(), "b": right.variant.model_dump(),
                                       "status": local_identity.status, "explanation": local_identity.explanation}))
        if local_identity.status != "verified":
            extra_identity_issues.append(identity_eid)
        left_rows = {row_key(row): row for row in left.annotations}
        right_rows = {row_key(row): row for row in right.annotations}
        for key in sorted(left_rows.keys() | right_rows.keys()):
            before, after = left_rows.get(key), right_rows.get(key)
            annotation_label = row_label(key)
            if before is None or after is None:
                add(f"{label}.annotations[{annotation_label}].presence", "present" if before else None,
                    "present" if after else None)
                continue
            add(f"{label}.annotations[{annotation_label}].consequence", before.consequence, after.consequence)
            add(f"{label}.annotations[{annotation_label}].protein_consequence", before.protein_consequence, after.protein_consequence)
            if before.clinical and after.clinical:
                add(f"{label}.annotations[{annotation_label}].clinical.classification", before.clinical.classification, after.clinical.classification, "clinical")
                add(f"{label}.annotations[{annotation_label}].clinical.review_status", before.clinical.review_status, after.clinical.review_status, "clinical")
    add("tool", a.provenance.tool, b.provenance.tool, "provenance")
    add("tool_version", a.provenance.tool_version, b.provenance.tool_version, "provenance")
    add("source_name", a.provenance.source_name, b.provenance.source_name, "provenance")
    add("source_release", a.provenance.source_release, b.provenance.source_release, "provenance")
    for key in sorted(set(a.provenance.configuration) | set(b.provenance.configuration)):
        add(f"configuration.{key}", a.provenance.configuration.get(key), b.provenance.configuration.get(key), "configuration")
    ac, bc = a.annotation.clinical, b.annotation.clinical
    if ac and bc:
        add("clinical.framework", ac.framework, bc.framework, "clinical_context")
        add("clinical.condition_id", ac.condition_id, bc.condition_id, "clinical_context")
        if ac.framework == bc.framework and ac.condition_id == bc.condition_id:
            add("clinical.classification", ac.classification, bc.classification, "clinical")
            add("clinical.review_status", ac.review_status, bc.review_status, "clinical")
        else:
            evidence.append(Evidence(id="clinical-scope", kind="comparability", description="Clinical assertions refer to different frameworks or conditions", data={"a": ac.model_dump(), "b": bc.model_dump()}))
    elif ac or bc:
        add("clinical.assertion_present", str(bool(ac)), str(bool(bc)), "clinical_context")

    findings: list[Finding] = []
    if extra_identity_issues:
        findings.append(Finding(status="unresolved", cause="additional variant identity",
                                explanation="One or more additional variants lack independently established identity across the two snapshots. Their annotation rows are compared by exact submitted representation only.",
                                affected_fields=["variant_records"], evidence_ids=extra_identity_issues))
    if annotation_check and annotation_check.status == "disagree":
        findings.append(Finding(status="unresolved", cause="annotation engine disagreement",
                                explanation="The supplied SnpEff output disagrees with VEP on at least one exact transcript. Different releases or configuration may explain it; causation remains unverified.",
                                affected_fields=["consequence"], evidence_ids=["annotation-check"]))
    if annotation_check and annotation_check.status == "unresolved":
        findings.append(Finding(status="unresolved", cause="incomplete annotation comparison",
                                explanation="The supplied SnpEff output does not cover every VEP transcript with an exact matching ID, so cross-engine consequence agreement is unresolved.",
                                affected_fields=["consequence"], evidence_ids=["annotation-check"]))
    if reference_check and reference_check.status == "disagree":
        findings.append(Finding(status="unresolved", cause="independent allele disagreement",
                                explanation="The pinned NCBI check disagrees with at least one reference or notation observation. The VEP transcript comparison cannot resolve that source disagreement.",
                                affected_fields=["variant"], evidence_ids=["reference-check", "identity-inputs"]))
    consequence_fields = [d.field for d in differences if d.field in {"consequence", "protein_consequence", "gene_id"}]
    only_transcript_config = (
        a.provenance == b.provenance and ident.status == "verified"
        and a.annotation.transcript_id != b.annotation.transcript_id
    )
    lookup = payload.controlled_lookup
    if consequence_fields and only_transcript_config and lookup and identity(a.variant, lookup.variant).status == "verified":
        rows = {row.transcript_id: row for row in lookup.rows}
        ra, rb = rows.get(a.annotation.transcript_id), rows.get(b.annotation.transcript_id)
        if ra and rb:
            computed = {"a": ra.model_dump(), "b": rb.model_dump()}
            observed = {"a": {"gene_id": a.annotation.gene_id, "consequence": a.annotation.consequence, "protein_consequence": a.annotation.protein_consequence}, "b": {"gene_id": b.annotation.gene_id, "consequence": b.annotation.consequence, "protein_consequence": b.annotation.protein_consequence}}
            matches = all(computed[k][field] == observed[k][field] for k in ("a", "b") for field in ("gene_id", "consequence", "protein_consequence"))
            eid = "controlled-lookup"
            evidence.append(Evidence(id=eid, kind="controlled_replay", description="Deterministic lookup replay using each selected transcript against one immutable synthetic table", data={"lookup_id": lookup.id, "lookup_sha256": digest(lookup.model_dump()), "computed": computed, "observed": observed, "matches": matches, "held_constant": ["variant identity", "tool/version", "source/release", "configuration"]}))
            if matches:
                findings.append(Finding(status="verified", cause="transcript selection", explanation="Changing only the selected transcript reproduces the observed annotation change in the supplied synthetic lookup. This verifies the cause within this controlled fixture, not an external annotation system.", affected_fields=consequence_fields, evidence_ids=[eid, "identity-inputs"]))
    if consequence_fields and not any(f.status == "verified" for f in findings):
        eid = next((d.evidence_ids[0] for d in differences if d.field == "consequence"), differences[0].evidence_ids[0])
        status = "possible" if a.annotation.transcript_id != b.annotation.transcript_id else "unresolved"
        findings.append(Finding(status=status, cause="transcript selection" if status == "possible" else "annotation discrepancy", explanation="Transcript selection differs, but no controlled replay established causation." if status == "possible" else "The supplied snapshots do not establish why the annotation changed.", affected_fields=consequence_fields, evidence_ids=[eid]))
    if any(d.field == "source_release" for d in differences):
        findings.append(Finding(status="possible", cause="source release", explanation="The source release differs. Without preserved source records, the causal data change cannot be reconstructed.", affected_fields=[d.field for d in differences if d.category in ("annotation", "clinical")], evidence_ids=[d.evidence_ids[0] for d in differences if d.field == "source_release"]))
    if ident.status == "unresolved" and not (reference_check and reference_check.status == "disagree"):
        findings.append(Finding(status="unresolved", cause="variant identity", explanation=ident.explanation, affected_fields=["variant"], evidence_ids=ident.evidence_ids))
    if ac and bc and (ac.framework != bc.framework or ac.condition_id != bc.condition_id):
        findings.append(Finding(status="unresolved", cause="clinical assertion comparability", explanation="Classification values refer to different conditions or frameworks and were not compared directly.", affected_fields=["clinical.classification"], evidence_ids=["clinical-scope"]))
    if not findings and differences:
        findings.append(Finding(status="unresolved", cause="unexplained change", explanation="Field differences were observed, but no controlled explanation was established.", affected_fields=[d.field for d in differences if d.meaningful], evidence_ids=[differences[0].evidence_ids[0]]))
    hash_ = digest(raw)
    record_id = digest({"engine_version": ENGINE_VERSION, "input_sha256": hash_})[:16]
    return InvestigationResult(id=record_id, engine_version=ENGINE_VERSION, input=payload, identity=ident, differences=differences, findings=findings, evidence=evidence, input_sha256=hash_)
