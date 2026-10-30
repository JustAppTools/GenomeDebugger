# GenomeDebugger 0.8.0 bug audit

Audited October 27, 2026. Application 0.8.0, comparator 0.6.5, SQLite schema 3. **12 confirmed bugs were found in that audit. All twelve were subsequently addressed in 0.8.1**; see [the fix report](fixes-0.8.1-2026-10-27.md). The observations below retain the original reproduction details.

P1 denotes higher-priority scientific accuracy, provenance, or recovery problems; P2 denotes functional defects; P3 denotes defensive API validation. This is the confirmed list from this pass, not a claim that all possible defects have been exhausted.

## Findings

### 1. P1 — Sorting CSV annotation rows creates apparent scientific changes

Location: [tabular_import.py:69](../backend/app/tabular_import.py#L69).

The importer silently treats the first encountered annotation as the selected primary annotation. The tabular format does not require users to declare a selected transcript, and the preview does not warn that row order selects one.

Reproduction: import two files with identical metadata, DNA context, and annotation sets: `T1 / missense_variant` and `T2 / intron_variant`. Reverse only the annotation-row order in the second file. Both files are accepted. The result reports meaningful `transcript_id` and `consequence` changes, and a possible transcript-selection cause, despite identical annotation contents.

Expected: a harmless file sort should not invent an analytical selection. Align unordered rows or require an explicit primary selection before assigning scientific meaning to it. Existing explicit primary-selection semantics in the comparator need not be removed.

### 2. P1 — CSV import changes original file bytes before recording their fingerprint

Location: [ImportWorkspace.tsx:16](../frontend/src/ImportWorkspace.tsx#L16), [readUtf8.ts:5](../frontend/src/readUtf8.ts#L5).

The CSV path calls `readUtf8(file)` with its default BOM-removing behavior. A valid UTF-8 CSV with a byte-order mark therefore loses its first three bytes before reaching the backend. The backend faithfully hashes and stores the altered text as `original_utf8` and presents that fingerprint as the original file fingerprint. The CLI path preserves the BOM, so the same original file can also receive different provenance depending on the entry path.

Reproduction: select a valid CSV beginning with UTF-8 bytes `EF BB BF`. The captured preview request lacks the BOM and is three bytes shorter. Its stored file hash cannot equal the original file's SHA-256. Biological row values are unaffected; original-byte provenance is incorrect.

Expected: retain the original bytes/text for hashing and storage, while stripping a BOM only in the parser's working copy. The decoder already supports explicit BOM preservation.

### 3. P1 — Restore accepts an incompatible database and replaces a working workspace

Location: [manage.py:19](../backend/app/manage.py#L19), [storage.py:75](../backend/app/storage.py#L75).

Restore verifies SQLite integrity, a schema-version number, and the existence of a table named `investigations`. It does not verify the table columns, required tables, or readable scientific records. Schema-3 initialization then trusts the version and returns immediately.

Reproduction: make a valid SQLite file containing `CREATE TABLE investigations (unexpected TEXT)` and `PRAGMA user_version=3`. Restore it over an isolated working workspace. Restore succeeds; `/api/health` still returns 200; the library returns 500 because expected tables/columns are missing.

The previous database is preserved in a before-restore copy, so this reproduction does **not** establish irreversible record loss. It does establish that recovery can install an unusable database and falsely report health.

Expected: validate the supported GenomeDebugger schema and records before replacing the destination; reject incompatible databases without replacing it.

### 4. P2 — Notes typed during a save are discarded when the older save completes

Location: [WorkspaceLibrary.tsx:33](../frontend/src/WorkspaceLibrary.tsx#L33), [WorkspaceLibrary.tsx:69](../frontend/src/WorkspaceLibrary.tsx#L69).

Reproduction: edit a comparison's notes, click Save, delay the response, and type newer notes into the still-enabled editor. When the response completes, `setEditing(null)` closes the editor and discards the newer text. The submitted request contains the earlier text. There is no draft-revision check or recovery notice.

Expected: lock the editor during submission, or preserve and identify edits made after submission rather than silently closing them.

### 5. P2 — A stale tab's Archive/Favorite action overwrites another tab's notes

Location: [WorkspaceLibrary.tsx:31](../frontend/src/WorkspaceLibrary.tsx#L31), [workspace.py:31](../backend/app/workspace.py#L31).

The UI sends every cached label field even for a single Archive/Favorite action. The backend replaces all label fields without a version check.

Reproduction: two clients load an empty label. Client A saves new notes. Client B archives its older cached row. Client B sends empty notes with `archived=true`, and the saved notes become empty. The archive succeeds without warning that unrelated text was overwritten.

Expected: atomic updates to the fields actually changed, or conflict detection against the label revision. This is distinct from typing during one pending save.

### 6. P2 — Valid Unicode names can make Next records fail

Location: [workspace.py:103](../backend/app/workspace.py#L103), [main.py:245](../backend/app/main.py#L245).

Generated cursors contain the full name, JSON-escaped and then base64-encoded. The same API refuses incoming cursors longer than 2,000 characters. A valid 200-character supplementary-Unicode title generates a 3,280-character cursor, including for the default newest-first sort, which does not need the name for continuation.

Reproduction: create 51 isolated records, placing a title of 200 DNA emoji at the boundary of the first 50-record page. The first page succeeds; using its returned cursor gives 422. This reproduces the actual default UI page size, not just a reduced test page.

Expected: every cursor emitted by the API must be accepted back by the API; encode only necessary keys and bound the resulting representation consistently.

### 7. P2 — Valid Unicode filenames can make CSV preview fail validation

Location: [ImportWorkspace.tsx:19](../frontend/src/ImportWorkspace.tsx#L19).

The generated comparison title uses JavaScript `.slice(0,200)`, which truncates UTF-16 code units. It can split a supplementary character into a lone surrogate that the backend correctly rejects.

Reproduction: use filename A consisting of 130 `a` characters plus `.csv`, and filename B consisting of 50 `b` characters plus `🧬.csv`. Both filenames are valid and within the backend's filename limit. The generated title ends with half an emoji. The preview returns 422 for invalid Unicode even though both source files and filenames are valid.

Expected: truncate complete Unicode characters without creating invalid text.

### 8. P2 — The home draft-recovery offer goes stale

Location: [App.tsx:109](../frontend/src/App.tsx#L109), [DraftTools.tsx:9](../frontend/src/DraftTools.tsx#L9).

The home screen snapshots draft availability once. Saving/discarding in `DraftTools` updates only the child component's state.

Two reproductions: save a new browser draft and navigate to the empty Results/home screen: no Resume offer appears. Conversely, begin with a saved draft, discard it in the editor, and return home: a Resume button remains, but clicking it does nothing because storage is empty. Reloading reconciles the state.

Expected: the home offer follows the actual saved-draft lifecycle. This bug does not remove a successfully saved draft from browser storage.

### 9. P2 — Matching and missing-evidence examples describe a nonexistent controlled lookup

Location: [App.tsx:356](../frontend/src/App.tsx#L356).

All synthetic examples receive the transcript-switch example's hardcoded instructions. Both newer examples have `controlled_lookup=null`; the missing-evidence example also has no supplied reference context. Nevertheless, their guide says a controlled lookup repeats the outputs and describes supplied reference letters.

Reproduction: open either Matching outputs or Missing evidence. The input contains no controlled lookup, but the guide claims one repeats the outputs. The Missing evidence instructions also contradict the absent context.

Expected: instructions reflect the actual example and distinguish the absence of a replay/reference context from evidence that was obtained.

### 10. P2 — Re-running a renamed comparison loses its name in Recent

Location: [App.tsx:240](../frontend/src/App.tsx#L240).

Reproduction: rename a saved comparison in the library, reopen it, and run the same comparison again. `showResult` replaces the Recent entry with only the scientific title and ID. The recognizable display name and saved date disappear from the sidebar until the app reloads. The library's persisted name remains intact.

Expected: updating the result should preserve or reload its organization metadata instead of replacing the sidebar row with an incomplete one.

### 11. P2 — Readable additional-variant evidence omits its identity verdict and reason

Location: [EvidenceInspector.tsx:22](../frontend/src/EvidenceInspector.tsx#L22).

Every input record containing `a` and `b` takes a specialized branch that renders only those two variants. Additional-variant identity evidence also contains `status` and `explanation`; these fields are omitted from the readable view.

Reproduction: compare an additional variant with no supplied reference context, then select its identity evidence. The actual engine record says `unresolved` and explains the missing context. Its readable details omit that verdict/reason; the exact explanation is available only after expanding JSON. A generic linked finding does not replace the case-specific evidence result.

Expected: show the recorded identity status and explanation alongside A/B values.

### 12. P3 — Oversized library paging numbers produce an internal server error

Location: [main.py:245](../backend/app/main.py#L245), [workspace.py:60](../backend/app/workspace.py#L60).

Reproduction: request `/api/workspace/library?ceiling=9223372036854775808`. The parameter passes admission but overflows SQLite's signed integer binding and returns 500. The older investigation-page endpoint already has the appropriate upper bound. Cursor-contained numeric bounds need equivalent validation.

Expected: return a bounded validation error, without entering the database operation. This requires a malformed API request; normal generated page ceilings are not this large.

## Verification and reproduction files

- Existing backend suite: **386 passed** during this audit, with one existing Starlette/anyio deprecation warning.
- Existing frontend suite: **44 passed across 11 files** during this audit. The passing regression suite does not cover the failures above.
- At audit time, six backend probes and nine frontend probes confirmed the broken behavior. These have now been converted and expanded into [19 backend regressions](../backend/tests/test_v081_fixes.py) and [12 frontend regressions](../frontend/src/V081Fixes.test.tsx) asserting the corrected behavior. The [backend audit command](../scripts/audit080-probes.py) and [frontend audit config](../frontend/audit080.vitest.config.ts) run those current regressions.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\audit080-probes.py
```

Then run from `frontend`:

```powershell
node .\node_modules\vitest\vitest.mjs run --config audit080.vitest.config.ts
```

No production source files or real saved investigations were changed. The probes used isolated SQLite files, supplied synthetic data, and mocked frontend requests. No live genetic identifier/source queries or external transmissions were performed.

The packaged executable, Firefox, and manual assistive-technology behavior were not newly validated in this pass. Their earlier validation limitations remain separate from the 12 confirmed bugs; they have not been counted as defects without reproduction.
