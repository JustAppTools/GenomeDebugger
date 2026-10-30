# GenomeDebugger 0.8.2 audit — October 29, 2026

**Repair follow-up:** all twelve application defects and the dependency, test-isolation, source-snapshot, and exceptional-cleanup findings are addressed in 0.8.3. See [repairs, verification, and remaining release limits](fixes-0.8.3-2026-10-29.md). The audit below is retained as historical evidence; its diagnostic entry points now run corrected-behavior regressions.

Audit of the current working tree: application 0.8.2, comparator 0.6.6, SQLite schema 3. No application fixes were made during this audit. The added diagnostics deliberately assert observed defects; their passing results mean the problems were reproduced.

There are **12 reproducible application defects**, **one conditional dependency advisory**, and **two testing/delivery issues** below. A further defensive backup-cleanup gap was reproduced with an injected transport exception; a real client cancellation did **not** reproduce that gap. These findings are bounded by the tested cases and are not a guarantee that no other defects exist.

All 11 original scientific records remain byte-for-byte unchanged, with the same identifiers and no added or removed investigations. All destructive or altered-backup cases used disposable synthetic databases.

## Application defects

### 1. Restore accepts a saved regression “pass” that actually fails — P2

**Location:** `backend/app/manage.py:83`, especially the check validation at lines 92–96; baseline evaluation is implemented in `backend/app/regression.py`.

Create a normal failing candidate run. In a disposable SQLite backup, replace that run's `checks` with an empty list and its `status` with `passed`, leaving the candidate result, ownership, and input fingerprints intact. Offline restore accepts it. Loading the restored run returns **passed**; evaluating the same candidate against its saved baseline returns **failed**.

Restore verifies the internal arithmetic of whatever checks the backup supplies. It does not establish that those checks are the assertions required by the baseline. With no required checks, `all(...)` evaluates to true. Requiring a nonempty list alone would also leave room to omit or replace individual checks.

**Impact:** an altered backup can retain a false saved-test verdict despite passing restore validation. This requires an altered backup; it was not observed arising spontaneously from normal saves.

**Repair direction:** regenerate and compare the required baseline checks using the appropriate versioned regression rules. Preserve the stored historical result and reject inconsistencies instead of rewriting it silently.

**Evidence:** `scripts/audit082-probes.py`, observation `restore_accepts_false_regression_pass`; `.build/audit082-backend.json` reports stored `passed`, recomputed `failed`, zero stored checks.

### 2. Restore accepts a broken database constraint, while health remains green — P2

**Location:** `backend/app/storage.py:62` (`validate_schema`), initialization around line 129, and label upserts used by the workspace API.

Replace `investigation_labels` in a disposable backup with a table containing the same columns and defaults but no primary key on `investigation_id`. Restore accepts it. `/api/health` returns 200, but saving notes returns 500 because the upsert's `ON CONFLICT(investigation_id)` has no matching uniqueness constraint.

**Impact:** a structurally damaged backup can become an apparently healthy workspace with broken editing. Column-name checks and SQLite integrity checks do not establish the required application constraints.

**Repair direction:** validate keys, uniqueness, and other constraints that application SQL depends on before accepting the staged database. Do not infer correctness from successful `CREATE TABLE IF NOT EXISTS` calls.

**Evidence:** backend diagnostic `restored_missing_primary_key_breaks_details_saves`: health 200, details save 500.

### 3. Typing reference letters invents a context-start coordinate — P2

**Location:** `frontend/src/GuidedInput.tsx:165`.

Start with a variant that has a position but no reference context. Enter only Reference sequence. The editor automatically creates `reference_context.start` equal to the variant position, although the user never supplied the start of those reference letters.

**Impact:** scientific input contains an assumed coordinate, contrary to the promise that values come from the original analysis. Flanking reference text need not begin at the variant position. This concerns the provenance of supplied coordinates; matching local text still does not independently authenticate a genome reference.

**Repair direction:** keep the start absent until explicitly entered, or offer a clearly labeled, deliberate action to use the variant position. Require the complete coordinate/text pair for submission.

**Evidence:** frontend unit diagnostic and browser reproduction in `frontend/audit/v082.probe.tsx` and `frontend/audit/v082.browser.probe.ts`.

### 4. “Enter results” can replace unfinished JSON with a blank guided document — P2

**Location:** `frontend/src/App.tsx:352`, parsed-input handling around line 121, and `frontend/src/GuidedInput.tsx:186`.

Enter unfinished JSON in the JSON editor, open Help, then click Enter results. `startInput()` selects guided mode without checking whether the existing text can be represented there. A parse failure becomes `null`, which the guided editor interprets as a new blank document. Editing any guided field then replaces the previous nonempty JSON.

