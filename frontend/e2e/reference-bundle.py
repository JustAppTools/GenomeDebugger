"""Create an internally consistent bundle with constructed NCBI observations."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from app import storage
from app.bundle import create_bundle
from app.engine import compare
from app.ensembl import SourceRecord, CompareTranscripts, comparison_input
from app.models import ReferenceCheckSummary
from app.ncbi import replay_reference_check

source = SourceRecord.model_validate(json.loads((ROOT/'fixtures/snpeff-mane-public-run.json').read_text(encoding='utf-8'))['source'])
agrees = len(sys.argv)>1 and sys.argv[1]=='agree'
base = 'C' if agrees else 'A'
check = replay_reference_check(source, f'>NC_000001.11:6524705-6524705 Constructed browser test observation\n{base}\n',
    {'data':{'seq_id':'NC_000001.11','position':6524704,'deleted_sequence':'C','inserted_sequence':'T'}} if agrees else None,
    {'data':{'hgvs':'NC_000001.11:g.6524705C>T'}} if agrees else None,
    '2026-10-12T04:00:00+00:00' if agrees else '2026-10-12T03:00:00+00:00')
summary = ReferenceCheckSummary.model_validate(check.model_dump(include=set(ReferenceCheckSummary.model_fields)))
payload = comparison_input(source, CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,
    transcript_b=source.transcripts[1].transcript_id), reference_check=summary)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)/'bundle.db'
    storage.save_source_record(path, source)
    storage.save_reference_check(path, check)
    print(json.dumps(create_bundle(path, compare(payload))))
