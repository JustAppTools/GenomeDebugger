# Architecture and data model

## Public-preview deployment — application 0.9.0

Local remains the default mode. Explicit public-free mode requires an exact HTTPS origin and a session-signing secret, and holds one server ownership lock. Request context selects a signed browser visitor's SQLite path; handlers do not use the installation database during hosted requests. Static HTML establishes the secure HttpOnly cookie before parallel initial API calls. API responses are no-store and vary by Cookie. Scientific record IDs stay deterministic, but records, labels, source captures, tests, and backups live in separate visitor databases.

The free configuration has no durable disk or external paid database. Server restarts/sleep can clear work; inactive visitor directories expire after 24 hours with active requests protected. Aggregate capacity is bounded and preserves existing download access. Local Java/SnpEff execution and server shutdown are unavailable in the hosted preview; supplied annotation output and public HTTP adapters still work. The frontend explains hosted processing, temporary storage, and explicit bundle/report transfer. The image copies application code, synthetic/public fixtures, and the compiled interface, excluding development databases and credentials.

## Local service

The React/TypeScript frontend submits snapshot input to a loopback FastAPI service. `models.py` owns strict schemas; `engine.py` performs pure deterministic comparisons; `regression.py` builds immutable assertions; `storage.py` persists SQLite; `bundle.py` verifies portable records; `report.py` renders Markdown. Comparison and bundle replay make no network calls.

Explicit source actions use `ensembl.py` for current GRCh38 SNVs, `ncbi.py` for source-bound SNV checks, and `allele_check.py` for reference-backed contextual SPDI/HGVS checks of the two primary alleles. `historical.py` parses original VEP JSON with declared metadata. Historical imports have a separate source kind and never enter the current-source cache.

`snpeff.py` compares exact transcript IDs and consequence sets. `snpeff_runner.py` optionally runs locally installed Java/SnpEff/database artifacts after verifying their hashes. It disables downloads/logging, uses a temporary working directory, preserves execution provenance, and verifies artifacts again afterward. The Windows installer is `scripts/setup_snpeff.py`; artifacts stay in ignored `tools/snpeff`.

## Records

- `Snapshot`: primary variant/annotation, additional annotations and `variant_records`, software/source/configuration provenance.
- `Variant`: assembly/accession, one-based position, nonempty A/C/G/T ref/alt, optional supplied reference context. Additional variants match exact submitted representation.
- `Annotation`: gene, transcript, consequence, optional protein and condition/framework-scoped clinical assertion. Tuple keys avoid delimiter collisions.
- `InvestigationResult`: engine version, canonical input hash, versioned result ID, identity, differences, findings, evidence. Current version is centralized in `version.py`.
- `RegressionCase` and `RegressionRun`: immutable saved outputs, absolute assertions for all annotation/variant rows, evidence checks, input drift, run history. Candidate evidence changes are informative; output changes fail.
- `SourceRecord`: current capture or historical artifact, query, assembly/releases, timestamps, response/hash, transcript rows. Historical artifacts retain exact original text and declared metadata.
- `ReferenceCheck`: source-bound NCBI FASTA, SPDI/HGVS responses, pinned assembly metadata, hashes, agreement flags.
- `AlleleCheck`: investigation-bound observations for both primary variants, complete ref validation, SPDI/HGVS, URLs/hashes, agree/disagree status. Separate from the stored local-context result.
- `SnpEffCheck`: ANN VCF, declared metadata, exact transcript matches and unmatched rows, optional recorded local execution/artifact provenance.
- Bundle version 2: investigation, up to two linked sources, exact linked source checks, optional allele check, entry hashes, engine version. Verification derives observations from responses and replays output. Frozen `legacy_engine_v050.py` and `legacy_engine_v060.py` verify their respective archived engine outputs. Current comparisons use version 0.6.5, with frozen 0.5.0–0.6.4 replay implementations retained.

## Boundaries

Local-context identity requires identical declared assembly/accession/context and equal-length substitution edits. Length-changing edits remain unresolved in the pure engine. Independent NCBI checks can establish matching observed contextual alleles on pinned primary nuclear sequences; cross-assembly mapping remains unsupported. Clinical and causal boundaries are described in [scientific-validity.md](scientific-validity.md).

