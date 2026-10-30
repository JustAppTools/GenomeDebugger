# Current bug audit — application 0.7.5 / comparator 0.6.3

Reviewed on **2026-10-20** against the current workspace, including the existing uncommitted fixes on top of commit `b085e08290dc52bf8610d3c588d037a78b3de359`.

**Eleven findings were reproduced.** No application code was changed. This review does not prove that every possible defect has been found.

**Repair follow-up:** all eleven findings were addressed in application 0.7.6; see [repairs and verification](fixes-0.7.6-2026-10-20.md). The findings below describe the audited 0.7.5 state.

## Verification and limits

- Existing checks pass: **204 backend tests, 34 frontend tests, all 43 Chromium workflows, and the production build**.
- Five additional Chromium probes reproduced both directions of source-form draft loss, malformed UTF-8 decoding, refresh of an older-page selection, and duplicate regression history. These probes asserted defective behavior; passing probes mean the bugs were reproduced. The temporary browser test file was removed.
- Backend/API/CLI probes used temporary databases, actual FastAPI requests, and captured or constructed fixtures. No user database records were changed and no upstream biological services were queried.
- The startup/restart reproduction mocked process, network, and directory operations. No real process was stopped or launched. The regression evidence-link test injected a defective comparator result; it demonstrates a checker false pass, not that the current comparator normally creates dangling links. The legacy-report probe simulates an already stored out-of-scope check; it does not demonstrate importing such a check through current bundle validation.
- A rapid real-clock SnpEff sample generated 100 checks with distinct version declarations. Two genuinely colliding results were replayed through the API's check function to verify immutable-storage conflict handling.
- The first CLI probe left two empty audit database files in a temporary directory after its inspection connection prevented immediate cleanup. A subsequent successful probe used explicit connection closing. Automatic execution review rejected both recursive and explicit-file cleanup of the first directory with `blocked by policy`. The residual files are `C:/Users/vicsp/AppData/Local/Temp/tmppszyq7xi/backup.db` and `misspelled-source.db`; neither contains user records. No further deletion workaround was attempted.
- Live upstream availability, other browser engines, and production deployment were not tested.

## 1. P1 — Restart ownership checks can approve stopping an unrelated project

Locations: [start-local.ps1](D:/Creation/GenomeDebugger/scripts/start-local.ps1:17), [start-local.ps1](D:/Creation/GenomeDebugger/scripts/start-local.ps1:27).

Reproduction with mocked system calls:

