# Roadmap

## Completed through 0.3.0

- [x] Focused competitor and standards assessment.
- [x] Strict two-snapshot schema and local API.
- [x] Conservative substitution identity comparison.
- [x] Structured annotation, provenance, and condition-aware clinical comparison.
- [x] Evidence-linked synthetic transcript replay with qualitative finding status.
- [x] Browser comparison, discrepancy filters, evidence inspector, JSON/Markdown export.
- [x] SQLite record storage, size limit, backend/frontend tests, Windows launch guide.
- [x] Immutable saved regression cases, pinned and candidate replays, field-level pass/fail, changed evidence and input drift, persistent run history.
- [x] Explicit current Ensembl VEP GRCh38 SNV adapter, reference-base check, release/assembly metadata, immutable local source records, cache-only and failure fallback modes, and transcript-row comparison. The public example is documented; external causation remains unverified.

## Next milestones

1. Validate the public adapter and comparison semantics against independent authoritative cases, including wrong-reference and multiple-consequence examples. Capture a versioned reference source where possible.
2. Introduce a standards-aware reference sequence and allele normalization adapter for indels, SPDI/HGVS/VRS mappings, and explicit cross-assembly uncertainty.
3. Support multiple annotations per snapshot, stable transcript matching, configurable difference significance, and larger local datasets.
4. Add genuinely sourced version timelines, dependency graph visualization, reproducibility bundles, and background jobs.

No timeline data or source history will be inferred from present-day responses.
