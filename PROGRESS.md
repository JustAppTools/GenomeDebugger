# Current state — 2026-10-13

Version 0.4.0 adds an explicitly triggered NCBI reference and notation check to the current Ensembl VEP workflow. A pinned GRCh38.p14 assembly report maps primary chromosomes to versioned RefSeq accessions. The app checks one base through NCBI EFetch, then compares contextual SPDI and genomic HGVS responses from NCBI Variation Services. It preserves each check, can read it offline, links its ID to a saved investigation, and marks cross-source identity unresolved if the observations disagree. A transcript-selection explanation remains possible even when NCBI agrees. The repository is at `https://github.com/JustAppTools/GenomeDebugger`.

## Verified commands

- `.\.venv\Scripts\python.exe -m pytest -q`: 27 passed (one third-party deprecation warning).
- `npm test` in `frontend`: 4 workflow tests passed.
- `npm run build` in `frontend`: TypeScript and Vite build passed.
- Live Ensembl documentation example: GRCh38 chromosome 1:6,524,705 C→T; reference base C; current server reported GRCh38.p14, accession GCA_000001405.29, release 116, and 16 transcript consequences. The response is saved in local SQLite and can be loaded offline.
- Live NCBI check of that example: `NC_000001.11` base C, contextual `NC_000001.11:6524704:C:T`, genomic HGVS `NC_000001.11:g.6524705C>T`; all agreed.
- Second public example from Ensembl VEP ID `rs56116432`: GRCh38 chromosome 9:133,256,042 C→A, seven transcript rows including one with both `intron_variant` and `non_coding_transcript_variant`. NCBI `NC_000009.12` base C, SPDI, and HGVS agreed. Both source and check are cached locally.
- Browser pass: loaded the first source and saved NCBI check from cache, observed agreement and pinned provenance, then created a comparison with the reference check in its evidence trail. Loaded the second source from cache and inspected its multiple consequence terms.
- Earlier 0.2.0 synthetic and regression workflows remain covered by backend and frontend tests.

## What to inspect on CONTINUE

1. Read Git status, this file, and `docs/roadmap.md`.
2. Rerun backend/frontend tests and launch both local servers.
3. Implement the next roadmap item: independent consequence-annotation validation, then reference-backed normalization for indels and broader variant notation.
4. Keep current Ensembl responses distinct from historical snapshots and avoid calling a public transcript comparison a verified causal replay.