1. Make the port-8000 listener belong to an unrelated project with command line `D:\OtherProject\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
2. Run the script with `-NoBrowser -Restart`, replacing `Stop-Process` with a recording stub and network calls with a different application's HTTP 200 responses.

Observed:

```text
AUDIT MOCK: would stop unrelated project: -Id 777777 -Force
GenomeDebugger is ready at http://127.0.0.1:5173/
```

Cause: the restart guard checks only a generic relative Uvicorn invocation. It does not verify that the executable/module belongs to this repository. Readiness checks only HTTP status, so another application returning 200 is accepted as GenomeDebugger.

Impact: a common local development port collision can be misidentified as a healthy GenomeDebugger instance; requesting restart can approve stopping that other project's backend. No such real process was stopped in this audit.

Repair: establish and validate project-specific process ownership before termination and verify application identity for both frontend/backend readiness. An unrelated listener should produce an actionable port-conflict error.

## 2. P1 — Comparisons still erase newer drafts in the other source form

Locations: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:108), [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:125), [HistoricalPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/HistoricalPanel.tsx:70).

Two browser reproductions:

- Hold a **current source Compare** response. While it is pending, open the historical importer, choose a VEP JSON file, and enter a new historical software version. Release the comparison response. It navigates to overview; reopening the source screen shows empty historical metadata and loses the selected file.
- Hold a **Compare preserved sources** response. Enter a new VCF draft in the current source's SnpEff editor. Release the earlier comparison response. It navigates to overview; reopening the same source shows an empty VCF editor.

Cause: both forms are simultaneously mounted in one screen, with separate operation/selection revisions. Editing one form does not invalidate a comparison started in the other. The root navigation guard added in 0.7.5 is not involved because the user never navigated away while editing.

Repair: coordinate draft revisions and comparison intent across both source forms. An older completion should remain saved without unmounting newer work. Test both directions, including uploads and metadata edits.

## 3. P2 — Malformed UTF-8 input silently becomes different, valid comparison data

Location: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:207).

Reproduction:

1. Prepare an otherwise complete comparison with identical variants/annotations and no controlled lookup.
2. Put raw byte `0xE9` in Analysis A's consequence string and `0xF1` in B's consequence string. The resulting file is not valid UTF-8 JSON.
3. Import the file and click **Compare**.

Observed: the editor contains `�` in both consequence fields. The API accepts the silently converted input and returns **zero differences**. The distinct invalid byte sequences have collapsed to the same Unicode replacement character.

Cause: `File.text()` uses replacement decoding for malformed UTF-8. `JSON.parse` sees only the repaired text, so it cannot reject the original encoding error. The historical-file path already uses fatal UTF-8 decoding, but the main importer does not.

Repair: validate/decode supported file encodings explicitly and reject malformed bytes before changing the draft. Audit the separate bundle and VCF text readers for the same decoding policy. Do not silently manufacture replacement characters in analysis data.

## 4. P2 — Distinct SnpEff checks can receive the same immutable ID

Location: [snpeff.py](D:/Creation/GenomeDebugger/backend/app/snpeff.py:114).

Reproduction:

1. Generate 100 matching SnpEff checks rapidly against one source and VCF, changing the declared SnpEff version for each.
2. Observe generated IDs and timestamps using the actual local clock.
3. Replay two genuinely colliding generated results through the API check function and storage boundary.

Observed in this environment: **only five IDs for 100 distinct version declarations**. Two checks with the exact same timestamp `2026-10-20T20:11:05.209885+00:00`, but versions `version-0` and `version-1`, share an ID. Saving the first returns HTTP 200; saving the second returns **HTTP 409** because its immutable contents differ.

Cause: the check ID hashes only source ID, VCF text, and wall-clock timestamp. It excludes the declared software version, genome database, and database hash. Clock resolution is not a uniqueness guarantee. Immutable conflict protection prevents overwriting, but valid distinct observations cannot both be stored under this ID scheme.

Repair: use a collision-safe identity that includes the immutable declaration or an appropriate unique observation identifier. Preserve compatibility with already saved checks and their bundle replay rules.

## 5. P2 — Backup/check commands report success for a missing database

Locations: [manage.py](D:/Creation/GenomeDebugger/backend/app/manage.py:30), [manage.py](D:/Creation/GenomeDebugger/backend/app/manage.py:33), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:295).

Reproduction in a temporary directory:

```text
python -m app.manage --db misspelled-source.db backup --output backup.db
python -m app.manage --db also-missing.db check
```

Neither source database exists before its command.

Observed: both exit with code 0. Backup prints **Backup saved**, creates the missing source, and produces an empty backup with zero investigations. Check creates the missing database and prints **Integrity: ok; schema version: 1**.

Cause: management operations call initialization, which creates an empty database for missing paths. They cannot distinguish a real backup/integrity check from a typo that initialized new storage.

Repair: require an existing readable source for backup/check, open it without create permission, and return a nonzero actionable error when it is missing. Initialization should be a distinct operation.

## 6. P2 — Reports endorse a saved allele check that cache/export reject

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:430), [report.py](D:/Creation/GenomeDebugger/backend/app/report.py:54).

Reproduction:

1. Simulate a legacy stored mitochondrial investigation and an agreeing check record. Mitochondrial checking is outside the current application's supported scope.
2. Request its cache-only allele check, portable bundle, and text report.

Observed: cache loading returns **HTTP 422** and bundle export returns **HTTP 409** due to the scope restriction. The report still returns HTTP 200 and prints that check as **AGREE** under **Independent reference-backed allele identity**.

Cause: the report endpoint forwards `latest_allele_check` directly to the renderer. The renderer handles synthetic inputs specially but does not perform the reconstruction/scope validation used by cache and export paths.

Scope: this concerns an already stored legacy/out-of-scope or inconsistent record. Current bundle import rejects the constructed check. No such record was added to the user's database.

Repair: share saved-check validation across all presentation/export paths. Preserve legacy bytes, but mark invalid/out-of-scope evidence unavailable rather than endorsing its stored status.

## 7. P2 — Pinned regressions pass when every evidence link is dangling

Location: [regression.py](D:/Creation/GenomeDebugger/backend/app/regression.py:72).

Reproduction by comparator fault injection:

1. Save the normal example as a pinned baseline.
2. Make the comparator return the same result data, except that identity, difference, and finding `evidence_ids` all contain `missing-evidence`, which does not exist in the evidence collection.
3. Run the pinned case through the actual API.

Observed: HTTP 200, **status: passed**, with **zero failed required checks**. The saved actual result contains the dangling evidence links.

Cause: difference assertions omit `evidence_ids`; finding assertions omit them; identity checks only its status. Evidence hashing validates each item's kind/data but does not check the relationships from conclusions to that evidence. A complete trail can therefore be broken without failing the pinned checker.

Scope: the current comparator was not observed spontaneously producing these links. The injected fault demonstrates that the regression tool would falsely approve this semantic regression.

Repair: assert reference integrity and the intended evidence relationships in pinned replay. Wording-only changes can remain exempt; dangling or incorrectly linked evidence should not pass.

## 8. P2 — Refresh drops a valid selection from an older source page

Location: [HistoricalPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/HistoricalPanel.tsx:48).

Reproduction:

1. Preserve more than 200 source records. The probe created 201 small historical fixtures plus a current capture.
2. Load preserved sources, click **Load older sources**, and select a record outside the first 200.
3. Click **Load preserved sources** again.

Observed: the panel resets the selection and claims that a source/transcript is **no longer available**. GET of the selected source still returns HTTP 200. Only the first page was refreshed; nothing was deleted.

Cause: refresh validates selection membership against its first 200 returned rows, rather than the full preserved collection. The 0.7.5 fix preserves choices on that page but treats an older-page choice as missing.

Repair: retain or fetch selected records independently of page membership and preserve their valid transcript choices. Distinguish an unavailable record from one outside the current page; coordinate retained rows with pagination offsets/cursors.

## 9. P2 — User text can create forged conclusion sections in reports

Location: [report.py](D:/Creation/GenomeDebugger/backend/app/report.py:22).

Reproduction:

1. Submit an otherwise valid comparison whose actual identity is `unresolved`.
2. Use a title containing newlines, a `## Variant identity` heading, and `**VERIFIED** — inserted title text`.
3. Download the text report.

