"""Pipeline-friendly adapter for the documented tabular v1 format."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx


def main():
    parser = argparse.ArgumentParser(description='Preview two annotated tabular v1 files using the local GenomeDebugger API')
    parser.add_argument('analysis_a', type=Path)
    parser.add_argument('analysis_b', type=Path)
    parser.add_argument('--title', required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--save', action='store_true', help='Save the reviewed comparison after successful preview')
    parser.add_argument('--output', type=Path, help='Write the full preview/result to a new JSON file')
    args = parser.parse_args()
    target = urlparse(args.url)
    if target.scheme != 'http' or target.hostname not in ('127.0.0.1','localhost','::1') or target.username or target.password or target.query or target.fragment or target.path not in ('','/'):
        parser.error('Use an explicit local HTTP workspace origin')
    files = []
    for path in (args.analysis_a, args.analysis_b):
        if path.suffix.lower() not in ('.csv','.tsv') or path.stat().st_size > 600_000:
            parser.error('Use CSV/TSV files of at most 600 KB in the documented tabular v1 format')
        files.append({'name':path.name,'text':path.read_bytes().decode('utf-8',errors='strict'),'delimiter':'\t' if path.suffix.lower()=='.tsv' else ','})
    with httpx.Client(timeout=60) as client:
        response = client.post(args.url.rstrip('/')+'/api/imports/tabular/preview', json={'title':args.title,'files':files})
        response.raise_for_status()
        preview = response.json()
        for file in preview['files']:
            print(f"{file['file']}: {file['rows']} annotation rows; {file['variants']} variants; {file['original_sha256']}")
        body = preview
        if args.save:
            response = client.post(args.url.rstrip('/')+'/api/investigations', json=preview['input'])
            response.raise_for_status()
            body = response.json()
            print('Saved comparison ' + body['id'])
        else:
            print('Preview only. Use --save after reviewing counts, warnings, and metadata.')
        if args.output:
            with args.output.open('x',encoding='utf-8') as output:
                json.dump(body,output,ensure_ascii=False,indent=2)


if __name__ == '__main__':
    main()
