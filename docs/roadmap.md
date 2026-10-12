# Roadmap

## Completed through 0.2.0

- [x] Focused competitor and standards assessment.
- [x] Strict two-snapshot schema and local API.
- [x] Conservative substitution identity comparison.
- [x] Structured annotation, provenance, and condition-aware clinical comparison.
- [x] Evidence-linked synthetic transcript replay with qualitative finding status.
- [x] Browser comparison, discrepancy filters, evidence inspector, JSON/Markdown export.
- [x] SQLite record storage, size limit, backend/frontend tests, Windows launch guide.
- [x] Immutable saved regression cases, pinned and candidate replays, field-level pass/fail, changed evidence and input drift, persistent run history.

## Next milestones

1. Add a small, explicitly user-triggered public-source adapter (likely VEP or a curated ClinVar XML subset) with caching, recorded release/accession, and offline failure behavior. Validate against authoritative published cases.
2. Introduce a standards-aware reference sequence and allele normalization adapter for indels, SPDI/HGVS/VRS mappings, and explicit cross-assembly uncertainty.
3. Support multiple annotations per snapshot, stable transcript matching, configurable difference significance, and larger local datasets.
4. Add genuinely sourced version timelines, dependency graph visualization, reproducibility bundles, and background jobs.

No timeline data or source history will be inferred from present-day responses.
