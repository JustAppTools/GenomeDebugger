# Current state — 2026-10-17

Version 0.5.0 retains the 0.4.0 Ensembl VEP and NCBI SNV checks and adds guided input, additional annotation and variant rows, a saved-investigation library, portable replay-checked bundles, a user-supplied SnpEff ANN comparison, backend health feedback, a one-command Windows startup script, and browser end-to-end tests.

## Verified in this working tree

- Backend unit/API tests: 43 passed. The two regression cases already in `data/investigations.db` pass pinned replay with the current engine.
- Frontend unit tests: 5 passed. TypeScript and Vite production build pass.
- Browser end-to-end suite covers demo, evidence, regression pass/fail, bundle export/import, saved records, mobile guided input, offline state, and empty public cache.
- Existing local investigations export as bundles containing a current-engine replay; their original saved rows remain unchanged.
- Local services start at `127.0.0.1:8000` and `127.0.0.1:5173` through `scripts/start-local.ps1`.

## Scientific boundaries

The SnpEff adapter compares a user-supplied annotated VCF against preserved Ensembl output; the claimed SnpEff version and database hash are not authenticated. It does not prove a causal annotation explanation. Indels with only supplied local context remain unresolved even when their edited local sequences match. General reference-backed normalization, HGVS/SPDI/VRS mapping, and historical source reconstruction remain future work. These limits are described in `README.md` and `docs/scientific-validity.md`.

## Next engineering work

1. Add a pinned reference sequence source and a validated normalization library before upgrading indel identity claims.
2. Run an independently controlled annotation engine with verifiable software and transcript database artifacts.
3. Build historical release import and reconstruction from preserved upstream artifacts, where the upstream source makes them available.
4. Broaden public cases, failure-path tests, and accessibility checks before any hosted deployment.
