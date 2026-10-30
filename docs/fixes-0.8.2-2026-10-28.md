# GenomeDebugger 0.8.2 — fixes for the 0.8.1 audit

October 28, 2026. Application **0.8.2**, comparator **0.6.6**, SQLite schema **3**.

All thirteen findings in [the 0.8.1 audit](bug-audit-0.8.1-2026-10-28.md) are addressed. Existing scientific records are preserved; comparator 0.6.5 remains available for historical verification.

| Finding | Resulting behavior |
| --- | --- |
| 1. Restore replaces a running workspace through another port | Every FastAPI server holds an operating-system lock for its resolved database during its application lifetime. Restore obtains the same lock before staging, backing up, or replacing that destination. A different port cannot bypass ownership. Locks release on shutdown/process exit; the remaining lock file is not evidence of an active owner. |
| 2. Restore accepts altered scientific results | Staged investigation inputs, hashes, identifiers, differences, findings, evidence, and check summaries must match their declared comparator replay and preserved evidence. Restoration validates the original result, never a current replay that would conceal an altered saved result. Original pre-versioned formats use archived models/rules, preserving their exact serialized records. |
| 3. Restored metadata bypasses baseline protection | SQL indexes must agree with typed baseline names/parents, run ownership, source query/origin/dates, and check ownership/dates. Parents must exist and match their embedded records; run hashes, actual results, and check verdicts must be coherent. Ordering must contain exactly the investigations with positive sequence values. Invalid restore attempts leave the destination unchanged. |
| 4. Favorite bypasses editor conflicts | Editable details have a separate deterministic fingerprint. Detail saves submit name/notes/tags with the loaded details fingerprint; flags are independent partial updates. Flag responses never install a new details fingerprint into stale editor text. Concurrent note changes return 409 while keeping unsaved text visible. A user's own Favorite action does not prevent a valid details save. |
| 5. Added CSV rows invent a transcript selector | Comparator 0.6.6 compares complete imported variant/annotation sets, including every overview row, by their explicit keys. An added low-sorting transcript or variant is a row addition, not a changed selection/effect. Collection identity covers represented sets and supplied contexts. The overview explains row additions/removals and shows row counts; the inventory remains available. |
| 6. Different edits receive a transcript cause | Possible transcript-selection attribution requires verified common variant identity. Rejected identity exposes a variant-mismatch finding; unresolved identity retains uncertainty instead of proposing a same-variant transcript cause. |
| 7. Source hashes and locations vanish from changes | `source_uri` and original `input_sha256` changes appear as provenance differences. They have low default comparison priority; they do not prove biological change or external authenticity. User priority overrides remain supported. |
| 8. HTML omits unchanged output rows | Readable HTML includes every represented variant and annotation from each analysis, including unchanged transcripts, protein values, and supplied clinical assertions. Reference context and source locations/fingerprints are included. Supplied values remain escaped; the preview remains sandboxed. |
| 9. Switching editors loses details | Per-record unsaved library details remain in memory across record and section switches. Reopening returns to the retained text. Save/cancel/delete clear the relevant draft; leaving or reloading the page warns when unsaved library details remain. These drafts are not silently written to browser storage or a database backup. |
| 10. Valid long filenames fail with unrelated errors | Original filenames up to 255 characters are retained in provenance. Only the 150-character display label is shortened, on complete Unicode characters. Original file bytes/hashes are untouched. Import validation surfaces field-specific errors and explains an unsupported filename length. |
| 11. Local dates are filtered as UTC dates | The browser sends the selected date's local-midnight instant with its timezone conversion. SQL compares normalized instants. The filter explicitly says “your local date”; direct API date-only callers retain a documented UTC-midnight interpretation. Invalid dates/instants return 422. |
| 12. Undo leaves a false stale warning | Staleness is derived from current versus compared input, not whether an edit ever happened. JSON whitespace and key order are normalized; meaningful input edits still warn, including edits made while an older comparison completes. Undo or manually returning to matching input clears the warning. |
| 13. Other list offsets overflow SQLite | All four remaining offset-based API parameters use the signed SQLite integer bound and return 422 for overflow before executing SQL. Existing bounded keyset endpoints remain covered. |

