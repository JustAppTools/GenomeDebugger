# GenomeDebugger

GenomeDebugger is a local, research-oriented workstation for comparing two genomic analysis snapshots and tracing why their results differ. Version 0.3.0 adds an explicitly triggered Ensembl VEP adapter for current GRCh38 single nucleotide variants. The synthetic transcript-selection investigation and regression workflow remain available offline. The tool does **not** assign clinical pathogenicity.

## Start on Windows

Requires Python 3.11+ and Node.js 20+. From `D:\Creation\GenomeDebugger` in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
```

If `python` is unavailable in the Codex desktop environment, this machine also has a bundled Python executable at `C:\Users\vicsp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`. Use it instead of `python` for the first command.

Start the backend in one PowerShell terminal:

```powershell
cd D:\Creation\GenomeDebugger\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
cd D:\Creation\GenomeDebugger\frontend
npm run dev -- --host 127.0.0.1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Select **Load synthetic demo**, inspect the JSON, then **Run comparison**. The API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## What works

- Strict validation of two versioned JSON snapshots, provenance fields, and an optional synthetic controlled lookup.
- Reference-context-checked comparison of short substitution edits on the same assembly and sequence accession. Padded and unpadded descriptions of the demo substitution match. Indels, assembly changes, missing reference context, and mismatched contexts remain unresolved.
- Field-level differences with a meaningful-change filter. Clinical classification is compared only for matching condition IDs and frameworks.
- Candidate findings linked to evidence. The synthetic demo replays the same lookup table with two transcript selections and verifies that the outputs match the supplied snapshots while tool, source release, configuration, and allele identity are held constant.
- Local SQLite storage, investigation retrieval, JSON export, and Markdown report export with SHA-256 hash of canonicalized input JSON.
- Immutable regression cases captured from saved investigations. Rerun a pinned case after an engine change, or paste candidate outputs for the same variant descriptions. The workbench shows pass/fail, failed fields, changed evidence, input drift, and saved run history.
- Explicit **Public source** workflow for a GRCh38 SNV. **Fetch current from Ensembl** transmits only chromosome, position, reference, and alternate allele to `rest.ensembl.org`; **Load cached** makes no external request. The adapter checks the reference base against Ensembl sequence, records its assembly accession and reported release, preserves the VEP response and SHA-256 hash in local SQLite, and falls back to an existing cached record if a live request fails. Two transcripts from one preserved response can be compared as an investigation.
- Other investigation input stays local. POST bodies are limited to 1 MB.

The synthetic `GENE-DEMO-1`, transcript names, and protein labels are fabricated. They are not ClinVar or Ensembl assertions. “Verified” in the demo means verified **within the supplied controlled synthetic fixture**, not independently confirmed against a biological reference assembly or external annotation system.

## Input format

See [fixtures/transcript-switch.json](fixtures/transcript-switch.json) for a complete example. Each `Snapshot` has `id`, `label`, `variant`, `annotation`, and `provenance`. `variant.position` and `reference_context.start` use one-based coordinates. `ref` must match its supplied reference context. `controlled_lookup` is optional and accepted only when `synthetic: true`.

To submit a file from PowerShell:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/investigations -Method Post -ContentType 'application/json' -InFile .\fixtures\transcript-switch.json
```

The API response contains `input`, `identity`, `differences`, `findings`, `evidence`, and `input_sha256`. A saved record is retrieved at `/api/investigations/{id}` and its Markdown report at `/api/investigations/{id}/report.md`.

## Regression workflow

After running an investigation, open **Regression** and save a named baseline. **Run pinned baseline** recomputes the saved input with the current engine and requires the same annotations, identity status, field differences, findings, and evidence data. **Check candidate** accepts new structured snapshot JSON for the exact same submitted variants. It checks expected outputs and findings, while listing provenance and evidence changes separately. Candidate evidence changes are informative and do not fail an otherwise matching output assertion. Both modes save their run results locally. After restarting the browser, reopen the investigation from **Recent investigations** to access its saved regression case and run history.

API equivalents: `POST /api/investigations/{id}/regression-cases` with `{"name":"..."}`, then `POST /api/regression-cases/{case_id}/runs` with `{}` for pinned replay or `{"candidate": <InvestigationInput>}` for a candidate. Retrieve saved cases and runs with the corresponding GET endpoints in `/docs`.

## Public Ensembl workflow

Open **Public source**. The form starts with [Ensembl's documented VEP example](https://rest.ensembl.org/documentation/info/vep_region_get), GRCh38 chromosome 1, position 6,524,705, C→T. Click **Load cached** to work without network access, or **Fetch current from Ensembl** to make four requests: [reported releases](https://rest.ensembl.org/documentation/info/data), [human assembly](https://rest.ensembl.org/documentation/info/assembly_info), [one-base reference sequence](https://rest.ensembl.org/documentation/info/sequence_region), and [VEP region annotation](https://rest.ensembl.org/documentation/info/vep_region_get). The adapter checks the coordinate, assembly, alleles, and reference base before saving the response. Each fetch is a separate local record; it does not overwrite older records. Select two returned transcripts and click **Compare** to save a local investigation. Findings from this public-source comparison remain **possible**, since no independent controlled annotation replay proves why two transcript consequences differ.

API equivalent: `POST /api/sources/ensembl/lookup` with `{"query":{"chromosome":"1","position":6524705,"ref":"C","alt":"T"},"mode":"fetch"}`. Use `"mode":"cache_only"` for a guaranteed offline lookup. A saved record is available at `GET /api/sources/ensembl/records/{id}`. To compare, call `POST /api/sources/ensembl/records/{id}/compare` with `{"transcript_a":"...","transcript_b":"..."}` using IDs in that record.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run build
npm audit
```

## Current boundaries

The public adapter supports only current Ensembl GRCh38 SNVs and transcript consequence predictions. Its release metadata is observed during retrieval and does not prove an atomic or historical release snapshot; tool version is not reported by the API. There is no reference-genome download, repeat-aware indel normalization, HGVS/SPDI/VRS conversion, liftover, ClinVar adapter, or historical timeline yet. Regression checks rerun the comparison engine against saved snapshots; they do not rerun VEP. User supplied snapshot values are not externally authenticated. The application is a research and bioinformatics quality-assurance tool, not a clinical device. See [scientific validity](docs/scientific-validity.md) and [roadmap](docs/roadmap.md).
