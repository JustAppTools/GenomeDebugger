"""Bounded synthetic import/comparison/library measurement; no external requests."""
import csv
import io
import json
from pathlib import Path
import sys
import time
import uuid

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from app.tabular_import import REQUIRED, TabularPair, preview_pair
from app.engine import compare
from app.limits import validate_input_size
from app.models import InvestigationInput
from app.storage import save
from app.workspace import list_library

output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=list(REQUIRED));writer.writeheader()
for index in range(1000):
    writer.writerow(dict(assembly='GRCh38',sequence_id='NC_000001.11',position='102',ref='C',alt='T',gene_id='GENE-BENCH',
                         transcript_id=f'TX-BENCH-{index}',consequence='missense_variant',tool='Synthetic benchmark tool',tool_version='1',source_name='Synthetic benchmark source',source_release='1'))
payload=TabularPair(title='Synthetic 1000-row import benchmark',files=[{'name':f'analysis-{side}.csv','text':output.getvalue(),'delimiter':','} for side in 'AB'])
started=time.perf_counter();preview=preview_pair(payload);preview['input'].synthetic=True;validate_input_size(preview['input']);import_ms=(time.perf_counter()-started)*1000
started=time.perf_counter();result=compare(preview['input']);compare_ms=(time.perf_counter()-started)*1000
folder=root/'.build'/('benchmark-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True);database=folder/'workspace.db';save(database,result)
small=InvestigationInput.model_validate_json((root/'fixtures/transcript-switch.json').read_text(encoding='utf-8'))
for index in range(50):
    small.title=f'Synthetic library measurement {index:03d}';save(database,compare(small))
started=time.perf_counter();page=list_library(database,sort='oldest');library_ms=(time.perf_counter()-started)*1000
encoded=json.dumps(page).encode()
assert len(page['items'])==50 and page['total']==51 and 'original_utf8' not in json.dumps(page)
assert len(encoded)<100_000
measurement={'annotation_rows_per_analysis':1000,'import_preview_ms':round(import_ms,2),'comparison_ms':round(compare_ms,2),
             'library_total_records':51,'library_page_records':50,'library_page_ms':round(library_ms,2),'library_json_bytes':len(encoded),
             'scope':'Synthetic local measurement; not a throughput or genome-scale guarantee'}
(folder/'measurement.json').write_text(json.dumps(measurement,indent=2),encoding='utf-8')
print(json.dumps(measurement));print('Measurement saved in '+str(folder))
