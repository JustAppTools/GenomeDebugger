# Current state — October 29, 2026

Application **0.8.3**, comparator **0.6.7**, SQLite schema **3**. All twelve application bugs in the 0.8.2 audit are repaired, along with the dependency advisory, shared browser-test data, source snapshot, and exceptional backup-cleanup findings. See [repairs and release limits](docs/fixes-0.8.3-2026-10-29.md). Previous audits and fix reports remain historical evidence.

Latest verification: **457 backend tests** and **71 frontend tests** pass, with **28 backend and 9 frontend regressions added**. The production build passes. The full browser suite now tests the compiled interface on isolated backend/database instances per browser project; all 118 scenarios pass in one uninterrupted run. Full npm audit reports zero known vulnerabilities. Original scientific records are preserved.

The earlier development-server browser run stopped after 54 passes when Vite exited. It is not counted as a green run. The production-server configuration removes that test dependency, while the development site still uses the patched Vite 6.4.5.

## Delivered

- Three clear starting paths: a synthetic example, two existing analysis outputs, or a public GRCh38 substitution. Blank manual inputs contain no invented scientific values.
- Four guided steps, field-origin help, required/optional markers, review feedback, explicit copying of confirmed shared DNA descriptions, and an experienced-user view.
- Supported-file discovery and strict tabular v1 CSV/TSV pair previews. Original UTF-8 text and SHA-256 are retained; previews do not create saved investigations. The documented adapter supports bounded multi-variant comparisons without claiming arbitrary CSV/VCF or genome-scale support.
- Specific result narratives, visible causal findings, separate descriptions of reference/annotation/provenance scope, friendly effect definitions, readable evidence, and factual supplied-text DNA edit diagrams. Exact terms and original JSON remain available.
- Explicit browser-local draft save/resume/discard, undo/redo, comparison/section bookmarks, and browser Back/Forward navigation.
- Saved-work names, notes, tags, favorites, archive/restore, source/date filters, sorting, compact 50-record keyset pages, and selected bundle export. Labels are separate from scientific identity.
- Escaped standalone HTML reports with sandboxed previews, alongside existing Markdown, JSON, and replay-checked bundles. Local links explain their installation-specific scope.
- Current public lookup before advanced historical/SnpEff tools; explicit rsID/simple HGVS resolution with deliberate mapping selection; source capture/import dates distinguished from declared run/release metadata.
- Searchable help, capability limits, local storage/version/quota details, consistent database backup, validated offline restore, and clearer saved-expectation workflows.
- Improved phone layouts, contrast, focus, touch controls, reduced motion, and automated accessibility checks. Optional local comprehension feedback and an honest participant-testing protocol are included.
- Windows Setup/Start/Stop source launchers, an isolated portable desktop entry point, and a build script for a bundled Windows ZIP. Public hosting and automatic updates are not enabled.

## Verification

- Backend: **457 passed**, including 28 added regressions. One existing Starlette/anyio deprecation warning remains (`.build/fixes083-backend-final.log`).
- Frontend: **71 passed across 14 files**, including 9 added regressions (`.build/fixes083-frontend-final.log`).
- Production build: JavaScript **367.30 kB / 107.88 kB gzip**, CSS **44.02 kB / 9.74 kB gzip**; TypeScript and Vite pass.
- Browser production suite: **118 passed in one uninterrupted run** (111 Chromium, including core axe checks, and 7 WebKit). Log: `.build/fixes083-browser-final.log`. This includes all 9 new audit workflows and the existing local-date/DST regression. Earlier runs are retained: a dev-server interruption and a production run with a superseded temporary-database filename guard are not counted as green runs.
- Full npm audit reports **zero known vulnerabilities**; `pip check` reports no broken requirements.
- Source desktop entry point: built UI, comparison, backup, and owned shutdown pass in `.build/desktop-smoke-254992e2`.
- Real mid-download cancellation leaves **zero** temporary backup copies. Success and injected-send-error regressions also verify removal of the temporary file and folder. The audit helper now closes its SQLite connection and shuts down its owned server gracefully on Windows.
- Portable package: `release/windows-0.8.3-20261029-195233/GenomeDebugger-0.8.3-Windows.zip` (**17,846,515 bytes**), SHA-256 `a71c452dcc0395671e9c7d36ee82119289900367a9f46cadbf91fb19c51e91e2`. ZIP integrity/checksum pass, bundled UI matches the production build, and no database/log/.env files are included. Frozen execution remains unverified.
- Prior bounded performance measurements and earlier 109-scenario browser validation remain historical results, not new 0.8.3 performance claims. See the 0.8.2 report for those details.

Browser tests use isolated databases and synthetic/public fixtures. No personal variant requests were sent to external services.

## Preservation and local access

- Development URL: `http://127.0.0.1:5173/`; API: `http://127.0.0.1:8000/`.
- The development database was backed up before this update: `data/backups/before-0.8.3-2a2e0922.db`. The original pre-migration backup also remains available.
- 0.8.3 keeps schema 3. Label/details fingerprints are computed separately from immutable scientific JSON. Operating-system workspace ownership does not depend on SQLite schema or network port. Comparator 0.6.7 creates separate new result IDs; old records are not rewritten.
- After the 0.8.3 restart, all **11 original scientific records** and their IDs match the pre-update checkpoint exactly, with no records added or removed. A consistent copy passed the new restore validator, including all saved baselines, runs, sources/checks, and pre-versioned investigations (`.build/restore-validation-083-8fb18b39.db`). The live API reports application 0.8.3/comparator 0.6.7/schema 3.
- Portable desktop data is separate from the development database, under `%LOCALAPPDATA%\GenomeDebugger\data` unless deliberately overridden. Use bundles or validated offline database restore for transfer.
- Earlier 0.8.1 visual verification: [application version and preserved workspace](docs/images/genomedebugger-0.8.1-verified.jpg).
- Earlier visual review screenshots: [home](docs/images/genomedebugger-0.8.0-home.jpg) and [readable evidence](docs/images/genomedebugger-0.8.0-evidence.jpg).

## Remaining validation and conditional work

Automatic approval review rejected launching the generated Windows executable, with the stated reason **“blocked by policy.”** Source-launcher verification does not establish frozen-binary execution. The packaged application requires launch testing and code signing before a public release.

Firefox could not launch on this host (`spawn UNKNOWN`); its product suite is opt-in using `GENOMEDEBUGGER_TEST_FIREFOX=1`. No Firefox pass is claimed. Representative-user sessions and manual assistive-technology testing have not been performed; automated accessibility checks do not establish full WCAG conformance.

Broader assemblies/normalization, cross-assembly mapping, independently sourced historical datasets, reviewed translations, and hosted collaboration remain conditional work requiring actual reference data, audience requirements, or a deployment/data-access design. See [scientific boundaries](docs/scientific-validity.md), [roadmap](docs/roadmap.md), and [usability validation](docs/usability-validation.md). No additional biological capability or human research result has been fabricated.
