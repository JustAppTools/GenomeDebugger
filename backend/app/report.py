from .models import InvestigationResult
from .allele_check import AlleleCheck, validate_saved_allele_check
from .ncbi import ReferenceCheckError
import html
import re
from .snpeff import SnpEffCheck
from .ensembl import SourceRecord


def literal(value) -> str:
    """One line of literal Markdown text, including values used in tables."""
    text = ' '.join(str(value).splitlines())
    text = html.escape(text, quote=False)
    # Intraword underscores cannot open emphasis; keep scientific field names
    # readable while escaping boundary underscores and all structural markers.
    text = re.sub(r'([\\`*{}\[\]()#+!|])', r'\\\1', text)
    return re.sub(r'(?<!\w)_|_(?!\w)', r'\\_', text)


def displayed(value) -> str:
    if value is None:
        return 'Not provided'
    if value == '':
        return 'Empty text'
    if isinstance(value, str) and not value.strip():
        return 'Whitespace only'
    return literal(value)


def annotation_text(row) -> str:
    text = f"{literal(row.gene_id)}, {literal(row.transcript_id)}, {literal(row.consequence)}; protein: {displayed(row.protein_consequence)}"
    if row.clinical:
        c = row.clinical
        text += f"; clinical assertion as supplied: framework {literal(c.framework)}; condition {literal(c.condition_id)}; classification {literal(c.classification)}; review status {displayed(c.review_status)}; assertion date {displayed(c.assertion_date)}"
    return text


def code(value) -> str:
    text = ' '.join(str(value).splitlines())
    # Use HTML only for unusual values that could terminate a Markdown span.
    if '`' in text or '<' in text or '>' in text or '&' in text:
        return '<code>' + html.escape(text, quote=False) + '</code>'
    return '`' + text + '`'


