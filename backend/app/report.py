from .models import InvestigationResult


def markdown_report(result: InvestigationResult) -> str:
    a, b = result.input.snapshots
    public_source = bool(a.provenance.configuration.get("source_record_id") and b.provenance.configuration.get("source_record_id"))
    lines = [
        f"# GenomeDebugger investigation: {result.input.title}", "",
        f"Investigation ID: `{result.id}`  ",
        f"Input SHA-256: `{result.input_sha256}`  ",
        f"Data type: {'SYNTHETIC DEMONSTRATION' if result.input.synthetic else 'CURRENT PUBLIC SOURCE' if public_source else 'User supplied'}", "",
        "## Compared snapshots", "",
    ]
    for snapshot in (a, b):
        p = snapshot.provenance
        lines.extend([f"### {snapshot.label} (`{snapshot.id}`)", "", f"Variant: {snapshot.variant.assembly} {snapshot.variant.sequence_id}:{snapshot.variant.position} {snapshot.variant.ref}>{snapshot.variant.alt}  ", f"Annotation: {snapshot.annotation.gene_id}, {snapshot.annotation.transcript_id}, {snapshot.annotation.consequence}  ", f"Software: {p.tool} {p.tool_version}; source: {p.source_name} {p.source_release}  ", f"Source URI: {p.source_uri or 'not supplied'}  ", f"Source response SHA-256: {p.input_sha256 or 'not supplied'}  ", f"Configuration: `{p.configuration}`", ""])
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
    lines.extend(["", "## Reproduction", "", "1. Save the JSON report from the application.", "2. POST its `input` object to `/api/investigations` using the same GenomeDebugger version.", "3. Compare the returned `input_sha256`, identity, differences, findings, and evidence.", ""])
    if public_source:
        lines.extend(["The Ensembl response was current when retrieved. Its reported release and transcript comparison do not establish historical causation.", ""])
    lines.extend(["This report is for research and quality assurance; it is not a clinical interpretation.", ""])
    return "\n".join(lines)
