# Current bug audit — application 0.7.4 / comparator 0.6.3

Reviewed on **2026-10-20** against the current workspace, including uncommitted repairs on top of commit `b085e08290dc52bf8610d3c588d037a78b3de359`.

**Six findings were reproduced.** The initial audit made no application changes. Subsequent repairs are recorded below. This audit does not establish that every possible bug has been found.

**Resolved in application 0.7.5.** Comparator 0.6.3 and archived comparison rules remain unchanged. The numbered findings describe the audited 0.7.4 behavior.

## Verification and limits

- Existing checks pass: **194 backend tests, 30 frontend tests, all 37 Chromium workflows, and the production build**.
- Three additional browser probes reproduced the main-comparison navigation/draft loss, stale SnpEff selection, and preserved-source refresh race. These probes asserted the faulty behavior; passing probes mean the defects were reproduced. The temporary test file was removed afterward.
- Backend probes used temporary SQLite databases, captured fixtures, actual FastAPI requests, and offline bundle replay. No user records were changed and no upstream biological services were contacted.
- The timestamp probe used two different, valid time-zone offsets in otherwise replay-valid checks. The synthetic-scope probe reused captured repeat-deletion observations under an input explicitly marked synthetic. The browser probe's second current-source record preserves the same raw source output under a distinct retrieval timestamp/ID. These are controlled validation fixtures, not new live biological observations.
- Other browser engines, live upstream availability, large production datasets, and hosted operation were not tested.

## 1. P1 — A delayed main comparison destroys newer source-form work

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:162), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:168), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:116).

Reproduction:

1. Load the example, then click **Run comparison** and hold its successful POST response.
2. Navigate to **Look up a DNA change**, load a cached source, and enter `My new VCF draft that must survive` in **SnpEff annotated VCF**.
3. Release the earlier main comparison response.
4. Reopen the source screen and load the same cached source.

Observed: the old main comparison forces navigation to its overview and unmounts the source editor. The VCF draft is gone when the source screen is reopened. There is no warning or recovery path for the unsaved source data.

Cause: root navigation does not invalidate a pending main comparison. `showResult` always changes the tab to overview. Its submitted-text check observes only the root investigation draft, not source-panel drafts. The 0.7.4 mount guard protects requests completing from a discarded source screen; it does not protect source work from a request that began in the main comparison flow.

Repair: coordinate navigation, operation intent, and drafts across the workspace. A completed older operation may be saved without taking over a newer screen or destroying its local form state. Cover main comparisons and the analogous root open/demo/import completion paths; only the main-comparison reproduction is confirmed here.

## 2. P2 — An unmounted SnpEff panel can attach its old check to a newer source

Locations: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:140), [SnpEffPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/SnpEffPanel.tsx:35).

Reproduction:

1. Load current source record A and click **Load saved comparison** in its SnpEff panel; hold that GET response.
2. Preserve a second valid capture B of the same raw output, with a different retrieval timestamp and record ID.
3. Change the coordinate field away and back, then click **Load cached**. B is now the latest current capture. The screen says **No SnpEff check is selected for the comparison.**
4. Release A's earlier SnpEff response.
5. Click **Compare** for B.

Observed: the parent suddenly selects A's check, even though B's new SnpEff panel has no displayed result. The comparison returns HTTP 422: **Selected SnpEff check is missing or belongs to a different source record**. A simpler same-record reload also reproduces a cleared selection being restored by a discarded panel.

Cause: SnpEff's request/draft revisions belong to the old child instance. Unmounting it does not invalidate its pending `onCheck` callback. The parent accepts the callback without checking the active source record or child lifetime. The comparison-completion guard added in 0.7.4 does not guard check-selection callbacks.

Repair: invalidate child callbacks on unmount and bind all selected-check callbacks to the current source/operation. Keep the parent selection and the active child result consistent. Apply the same rule to saved, supplied-output, and local-run completions.

## 3. P2 — Bundle replay bypasses the synthetic-input restriction on public allele checks

Locations: [allele_check.py](D:/Creation/GenomeDebugger/backend/app/allele_check.py:123), [allele_check.py](D:/Creation/GenomeDebugger/backend/app/allele_check.py:142), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:189), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:363).

Reproduction:

1. Load the captured repeat-deletion fixture and explicitly mark its investigation input `synthetic: true`.
2. Recompute that investigation and rebuild an allele check from its two captured observations using `replay_allele_check`.
3. Include the rebuilt check in the correctly hashed bundle. Verify/import it, then request the cache-only allele check and text report.

Observed: the rebuilt check reports `agree`. Bundle verification, import, and cache retrieval all return HTTP 200. The synthetic investigation's report includes **Independent reference-backed allele identity**. Calling the live fetch path for a synthetic input correctly rejects it.

Cause: `fetch_allele_check` enforces the synthetic restriction, but the shared replay function does not. Bundle verification and cache validation use replay directly, admitting a combination excluded from the live workflow. The UI normally hides the optional allele checker for synthetic results, but reports and portable records still admit it.

Repair: enforce this scope restriction in the shared reconstruction/validation boundary, consistently during live checking, bundle verification/import/export, and cache use. Do not reinterpret synthetic observations as public reference checks. Preserve stored records rather than silently rewriting them.

## 4. P2 — “Latest” check selection sorts timestamp text instead of actual time

Locations: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:185), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:204), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:215), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:252).

Reproduction:

1. Construct two valid SnpEff checks for one preserved source, with matching IDs and complete, replay-valid bundles:

| Check | Declared time | Actual UTC time | Status |
|---|---|---|---|
| Earlier | `2024-01-01T12:00:00+10:00` | 02:00 UTC | `agree` |
| Later | `2024-01-01T03:00:00+00:00` | 03:00 UTC | `disagree` |

2. Verify and import both bundles. Both operations succeed for both records.
3. GET the source's saved SnpEff comparison.

Observed: the API returns the **earlier agreeing check**, because its timestamp text begins with a larger local hour. It does not return the later disagreeing observation. This probe confirmed the SnpEff path; reference checks, allele checks, source ordering, and current-source caching use the same text-ordering pattern.

Cause: SQL uses `ORDER BY checked_at DESC` / `retrieved_at DESC` on unnormalized timestamp strings. Native captures use UTC, but bundle inputs accept valid offset-bearing timestamps without normalization. Lexicographic ordering of different offsets does not preserve chronological order.

Repair: validate timestamps and maintain a normalized chronological sort value separate from immutable raw provenance. Preserve imported text/IDs/hashes. Define deterministic tie handling and compatibility for legacy invalid dates. Explicit check IDs remain pinned; the defect concerns latest-record lookup and ordering.

## 5. P2 — Refreshing preserved sources overwrites a newer transcript selection

Location: [HistoricalPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/HistoricalPanel.tsx:38).

Reproduction:

1. Load preserved sources and select a source with at least two transcripts.
2. Click **Load preserved sources** again, holding the list response.
3. While the refresh is pending, select the second transcript as Analysis A. The selector remains enabled.
4. Release the list response.

Observed: Analysis A silently resets to the source's first transcript, replacing the user's later selection. The probe confirmed the exact selected transcript before and after response delivery. Subsequent comparison uses the reset selection.

Cause: `list()` always initializes `ids` and `transcripts` after a full refresh and does not consult the selection revision. That revision guards comparison completions, but does not protect the selection from a delayed list response.

Repair: preserve still-valid source/transcript selections during refresh and honor edits made after the request began. Choose defaults only for initial discovery or invalidated selections, with an explicit policy when records disappear.

## 6. P3 — Text reports mislabel non-important metadata as allele representation

Location: [report.py](D:/Creation/GenomeDebugger/backend/app/report.py:43).

Reproduction:

1. Compare matching variants/annotations with the same clinical framework, condition, and classification.
2. Change only the assertion date from `2024-01-01` to `2025-01-01`.
3. Download the text report.

Observed report row:

```text
| clinical.assertion_date | 2024-01-01 | 2025-01-01 | representation only | diff-1 |
```

The engine correctly categorizes this as `clinical_metadata` and marks it non-important by default. The report replaces every `meaningful: false` with **representation only**, even for dates and user-overridden annotation/configuration changes.

Repair: describe the boolean consistently as important/not marked important by comparison rules, or use category-aware wording. Do not call metadata or suppressed output changes allele-representation differences.

## Repair order

1. Protect all workspace drafts from older completions and bind check callbacks to active source records.
2. Apply scope restrictions consistently to offline/public-check reconstruction.
3. Correct chronological selection without changing immutable provenance.
4. Preserve selections during source refresh and correct report wording.

The previously discussed clarity gaps—technical input fields with insufficient explanation and raw JSON in the evidence inspector—remain separate known usability work. They are not counted as newly discovered functional bugs in this report.

## Repair details — application 0.7.5

1. Explicit workspace navigation invalidates pending root operations and clears their UI loading ownership. Main comparisons, examples, saved-record opens, input reads, and bundle imports cannot take over a newer screen. Writes already submitted can still finish saving. Navigation through the sidebar, result tabs, changes shortcut, and evidence links follows the same rule.
2. SnpEff child lifetime guards invalidate pending reads and check completions on unmount. The parent also binds selected-check callbacks to its active source ID and stops accepting old-source callbacks while a new lookup is pending. Saved, supplied-output, and local-run callbacks are covered.
3. Shared allele reconstruction rejects synthetic investigations, so offline bundle replay and cached-check validation enforce the live checker’s restriction. Out-of-scope stored records remain stored. Reports explain why they are excluded, and bundle export returns an actionable conflict instead of presenting them as valid public observations.
4. SQLite derives UTC sort keys from preserved timestamp text when querying sources and checks. Equal instants use insertion order as a deterministic tie-breaker. Original JSON, date text, IDs, and hashes are not rewritten. New records and imported bundles require valid timezone-aware timestamps; existing malformed dates remain readable and sort after valid dates.
5. Preserved-source refresh uses the latest selection, including edits made during the request, and keeps valid source/transcript choices. If a chosen item is absent from the refreshed list, the panel selects an available replacement and displays a review notice.
6. Text report tables now label importance according to comparison rules with yes/no values. Non-important assertion dates and overridden outputs are no longer called allele-representation differences.

Compatibility checks on a temporary read-only-backed-up copy of the user database confirm that all **10 saved comparisons** produce reports and verified bundles, and both pinned baselines pass and save runs. User records were not changed. No push was performed.

Final verification passes **204 backend tests, 34 frontend tests, all 43 Chromium workflows, and the production build**. Coverage includes all four root completion paths, saved/supplied/local SnpEff child lifetimes, source replacement and successful subsequent comparison, refresh edits and missing-selection notices, live/offline synthetic scope, all four timestamp-sorted record types, deterministic ties, malformed legacy dates, invalid new dates, replay-valid offset bundles, and report importance labels.

Test fixtures were updated to use valid changed timestamps for immutable-conflict assertions, explicitly choose historical source pairs after refresh, and search for a saved record that can be beyond the first library page. The final browser run passes without retries. The normal local application was restarted with application 0.7.5.