## Historical compatibility and scientific scope

The new comparator produces separate versioned record IDs. Opening an old comparison does not rewrite it; running it again creates a current result. Existing 0.6.5 bundles still verify against frozen 0.6.5 rules. Older rules remain available.

Some original workspace records predate explicit comparator versions and later model defaults. Restoration verifies these with supported frozen original model/rule profiles, including the known early selection/presence behavior. This compatibility validation never applies those old rules to new comparisons and never repairs a historical result by changing its saved JSON.

Original CSV text remains preserved, including BOM and file order. Collection comparison does not add biological normalization, liftover, source authentication, or causal proof. A known old result can retain an old display/selection defect as historical evidence; rerun or reimport to obtain a separate corrected result.

The lifetime lock is advisory across GenomeDebugger 0.8.2 processes. Stop older application versions and other tools editing the database before upgrading/restoring; older binaries cannot retroactively acquire a lock they did not implement. A stopped restore still preserves the previous destination in a unique backup.

## Verification

- Backend: **429 passed**, including 24 new regressions for locking, corrupted scientific replay, broken ownership/indexes, valid pre-versioned restore, archived 0.6.5 bundles, details conflicts, collection additions, provenance changes, filenames, time boundaries, and paging rejection.
- Frontend: **62 passed** across 13 files, including 6 regressions for conflicts, per-record/section drafts, Undo, report completeness/escaping, and details-only saves.
- Production TypeScript/Vite build passes: JavaScript approximately **366 kB / 107 kB gzip**, CSS **44 kB / 10 kB gzip**.
- New browser regressions: **8 passed**, including actual note-conflict handling, own-flag saves, editor recovery, Undo, report downloads, filenames, added CSV rows, and America/Chicago midnight boundaries before/after the daylight-saving change.
- Source desktop cross-port probe: active restore rejected; the later comparison remained available; restore succeeded after shutdown and preserved the prior database.
- Source desktop smoke: compiled UI, synthetic comparison, consistent backup download, and owned shutdown passed in `.build/desktop-smoke-05dc832c`.
- A consistent copy of the real workspace passed staged replay/evidence/ownership validation, including its original pre-versioned records. Pre-change database backup: `data/backups/before-0.8.2-4fc74c7f.db`.

All **109 distinct browser scenarios passed across batches** (102 Chromium, 7 WebKit). A longer run passed 84 scenarios before an outdated collection-wording assertion and server-connection failures; focused runs passed the remaining/corrected scenarios. No uninterrupted 109-test pass is claimed. Test startup uses Vite directly with `CI=true` to avoid interactive stdin handling; intermittent long-run server exits remain a host/test validation limitation. Logs and totals are recorded in [PROGRESS.md](../PROGRESS.md).

After restart, the live app reports 0.8.2 / comparator 0.6.6 / schema 3. All **11 original investigations**, their IDs, and their serialized scientific JSON remain unchanged. The portable Windows ZIP was rebuilt from final source; ZIP integrity, checksum, included compatibility/lock modules, and equality of bundled/production UI pass. No local database or logs are included. Frozen-executable launch remains unverified.

Diagnostic entry points from the original audit now execute corrected-behavior regression assertions:

```powershell
.\.venv\Scripts\python.exe scripts\audit081-probes.py
.\.venv\Scripts\python.exe scripts\audit081-desktop-probe.py
```

From `frontend`:

```powershell
node .\node_modules\vitest\vitest.mjs run --config audit081.vitest.config.ts
node .\node_modules\@playwright\test\cli.js test --config audit081.playwright.config.ts
```

No live provider requests or personal variant transmissions were used. Previously blocked frozen-executable launch was not retried; a source-launcher pass or generated ZIP is not a frozen-executable launch claim. Firefox and manual assistive-technology testing remain outside this verification.
