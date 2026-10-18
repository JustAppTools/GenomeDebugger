# GenomeDebugger

GenomeDebugger is a local, research-oriented workstation for comparing two genomic analysis snapshots and tracing why their results differ. Version 0.5.0 adds guided input, additional variant and annotation rows, local record management, replay-checked bundles, and a comparison with user-supplied SnpEff ANN output. The synthetic transcript-selection investigation and regression workflow remain available offline. The tool does **not** assign clinical pathogenicity.

## Start on Windows

Requires Python 3.11+ and Node.js 20+. From `D:\Creation\GenomeDebugger` in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
```

If `python` is unavailable in the Codex desktop environment, this machine also has a bundled Python executable at `C:\Users\vicsp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`. Use it instead of `python` for the first command.

After installation, start both local services with `powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1`. Use `-NoBrowser` to leave the browser where it is. The script checks both services and prints the local URL when ready. After changing Python code, rerun it with `-Restart` to restart the local API safely.

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

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Select **Load synthetic demo** to run the comparison and see its findings. Open **Snapshot JSON** to inspect or edit the input, then use **Compare** to run an edited version. The API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## What works

- Strict validation of two versioned snapshots, provenance fields, optional additional `variant_records` and annotation rows, and an optional synthetic controlled lookup. The guided editor covers one primary variant; JSON mode exposes additional rows.
- Reference-context-checked comparison of short substitution edits on the same assembly and sequence accession. Padded and unpadded descriptions of the demo substitution match. Local sequence agreement for indels remains **unresolved** until a validated assembly reference and standards-aware normalization establish equivalence.
- Field-level differences with a meaningful-change filter. Clinical classification is compared only for matching condition IDs and frameworks.
- Candidate findings linked to evidence. The synthetic demo replays the same lookup table with two transcript selections and verifies that the outputs match the supplied snapshots while tool, source release, configuration, and allele identity are held constant.
- Local SQLite storage, search and deletion of unpinned investigations, JSON and Markdown exports, backup CLI, and portable bundles. Bundle import recomputes results with the current engine and checks preserved response hashes; contained hashes detect corruption but do not authenticate external data. Older saved records export as current-engine replays under a new input ID while their originals stay saved.
- Immutable regression cases captured from saved investigations. Rerun a pinned case after an engine change, or paste candidate outputs for the same variant descriptions. The workbench shows pass/fail, failed fields, changed evidence, input drift, and saved run history.
- Explicit **Public source** workflow for a GRCh38 SNV. **Fetch current from Ensembl** transmits only chromosome, position, reference, and alternate allele to `rest.ensembl.org`; **Load cached** makes no external request. The adapter checks the reference base against Ensembl sequence, records its assembly accession and reported release, preserves the VEP response and SHA-256 hash in local SQLite, and falls back to an existing cached record if a live request fails. Two transcripts from one preserved response can be compared as an investigation.
- Optional **Check with NCBI** action on a saved Ensembl record. It uses the pinned GRCh38.p14 chromosome accession from [NCBI's assembly report](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/405/GCF_000001405.40_GRCh38.p14/GCF_000001405.40_GRCh38.p14_assembly_report.txt), retrieves the one-base RefSeq sequence through EFetch, and checks the SNV's zero-based SPDI and genomic HGVS against NCBI Variation Services. The original responses, URLs, hashes, and pass/disagree status are saved separately. **Load saved check** stays offline. If the reference base disagrees, the representation checks are skipped. This checks allele representation independently of Ensembl, not VEP consequence predictions.
- Optional comparison of a user-supplied, single-variant SnpEff `ANN` VCF with every transcript in a preserved Ensembl record. Only exact transcript IDs and consequence term sets are compared. Missing transcript rows yield `unresolved`; mismatched terms yield `disagree`. The app does not run SnpEff or authenticate the declared version or database hash.
- Other investigation input stays local. POST bodies are limited to 1 MB.

The synthetic `GENE-DEMO-1`, transcript names, and protein labels are fabricated. They are not ClinVar or Ensembl assertions. “Verified” in the demo means verified **within the supplied controlled synthetic fixture**, not independently confirmed against a biological reference assembly or external annotation system.

## Input format

See [fixtures/transcript-switch.json](fixtures/transcript-switch.json) for a complete example. Each `Snapshot` has `id`, `label`, a primary `variant` and `annotation`, and `provenance`. Optional `annotations` add rows for the primary variant; optional `variant_records` add other exact variant representations, each with one or more annotations. `variant.position` and `reference_context.start` use one-based coordinates. `ref` must match its supplied reference context. `controlled_lookup` is optional and accepted only when `synthetic: true`.

To submit a file from PowerShell:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/investigations -Method Post -ContentType 'application/json' -InFile .\fixtures\transcript-switch.json
```

The API response contains `input`, `identity`, `differences`, `findings`, `evidence`, and `input_sha256`. A saved record is retrieved at `/api/investigations/{id}` and its Markdown report at `/api/investigations/{id}/report.md`.

## Regression workflow

