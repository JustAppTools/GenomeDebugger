import hashlib
import json
from .models import (
    Difference, Evidence, Finding, IdentityResult, InvestigationInput,
    InvestigationResult, Variant,
)


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


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
    if not ea[1] or not ea[2] or not eb[1] or not eb[2]:
        return IdentityResult(status="unresolved", explanation="An insertion or deletion needs repeat-aware normalization; flank trimming is insufficient.", normalized_a=fmt(ea), normalized_b=fmt(eb), evidence_ids=["identity-inputs"])
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
    differences: list[Difference] = []

    def add(field, before, after, category="annotation", meaningful=True):
        if before == after:
            return
        eid = f"diff-{len(differences)+1}"
        evidence.append(Evidence(id=eid, kind="field_comparison", description=f"Observed {field} values in the two supplied snapshots", data={"field": field, "a": before, "b": after, "snapshot_ids": [a.id, b.id]}))
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
    return InvestigationResult(id=hash_[:16], input=payload, identity=ident, differences=differences, findings=findings, evidence=evidence, input_sha256=hash_)
