# Architecture and data model

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
- Bundle version 2: investigation, up to two linked sources, exact linked source checks, optional allele check, entry hashes, engine version. Verification derives observations from responses and replays output. Frozen `legacy_engine_v050.py` and `legacy_engine_v060.py` verify their respective archived engine outputs. Current comparisons use version 0.6.1.

## Boundaries

Local-context identity requires identical declared assembly/accession/context and equal-length substitution edits. Length-changing edits remain unresolved in the pure engine. Independent NCBI checks can establish matching observed contextual alleles on pinned primary nuclear sequences; cross-assembly mapping remains unsupported. Clinical and causal boundaries are described in [scientific-validity.md](scientific-validity.md).

Ordinary POST requests accept 1 MB. Bundle import/verification and compact export share a 32 MB limit. SQLite has a configurable storage budget and backup support. Result IDs include engine version so replay cannot overwrite history. Hashes and replay detect contradictions but do not authenticate external data or imported execution claims. A current API capture never substitutes for a historical artifact.

## 0.6.1 integrity changes

Artifact saves and bundle imports share immutable conflict checks. Bundle imports preflight all records and capacity inside a single SQLite transaction, then roll back all writes on failure. Connections close explicitly. Storage budgets subtract reusable free pages and identical records are not charged again.

Bundle manifests receive strict type validation before verification. Source-generated VEP snapshots must match captured variants and annotation rows; declared full sets cannot omit rows. Historical selected-row formats and the earlier equivalent release label remain supported. A separately named custom tool can cite VEP as an input while recording transformed outputs. SnpEff verification checks derived explanatory prose as well as structured outcomes.

The local runner permits reviewed database/build combinations, requires matching source assembly metadata, and hashes the exact input bytes it writes. Execution records retain assembly name and accession. Browser responses are associated with draft/query revisions; obsolete source replies cannot reactivate old comparisons. Regression discovery uses a source-investigation filter and lists expose pagination.
