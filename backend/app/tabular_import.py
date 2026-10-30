"""Explicit, lossless UTF-8 tabular analysis import. No assembly/allele guessing."""
import csv
import hashlib
import io
import re
from pydantic import Field
from .models import StrictModel, Snapshot, Variant, Annotation, Provenance, VariantRecord, InvestigationInput
from .admission import validate_required_text

REQUIRED = ('assembly', 'sequence_id', 'position', 'ref', 'alt', 'gene_id', 'transcript_id',
            'consequence', 'tool', 'tool_version', 'source_name', 'source_release')
OPTIONAL = ('protein_consequence', 'context_start', 'reference_sequence')


class TabularFile(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=600_000)
    delimiter: str = Field(pattern=r'^[,\t]$')


class TabularPair(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    files: list[TabularFile] = Field(min_length=2, max_length=2)


def parse_snapshot(file: TabularFile, side: str) -> tuple[Snapshot, int]:
    reader = csv.DictReader(io.StringIO(file.text.lstrip('\ufeff'), newline=''), delimiter=file.delimiter, strict=True)
    names = reader.fieldnames or []
    if len(names) != len(set(names)) or not set(REQUIRED) <= set(names) or set(names) - set(REQUIRED + OPTIONAL):
        raise ValueError(f'{file.name}: use unique documented columns. Required: {", ".join(REQUIRED)}. Optional: {", ".join(OPTIONAL)}')
    records = {}
    provenance = None
    row_count = 0
    for row_number, row in enumerate(reader, 2):
        row_count += 1
        if row_count > 1500:
            raise ValueError(f'{file.name}: maximum 1500 annotation rows per file')
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'{file.name}, row {row_number}: column count does not match header')
        if any(not row[key].strip() for key in REQUIRED):
            raise ValueError(f'{file.name}, row {row_number}: required values must be present; unknown values cannot be inferred')
        if not re.fullmatch(r'[1-9][0-9]*', row['position']):
            raise ValueError(f'{file.name}, row {row_number}: position must be an explicit one-based positive integer')
        context_start, context_sequence = row.get('context_start', ''), row.get('reference_sequence', '')
        context = None
        if context_start or context_sequence:
            if not re.fullmatch(r'[1-9][0-9]*', context_start) or not context_sequence:
                raise ValueError(f'{file.name}, row {row_number}: supply both context_start and reference_sequence or leave both empty')
            context = {'start': int(context_start), 'sequence': context_sequence}
        variant = Variant(**{key: row[key] for key in ('assembly', 'sequence_id', 'ref', 'alt')},
                          position=int(row['position']), reference_context=context)
        metadata = {key: row[key] for key in ('tool', 'tool_version', 'source_name', 'source_release')}
        if provenance is not None and metadata != provenance:
            raise ValueError(f'{file.name}, row {row_number}: tool/source metadata must be consistent within one analysis')
        provenance = metadata
        key = (variant.assembly, variant.sequence_id, variant.position, variant.ref, variant.alt)
        annotation = Annotation(**{key: row[key] for key in ('gene_id', 'transcript_id', 'consequence')},
                                protein_consequence=row.get('protein_consequence') or None)
        if key in records:
            if records[key][0] != variant:
                raise ValueError(f'{file.name}, row {row_number}: reference context conflicts for the same variant')
            records[key][1].append(annotation)
        else:
            records[key] = (variant, [annotation])
    if not records:
        raise ValueError(f'{file.name}: no annotation rows found')
    if len(records) > 51:
        raise ValueError(f'{file.name}: maximum 51 explicitly represented variants')
    # File order is not a transcript selector. Use identifier keys as stable
    # display anchors, while retaining every row and the exact original text.
    ordered = [(records[key][0], sorted(records[key][1], key=lambda row: (row.gene_id, row.transcript_id)))
               for key in sorted(records)]
    primary, *additional = ordered
    digest = hashlib.sha256(file.text.encode('utf-8')).hexdigest()
    snapshot = Snapshot(id=side, label=file.name[:150], variant=primary[0], annotation=primary[1][0],
                        annotations=primary[1][1:],
                        variant_records=[VariantRecord(variant=v, annotations=rows) for v, rows in additional],
                        provenance=Provenance(**provenance, input_sha256=digest,
                            configuration={'import_format': 'genomedebugger-tabular-v1', 'coordinate_system': 'one-based',
                                           'import_filename': file.name, 'original_utf8': file.text,
                                           'row_order_policy': 'canonical-variant-and-annotation-keys-v1',
                                           'metadata_origin': 'user_declared_file'}))
    return snapshot, row_count


def preview_pair(payload: TabularPair):
    snapshots, counts = [], []
    try:
        for file, side in zip(payload.files, 'AB'):
            snapshot, count = parse_snapshot(file, side)
            snapshots.append(snapshot)
            counts.append({'file': file.name, 'rows': count, 'variants': 1 + len(snapshot.variant_records),
                           'original_sha256': snapshot.provenance.input_sha256})
    except csv.Error as exc:
        raise ValueError(f'Malformed tabular file: {exc}') from exc
    result = InvestigationInput(title=payload.title, snapshots=snapshots,
        meaningful_overrides={f'configuration.{key}':False for key in
            ('import_filename','original_utf8','import_output_edited','metadata_origin','import_format')})
    validate_required_text(result)
    return {'input': result, 'files': counts, 'warnings': [
        'All rows were parsed; no unsupported rows were silently dropped.',
        'Tool, source, assembly, and coordinate metadata are declared by the supplied files, not independently authenticated.',
        'Additional variants are matched by exact submitted representation; no cross-assembly mapping is performed.',
        'Rows are sorted by variant and gene/transcript identifiers for a stable overview. This display anchor does not declare a preferred transcript or biological selection.',
        'Original UTF-8 text is preserved in input provenance and portable bundles.']}
