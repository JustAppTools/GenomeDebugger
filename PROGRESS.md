# Current state — 2026-10-11

Version 0.2.0: complete local synthetic end-to-end investigation plus saved regression cases. Cases preserve a full immutable baseline. Pinned and candidate runs report required assertion failures, changed evidence, and input drift. No public repository or cloud service was created.

## Verified commands

- `.\.venv\Scripts\python.exe -m pytest -q`: 18 passed (one third-party deprecation warning).
- `npm test` in `frontend`: 3 workflow tests passed.
- `npm run build` in `frontend`: TypeScript and Vite build passed.
- `npm audit` in `frontend`: zero reported vulnerabilities after dev-tool upgrades.
- Live local browser pass: loaded synthetic demo, ran comparison, observed verified identity and controlled transcript-selection replay evidence.
- Live regression browser pass: saved case `3429c64466f84004`, pinned replay passed 26/26 required checks; candidate with changed consequence failed with explicit field, finding, and evidence drift.
- Browser refresh pass: recent-investigations list reopened the source record, then the saved regression case and both historical runs appeared.

## What to inspect on CONTINUE

1. Read Git status, this file, and `docs/roadmap.md`.
2. Rerun backend/frontend tests and launch both local servers.
3. Implement the highest-priority unfinished task: a small public-source adapter with explicit user action, release provenance, cache, and offline behavior.
4. Keep verified claims scoped to supplied controlled fixtures until an authoritative source adapter and reference validation are present.
