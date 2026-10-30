# GenomeDebugger 0.8.1 bug audit

October 28, 2026. Application 0.8.1, comparator 0.6.5, SQLite schema 3.

**Historical audit: all 13 findings are addressed in application 0.8.2 / comparator 0.6.6.** See [the fix report and validation](fixes-0.8.2-2026-10-28.md). Original reproductions below are retained as history. Diagnostic commands now run corrected-behavior regression assertions. This audit was bounded, not a guarantee that no other bugs exist. Existing scientific records remain preserved.

The twelve particular reproductions from the 0.8.0 audit remain covered by the 0.8.1 regressions. Some findings below expose related conditions that those tests did not cover: combining a flag action with an open stale editor, adding a row rather than reordering identical rows, and checking backup semantics beyond schema/model readability.

## 1. P1 — Restore can replace a database that another port is actively serving

Location: [desktop.py](../scripts/desktop.py#L32), [manage.py](../backend/app/manage.py#L67).

Reproduction, against disposable data only:

1. Run the source desktop launcher with a chosen `--port` and isolated `--data-dir`.
2. Save an example and download a database backup.
3. Save another comparison after that backup.
4. Invoke the launcher with the **same data directory**, a different unused `--port`, and `--restore-backup` pointing to the older backup.

Observed: restore exits successfully while the original application process remains alive and its health endpoint returns 200. The later comparison becomes 404 on that still-running application. A before-restore database copy is preserved, so this does not demonstrate irreversible loss.

Cause: the launcher checks only its requested network port, and the restore helper checks only transient SQLite journal files. An idle connection leaves no journal that proves a workspace is in use. The source management command similarly checks a fixed port 8000 rather than ownership of the destination database.

Required repair: enforce an application-lifetime lock tied to the resolved database/data directory. Restore and every launcher must consult that lock, independent of network port. Preserve the previous-copy behavior.

## 2. P1 — Restore accepts a scientific result that cannot replay

Location: [manage.py](../backend/app/manage.py#L32).

Reproduction: make a temporary copy of a valid backup and change a saved investigation's identity status from `verified` to `rejected`, leaving the input, ID, hash, schema, and valid JSON types intact. Restore that copy into a temporary destination.

Observed: restore succeeds and loads the altered `rejected` result, while running the unchanged saved input through its comparator produces `verified`.

Cause: validation parses the result model and checks its ID/title against SQL columns, but does not check input fingerprints, deterministic identity, or scientific replay. Portable bundles perform stronger consistency checks than full-workspace restore.

Required repair: validate each restored immutable record using the appropriate archived/current comparator and evidence validation before replacing the destination. Do not rewrite legacy scientific records or treat hashes as authentication of a source.

## 3. P2 — Restore accepts a broken saved-test parent and removes deletion protection

Location: [manage.py](../backend/app/manage.py#L37), [storage.py](../backend/app/storage.py#L370).

Reproduction: create a valid investigation with a pinned regression baseline. In a temporary backup, change only the SQL `regression_cases.source_investigation_id` column to `missing-parent`; leave the baseline JSON pointing to the real investigation. Restore the copy.

Observed: restore succeeds. Loading the baseline still shows the real embedded parent, but deleting that investigation now succeeds because deletion protection consults the inconsistent SQL column. Ordinary saves reject inconsistent parents; restore bypasses that protection.

Required repair: reconcile indexed SQL metadata with the typed records and validate parent existence, baseline identity, run ownership, and linked checks as a complete staged workspace.

## 4. P2 — Favorite bypasses the open editor's concurrent-note conflict check

Location: [WorkspaceLibrary.tsx](../frontend/src/WorkspaceLibrary.tsx#L33).

Reproduction:

1. Open a comparison's details and type unsaved notes.
2. Save different notes for that comparison from another tab.
3. In the first tab, click **Favorite** on the same record.
4. Click **Save library details** in its still-open editor.

Observed: the last save returns 200 and silently overwrites the other tab's saved notes. Directly saving the stale editor without the Favorite step correctly returns 409.

Cause: a flag response installs its latest `label_revision` into the open editor while retaining that editor's stale name/notes/tags. It therefore gives the stale form a fingerprint for data it never loaded or reconciled.

Required repair: keep the editor's original revision until its text has been reconciled, or explicitly merge nonconflicting changes without accepting stale fields as current.

## 5. P2 — Adding a CSV annotation invents a transcript-selection change

Location: [tabular_import.py](../backend/app/tabular_import.py#L69), [engine.py](../backend/app/engine.py#L119), [engine.py](../backend/app/engine.py#L238).

Reproduction: import A with transcript `T2` reporting `intron_variant`. Import B with the exact same T2 row plus a new T1 row reporting `missense_variant`. Use the same variant, context, tool, and source metadata.

Observed: the engine reports top-level `transcript_id` and `consequence` changes and a possible **transcript selection** cause, as well as the actual T1 row addition. The common T2 output did not change, and neither file declares a selected transcript.

Cause: canonical sorting fixes reordering identical files, but the lowest identifier can change when a row is added. The engine still treats that display anchor as a scientific selector. The overview caveat does not remove the misleading finding or artificial changed values.

Required repair: compare imported complete row sets independently of an arbitrary overview anchor. Derive selection findings only from an actual declared selection. Version any scientific comparator change and retain archived replay support.

## 6. P2 — Different DNA edits still produce a possible transcript-selection explanation

Location: [engine.py](../backend/app/engine.py#L235).

Reproduction: take the synthetic transcript-switch input, remove its controlled lookup, and change B's alternate allele to `G` while keeping A's alternate `T` and valid shared context.

Observed: allele identity is correctly `rejected`, but the findings still propose **transcript selection** as a possible cause of the annotation changes.

Cause: fallback attribution checks only for differing transcript IDs and annotation values. It does not require an established common allele or distinguish annotation comparisons across different edits.

Required repair: surface the variant mismatch first and gate same-variant causal suggestions on their actual applicability. No verified causal conclusion was produced in this reproduction.

## 7. P2 — Different source fingerprints and source locations disappear from the change list

Location: [engine.py](../backend/app/engine.py#L180).

Reproduction: compare otherwise matching snapshots with different valid `provenance.input_sha256` values and different `provenance.source_uri` values. Keep tool/version, source/release, and configuration identical.

Observed: the API returns an empty `differences` array. The overview therefore reports no changed values even though two supplied provenance fields differ.

Cause: these optional provenance fields are preserved in the model but omitted from field comparison.

Required repair: expose changed provenance fields, with suitable rule priority and without interpreting a different hash or location as proof of changed biology or source authenticity.

## 8. P2 — Readable HTML reports omit unchanged additional outputs

Location: [ReadableReport.tsx](../frontend/src/ReadableReport.tsx#L5).

Reproduction: save a matching comparison with an additional primary-variant transcript and a second represented variant with its own transcript. Keep these outputs identical between A and B. Download the readable HTML report.

Observed: the live app contains the additional rows, but the downloaded report contains neither additional transcript ID. The technical appendix does not recover them: equal annotation rows do not generate field-difference evidence. The generated report lists only each primary annotation, without a complete represented-row section.

Required repair: include a readable inventory of all compared variants and annotations, including unchanged rows, or make an explicitly partial report's omissions/counts unmistakable. The full bundle retains these data; this finding concerns the reading copy.

## 9. P2 — Opening another record's editor silently discards unsaved details

Location: [WorkspaceLibrary.tsx](../frontend/src/WorkspaceLibrary.tsx#L63).

Reproduction: type notes in record A's details editor, click **Edit details** on record B, then return to A's editor.

Observed: A's unsaved text is gone, with no warning, save, or recoverable per-record draft.

Cause: all Edit details buttons replace one `editing` object without checking for pending changes.

Required repair: keep per-record edit drafts or provide a deliberate save/discard decision when switching records. Apply consistent pending-edit handling to other navigation that unmounts the editor.

## 10. P2 — Ordinary long CSV filenames are rejected with an unrelated error

Location: [tabular_import.py](../backend/app/tabular_import.py#L16), [ImportWorkspace.tsx](../frontend/src/ImportWorkspace.tsx#L20).

Reproduction: select a valid CSV named with 147 ASCII `x` characters followed by `.csv` (151 characters total), and a valid second CSV. Preview them.

Observed: file selection works, but preview returns 422 because the filename exceeds 150 characters. The UI says the file's **columns and metadata** are invalid and hides the actual filename limit. A 151-character ASCII filename is valid on this host; neither the format explanation nor file picker discloses this restriction.

Required repair: preserve a supported original filename independently of the bounded display label, or disclose/check a filename bound with an actionable error. Keep Unicode truncation and original-byte hashing correct.

## 11. P2 — Saved-date filtering disagrees with the locally displayed date

Location: [workspace.py](../backend/app/workspace.py#L103), [WorkspaceLibrary.tsx](../frontend/src/WorkspaceLibrary.tsx#L57).

Reproduction: in a temporary database set a record's valid save time to `2026-10-28T02:00:00+00:00`. In America/Chicago this is October 27 at 9 p.m. Filter **Saved on or after** October 28.

Observed: the record is included, although the UI's localized save timestamp is October 27.

Cause: the browser displays local time but submits only `YYYY-MM-DD`; SQL compares that date directly against the UTC timestamp string. No timezone boundary is passed or explained.

Required repair: consistently use a local-midnight instant including offset/timezone, or explicitly label and display UTC filtering. Test daylight-saving boundaries as well as positive and negative timezone offsets.

## 12. P3 — Undoing back to the exact compared input leaves a false stale-result warning

Location: [App.tsx](../frontend/src/App.tsx#L117), [App.tsx](../frontend/src/App.tsx#L141).

Reproduction: open a saved comparison, enter Input JSON, append one space, then click **Undo edit**. The textarea now equals the original compared text exactly. Return to Results.

Observed: the application still says the input has changed and the displayed comparison uses previous input.

Cause: `inputDirty` records edit history rather than actual divergence; Undo always sets it to true.

Required repair: derive stale-result state from the current input versus the displayed comparison, with a defined normalization policy. Editing back manually should also clear the warning.

## 13. P3 — Four remaining list APIs return 500 for oversized offsets

Locations: [main.py](../backend/app/main.py#L296), [main.py](../backend/app/main.py#L513), [main.py](../backend/app/main.py#L618), [main.py](../backend/app/main.py#L648).

Reproduction: submit `offset=9223372036854775808` to each endpoint below, using an existing case for the last one:

- `/api/investigations`
- `/api/sources/records`
- `/api/regression-cases`
- `/api/regression-cases/{id}/runs`

Observed: all four return 500 from SQLite integer conversion. The newer workspace-library endpoint correctly rejects the same input with 422.

Required repair: apply a common signed SQLite integer bound at every paging entry point and internal cursor boundary.

## Reproduction artifacts and verification

All destructive restore and SQL-corruption probes use disposable databases. No live provider requests, personal variant uploads, or application-record edits were made. The real workspace still has exactly 11 investigations; their serialized scientific records match the pre-update backup byte-for-byte.

Diagnostics intentionally assert the observed defects. They are separate from normal regression suites, and must be changed to correct-behavior assertions when fixes are implemented.

From the checkout root:

```powershell
.\.venv\Scripts\python.exe scripts\audit081-probes.py
.\.venv\Scripts\python.exe scripts\audit081-desktop-probe.py
```

From `frontend`:

```powershell
node .\node_modules\vitest\vitest.mjs run --config audit081.vitest.config.ts
node .\node_modules\@playwright\test\cli.js test --config audit081.playwright.config.ts
```

- Backend diagnostics: 8 observed conditions verified, covering findings 2, 3, 5, 6, 7, 10, 11, and 13.
- Source desktop diagnostic: the running-workspace restore gap reproduced, then the owned isolated server was stopped.
- Component diagnostics: 4 observed conditions verified, covering findings 4, 8, 9, and 12.
- Browser diagnostics: 5 passed, reproducing the actual API/UI note overwrite, editor switching, Undo warning, downloaded-report omission, and long-filename error.
- Existing backend suite: **405 passed** on the final complete rerun. The initial run had one SQLite disk I/O failure; its affected file passed independently and the complete rerun passed. This is recorded as an unreproduced environment/test interruption, not an additional confirmed application defect.
- Existing frontend unit suite: **56 passed** across 12 files.
- Production TypeScript/Vite build: **passed**, with unchanged production asset hashes.
- Existing browser regression: **all 101 distinct scenarios passed across batches** (94 Chromium and 7 WebKit). A longer run passed 57 scenarios before test-server connections reset/refused; a focused 38-scenario Chromium run then passed, covering every interrupted case and remaining Chromium scenario, with one overlapping scenario. A separate WebKit run passed all 7. A prior longer attempt was also interrupted after 38 passes. **No uninterrupted 101-test pass is claimed for this audit.** The cause of the intermittent server exits is undetermined; it is a validation limitation, not an additional confirmed bug with an established cause. Missing Playwright browser runtimes were installed before browser execution.

Ignored verification logs are retained under `.build/audit081-browser-baseline.log`, `.build/audit081-browser-remaining.log`, `.build/audit081-webkit.log`, and `.build/audit081-backend.json`. Whitespace checks pass. Production assets and the application version remain unchanged.

This audit did not retry the previously blocked Windows executable launch. Source-launcher observations do not establish frozen-executable behavior. Firefox, representative-user sessions, and manual assistive-technology validation remain outside this pass.