**Impact:** work is unexpectedly displaced by a blank input. Undo may still recover the previous text during that session, but no warning explains what happened or directs the user to recovery.

**Repair direction:** use the guarded JSON-to-guided transition for every entry point. Preserve unsupported or unfinished text in JSON mode and require an explicit action to start over.

**Evidence:** unit and actual-browser reproduction, including editing the resulting blank form and inspecting the replacement JSON.

### 5. A near-limit draft reports a successful save but cannot be resumed — P2

**Location:** `frontend/src/DraftTools.tsx:5` and `frontend/src/DraftTools.tsx:11`.

Saving checks the UTF-8 size of the text against 2,000,000 bytes. Reading rejects the serialized localStorage envelope above 4,000,000 characters. JSON escaping can double the text length before the envelope is added.

For example, `JSON.stringify('\\'.repeat(999990))` produces a 1,999,982-byte valid JSON text. The browser accepts its saved envelope and shows success. After leaving and returning, `readSavedDraft()` returns null, so Resume is unavailable. Drafts permit unfinished or schema-invalid input; being a JSON string rather than a complete investigation does not justify a false save confirmation.

**Impact:** users can rely on a saved draft that the application subsequently refuses to read. A browser quota rejection is a separate case and was not the failure reproduced here.

**Repair direction:** apply one round-trip-safe format and size rule to saving and reading, including serialization overhead, and verify readability before reporting success.

**Evidence:** unit diagnostic and Chromium browser reproduction; the stored value exists after the successful save but cannot be resumed.

### 6. Returning during a pending library save causes a conflict with the user's own save — P2

**Location:** `frontend/src/WorkspaceLibrary.tsx:32`, especially draft deletion and the component-lifetime guard around lines 39–48.

Save notes, allow the server to commit, and delay delivery of the successful response. Open Help, then return to Saved comparisons before releasing that response. The retained editor still holds the old details revision. Once the earlier success arrives, another edit/save returns 409 and says another tab changed the record, although the only change was the user's own successful save.

**Impact:** ordinary navigation during a slow request leaves a stale editor that cannot save normally. Existing unsaved text is still visible; this reproduction does not claim that the server lost the first save.

**Repair direction:** reconcile save results and draft revisions at workspace scope, independently of the lifetime of the component that initiated the request. Preserve any newer edits while updating their base revision.

**Evidence:** controlled-response unit diagnostic and real HTTP/browser workflow; the second save receives 409.

### 7. Opening Help discards public-query and candidate edits — P2

**Location:** local state in `frontend/src/PublicSourcePanel.tsx:49`, `frontend/src/RegressionPanel.tsx:29`, and conditional mounting in `frontend/src/App.tsx:389`.

Two reproduced cases:

- Enter public-query Position `12345`, visit Help, and return to Look up a DNA change: Position resets to the default `6524705`.
- Edit a saved-test candidate's predicted consequence to `stop_gained`, visit Help, and return to Saved tests: the candidate resets to the original `missense_variant` input.

**Impact:** using the help that explains these technical fields destroys the work the user was trying to understand. There is no warning or in-memory recovery for these panels. Main-input drafts and library-details drafts do not cover them.

**Repair direction:** retain per-workspace/per-comparison edits across navigation, or provide an explicit discard decision with recovery. Include other advanced input panels in the same lifecycle review.

**Evidence:** both cases reproduced in Chromium; the public-query reset also has a unit diagnostic. This is one shared recovery issue, not two separate counted defects.

### 8. Overview can contradict the comparator about transcript selection — P2

**Location:** `frontend/src/ResultsSummary.tsx:8`, `:25`, `:31`; `frontend/src/explanations.ts:46` and `:60`; compare `backend/app/engine.py:76`.

Set the synthetic transcript-switch input's `configuration.row_order_policy` to `manual-input-order`, without a tabular import marker. The engine correctly uses the selected-transcript comparison and verifies the transcript-selection finding. The overview instead says no preferred transcript was declared and displays collection-mode explanations.

**Cause:** the frontend treats any truthy `row_order_policy` as collection mode. The backend requires the exact supported import format **and** the exact canonical policy.

**Impact:** a supported arbitrary configuration key changes the explanation without changing the actual comparison rules. The page gives incompatible accounts of the same result.

**Repair direction:** use a shared explicit mode predicate or a versioned result-mode field. Keep the mode consistent in summary text, counts, and next steps.

**Evidence:** real API-created result, browser contradiction, and captured synthetic fixture `frontend/audit/v082-fixtures.json`.

### 9. Reordering ampersand-separated consequence terms creates a false meaningful change — P2

