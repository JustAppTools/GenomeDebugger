# Roadmap

## Completed through 0.5.0

- [x] Focused competitor and standards assessment.
- [x] Strict two-snapshot schema and local API.
- [x] Conservative substitution identity comparison.
- [x] Structured annotation, provenance, and condition-aware clinical comparison.
- [x] Evidence-linked synthetic transcript replay with qualitative finding status.
- [x] Browser comparison, discrepancy filters, evidence inspector, JSON/Markdown export.
- [x] SQLite record storage, size limit, backend/frontend tests, Windows launch guide.
- [x] Immutable saved regression cases, pinned and candidate replays, field-level pass/fail, changed evidence and input drift, persistent run history.
- [x] Explicit current Ensembl VEP GRCh38 SNV adapter, reference-base check, release/assembly metadata, immutable local source records, cache-only and failure fallback modes, and transcript-row comparison. The public example is documented; external causation remains unverified.
- [x] Pin NCBI's GRCh38.p14 primary chromosome mapping with source hash. Add an explicit, cached EFetch reference check and NCBI contextual SPDI/HGVS response capture. Validate two public examples, including a multi-term transcript, plus disagreement, offline, and unsupported-assembly cases. Reference agreement does not validate VEP consequences.
- [x] Add additional annotation and exact-match variant rows, guided primary input, search and retention controls, backend health feedback, replay-checked portable bundles, user supplied SnpEff ANN comparison, and browser end-to-end smoke tests.

## Next milestones

1. Run an independently controlled annotation engine and preserve verifiable software, transcript database, and reference artifacts. The current SnpEff path compares user supplied output only.
2. Introduce standards-aware, reference-backed normalization for indels and general SPDI/HGVS/VRS mappings, with explicit cross-assembly uncertainty. The current NCBI check covers only SNV notation.
3. Expand independently sourced validation cases, multi-variant UI editing, significance rules, and large dataset performance.
4. Add genuinely sourced version timelines, dependency graph visualization, and background jobs.

No timeline data or source history will be inferred from present-day responses.
