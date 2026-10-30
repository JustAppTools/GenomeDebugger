# Repairs for the 0.8.2 audit

Application **0.8.3**, comparator **0.6.7**, SQLite schema **3** — October 29, 2026.

All twelve application defects in [the audit](bug-audit-0.8.2-2026-10-29.md) are addressed. The dependency advisory, browser-test collision, and exceptional backup cleanup gap are also addressed. The intended source, tests, documentation, and launchers are included in the release's local Git snapshot. No push or public release is part of this change.

| Audit finding | Repair |
|---|---|
| 1. False restored regression pass | Restore reconstructs the entire expected check list, required flags, expected/actual values, input changes, and verdict from the saved baseline and preserved candidate result. Missing, substituted, or downgraded checks reject the staged restore. New runs declare assertion version 0.6.7. Frozen historical assertion layouts preserve old runs without rewriting them. |
| 2. Missing database constraints | Schema validation checks the required primary keys, column types/nullability, ordering uniqueness, and autoincrement sequence. A database missing these constraints is rejected before replacing the destination. |
| 3. Guessed reference-context coordinate | Entering reference letters leaves Context start blank. An incomplete coordinate is an invalid draft and cannot be submitted until the user supplies a positive start. No start is copied from the variant position. |
| 4. Unfinished JSON displaced | Enter results uses the guarded form transition. Malformed/unsupported input stays in the JSON editor with an actionable message and its original text intact. |
| 5. Near-limit draft cannot resume | Save and read use the same decoded UTF-8 limit, with a bound that accounts for JSON escaping. A save is reported successful only after the stored envelope round-trips exactly. Existing large escaped drafts can be recovered. |
| 6. Pending save conflicts with itself | Shared per-workspace draft subscriptions reconcile successful save revisions across component lifetimes. Newer notes are retained while their base revision advances. Flag-only saves cannot advance an unrelated details conflict. Recent metadata is fetched again to avoid stale completions reviving deleted or archived entries. |
| 7. Help loses advanced edits | The source workspace remains mounted while hidden, preserving public queries and nested historical/SnpEff/identifier drafts. An inactive workspace cannot navigate to a late comparison result. Saved-test candidate/name/view drafts are retained per comparison in App memory; unmounted requests cannot overwrite newer drafts. |
| 8. Wrong collection explanation | Summary and narrative share the same exact import-format/policy predicate as the comparator. An unrelated row-order setting cannot activate collection explanations. |
| 9. Reordered compound terms | Comparator 0.6.7 compares semicolon-, ampersand-, and comma-separated consequence terms as unordered sets. Original input strings remain unchanged. Frozen comparator 0.6.6 preserves verification of prior results. |
| 10. Clearing optional protein field changes meaning | Clearing the guided optional control restores null (unavailable), matching its field help. Deliberate empty strings in advanced JSON remain distinct and readable. |
| 11. Invisible import focus | Visible file-input labels receive an outline on focus-within. Browser checks reach both controls with Tab and verify the visual change. |
| 12. Error still says Loading | Local data has separate loading/error/success states and a Retry storage details action. |
| 13. Vite advisory | Vite is pinned to patched 6.4.5 and the lockfile is updated. The full npm audit reports zero known vulnerabilities. |
| 14. Browser-project interference | Browser projects have separate disposable databases and servers. Library organization assertions follow the immutable record ID through renames. The suite uses the built production interface served by the backend, avoiding the dev-server lifetime failure seen in long runs. `npm run test:e2e` builds before testing. |
| 15. Uncommitted release implementation | The release source snapshot includes the previously uncommitted implementation and required untracked files, alongside these repairs, after validation. Database files, local logs, tool caches, and generated packages are excluded. |
| 16. Exceptional backup cleanup | Backup response cleanup runs in a finally block after normal completion or transport failure. Success and injected-send-error tests check removal of both the file and folder. A real mid-download TCP reset also leaves zero copies. |

## Validation

- Backend: **457 passed**, including **28 added regressions**. One existing Starlette/anyio deprecation warning remains. Log: `.build/fixes083-backend-final.log`.
- Frontend: **71 passed across 14 files**, including **9 added regressions**. Log: `.build/fixes083-frontend-final.log`.
- TypeScript/Vite production build: **passed**. JavaScript **367.30 kB / 107.88 kB gzip**; CSS **44.02 kB / 9.74 kB gzip**.
- Browser production suite: **118 passed in one uninterrupted run** (111 Chromium with core axe checks, 7 WebKit), including all 9 new audit workflows. Log: `.build/fixes083-browser-final.log`. The earlier dev-server run stopped after 54 passes when the server exited. An initial production run passed 117/118 because a test guard expected the old temporary-database filename; the guard now accepts the explicit per-browser suffix. Neither earlier run is treated as green. An earlier focused run's copied protein assertion was corrected to expect the repaired behavior.
- Full npm audit: **zero known vulnerabilities**. `pip check`: **no broken requirements**; this checks dependency consistency, not Python vulnerability coverage.
- The source desktop entry point passes built-interface, comparison, backup, and owned-shutdown smoke checks in `.build/desktop-smoke-254992e2`.
- Launcher regressions: **23 passed** after updating Restart to restart both owned services, ensuring development dependency updates take effect. Log: `.build/fixes083-launcher-regression.log`.
- A consistent copy of the user's workspace passes the stricter restore validator, including original pre-versioned results and saved runs. No historical scientific JSON was rewritten.
- Original scientific-record hashes and IDs are checked against `.build/fixes083-original-records.json`; all **11** records remain unchanged, with no added or removed investigations.

## Local package and release limits

Portable ZIP: `release/windows-0.8.3-20261029-195233/GenomeDebugger-0.8.3-Windows.zip`, **17,846,515 bytes**.

SHA-256: `a71c452dcc0395671e9c7d36ee82119289900367a9f46cadbf91fb19c51e91e2`.

ZIP integrity and the adjacent checksum pass. Bundled interface files match the production build byte-for-byte. The archive contains no database, `.env`, or log files. Package checks are recorded in `.build/fixes083-package-verification.json`.

Frozen-executable execution remains unverified: the earlier automatic approval review rejected launching it with the reason **“blocked by policy.”** No executable launch was retried or bypassed. Source execution and archive inspection do not establish frozen-binary execution. Code signing and clean-machine launch validation remain public-release work.

Firefox launch on this host, representative-user sessions, and manual assistive-technology validation remain incomplete. Automated browser/accessibility checks do not establish user comprehension or full accessibility conformance. These limits have not been presented as completed fixes or fabricated research results.
