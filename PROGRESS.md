# Current state — 2026-10-13

Version 0.3.0 adds an explicitly triggered current Ensembl VEP adapter for GRCh38 single nucleotide variants. It checks the one-base reference against Ensembl, validates returned VEP identity, preserves each source response with hash, reported release, assembly accession, URI, and retrieval time, and supports cache-only reads and cached fallback on live failure. The public-source workspace can compare two transcripts from one preserved response. Such a comparison reports a possible transcript explanation, not a verified historical cause. The repository is at `https://github.com/JustAppTools/GenomeDebugger`.

## Verified commands

- `.\.venv\Scripts\python.exe -m pytest -q`: 22 passed (one third-party deprecation warning).
- `npm test` in `frontend`: 4 workflow tests passed.
- `npm run build` in `frontend`: TypeScript and Vite build passed.
- Live Ensembl documentation example: GRCh38 chromosome 1:6,524,705 C→T; reference base C; current server reported GRCh38.p14, accession GCA_000001405.29, release 116, and 16 transcript consequences. The response is saved in local SQLite and can be loaded offline.
- Browser pass: opened **Public source**, loaded the cached example, viewed provenance and transcript rows, and compared two same-gene transcripts. Identity was verified; transcript selection was possible, with two meaningful differences.
- Earlier 0.2.0 synthetic and regression workflows remain covered by backend and frontend tests.

## What to inspect on CONTINUE

1. Read Git status, this file, and `docs/roadmap.md`.
2. Rerun backend/frontend tests and launch both local servers.
3. Implement the next roadmap item: independent authoritative validation cases, then standards-aware normalization with a versioned reference source.
4. Keep current Ensembl responses distinct from historical snapshots and avoid calling a public transcript comparison a verified causal replay.
