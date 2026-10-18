# Roadmap

## Completed through application 0.7.1 / comparator 0.6.3

- Strict snapshot/provenance schema, conservative local comparison, condition-aware clinical comparisons, evidence-linked synthetic replay, meaningful-change overrides, and offline demo.
- Guided primary and additional variant/annotation editing, advanced JSON, saved-record search and retention, evidence inspection, regression workbench, JSON/Markdown exports, backend status, and Windows startup.
- Immutable regression baselines and candidate assertions across all output rows, with input/evidence drift and persistent runs.
- Explicit current Ensembl GRCh38 SNV capture, reference checking, preserved sources, transcript comparison, offline cache, and visible fallback warnings.
- Pinned GRCh38.p14 NCBI mapping, independent reference/SPDI/HGVS checks including length-changing primary alleles and a captured repeat-deletion case.
- Pinned local SnpEff execution with before/after artifact verification and preserved provenance. Exact transcript-version matching retains uncertainty.
- Historical VEP output import with original bytes and declared metadata; comparisons and bundles can preserve two sources.
- Replay-checked bundles up to 32 MB, archived 0.5.0 verification, versioned current result IDs, storage backup, and unit/API/browser suites.
- Fixes for shared candidate drift, complex replacement identity, transcript-selector row matching, NCBI bundle contradictions, large bundle import, delimiter key collisions, and malformed guided input.

- Fixed all 14 findings in the October 18 audit, with focused backend and browser regression coverage, atomic imports, immutable artifact conflicts, exact execution bytes, assembly validation, storage recovery, draft/query freshness, clinical dates, manifest validation, pagination, and guided defaults.
- Fixed the subsequent 0.6.1 and 0.6.2 audit findings, including check applicability, primary collection matching, execution origin, complete source ingestion, save-time validation, and record/selection races.
- Plain-language onboarding, a three-question results summary, optional definitions and technical disclosures, and simpler navigation. Removed the game-oriented interface and animated playback.


## Further development

1. Broaden independently sourced positive, negative, ambiguous, and transcript-version cases. Run deliberately controlled pipeline changes before upgrading any causal finding.
2. Extend validated reference/normalization support to additional rows, assemblies, and sequence types; evaluate VRS and explicit cross-assembly mappings.
3. Import original historical tool/database/reference artifacts where available and support full pipeline reproduction. Declared metadata alone cannot establish authenticity.
4. Add genuinely sourced release timelines, dependency graphs, and background jobs when dataset size requires them.
5. Evaluate larger datasets, additional browsers, accessibility, and deployment access controls before hosted or multi-user operation.

No source history will be inferred from present-day responses. Scientific boundaries are recorded in [scientific-validity.md](scientific-validity.md).