Observed: the report contains **two Variant identity sections**, including the inserted VERIFIED block, despite the actual result being unresolved. The user value is emitted as Markdown structure instead of literal title text. Other labels, IDs, and metadata are also interpolated without context-appropriate escaping.

Scope: this is report content/format injection. No browser script execution or remote exploit was demonstrated. It can make a rendered report misrepresent which text is an application-generated conclusion.

Repair: render user fields as literal content with appropriate escaping and newline policy. Keep generated headings/conclusions structurally distinct from submitted text, including code and table contexts.

## 10. P3 — A concurrent new run duplicates an older history entry

Location: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:84).

Reproduction:

1. Create 101 runs and open the saved-test panel, which loads the newest 100.
2. Save another run through a second client.
3. Click **Load older runs** in the first client.

Observed: the panel shows **102 history buttons but only 101 distinct run IDs**. One already displayed run is appended again because the new insertion shifts the offset. The new run itself was not part of the initial page.

Repair: use a stable continuation anchor for history, or reconcile/deduplicate pages while preserving correct pagination progress. Keep entries unique when other tabs/clients write during browsing.

## 11. P3 — Literal title searches treat underscore and percent as wildcards

Location: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:277).

Reproduction:

1. Save investigations titled `Literal_Batch_1` and `LiteralXBatchY1`.
2. Search for the exact substring `Literal_Batch_1` through the investigations API/library.

Observed: both records are returned. SQL LIKE interprets `_` as any single character; `%` similarly acts as a wildcard. The UI/docs do not identify this as pattern-search syntax or offer a way to request literal underscores/percent signs.

Repair: escape LIKE metacharacters for ordinary substring search, with an explicit alternative if wildcard search is desired. SQL values are parameterized; this finding is incorrect search semantics, not SQL injection.

## Suggested repair sequence

1. Verify process ownership before restart and stop source comparisons from destroying newer sibling-form drafts.
2. Reject malformed file encodings; fix SnpEff observation IDs and missing-source backup success.
3. Validate report evidence and pinned evidence relationships; escape report inputs.
4. Preserve older-page selections, stabilize history paging, and make ordinary searches literal.

The previously discussed technical-field explanations and raw JSON evidence display remain separate known usability work, not additional newly counted bugs here.
