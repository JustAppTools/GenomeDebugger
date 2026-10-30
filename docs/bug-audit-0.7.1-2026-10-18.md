# Current bug audit — application 0.7.1 / comparator 0.6.3

Reviewed on 2026-10-18 at commit `b085e08290dc52bf8610d3c588d037a78b3de359`.

Six confirmed issues are listed below. This review does not establish that no other defects exist. Application code was not changed.

**Resolved in application 0.7.2:** all six findings below describe the audited 0.7.1 behavior. Comparator engine 0.6.3 and archived comparison rules are unchanged. See the repair verification at the end of this report.

## Verification and scope

- Existing checks pass: **139 backend tests, 27 frontend tests, all 18 Chromium workflows, and the production build**.
- Four additional Chromium probes reproduced the field search failure, stale candidate verdict, overlapping input imports, and example-loading draft loss. These probes asserted the observed faulty behavior; their passing results do not mean those behaviors are correct. The temporary probe file was removed after the audit.
- Three additional backend probes reproduced contradictory reference-check reporting, a regression-case/deletion race, and concurrent database quota bypass.
- A read-only backup of the current user database was checked separately: all **10 saved investigation bundles** verified, and both existing pinned regression baselines passed on the copy.
- Browser probes used Playwright's isolated servers and temporary database. Backend probes used temporary databases, fixtures, mocked external responses, and deterministic request barriers. User records were not added, edited, or deleted. No new live scientific observations are claimed.
- Scope included the simplified results flow, editors/imports, saved tests, persistence/deletion, source/check validation, reports, and bundle compatibility. External service availability and additional browser engines were not independently exercised.

## 1. P1 — Text reports can contradict the actual preserved NCBI check

Locations: [report.py](D:/Creation/GenomeDebugger/backend/app/report.py:57), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:36).

Reproduction:

1. Preserve an Ensembl source and an NCBI check whose observed reference disagrees with the submitted reference. The preserved check and its summary have `status: disagree`.
2. Generate a comparison linked to the real check.
3. In both snapshots, change only `provenance.configuration.reference_check_status` to `agree` and `reference_check_id` to `nonexistent-check`. Leave the actual `reference_check` summary intact.
4. POST the input to `/api/investigations`, request its text report, export its bundle, and verify the bundle.

Observed: creation, bundle export, and bundle verification all return HTTP 200. The report says:

```text
Linked NCBI allele check: `nonexistent-check` (agree).
```

The real preserved check still records disagreement. Other sections can therefore contradict this report line, and the advertised retrieval link points to a nonexistent record. The same editable configuration also supplies the check ID displayed in the technical snapshot cards.

Cause: validation checks the real summary against preserved evidence but does not reconcile duplicate check metadata in snapshot configuration. The text report reads the duplicate configuration instead of the validated summary.

Repair: derive displayed check identity/status from the validated linked check, reject contradictory duplicate metadata, and apply the same consistency rule during bundle verification. User-supplied artifacts remain externally unauthenticated.

## 2. P2 — A passing candidate verdict remains visible beside untested edits

Location: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:59).

Reproduction:

1. Open the example, open **Saved tests**, and save a baseline.
2. Submit the unchanged candidate, holding its successful response before delivery to the browser.
3. While the request is pending, change **Candidate analysis 2 consequence** to `stop_gained`.
4. Release the old response.

Observed: the editor retains `stop_gained` while the page displays **Regression passed**. There is no stale-result notice identifying the displayed verdict as belonging to the earlier candidate. Submitting the edited candidate immediately afterward produces **Regression failed**.

Editing after a completed run has the same underlying problem: neither the guided candidate inputs nor Advanced JSON invalidate or label the previous verdict.

Cause: `runCase` installs every response without checking the submitted candidate against the current draft. Candidate edits leave `run` untouched.

Repair: bind the verdict to its submitted input, show a clear stale notice or hide the active verdict after edits, and handle edits made during the request. Keep the historical run available as a historical result.

## 3. P2 — Asynchronous input loading can overwrite newer work

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:139), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:191).

Two browser reproductions confirmed this issue:

### A. Earlier file import replaces the latest selected file

1. Start importing a valid `slow.json` input and hold its `File.text()` completion.
2. Import another valid input with title `New selected input` and wait until it appears in the JSON editor.
3. Release the earlier file read.

Observed: the editor changes back to the older file, with no warning. Raw input-file imports have no request revision guard.

### B. Example loading erases edits made while fetching the example

1. Open the JSON editor and click **Try an example**.
2. Hold the initial `/api/demos/transcript-switch` GET response.
3. Enter a new JSON draft while waiting, then release the response.
4. After the example appears, reopen the editor.