**Location:** `backend/app/engine.py:19`; compare `frontend/src/explanations.ts:33` and `backend/app/snpeff.py:130`.

Submit otherwise matching annotation fields containing `intron_variant&splice_region_variant` and `splice_region_variant&intron_variant`. The API reports a meaningful consequence change, although these are the same terms in another order.

The comparator canonicalizes semicolon-separated terms only. The explanation UI recognizes ampersands, and the supported SnpEff parser also treats them as compound-term separators. Generic pasted consequence fields accept the notation.

**Repair direction:** normalize the supported compound consequence notation consistently while retaining original supplied text. Test semicolon and ampersand representations through both manual-input and adapter paths.

**Evidence:** backend API diagnostic `reordered_ampersand_terms_are_meaningful_changes`.

### 10. Clearing an optional protein field cannot restore its original missing state — P2

**Location:** `frontend/src/GuidedInput.tsx:180`–181.

Begin with otherwise identical annotations whose `protein_consequence` is null. Type a temporary protein value in Analysis A and clear it. Both fields look blank, but A is now an empty string and B remains null. Comparing creates a meaningful protein-consequence difference.

**Impact:** a visually reversed edit changes the scientific input and creates an unexpected difference. Distinguishing missing values from explicit empty strings is intentional in the engine; the defect is that the editor renders them alike and cannot restore the missing state, despite saying to leave the field blank if unavailable.

**Repair direction:** offer an explicit missing/unavailable state or consistently map a cleared optional control to null. Preserve the distinction in advanced JSON when deliberately supplied.

**Evidence:** backend, unit, and actual-browser reproductions.

### 11. Keyboard focus disappears on the two JSON import controls — P2

**Location:** `frontend/src/style.css:14`; import labels in `frontend/src/App.tsx` and `frontend/src/WorkspaceLibrary.tsx:71`.

Tab to Import input JSON or Import replay-checked bundle. The focused native file input is one pixel and transparent; its visible parent has no focus-within indicator. Screenshots of each control are byte-for-byte identical before and after it receives keyboard focus.

**Impact:** keyboard users cannot see which import action is focused. Existing automated axe checks do not establish visible focus for these interactions.

**Repair direction:** expose a visible focus indicator on the associated label/button without removing the native file input's keyboard behavior.

**Evidence:** browser tests use Tab, assert actual focus, and compare screenshots under `.build/audit082-{import,bundle}-focus-{before,after}.png`.

### 12. Failed Local data requests keep claiming to load — P3

**Location:** `frontend/src/LocalDataPanel.tsx:7`.

Fail `/api/workspace/data`. The completed request displays its error, but the panel continues showing “Loading storage details…” because `data` remains null. There is no retry action in that view.

**Impact:** the interface gives contradictory operation status and no direct recovery action. Leaving and returning or reloading is required to retry.

**Repair direction:** represent loading, error, and success separately and offer Retry.

**Evidence:** unit diagnostic and browser route failure.

## Dependency and engineering issues

### 13. Vite 6.4.4 has a moderate development-server advisory — conditional P2

**Location:** `frontend/package.json:27` and its lockfile.

