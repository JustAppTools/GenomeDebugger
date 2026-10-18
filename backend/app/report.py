from .models import InvestigationResult
from .allele_check import AlleleCheck


def markdown_report(result: InvestigationResult, allele_check: AlleleCheck | None = None) -> str:
    a, b = result.input.snapshots
    public_source = bool(a.provenance.configuration.get("source_record_id") and b.provenance.configuration.get("source_record_id"))
    historical = any(s.provenance.configuration.get("source_origin")=="historical_artifact" for s in (a,b))
    lines = [
        f"# GenomeDebugger investigation: {result.input.title}", "",
        f"Investigation ID: `{result.id}`  ",
        f"Engine version: `{result.engine_version}`  ",
        f"Input SHA-256: `{result.input_sha256}`  ",
        f"Data type: {'SYNTHETIC DEMONSTRATION' if result.input.synthetic else 'PRESERVED HISTORICAL OUTPUT (declared provenance)' if historical else 'CURRENT PUBLIC SOURCE' if public_source else 'User supplied'}", "",
        "## Compared snapshots", "",
    ]
    for snapshot in (a, b):
        p = snapshot.provenance
        lines.extend([f"### {snapshot.label} (`{snapshot.id}`)", "", f"Variant: {snapshot.variant.assembly} {snapshot.variant.sequence_id}:{snapshot.variant.position} {snapshot.variant.ref}>{snapshot.variant.alt}  ", f"Annotation: {snapshot.annotation.gene_id}, {snapshot.annotation.transcript_id}, {snapshot.annotation.consequence}  ", f"Software: {p.tool} {p.tool_version}; source: {p.source_name} {p.source_release}  ", f"Source URI: {p.source_uri or 'not supplied'}  ", f"Source response SHA-256: {p.input_sha256 or 'not supplied'}  ", f"Configuration: `{p.configuration}`", ""])
        for row in snapshot.annotations:
            lines.extend([f"Additional annotation: {row.gene_id}, {row.transcript_id}, {row.consequence}  "])
        for record in snapshot.variant_records:
            v=record.variant
            lines.extend([f"Additional variant: {v.assembly} {v.sequence_id}:{v.position} {v.ref}>{v.alt}  "])
            lines.extend(f"Annotation: {row.gene_id}, {row.transcript_id}, {row.consequence}  " for row in record.annotations)
    lines.extend(["## Variant identity", "", f"**{result.identity.status.upper()}** — {result.identity.explanation}", "", "## Differences", ""])
    if result.differences:
        lines.extend(["| Field | Before | After | Meaningful | Evidence |", "|---|---|---|---|---|"])
        for d in result.differences:
            safe = lambda x: str(x if x is not None else "—").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {safe(d.field)} | {safe(d.before)} | {safe(d.after)} | {'yes' if d.meaningful else 'representation only'} | {', '.join(d.evidence_ids)} |")
    else:
        lines.append("No field differences detected.")
    lines.extend(["", "## Findings", ""])
    for f in result.findings:
        lines.extend([f"### {f.status.upper()}: {f.cause}", "", f.explanation, "", f"Affected fields: {', '.join(f.affected_fields) or 'none'}  ", f"Evidence: {', '.join(f.evidence_ids)}", ""])
    lines.extend(["## Evidence trail", ""])
    for e in result.evidence:
        lines.extend([f"- `{e.id}` ({e.kind}): {e.description}"])
    if allele_check:
        lines.extend(["", "## Independent reference-backed allele identity", "",
            f"Check: `{allele_check.id}` · {allele_check.status.upper()} · {allele_check.checked_at}", "",
            allele_check.explanation, "",
            f"Assembly report SHA-256: `{allele_check.assembly_report_sha256}`", ""])
        for index, observation in enumerate(allele_check.observations):
            lines.extend([f"Analysis {'AB'[index]} contextual SPDI: `{observation.normalized.text() if observation.normalized else 'not checked'}`  ",
                f"HGVS: `{observation.hgvs or 'not checked'}`  ",
                f"Contextual response SHA-256: `{observation.contextual_sha256 or 'not retrieved'}`  ",
                f"Reference observation: {observation.reference_uri}", ""])
    lines.extend(["", "## Reproduction", "", "1. Save the JSON report from the application.", "2. POST its `input` object to `/api/investigations` using the same GenomeDebugger version.", "3. Compare the returned `input_sha256`, identity, differences, findings, and evidence.", ""])
    if historical:
        lines.extend(["Historical dates, software versions, and source releases were declared with imported output artifacts. Their hashes preserve bytes, not external authenticity or causal proof.", ""])
    if public_source and not historical:
        lines.extend(["The Ensembl response was current when retrieved. Its reported release and transcript comparison do not establish historical causation.", ""])
        check_id = a.provenance.configuration.get("reference_check_id")
        if check_id:
            lines.extend([f"Linked NCBI allele check: `{check_id}` ({a.provenance.configuration.get('reference_check_status', 'status unknown')}). Retrieve its preserved responses at `/api/sources/reference-checks/{check_id}`. This does not validate VEP consequences.", ""])
        annotation_id = a.provenance.configuration.get("annotation_check_id")
        if annotation_id:
            origin = "recorded local execution" if a.provenance.configuration.get("annotation_check_origin")=="local_execution" else "user-supplied output"
            lines.extend([f"Linked SnpEff ANN check ({origin}): `{annotation_id}` ({a.provenance.configuration.get('annotation_check_status', 'status unknown')}). Preserved execution records include artifact hashes; imported records are not externally authenticated. Output comparison does not establish causation.", ""])
    lines.extend(["This report is for research and quality assurance; it is not a clinical interpretation.", ""])
    return "\n".join(lines)