After running an investigation, open **Regression** and save a named baseline. **Run pinned baseline** recomputes the saved input with the current engine and requires the same annotations, identity status, field differences, findings, and evidence data. **Check candidate** accepts new structured snapshot JSON for the exact same submitted variants. It checks expected outputs and findings, while listing provenance and evidence changes separately. Candidate evidence changes are informative and do not fail an otherwise matching output assertion. Both modes save their run results locally. Reopen an investigation from **Saved records** to access its regression case and run history.

API equivalents: `POST /api/investigations/{id}/regression-cases` with `{"name":"..."}`, then `POST /api/regression-cases/{case_id}/runs` with `{}` for pinned replay or `{"candidate": <InvestigationInput>}` for a candidate. Retrieve saved cases and runs with the corresponding GET endpoints in `/docs`.

## Public Ensembl workflow

Open **Public source**. The form starts with [Ensembl's documented VEP example](https://rest.ensembl.org/documentation/info/vep_region_get), GRCh38 chromosome 1, position 6,524,705, C→T. Click **Load cached** to work without network access, or **Fetch current from Ensembl** to make four requests: [reported releases](https://rest.ensembl.org/documentation/info/data), [human assembly](https://rest.ensembl.org/documentation/info/assembly_info), [one-base reference sequence](https://rest.ensembl.org/documentation/info/sequence_region), and [VEP region annotation](https://rest.ensembl.org/documentation/info/vep_region_get). The adapter checks the coordinate, assembly, alleles, and reference base before saving the response. Each fetch is a separate local record; it does not overwrite older records. Select two returned transcripts and click **Compare** to save a local investigation. Findings from this public-source comparison remain **possible**, since no independent controlled annotation replay proves why two transcript consequences differ.

The **rs56116432 example** button fills GRCh38 chromosome 9, position 133,256,042, C→A. It comes from the [Ensembl VEP ID example](https://rest.ensembl.org/documentation/info/vep_id_get) and exercises a transcript carrying both `intron_variant` and `non_coding_transcript_variant` consequence terms. Both examples were checked live against Ensembl and NCBI during development; their current responses can change.

After loading a source record, click **Check with NCBI** to contact `eutils.ncbi.nlm.nih.gov` and `api.ncbi.nlm.nih.gov` with its pinned accession, coordinate, and alleles. The [EFetch parameters](https://www.ncbi.nlm.nih.gov/books/NBK25499/) request one base; NCBI [Variation Services](https://api.ncbi.nlm.nih.gov/variation/v0/) returns contextual SPDI and HGVS. The app stores an independent check record. A subsequent transcript comparison links its check ID, response hash, and agreement status in the investigation input and provenance. Agreement does not upgrade a transcript cause above **possible**. Disagreement makes cross-source identity **unresolved** and adds an explicit finding. See [NCBI's disclaimer and copyright](https://www.ncbi.nlm.nih.gov/home/about/policies/).

API equivalent: `POST /api/sources/ensembl/lookup` with `{"query":{"chromosome":"1","position":6524705,"ref":"C","alt":"T"},"mode":"fetch"}`. Use `"mode":"cache_only"` for a guaranteed offline lookup. A saved record is available at `GET /api/sources/ensembl/records/{id}`. To compare, call `POST /api/sources/ensembl/records/{id}/compare` with `{"transcript_a":"...","transcript_b":"..."}` using IDs in that record.

For the independent check, `POST /api/sources/ensembl/records/{id}/reference-check` with `{"mode":"fetch"}` or `{"mode":"cache_only"}`. Retrieve a saved check at `GET /api/sources/reference-checks/{id}`. A check is valid only for the same preserved Ensembl record and the pinned assembly mapping.

The SnpEff comparison is available below the Ensembl record. Paste one annotated VCF row and declare its SnpEff version, database name, and database SHA-256. These fields are user assertions, not an authenticated run. The comparison and VCF are saved locally and can be linked to a new transcript comparison. A partial transcript match is unresolved. API: `POST /api/sources/ensembl/records/{id}/snpeff-check`, then `GET` the same path to load the latest saved check.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run build
npx playwright install --only-shell chromium
npm run test:e2e
npm audit
```

## Current boundaries

The public adapter supports only current Ensembl GRCh38 SNVs and transcript consequence predictions. Its release metadata is observed during retrieval and does not prove an atomic or historical release snapshot; tool version is not reported by the API. The NCBI check supports only GRCh38.p14 primary nuclear chromosomes and single-base substitutions; mitochondrial HGVS is outside its scope. It validates one reference base and two notation services, not transcript consequences or clinical meaning. Additional variants can be compared by exact representation, but no full reference-genome download, reference-backed repeat-aware indel normalization, general HGVS/SPDI/VRS mapping, liftover, ClinVar adapter, or historical timeline exists yet. Regression checks rerun the local comparison engine, not VEP, NCBI, or SnpEff. User supplied snapshot and SnpEff metadata are not externally authenticated. The application is a research and bioinformatics quality-assurance tool, not a clinical device. See [scientific validity](docs/scientific-validity.md) and [roadmap](docs/roadmap.md).
