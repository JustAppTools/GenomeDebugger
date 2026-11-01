# GenomeDebugger

## Public hosted preview

[**Open GenomeDebugger**](https://genomedebugger.onrender.com)

The full React/Python comparison workbench is live on **Render Free**, with a separate temporary browser workspace for each visitor. The free server can take about a minute to wake up; download full bundles or reports to keep work beyond restarts. See [free hosting and visitor data](docs/free-hosting.md) and the [verified deployment](docs/deployment-2026-10-31.md).

## Local application

GenomeDebugger compares two already analyzed genomic outputs and explains their differences, supporting evidence, and uncertainty. Application **0.10.1** repairs the fifteen findings in the [0.10.0 audit](docs/fixes-0.10.1-2026-10-31.md), retaining a guided workspace with horizontal navigation, three input paths, readable explanations, and a distinct warm neutral/plum visual design. Public hosting retains separate temporary browser workspaces. See [the workspace redesign](docs/guided-workspace-0.10.0-2026-10-31.md) and [previous fixes and release limits](docs/fixes-0.8.3-2026-10-29.md). Comparator **0.6.8** compares complete imported row collections and unordered compound consequence terms, trimming whitespace around each term, while archived rules preserve historical replay. The tool does **not** diagnose conditions or decide whether a DNA change is harmful.

See the [0.8.0 implementation coverage and remaining dependencies](docs/product-changes-0.8.0-2026-10-26.md), [input/data guide](docs/local-data-and-imports.md), and [desktop package guide](docs/desktop-guide.md).

## Getting started

- **Understand an example:** a clearly synthetic transcript comparison, matching-output example, or insufficient-evidence example.
- **Import two analysis results:** preview documented tabular v1 CSV/TSV files, import the two-snapshot JSON schema, or copy reported values through DNA/prediction/source/review steps. No assembly, accession, or allele is guessed for a new manual input.
- **Look up a public DNA change:** current Ensembl GRCh38 SNV lookup comes first. A scoped rsID/simple HGVS resolver previews supported mappings and requires explicit allele selection. Historical VEP and SnpEff tools remain available as advanced workflows.
- Read the specific result, separate check scopes, and engine findings. Supporting details show readable values and literal DNA edits first; exact JSON remains optional.
- Explicitly save/resume/discard a browser-local draft. Organize completed comparisons using labels, notes, tags, favorites, archive/restore, filters, and sorting. Organization does not change scientific records or their hashes.
- Preview/download a readable HTML report for reading or printing, export Markdown/JSON, or use **Full bundle** for replay-checked transfer. A copied localhost link only works on the installation holding the record.
- Use **Guide** for input origins, supported scopes, terms, and troubleshooting. Footer **Local data and settings** (or **Workspace data and settings** on the public preview) provides storage, backups, and restoration guidance. Open **Advanced tools** within a comparison for scientific saved tests or its original input JSON. The footer shows the application version; expand it for the comparison-engine version.


## Start on Windows

For the source checkout, use **Setup GenomeDebugger.cmd** once, then **Start GenomeDebugger.cmd** and **Stop GenomeDebugger.cmd**. Setup requires Python 3.11+ and an active Node.js LTS release. The optional portable desktop package bundles its runtime and compiled UI; see the desktop guide.

Manual source setup with Python 3.11+ and Node.js 20+: from `D:\Creation\GenomeDebugger` in PowerShell:

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

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Select **Try an example** to run the comparison and see its findings. Open **Advanced tools → Input JSON** to inspect or edit the input, then use **Compare** to run an edited version. The API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## What works

- Strict validation of two versioned snapshots, provenance fields, optional additional `variant_records` and annotation rows, and an optional synthetic controlled lookup. The guided editor supports additional variants and annotations; JSON mode retains the full schema.
- Reference-context-checked comparison of short substitution edits on the same assembly and sequence accession. Padded and unpadded descriptions of the demo substitution match. Local sequence agreement for indels remains **unresolved** until a validated assembly reference and standards-aware normalization establish equivalence.
- Field-level differences with a meaningful-change filter. Clinical classification is compared only for matching condition IDs and frameworks.
- Candidate findings linked to evidence. The synthetic demo replays the same lookup table with two transcript selections and verifies that the outputs match the supplied snapshots while tool, source release, configuration, and allele identity are held constant.
- Local SQLite storage, search and deletion of unpinned investigations, JSON and Markdown exports, backup CLI, and portable bundles. Bundle import recomputes results with the current engine and checks preserved response hashes; contained hashes detect corruption but do not authenticate external data. Older saved records export as current-engine replays under a new versioned result ID while their originals stay saved. Archived 0.5.0–0.6.4 bundles remain verifiable under their original engine rules, with current source/check consistency validation.
- Immutable regression cases captured from saved investigations. Rerun a pinned case after an engine change, or paste candidate outputs for the same variant descriptions. The workbench shows pass/fail, failed fields, changed evidence, input drift, and saved run history.
- Explicit **Look up a DNA change** workflow for a GRCh38 SNV. **Fetch current from Ensembl** transmits only chromosome, position, reference, and alternate allele to `rest.ensembl.org`; **Load cached** makes no external request. The adapter checks the reference base against Ensembl sequence, records its assembly accession and reported release, preserves the VEP response and SHA-256 hash in local SQLite, and falls back to an existing cached record if a live request fails. Two transcripts from one preserved response can be compared as an investigation.
- Optional **Check with NCBI** action on a saved Ensembl record. It uses the pinned GRCh38.p14 chromosome accession from [NCBI's assembly report](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/405/GCF_000001405.40_GRCh38.p14/GCF_000001405.40_GRCh38.p14_assembly_report.txt), retrieves the one-base RefSeq sequence through EFetch, and checks the SNV's zero-based SPDI and genomic HGVS against NCBI Variation Services. The original responses, URLs, hashes, and pass/disagree status are saved separately. **Load saved check** stays offline. If the reference base disagrees, the representation checks are skipped. This checks allele representation independently of Ensembl, not VEP consequence predictions.
- Optional comparison of a user-supplied, single-variant SnpEff `ANN` VCF with every transcript in a preserved Ensembl record. Only exact transcript IDs and consequence term sets are compared. Missing transcript rows yield `unresolved`; mismatched terms yield `disagree`. A separate runner supports pinned local SnpEff execution; supplied-output metadata remains user declared.
- Other investigation input stays local. Comparison data has a 1 MB budget, measured without optional default values. Ordinary POST bodies and input-file imports allow 2 MB so accepted inputs can be resubmitted with expanded defaults, including as regression candidates. Bundles allow 32 MB overall and enforce the same comparison-data budget during verification/import.

The synthetic `GENE-DEMO-1`, transcript names, and protein labels are fabricated. They are not ClinVar or Ensembl assertions. “Verified” in the demo means verified **within the supplied controlled synthetic fixture**, not independently confirmed against a biological reference assembly or external annotation system.

## Input format

See [fixtures/transcript-switch.json](fixtures/transcript-switch.json) for a complete example. Each `Snapshot` has `id`, `label`, a primary `variant` and `annotation`, and `provenance`. Optional `annotations` add rows for the primary variant; optional `variant_records` add other exact variant representations, each with one or more annotations. `variant.position` and `reference_context.start` use one-based coordinates. `ref` must match its supplied reference context. `controlled_lookup` is optional and accepted only when `synthetic: true`.

To submit a file from PowerShell:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/investigations -Method Post -ContentType 'application/json' -InFile .\fixtures\transcript-switch.json
```

The API response contains `input`, `identity`, `differences`, `findings`, `evidence`, and `input_sha256`. A saved record is retrieved at `/api/investigations/{id}` and its Markdown report at `/api/investigations/{id}/report.md`.

## Regression workflow

After running an investigation, open **Saved tests** and save a named baseline. **Run pinned baseline** recomputes the saved input with the current engine and requires the same annotations, identity status, field differences, findings, and evidence data. **Check candidate** accepts new structured snapshot JSON for the exact same submitted variants. It checks absolute primary and additional annotation and variant outputs and findings, while listing provenance and evidence changes separately. Shared changes in both snapshots fail; row ordering alone does not. Candidate evidence changes are informative and do not fail an otherwise matching output assertion. Both modes save their run results locally. Reopen an investigation from **Saved comparisons** to access its regression case and run history.

Preserved VEP values are read-only in the candidate form until you choose **Use custom output for analysis A/B**. This explicitly identifies your edited output as a custom transformation and lets you name its tool and version. The original source stays linked as an input citation, and the saved baseline stays intact. SnpEff evidence against the original output is detached from the candidate; allele-only reference evidence is retained. A changed output can then produce a saved failed assertion rather than a contradictory-source validation error. Test names support 1–200 Unicode characters, with a visible count. The name is locked while saving, becomes editable again after failure, and wraps in the saved phone layout.

When multiple baselines exist, choose **Saved baseline** to switch between them and their run histories. **Refresh baselines** discovers cases saved in other tabs while preserving the current selection. All discovery pages are included.

API equivalents: `POST /api/investigations/{id}/regression-cases` with `{"name":"..."}`, then `POST /api/regression-cases/{case_id}/runs` with `{}` for pinned replay or `{"candidate": <InvestigationInput>}` for a candidate. Retrieve saved cases and runs with the corresponding GET endpoints in `/docs`.

Editing a candidate marks its previous verdict as an earlier result, including edits made during a pending run. Opening a candidate from history identifies it as a saved run. Use **Check candidate** to test the current editor input. Input imports and example loading preserve edits made while loading and explain when a newer draft was kept. Navigating to another screen prevents older root operations from taking over that screen. Completed saves remain available in Saved comparisons; navigation does not cancel a write already submitted to the backend.

The library uses stable page anchors and an upper bound for the current browsing session. A persistent sequence prevents newly saved records from entering an older browsing snapshot after deletion, including after the library becomes empty. **Refresh records** starts again with the latest collection. API clients can use `GET /api/investigations/page` with `q` and `limit`; keep its returned `ceiling` and use `next_before` as `before` to continue. The original list API with `offset` remains available. Both searches use Unicode case folding and treat wildcard characters literally. Schema version 2 adds creation-order metadata while retaining original investigation IDs, dates, and serialized results.

VCF files show a reading status while decoding; check actions wait for completion. Loading a file invalidates checks for the previous text. Invalid Unicode, including malformed JSON escapes in nested metadata, is rejected without replacing analysis characters.

## Public Ensembl workflow

Open **Look up a DNA change**. The form starts with [Ensembl's documented VEP example](https://rest.ensembl.org/documentation/info/vep_region_get), GRCh38 chromosome 1, position 6,524,705, C→T. Click **Load cached** to work without network access, or **Fetch current from Ensembl** to make four requests: [reported releases](https://rest.ensembl.org/documentation/info/data), [human assembly](https://rest.ensembl.org/documentation/info/assembly_info), [one-base reference sequence](https://rest.ensembl.org/documentation/info/sequence_region), and [VEP region annotation](https://rest.ensembl.org/documentation/info/vep_region_get). The adapter checks the coordinate, assembly, alleles, and reference base before saving the response. Each fetch is a separate local record; it does not overwrite older records. Select two returned transcripts and click **Compare** to save a local investigation. Findings from this public-source comparison remain **possible**, since no independent controlled annotation replay proves why two transcript consequences differ.

The **rs56116432 example** button fills GRCh38 chromosome 9, position 133,256,042, C→A. It comes from the [Ensembl VEP ID example](https://rest.ensembl.org/documentation/info/vep_id_get) and exercises a transcript carrying both `intron_variant` and `non_coding_transcript_variant` consequence terms. Both examples were checked live against Ensembl and NCBI during development; their current responses can change.

After loading a source record, click **Check with NCBI** to contact `eutils.ncbi.nlm.nih.gov` and `api.ncbi.nlm.nih.gov` with its pinned accession, coordinate, and alleles. The [EFetch parameters](https://www.ncbi.nlm.nih.gov/books/NBK25499/) request one base; NCBI [Variation Services](https://api.ncbi.nlm.nih.gov/variation/v0/) returns contextual SPDI and HGVS. The app stores an independent check record. A subsequent browser comparison links the check currently displayed as selected, including its ID, response hash, and agreement status. Agreement does not upgrade a transcript cause above **possible**. Disagreement makes cross-source identity **unresolved** and adds an explicit finding. See [NCBI's disclaimer and copyright](https://www.ncbi.nlm.nih.gov/home/about/policies/).

API equivalent: `POST /api/sources/ensembl/lookup` with `{"query":{"chromosome":"1","position":6524705,"ref":"C","alt":"T"},"mode":"fetch"}`. Use `"mode":"cache_only"` for a guaranteed offline lookup. A saved record is available at `GET /api/sources/ensembl/records/{id}`. To compare, call `POST /api/sources/ensembl/records/{id}/compare` with `{"transcript_a":"...","transcript_b":"..."}` using IDs in that record.

For explicit evidence selection, include `reference_check_id` and `annotation_check_id` in that comparison request: a saved check ID pins that exact record; `null` excludes that check. IDs must belong to the selected source. The browser always sends both fields and displays its selected checks. Legacy API clients that omit a field retain automatic latest-check selection for that field. A later check saved by another client cannot replace an explicitly selected record.

For the independent check, `POST /api/sources/ensembl/records/{id}/reference-check` with `{"mode":"fetch"}` or `{"mode":"cache_only"}`. Retrieve a saved check at `GET /api/sources/reference-checks/{id}`. A check is valid only for the same preserved Ensembl record and the pinned assembly mapping.

The SnpEff comparison is available below the Ensembl record. Paste one annotated VCF row and declare its SnpEff version, database name, and database SHA-256. These fields are user assertions, not an authenticated run. The comparison and VCF are saved locally and can be linked to a new transcript comparison. A partial transcript match is unresolved. API: `POST /api/sources/ensembl/records/{id}/snpeff-check`, then `GET` the same path to load the latest saved check.

## Local browser access

The API accepts loopback connections with localhost or loopback-IP Host headers. Browser mutations require the default frontend origin (`http://127.0.0.1:5173` or `http://localhost:5173`) or the API's own origin, so its `/docs` interface remains usable. Other origins, including `null`, are rejected before side effects. Local CLI clients without browser Origin/Fetch Metadata headers remain supported.

For an intentional alternate frontend port, set `GENOMEDEBUGGER_ALLOWED_ORIGINS` to a comma-separated list of exact trusted origins before starting the backend. The isolated browser test server explicitly trusts its frontend on port 5174. CORS uses the same configured origins. This local-only policy is not authentication for a hosted or multi-user service.

## Timestamp ordering and check scope

Preserved source/check dates are ordered by normalized UTC time, with most recently inserted records first when times are equal. Original timestamp text, immutable JSON, IDs, and hashes are retained. New records and bundle imports require valid ISO 8601 datetimes with a timezone. Older malformed dates remain readable and sort after valid dates.

Synthetic investigation inputs cannot carry public-reference allele checks through live checking, offline replay, bundles, or cache loading. Previously stored out-of-scope checks remain stored; reports explain their exclusion and bundle export reports the scope error. Refreshing the preserved-source list keeps valid source/transcript selections, including edits during loading; unavailable selections receive explicit replacements and a notice.

## Integrity and record management

SnpEff ID/status/origin claims must agree with the actual linked summary and preserved check. Missing legacy flags are allowed; contradictory or dangling flags are rejected. Technical cards derive their check links from the real summary.

Bundle import validates linked VEP outputs against their preserved source and checks every derived SnpEff outcome, including its explanation. Source-generated comparisons declare whether they contain the full transcript set; older selected-row snapshots remain supported. Custom postprocessors must identify their own tool in provenance rather than claim direct VEP output. All linked records import in one transaction. Conflicting immutable artifact IDs return HTTP 409; identical re-imports do not consume new capacity.

Source-linked direct VEP claims are validated before generic comparisons and regression candidates are saved. Both VEP adapters and bundle verification reject malformed transcript rows rather than silently omit them from a complete set. SnpEff origin flags must agree with the preserved check's execution record. Reports derive execution provenance from that record, and comparator evidence stays neutral about execution. Preserved or imported execution records are not external attestations.

Source-origin flags must agree with preserved source records. Missing legacy flags remain supported. Reports determine current, historical, or mixed source origins from the preserved records; without those records, they identify source provenance as unavailable. Duplicate SnpEff INFO tags are rejected before annotations or warnings can be discarded. Mitochondrial targets are rejected before external requests and during offline replay; cached allele checks are replayed before being returned.

NCBI check IDs and statuses in snapshot configuration must agree with the linked `reference_check` summary. Legacy inputs may omit these duplicate fields. When removing a check, also remove `reference_check_id` and `reference_check_status` from snapshot configuration. Reports and technical cards display the linked summary rather than editable duplicate metadata. Regression cases and runs are saved under the same transactional parent, immutability, and capacity checks as other records; actual SQLite allocations are checked before commit.

Linked NCBI reference and SnpEff annotation checks must apply to the complete primary variant in both snapshots: assembly, sequence, position, reference, and alternate allele. Known pinned GRCh38 aliases are supported. Transformed output alleles must remove inapplicable checks; generic comparisons and regression candidates require the original check records locally. All ANN warnings/errors are checked before filtering feature types. Invalid normalized SPDI intervals are rejected against pinned sequence lengths, including during bundle replay.

Storage budgeting checks actual SQLite allocation inside the write transaction. Deleted cells within occupied pages can be reused, as can whole free pages; a serialized-size estimate no longer rejects writes that fit. Growth beyond the configured quota still rolls back the entire write. Saved investigations have page controls, preserved sources and run history can load older entries, and regression discovery filters by investigation before pagination. API lists accept `limit` and `offset`; `/api/regression-cases` additionally accepts `source_investigation_id`.

Deleting an investigation removes its owned allele checks in the same transaction; shared source records remain preserved. Switching the selected primary variant retains complete collection membership. Only the latest requested investigation selection can replace the workspace. Default regression names respect the 200-character limit and validation errors identify the affected field.

Owned allele checks require their investigation and matching input hash inside the save transaction. If an investigation is deleted while an external check runs, the late save returns HTTP 404 and leaves no owned data behind. Transcript/source selection changes invalidate pending comparisons in both source panels and preserve the newer selection for retry. Guided text limits count Unicode code points consistently with the API.

Clinical assertion date differences are retained as metadata and are nonmeaningful by default. A field-specific override can change that policy. Overrides support all generated field-path lengths within the existing request-size and override-count limits.

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

## Reference-backed allele identity

After comparing non-synthetic snapshots, use **Check allele identity with NCBI** in the overview. This explicitly sends the two accessions, coordinates, and alleles to NCBI. EFetch validates each complete reference allele against pinned GRCh38.p14 primary nuclear sequences before Variation Services contextualizes SPDI and returns genomic HGVS. Length-changing alleles and repeat-shifted deletions are supported. Raw responses and hashes are saved, included in Markdown, and replay-verified in bundles. The independent check is separate from the stored local-context result. **Load saved allele check** stays offline. API: `POST /api/investigations/{id}/allele-check` with `{"mode":"fetch"}` or `{"mode":"cache_only"}`.

The live example in [ncbi-repeat-deletion-observation.json](fixtures/ncbi-repeat-deletion-observation.json) compares chr1:10004 CC>C with chr1:10005 CC>C. Both yielded `NC_000001.11:10003:CCC:CC` and `NC_000001.11:g.10006del`. Annotation placeholders make no consequence claim.

## Pinned local SnpEff

Install once on Windows:

```powershell
.\.venv\Scripts\python.exe scripts/setup_snpeff.py
```

The installer downloads official Eclipse Temurin Java, SnpEff, and the reviewed `GRCh38.mane.1.0.ensembl` database. This is the currently supported local database/build combination; unsupported or conflicting assembly metadata is rejected before execution. It verifies the Java publisher checksum and pins observed software, configuration, and database file hashes in ignored `tools/snpeff/runtime.json`. Installation needs network access, disk space, and several minutes. Existing pinned binaries and databases are preserved. The installer can add assembly metadata to a known 0.6.0 installation after verifying its pinned files. Override the manifest path with `GENOMEDEBUGGER_SNPEFF_MANIFEST` if needed.

In **Look up a DNA change**, load an Ensembl record, inspect local setup, then run local SnpEff. The runner verifies artifacts before and after execution, disables downloads/logging, uses a temporary working directory, and preserves input/output VCF, stderr, version, command, assembly metadata, artifact sources and hashes. New executions capture and hash exact input, stdout, and stderr bytes, preserve CRLF, and reject invalid UTF-8 without replacement. Their capture format is `utf8_bytes`; existing execution records default to `legacy_text` and retain their original representation and hashes. API: `GET /api/tools/snpeff` and `POST /api/sources/ensembl/records/{id}/snpeff-run`.

Exact transcript versions are retained. The captured [real MANE run](fixtures/snpeff-mane-public-run.json) has unmatched transcript versions and remains unresolved. Install binaries/databases on each machine; they are not committed. Imported execution records preserve provenance but are not authenticated execution attestations.

## Historical VEP output

In **Look up a DNA change**, expand **Import historical VEP output**. Upload actual VEP JSON for one GRCh38 SNV and declare its original time, release, software version, assembly accession, and artifact location. Original bytes and hashes are preserved. Load preserved sources and select two records and transcripts for comparison. Bundles retain both sources. Historical imports cannot satisfy current-source cache lookups.

Admission rejects non-finite/overflowing numeric values and transcript data that exceeds supported comparison limits: at most 1,001 total transcripts, gene/transcript IDs up to 100 characters, and a joined consequence string up to 500 characters. No excess rows are silently omitted. Direct VEP snapshots must agree with any supplied source-derived assembly, capture time, artifact hash, and generation time; omitted legacy duplicate fields remain supported. Bundle download/import forwards original JSON text so valid finite numbers, including large integers, survive transfer without JavaScript rounding or numeric-type changes.

Provider and historical artifact JSON support up to 64 nested containers. Unsupported nesting returns a structured error and failed live lookups can retain cached data. Source envelopes must describe GRCh38 or a GRCh38 patch release, carry a versioned GenBank/RefSeq assembly accession, and agree with the preserved VEP assembly family. This checks consistency; it does not authenticate assembly metadata or establish a patch-to-accession mapping. Reloading the same capture preserves transcript choices, drafts, and selected checks. The initial page uses system fonts without external resource requests.

Dates and releases are declared provenance. This reconstructs comparisons from saved output; reproducing an old pipeline still needs its original executables, databases, configuration, and references. API: `POST /api/sources/historical-vep`, `GET /api/sources/records`, and `POST /api/sources/compare`; see `/docs` for schemas.

## Current boundaries

New submissions require integer coordinates/counts and nonblank required names and identifiers. Rejected drafts remain editable; valid names retain their original spacing. Existing saved records remain inspectable. Empty optional text is displayed as **Empty text**, while missing values show **Not provided**; comparison rules and fingerprints are unchanged.

NCBI notation must include complete valid SPDI and genomic HGVS observations before a verdict is saved. Unavailable data uses the provider-error/cache-fallback path. Cached checks are replay-validated before reuse, skipping invalid older observations while retaining their stored records. A SnpEff check can accompany a custom output only when its primary transcript IDs, genes, and consequence terms still match the preserved source; changed consequences require detaching that check. Protein/clinical output is outside this term-agreement check's scope.

Long release lists retain every number in the source record and bundle. When their joined display would exceed the provenance limit, the comparison uses a short count and a reference to the source record. Execution admission checks timezone-aware start time, nonnegative finite duration, command text, and artifact fingerprint formats for both capture formats. Imported execution metadata remains unauthenticated.

Current Ensembl and historical VEP import accept GRCh38 SNVs. NCBI identity checks short non-symbolic A/C/G/T primary alleles on pinned GRCh38.p14 primary nuclear sequences. Cross-assembly mapping, mitochondrial HGVS, VRS, and general notation parsing are unsupported. Additional rows match exact representations; independent normalization checks primary variants. No ClinVar adapter, clinical interpretation, or authenticated historical timeline exists. Regression checks rerun the comparator; SnpEff execution is an explicit separate action. Current Ensembl metadata does not prove an atomic release pin. Independent annotation agreement does not establish causal certainty. See [scientific validity](docs/scientific-validity.md) and [roadmap](docs/roadmap.md).