Observed: the newer draft is gone; the editor contains the example and shows no stale-draft notice. The existing protection for edits during comparison POST requests does not cover this earlier GET stage.

Repair: track both the latest input-loading operation and the draft revision. A late load must not silently replace a newer file selection or edits made after the load began.

## 4. P2 — Saving a baseline can race deletion and leave an orphaned saved test

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:374), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:264), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:244).

Reproduction:

1. POST `/api/investigations/{id}/regression-cases`, pausing after the source investigation is read and the case is constructed, before persistence.
2. DELETE that investigation through the API.
3. Release the baseline save.

Observed: both requests return HTTP 200. GET of the investigation returns HTTP 404, but `regression_cases` contains one case referencing that deleted investigation.

The embedded baseline data survives in the case, but the normal investigation-based Saved tests navigation cannot reopen it. The intended protection against deleting investigations with pinned tests has been bypassed by the request ordering.

Cause: parent lookup and child insertion are separate operations. `save_case` does not validate parent existence inside the transaction that inserts the baseline. The transactional parent guard added for allele checks does not cover regression cases.

Repair: serialize parent validation, baseline insertion, and deletion through the same transactional rule. Either deletion or baseline creation must fail cleanly when the other has already won.

## 5. P2 — Concurrent regression saves exceed the configured database limit

Locations: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:264), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:287).

Reproduction:

1. On a temporary database, set `GENOMEDEBUGGER_MAX_DB_MB=10` and prepare usage near that limit.
2. Prepare two valid baseline saves, each small enough to fit by itself but too large to fit together.
3. Allow both requests to finish `_guard_size` before either inserts, then release both saves.

Observed in the deterministic probe:

| Measurement | Bytes / result |
|---|---:|
| Configured limit | 10,485,760 |
| Used pages before saves | 9,531,392 |
| Serialized size of each baseline | 604,279 |
| Response statuses | 200, 200 |
| Used pages after saves | 10,743,808 |

Cause: `save_case` checks capacity outside its insertion transaction. Both requests see the same available space. `save_run` uses the same non-atomic pattern; the measured reproduction used baseline saves.

Repair: perform the capacity decision while holding the write transaction, include the pending write, and use the same guarded persistence path for cases and runs. Return the existing storage-limit error for the request that cannot fit.

## 6. P2 — Searching the displayed plain-language field names returns no matches

Location: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:58).

Reproduction:

1. Open **Try an example**, then **See the changes**.
2. Confirm that the table contains **Predicted effect**.
3. Enter `Predicted effect` into **Search fields**.

Observed: the visible row disappears and the table says **No differences match these filters.** Searching the internal field identifier `consequence` finds it instead.

Cause: the table renders translated names through `fieldNames`, but its search predicate checks only the raw `d.field` string. Several new plain-language labels therefore cannot be used to find their own rows.

Repair: search both displayed field names and raw identifiers, with consistent normalization. Preserve raw identifiers for advanced users.

## Suggested repair order

1. Report/check consistency.
2. Candidate verdict freshness and input-loading draft preservation.
3. Transactional baseline parent checks and storage limits.
4. Plain-language field search.

## Repair verification — application 0.7.2

All six findings are resolved:

1. Shared API/bundle validation rejects contradictory or dangling NCBI configuration claims. Reports and technical cards use the linked summary. Valid older inputs may omit duplicate configuration fields.
2. Candidate verdicts track the submitted editor input. Edits before or after response delivery label the result as previous; historical candidate runs are explicitly identified as saved runs.
3. Input loading checks both request order and draft revisions. Older file reads cannot replace a newer file, and example/file loads preserve intervening edits with a visible explanation. Saved-record and bundle opening also preserve intervening draft edits.
4. Regression-case persistence checks parent existence and baseline equality inside the same write transaction used to coordinate deletion.
5. Cases and runs use the common transactional storage path. Capacity is checked while holding the write lock and actual SQLite usage is checked before commit; an allocation failure rolls back the whole save.
6. Field search matches both displayed labels and raw identifiers, ignoring case and surrounding whitespace.

Verification: **150 backend tests, 27 frontend tests, all 25 Chromium workflows, and the production build pass**. The new coverage includes contradictory check metadata in either snapshot, API/candidate/bundle rejection, legacy reports, deleted/mismatched parents, immutable case/run saves, concurrent case and run quota checks, SQLite growth rollback, candidate edits during and after runs, historical verdict labels, overlapping valid/invalid imports, edits during file/example loading, and displayed-name searches.

All 10 existing saved investigation bundles verify on a temporary database copy. Both existing pinned baselines pass, and their new run records can be persisted on that copy. User records were not modified. No push was performed.
