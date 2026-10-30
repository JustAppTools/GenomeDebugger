"""Preview identifier mappings; never silently select one allele or mapping."""
from datetime import datetime, timezone
import re
from urllib.parse import quote
import httpx
from pydantic import Field
from .models import StrictModel
from .ensembl import SourceQuery, SourceError, _json
from .engine import digest


class IdentifierRequest(StrictModel):
    identifier: str = Field(min_length=3, max_length=150)


def resolve_identifier(identifier: str, client=None):
    identifier = identifier.strip()
    if re.fullmatch(r'rs[1-9][0-9]*', identifier):
        path = '/vep/human/id/' + quote(identifier, safe='')
    elif re.fullmatch(r'[A-Za-z0-9_.-]+:[cg]\.[1-9][0-9]*[ACGT]>[ACGT]', identifier):
        path = '/vep/human/hgvs/' + quote(identifier, safe='')
    else:
        raise ValueError('Enter an rsID or a simple c./g. HGVS substitution. Gene names, protein notation, intronic offsets, and complex edits are outside this resolver’s scope.')
    owns = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    try:
        rows = _json(client, path + '?content-type=application/json')
    finally:
        if owns:
            client.close()
    if not isinstance(rows, list) or not rows:
        raise SourceError('The provider returned no usable mapping records')
    choices = {}
    unsupported = 0
    for row in rows:
        if (not isinstance(row, dict) or row.get('assembly_name') != 'GRCh38' or
                type(row.get('start')) is not int or row.get('start') != row.get('end') or
                type(row.get('strand')) is not int or row['strand'] != 1 or
                not isinstance(row.get('allele_string'), str)):
            unsupported += 1
            continue
        alleles = row['allele_string'].split('/')
        if len(alleles) < 2 or any(not re.fullmatch('[ACGT]', allele) for allele in alleles):
            unsupported += 1
            continue
        for alt in alleles[1:]:
            if alt == alleles[0]:
                continue
            try:
                query = SourceQuery(chromosome=row.get('seq_region_name'), position=row['start'], ref=alleles[0], alt=alt)
            except ValueError:
                unsupported += 1
                continue
            key = (query.chromosome, query.position, query.ref, query.alt)
            choices[key] = query.model_dump()
    if len(choices) > 20:
        raise ValueError('More than 20 mappings found; supply explicit coordinates instead. No mapping was selected.')
    return {'identifier':identifier, 'assembly':'GRCh38', 'choices':list(choices.values()), 'unsupported_records':unsupported,
            'resolved_at':datetime.now(timezone.utc).isoformat(), 'source_uri':'https://rest.ensembl.org'+path,
            'response_sha256':digest(rows), 'response':rows,
            'notice':'Select a forward-strand GRCh38 single-base mapping explicitly. Other mappings are outside the current lookup scope. This preview is not an independent reference check or a saved source capture.'}