Ordinary POST requests accept a 2 MB wire envelope and enforce a 1 MB canonical input-data budget. Bundle import/verification and compact export share a 32 MB limit. SQLite has a configurable storage budget and backup support. Result IDs include engine version so replay cannot overwrite history. Hashes and replay detect contradictions but do not authenticate external data or imported execution claims. A current API capture never substitutes for a historical artifact.

## 0.6.1 integrity changes

Artifact saves and bundle imports share immutable conflict checks. Bundle imports preflight all records and capacity inside a single SQLite transaction, then roll back all writes on failure. Connections close explicitly. Storage budgets subtract reusable free pages and identical records are not charged again.

Bundle manifests receive strict type validation before verification. Source-generated VEP snapshots must match captured variants and annotation rows; declared full sets cannot omit rows. Historical selected-row formats and the earlier equivalent release label remain supported. A separately named custom tool can cite VEP as an input while recording transformed outputs. SnpEff verification checks derived explanatory prose as well as structured outcomes.

The local runner permits reviewed database/build combinations, requires matching source assembly metadata, and hashes the exact input bytes it writes. Execution records retain assembly name and accession. Browser responses are associated with draft/query revisions; obsolete source replies cannot reactivate old comparisons. Regression discovery uses a source-investigation filter and lists expose pagination.


## 0.8.0 workflow and organization layer

The comparison core is unchanged. `tabular_import.py` validates explicit annotated CSV/TSV pairs without performing external requests or guessing scientific fields. Original UTF-8 text is included in input provenance; importer bookkeeping priority overrides are explicit. `identifier.py` previews current Ensembl mappings and returns every supported forward-strand GRCh38 SNV choice for deliberate selection, rather than silently changing a query.

SQLite schema 3 adds `investigation_labels`, separate from immutable investigation JSON. `workspace.py` provides organization, filtered/sorted cursor paging, compact SQL-projected summaries, storage information, and transactional label updates. Archive flags retain the scientific record; deletion remains a separate protected operation. Backup download uses SQLite's consistent backup facility. Restoration validates a stopped database and preserves its prior copy.

The frontend separates result explanation from raw records, uses hash routes for local bookmarks, and keeps explicitly saved browser drafts outside completed scientific records. HTML reports escape supplied content and render in a sandboxed preview. Local voluntary feedback has no external collection.

The optional desktop entry point serves the built UI from FastAPI on a loopback origin with a bundled Python runtime. Its default data folder is distinct from the development database. Public hosting and accounts are not enabled. See the desktop guide for source verification versus the unverified frozen-executable launch.


## Application 0.8.1 corrections

Tabular overview anchors use canonical variant and annotation identifier order, with original file bytes retained separately. Library flag updates merge only supplied fields under a write transaction; full editor saves compare a deterministic label fingerprint and return 409 on conflict. GET label details supplies current organization metadata for Recent. Compact UTF-8 cursors and signed-integer bounds make paging admission consistent. Restore validates and migrates an isolated SQLite copy before preserving/replacing the destination; schema checks also prevent false healthy responses for incomplete current databases. No comparator or schema-version change was needed.

## Application 0.8.3 / comparator 0.6.7

Saved regression runs now declare an assertion version independently of their input format. Restore reconstructs complete assertion sets from the saved baseline and historical candidate result using frozen rule layouts, including both original 0.6.3 layouts. New comparator 0.6.7 canonicalizes supported compound consequence separators; archived comparator 0.6.6 keeps prior results verifiable. App-memory draft stores and shared library-save subscriptions preserve edits across component lifetimes. Browser regression tests serve the compiled interface with separate backend/database instances per browser project.

Imported tabular snapshots are complete row collections. Their display anchors are excluded from selector comparisons; all represented variants/annotations are matched by explicit keys. Aggregate collection identity covers every represented key and its supplied context. Same-variant transcript attribution requires verified identity. Source locations and input hashes are provenance differences with low default priority. Frozen 0.6.5 rules preserve prior bundle verification.

Every server holds a database-specific operating-system lock for its lifespan; offline restore takes the same lock independently of port. Staged restore checks original comparator replay, linked evidence, SQL indexes, ownership, and record relationships. Frozen original models/rules handle supported pre-versioned records without rewriting their serialization.

Library details use a separate text-details fingerprint; flags remain independent partial updates. Unsaved per-record editor drafts live in the App session and survive section switches, with a page-close warning. Local-date filtering passes an explicit midnight instant and compares normalized timestamps. Input staleness compares normalized JSON content. HTML reports inventory unchanged and changed rows with escaped values.