`npm audit --json` reports one moderate advisory: **GHSA-8g5g-mxqh-grgj / CVE-2026-118662**, concerning a query-based bypass of Vite's filesystem deny rule. The affected pinned version is 6.4.4; the patched version is 6.4.5. [Vite's primary advisory](https://github.com/vitejs/vite/security/advisories/GHSA-8g5g-mxqh-grgj).

**Scope:** the advisory describes conditions involving an exposed development server and sensitive files within its allowed directories. Current launchers bind loopback, and the packaged static application does not run Vite. This audit did not demonstrate exploitation or external exposure. The production-only dependency audit reports zero known vulnerabilities.

**Repair direction:** update the pinned development dependency and lockfile to a patched compatible version, then rerun the production build and relevant browser checks.

**Evidence:** `.build/audit082-dependencies.json`, `.build/audit082-production-dependencies.json`, and the primary advisory.

### 14. Browser projects interfere with each other's saved-library assertions — P2

**Location:** `frontend/playwright.config.ts:9` and `frontend/e2e/product-workflows.spec.ts:55`–70.

The Chromium and WebKit projects share one database for the test invocation. The organization test assigns the same display name, `Recognizable saved comparison`, and later locates rows by that name. Earlier project data remains after the test.

The combined 23-scenario audit run passed 22 scenarios, but WebKit's archive assertion found another row with that name after the current row was archived. The trace shows multiple matching rows during the transition and one afterward. The same WebKit test passed when run alone against a fresh disposable database.

**Impact:** the suite can report a false archive regression and cannot provide a dependable combined green run. This evidence does not establish an application archive defect.

**Repair direction:** isolate data per browser project/test and target rows by the unique saved investigation ID throughout a rename. Retain the failed combined-run evidence when reporting the isolated rerun.

**Evidence:** `.build/audit082-core-browser.log` and `.build/audit082-archive-isolated.log`.

### 15. The tested version is not reproducible from the current commit — P2

**Location:** current Git working tree versus `HEAD:backend/app/version.py`.

The running/tested tree declares application 0.8.2 and comparator 0.6.6. The current committed version file still declares application **0.7.1** and comparator **0.6.3**. There are extensive modified tracked files and untracked implementation, test, documentation, and launcher files.

**Impact:** checking out the current commit does not reproduce the code or package being tested. Untracked implementation files also need explicit inclusion in the eventual versioned release.

**Repair direction:** review and commit the intended implementation, required tests, and release documentation together; associate a release with its exact commit and artifact checksum. This audit did not commit, push, or inspect the current remote GitHub contents.

## Defensive cleanup gap with limited reproduction

### 16. An exceptional backup-send failure skips temporary-file cleanup — P3

**Location:** `backend/app/main.py:233`–245.

The backup endpoint attaches cleanup as a `FileResponse` background task. Injecting an `OSError` into the ASGI `send` callback during the first response body makes execution exit before that task runs. The full temporary database copy remains. The diagnostic explicitly removed its own generated copy afterward.

**Reachability qualification:** a separate real HTTP test used an owned Uvicorn server, a 24 MB disposable database, and a TCP reset after receiving the initial SQLite bytes. It left **zero** temporary backups. Therefore, ordinary download cancellation is **not** a reproduced defect on the current server. The injected failure demonstrates an exception-cleanup gap, not a demonstrated normal-user leak.

**Repair direction:** make cleanup run on response completion and exceptional exits, with a narrowly scoped stale-file cleanup policy if needed. Avoid deleting another active response's backup.

**Evidence:** backend diagnostic `exceptional_backup_send_error_skips_cleanup` and `.build/audit082-disconnect.json`.

## Verification and remaining limits

- Existing backend suite: **429 passed**, with one existing Starlette/anyio deprecation warning.
- Existing frontend suite: **62 passed across 13 files**.
- Production TypeScript/Vite build: **passed**, JavaScript 365.99 kB / 107.21 kB gzip, CSS 43.92 kB / 9.71 kB gzip. Log: `.build/audit082-build.log`.
- New current-behavior unit diagnostics: **8 passed**. Log: `.build/audit082-frontend.log`.
- New Chromium diagnostic workflows: **9 passed**. Log: `.build/audit082-browser-final.log`.
- Selected core browser regression: **22 passed, 1 failed in the combined run**; the failed WebKit organization test **passed in isolation**. No uninterrupted 23-test pass is claimed. This audit did not rerun all 109 scenarios from the prior release validation.
- Six backend observations reproduced using disposable databases and synthetic input. One is the limited injected-send cleanup case above.
- Real backup cancellation: **zero retained temporary copies**. No real user database was used for this experiment.
- Production-only npm audit: **zero known vulnerabilities**. Full npm audit: **one moderate development dependency advisory**. `pip check`: **no broken requirements**; dependency consistency is not a Python vulnerability scan.
- Preservation: **11 before, 11 after, exact scientific JSON hash/ID match**, no added or missing investigations. Evidence: `.build/audit082-preservation.json`.

The frozen Windows executable still lacks execution validation: the earlier automatic approval review rejected its launch with the reason “blocked by policy.” No launch was retried during this audit. The prior source-launcher smoke test and package-integrity checks do not prove frozen-binary execution. Code signing and a clean-machine launch test remain release work.

Firefox was not validated because the earlier host launch failed. Representative-user sessions and manual assistive-technology checks remain unperformed; automated accessibility checks do not establish full conformance. No new biological capabilities, clinical claims, external-source authenticity guarantees, or genome-scale performance claims were tested.

## Diagnostic entry points

These commands reproduce current defects; they are not corrected-behavior regression tests:

```powershell
# Repository root
.\.venv\Scripts\python.exe scripts/audit082-probes.py
.\.venv\Scripts\python.exe scripts/audit082-disconnect-probe.py

# frontend
node ./node_modules/vitest/vitest.mjs run --config audit082.vitest.config.ts
node ./node_modules/@playwright/test/cli.js test --config audit082.playwright.config.ts --reporter=line
```

Suggested repair order: restore correctness (1–2), scientific input/explanation correctness (3, 8–10), recovery and saving (4–7), visible focus and request recovery (11–12), then dependency/test/release work (13–16). Add desired-behavior regressions as repairs are implemented, while preserving the historical audit evidence.
