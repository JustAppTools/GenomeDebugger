# Current state - 2026-10-17

Version 0.6.0 fixes all seven defects from the latest review and adds guided multi-variant editing, independent reference-backed primary allele checks, pinned local SnpEff execution, and preserved historical VEP comparison.

## Verified in this working tree

- Backend unit/API tests: 71 passed. Both existing saved regression cases pass current-engine replay.
- Frontend unit tests: 13 passed. TypeScript and Vite production build pass.
- Browser workflows: 6 passed, covering demo/evidence/regression, mobile guide, offline failures, malformed imported JSON, multi-variant editing, a bundle larger than 1 MB, and historical artifacts with two-source export.
- All 8 existing saved investigations export and verify as current-engine bundles; originals stay unchanged. Archived 0.5.0 bundles retain their declared replay rules.
- Live NCBI repeat-deletion observations normalized two shifted descriptions to the same contextual SPDI and genomic HGVS. Original responses are preserved in `fixtures/ncbi-repeat-deletion-observation.json`.
- Official Java/SnpEff and MANE database installed locally under ignored `tools/snpeff`, with artifact hashes verified before/after a real run. Exact transcript-version differences correctly yielded unresolved. Captured output/provenance: `fixtures/snpeff-mane-public-run.json`.
- Production dependency audit: no vulnerabilities. Local services restarted at ports 8000/5173; health reports version 0.6.0 and explicit input/bundle limits.

## Correctness fixes

1. Candidate checks assert absolute additional outputs, catching shared drift.
2. All length-changing complex replacements remain conservative without independent reference evidence.
3. Full annotation-set matching includes the selected primary row.
4. Bundle checks reconstruct NCBI metadata, observations, and agreement flags from raw responses.
5. Compact export and import share a 32 MB limit; ordinary input stays capped at 1 MB.
6. Tuple matching and escaped field paths prevent delimiter collisions.
7. Imported nested types are checked before guided rendering; invalid JSON remains editable.

## Scientific boundaries

Independent NCBI checks currently cover primary variants on pinned GRCh38.p14 primary nuclear sequences. Cross-assembly mapping, mitochondrial HGVS, VRS, and normalization of extra variant rows remain unsupported. Historical output comparison is supported with declared provenance; full original pipeline reproduction still requires its original artifacts. Local SnpEff execution preserves artifact provenance but does not establish causal certainty. Imported hashes and execution metadata are not external authentication. See `docs/scientific-validity.md` and `docs/roadmap.md`.
