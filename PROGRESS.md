# Current state — October 31, 2026

Application **0.10.1**, comparator **0.6.8**, SQLite schema **3**. All fifteen confirmed findings from the 0.10.0 audit are repaired. The update enforces transactional shared hosting quotas, keeps exports/deletion/page reuse available at capacity, corrects navigation and draft accessibility, preserves accurate hosted-storage copy, brings report previews into view, exposes clinical assertion scope, and fixes compound-term whitespace and JSON feedback. See [repair coverage and verification](docs/fixes-0.10.1-2026-10-31.md).

Validation: **491 backend tests**, **90 frontend tests**, production build, npm audit with **zero known vulnerabilities**, and `pip check` pass. The local app runs 0.10.1 / 0.6.8. All **11 original scientific records** retain their IDs and exact stored JSON hashes; a consistent database copy passes complete restore and historical replay validation. Frozen 0.6.7 comparator/assertion modules preserve verification of older bundles and regression runs.

**128 Chromium/WebKit browser scenarios pass in one uninterrupted final run**, and **4 hosted HTTPS workflows** pass. Separate hosted-test output prevents the trace collisions seen in the initial parallel run. Live deployment verification is pending. The existing Render Free service remains the only deployment target; no paid resources are required.

# Previous guided-workspace release — 0.10.0

Application **0.10.0**, comparator **0.6.7**, SQLite schema **3**. The guided workspace replaces the dark sidebar with horizontal Compare / Saved work / Guide navigation, visible comparison steps, clear input paths, warm neutral/plum styling, recent work on the home page, and footer storage/version controls. Result evidence, advanced tools, original JSON, reports, and visitor isolation retain their scope. See [redesign and verification](docs/guided-workspace-0.10.0-2026-10-31.md).

Validation: **479 backend tests**, **74 frontend tests**, production build, **122 Chromium/WebKit scenarios verified across the final run and one focused rerun**, and **4 HTTPS hosted-browser workflows**. The final full browser run passed 121 scenarios; one Windows test worker exited unexpectedly (3221226505) during a file-read race scenario, which then passed in isolation. No uninterrupted 122-scenario pass is claimed. The first browser pass identified an inherited low-contrast record-ID rule, now removed; remaining first-pass failures were navigation-test selectors/timing updated for the new shell. Final 320px/1280px layout and core axe checks pass.

Local services run 0.10.0 at `http://127.0.0.1:5173/` with engine 0.6.7. All **11 original scientific records** retain their IDs and stored result hashes after the restart. The same release is **live at [genomedebugger.onrender.com](https://genomedebugger.onrender.com)** on the existing Render Free service. Source `c47c5f813d981911e7f5eab91a663d4aa1e04734`, deployment `dep-dbj5ugflk1mc738bhr50`, completed successfully. Public checks passed for frontend assets/runtime versions, comparisons, visitor isolation, reports, and explicit bundle transfer. No paid resources or new service were created. See [release and live proof](docs/guided-workspace-0.10.0-2026-10-31.md).

## Previous hosting release — 0.9.0

Application **0.9.0**, comparator **0.6.7**, SQLite schema **3**. Public application live at **[genomedebugger.onrender.com](https://genomedebugger.onrender.com)** on one Render Free Docker service. No paid storage/database or payment method; service deployments and Blueprint sync are manual. Signed per-browser workspace cookies isolate temporary SQLite files. Visible notices explain server processing, temporary storage, and bundle/report transfer. Local mode remains loopback-only and preserves its existing database. See [free hosting](docs/free-hosting.md) and the [deployment verification](docs/deployment-2026-10-31.md).

Hosting verification: **479 backend tests**, **74 frontend tests**, production build, and **4 HTTPS hosted-browser workflows** pass. New backend coverage tests visitor isolation, forged cookies, cross-origin writes, concurrent request context, capacity/expiry, exported bundles, and disabled local-only actions. The existing local browser suite passed 117/118 on its initial run; the remaining paging test asserted text before its asynchronous row update. It now waits for the expected row count and its focused rerun passes (`.build/hosting-browser-library-retest.log`). No uninterrupted 118-test pass is claimed for 0.9.0. Render successfully built the Docker image and deployed it. Actual public HTTPS checks passed for comparisons, visitor record/notes isolation, saved baseline/replay, report and bundle transfer, backups, redacted storage information, and disabled local-only operations. Browser checks also fetched the public Ensembl example and compared its transcript outputs. The previous source release and its verification are retained below as history.

## Live Render deployment

Deployed GitHub `JustAppTools/GenomeDebugger` branch `main`, commit `ccb9020ce52309d7b4d0da10e4d30acc17d13ccd`, through the authenticated Render dashboard. Service `srv-dbj5biff3r2c73f0bdsg` is **Live / Free**; Blueprint `exs-dbj5b967bikc73ef8rj0` is named `genomedebugger-free`. The repository remains private and the website is public. The workspace is Hobby, has no card on file, and showed $0 accrued at deployment. Render generated the session secret; no local database or secret was uploaded.

Keep the user's **$0 budget**: one Free service, no disk/database/paid resources, no automatic deployment or Blueprint sync. Select a tested commit deliberately for future updates. Free-server sleep/restarts/redeploys can erase hosted work, and inactive workspaces expire after 24 hours. Visitors must download bundles/reports for retention. See [deployment details](docs/deployment-2026-10-31.md).

## Previous release — 0.8.3

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