def markdown_report(result: InvestigationResult, allele_check: AlleleCheck | None = None,
                    annotation_check: SnpEffCheck | None = None,
                    sources: list[SourceRecord] | None = None) -> str:
    a, b = result.input.snapshots
    source_map = {source.id: source for source in sources or []}
    linked = [source_map.get(s.provenance.configuration.get("source_record_id")) for s in (a, b)]
    origins = {source.origin for source in linked if source is not None}
    historical = "historical_artifact" in origins
    current = "current_api" in origins
    data_type = ("SYNTHETIC DEMONSTRATION" if result.input.synthetic else
                 "MIXED CURRENT AND HISTORICAL SOURCES" if historical and current else
                 "MIXED PRESERVED SOURCE AND USER-SUPPLIED OUTPUT" if origins and any(source is None for source in linked) else
                 "PRESERVED HISTORICAL OUTPUT (declared provenance)" if historical else
                 "CURRENT PUBLIC SOURCE" if current else "User supplied; source provenance unavailable")
    lines = [
        f"# GenomeDebugger investigation: {literal(result.input.title)}", "",
        f"Investigation ID: {code(result.id)}  ",
        f"Engine version: {code(result.engine_version)}  ",
        f"Input SHA-256: {code(result.input_sha256)}  ",
        f"Data type: {literal(data_type)}", "",
        "## Compared snapshots", "",
    ]
    for snapshot in (a, b):
        p = snapshot.provenance
        lines.extend([f"### {literal(snapshot.label)} ({code(snapshot.id)})", "", f"Variant: {literal(snapshot.variant.assembly)} {literal(snapshot.variant.sequence_id)}:{literal(snapshot.variant.position)} {literal(snapshot.variant.ref)}>{literal(snapshot.variant.alt)}  ", f"Annotation: {annotation_text(snapshot.annotation)}  ", f"Software: {literal(p.tool)} {literal(p.tool_version)}; source: {literal(p.source_name)} {literal(p.source_release)}  ", f"Source URI: {literal(p.source_uri or 'not supplied')}  ", f"Source response SHA-256: {literal(p.input_sha256 or 'not supplied')}  ", f"Configuration: {code(p.configuration)}", ""])
        for row in snapshot.annotations:
            lines.extend([f"Additional annotation: {annotation_text(row)}  "])
        for record in snapshot.variant_records:
            v=record.variant
            lines.extend([f"Additional variant: {literal(v.assembly)} {literal(v.sequence_id)}:{literal(v.position)} {literal(v.ref)}>{literal(v.alt)}  "])
            lines.extend(f"Annotation: {annotation_text(row)}  " for row in record.annotations)
    lines.extend(["## Variant identity", "", f"**{literal(result.identity.status.upper())}** — {literal(result.identity.explanation)}", "", "## Differences", ""])
    if result.differences:
        lines.extend(["| Field | Before | After | Important by comparison rules | Evidence |", "|---|---|---|---|---|"])
        for d in result.differences:
            lines.append(f"| {literal(d.field)} | {displayed(d.before)} | {displayed(d.after)} | {literal('yes' if d.meaningful else 'no')} | {literal(', '.join(d.evidence_ids))} |")
    else:
        lines.append("No field differences detected.")
    lines.extend(["", "## Findings", ""])
    for f in result.findings:
        lines.extend([f"### {literal(f.status.upper())}: {literal(f.cause)}", "", literal(f.explanation), "", f"Affected fields: {literal(', '.join(f.affected_fields) or 'none')}  ", f"Evidence: {literal(', '.join(f.evidence_ids))}", ""])
    lines.extend(["## Evidence trail", ""])
    for e in result.evidence:
        lines.extend([f"- {code(e.id)} ({literal(e.kind)}): {literal(e.description)}"])
    invalid_allele = None
    if allele_check:
        try:
            validate_saved_allele_check(result, allele_check)
        except (ReferenceCheckError, ValueError) as exc:
            invalid_allele = str(exc)
    if allele_check and result.input.synthetic:
        lines.extend(["", "A saved public-reference allele check is outside scope for this synthetic input and is not used in this report.", ""])
    elif invalid_allele:
        lines.extend(["", "Saved allele evidence unavailable: " + literal(invalid_allele) + ".", ""])
    elif allele_check:
        lines.extend(["", "## Independent reference-backed allele identity", "",
            f"Check: {code(allele_check.id)} · {literal(allele_check.status.upper())} · {literal(allele_check.checked_at)}", "",
            literal(allele_check.explanation), "",
            f"Assembly report SHA-256: {code(allele_check.assembly_report_sha256)}", ""])
        for index, observation in enumerate(allele_check.observations):
            lines.extend([f"Analysis {literal('AB'[index])} contextual SPDI: {code(observation.normalized.text() if observation.normalized else 'not checked')}  ",
                f"HGVS: {code(observation.hgvs or 'not checked')}  ",
                f"Contextual response SHA-256: {code(observation.contextual_sha256 or 'not retrieved')}  ",
                f"Reference observation: {literal(observation.reference_uri)}", ""])
    lines.extend(["", "## Reproduction", "", "1. Save the JSON report from the application.", "2. POST its `input` object to `/api/investigations` using the same GenomeDebugger version.", "3. Compare the returned `input_sha256`, identity, differences, findings, and evidence.", ""])
    if historical:
        lines.extend(["Historical dates, software versions, and source releases were declared with imported output artifacts. Their hashes preserve bytes, not external authenticity or causal proof.", ""])
    if current:
        lines.extend(["The Ensembl response was current when retrieved. Its reported release and transcript comparison do not establish historical causation.", ""])
    reference = result.input.reference_check
    if reference:
        lines.extend([f"Linked NCBI allele check: {code(reference.id)} ({literal(reference.status)}). Retrieve its preserved responses at {code('/api/sources/reference-checks/' + reference.id)}. This does not validate VEP consequences.", ""])
    annotation_id = result.input.annotation_check.id if result.input.annotation_check else None
    if annotation_id:
        preserved = annotation_check if annotation_check and annotation_check.id == annotation_id else None
        origin = ("preserved execution record; not externally authenticated" if preserved and preserved.execution
                  else "user-supplied output" if preserved else "execution provenance unavailable")
        lines.extend([f"Linked SnpEff ANN check ({literal(origin)}): {code(annotation_id)} ({literal(result.input.annotation_check.status)}). Inspect preserved execution records for artifact hashes; imported records are not externally authenticated. Output comparison does not establish causation.", ""])
    lines.extend(["This report is for research and quality assurance; it is not a clinical interpretation.", ""])
    return "\n".join(lines)
