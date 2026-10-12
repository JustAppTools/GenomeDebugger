# Current state — 2026-10-11

Version 0.1.0: complete local synthetic end-to-end investigation. Empty workspace was initialized with backend, frontend, fixture, tests, and documentation. No public repository or cloud service was created.

## Verified commands

- `.\.venv\Scripts\python.exe -m pytest -q`: 12 passed (one third-party deprecation warning).
- `npm test` in `frontend`: 1 workflow test passed.
- `npm run build` in `frontend`: TypeScript and Vite build passed.
- `npm audit` in `frontend`: zero reported vulnerabilities after dev-tool upgrades.
- Live local browser pass: loaded synthetic demo, ran comparison, observed verified identity and controlled transcript-selection replay evidence.

## What to inspect on CONTINUE

1. Read Git status, this file, and `docs/roadmap.md`.
2. Rerun backend/frontend tests and launch both local servers.
3. Implement the highest-priority unfinished task: a saved regression assertion and rerun workflow.
4. Keep verified claims scoped to supplied controlled fixtures until an authoritative source adapter and reference validation are present.
