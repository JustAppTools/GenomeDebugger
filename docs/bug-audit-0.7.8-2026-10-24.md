# Bug audit — application 0.7.8 / comparator 0.6.5

Reviewed on **2026-10-24** against the current workspace, including the existing uncommitted repairs.

**Eight additional findings were reproduced.** Application code was left unchanged. This is a bounded audit, not a claim that every possible defect has been found.

**Repair follow-up:** all eight findings were subsequently addressed in application **0.7.9**. See [repair details and verification](fixes-0.7.9-2026-10-24.md). The observations below describe the audited 0.7.8 state.

## Scope and verification

- Existing checks passed: **283 backend tests, 39 frontend unit tests, and the production build**.
- All **65 existing Chromium workflows passed across two fresh-server groups**: 34 in shard 1 and 31 in shard 2. This is distinct from a clean combined-suite run; the combined-run service failures are documented below.
- Four additional Chromium probes reproduced the source-reload check mismatch, lost test-name edits, long-name layout overflow, and automatic third-party font request. These probes asserted the defective behavior; their passing results confirm reproduction, not a repair. Their temporary files were removed afterward.
- Backend reproductions used FastAPI TestClient and temporary databases. Captured/constructed provider responses were delivered through local HTTP mock transports. No probe wrote to the normal application database or fetched new Ensembl/NCBI data.
- The runner probes used temporary pinned-artifact fixtures and a controlled Python child process emitting known bytes through the actual subprocess capture options. They did not run a new biological SnpEff annotation or change the installed runtime.
- The font probe intercepted and blocked external requests before transmission. It observed a request initiated by the original page markup, without clicking any Fetch or Check action.
- Browser verification encountered test-service exits during combined runs. Further verification and limits are recorded at the end. Those infrastructure symptoms are not counted among the eight application findings without an established cause.

## 1. P2 — Contradictory assembly metadata in a source record still passes bundle verification

Location: [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:46).

Reproduction:

1. Start with a valid current-source fixture whose VEP response declares `assembly_name: GRCh38`.
2. Change the enclosing source record's `assembly_name` to `GRCh37`, retaining its original assembly accession and captured response.
3. Generate its transcript comparison, construct a bundle with the correct entry hashes, and submit it to verification and import.

Observed:

```text
Bundle verification:             200
Bundle import:                   200
Cache-only lookup:               200
Cached source assembly_name:     GRCh37
Preserved VEP assembly_name:      GRCh38
Comparison variant assembly:     GRCh38
```

Cause: source verification checks the assembly in the captured response, but does not reconcile it with the source envelope's `assembly_name`. That name is also absent from the source ID calculation. Snapshot conversion continues to generate GRCh38 variants, so the newer snapshot-to-source configuration checks do not detect this contradiction inside the source itself.

Impact: internally inconsistent assembly claims can be imported into the current-source cache while passing replay checks. This is an internal consistency failure; it does not depend on authenticating the original supplier.

Repair: validate the supported source envelope against its captured response and assembly metadata before accepting it into a bundle or cache. Keep invalid new records separate from compatibility handling for legitimate older records.

## 2. P2 — Reloading a source drops the displayed SnpEff check from the comparison

Locations: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:89), [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:152).

Browser reproduction:

1. Load a preserved source capture and a valid saved SnpEff comparison.
2. Confirm that **AGREE** is displayed and that the parent panel identifies the check as selected for the comparison.
3. Click **Load cached** again, returning the same source record ID.
4. Run the transcript comparison.

Observed: **AGREE** and the old check ID remain displayed in the SnpEff result panel. The parent now says no SnpEff check is selected. The actual saved comparison contains `annotation_check: null`.

Cause: successful lookup clears the parent's `annotationCheck`, but the child component is keyed only by the unchanged record ID. Its own `check` state survives and continues to display the earlier result.

Impact: the visible supporting result and the evidence included in the new comparison diverge. The parent notice exposes the exclusion, but the persistent check result is not marked as an unselected historical result.

Repair: coordinate the child's displayed check with the parent's selected check when reloading the same capture. Either retain the compatible selection or clearly reset/deselect the displayed result while preserving unrelated drafts.

## 3. P2 — Local execution hashes altered stdout rather than the bytes emitted by the child

Locations: [snpeff_runner.py](D:/Creation/GenomeDebugger/backend/app/snpeff_runner.py:108), [snpeff_runner.py](D:/Creation/GenomeDebugger/backend/app/snpeff_runner.py:124).

Two controlled subprocess reproductions emitted a valid matching ANN row plus a comment:

- With CRLF line endings, the saved text contained LF endings and its declared output hash differed from SHA-256 of the emitted bytes.
- With byte `0xFF` in the comment, the saved text contained the replacement character `U+FFFD`; the declared output hash again differed from the emitted-byte hash.

Both resulting checks returned `agree`. The probe's matching annotation terms were unchanged; it demonstrated loss of the original output representation and fingerprint, not a contradictory biological consequence verdict.

Cause: capture uses `text=True` with `errors='replace'`. Decoding/newline conversion happens before hashing. `execution.output_vcf_sha256` then copies the hash of this changed text, and the original stdout bytes are unavailable.

Impact: an execution record cannot reproduce the fingerprint of the output actually emitted by the process. Invalid encoding is silently repaired even though file imports now reject malformed UTF-8.

Repair: capture stdout as bytes, hash the original byte stream, and decode with an explicit strict policy. Preserve any intentional normalized representation separately from the executed-output fingerprint. Retain versioned compatibility for existing execution records.

## 4. P2 — Deeply nested JSON causes server errors and bypasses source fallback

Locations: [historical.py](D:/Creation/GenomeDebugger/backend/app/historical.py:44), [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:120).

Reproductions:

- Add an ignored extension containing 1,100 nested arrays to a valid historical VEP artifact. The resulting **2,633-byte** artifact returns **500 Internal Server Error** on import.
- Deliver the same nested extension in an Ensembl response through a local mock transport while a valid source is cached. Live lookup returns **500**, while a subsequent cache-only lookup returns **200**.

Cause: the JSON decoder raises `RecursionError` before the iterative value validator can run. Historical import and the provider adapter handle `ValueError` but do not convert this parser failure into their normal validation/provider error paths.

Impact: a small unsupported artifact produces an unstructured server error instead of a useful rejection. A malformed provider response also bypasses the available cached-after-error behavior.

Repair: handle decoder depth failures explicitly, bound supported nesting, and return a structured validation or provider error. Preserve the existing fallback for failed live retrievals.

## 5. P2 — Read-only pages and health fail while a slow save holds a write lock

Location: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:62).

Reproduction in an initialized temporary database:

1. Start a normal investigation POST and hold it after its write transaction begins, before insertion.
2. Confirm that a separate ordinary SQLite SELECT can still read the existing investigation.
3. Request health and an investigation page concurrently, holding the save beyond the SQLite lock timeout.
4. Release the save.

Observed:

```text
Independent read of existing data: succeeds
GET /api/health:                    503
GET /api/investigations/page:       500
Released POST /api/investigations:  200
Subsequent health request:          200
```

Cause: every storage read calls `initialize()`, which now starts `BEGIN IMMEDIATE` even when schema version 2 is already installed. Consequently, read operations attempt to obtain another write reservation instead of using the readable committed snapshot.

Impact: a sufficiently slow concurrent save makes saved-record pages fail and the UI report an unavailable engine, even while existing data remains readable. The reproduction deliberately delayed a save; it does not establish that ordinary small saves normally last long enough to trigger the timeout.

Repair: perform migrations under a write lock only when needed. Fully initialized reads should not require a write reservation. Retain transactional migration safety and write quota enforcement.

## 6. P3 — Initial page load contradicts the stated external-request policy

Locations: [index.html](D:/Creation/GenomeDebugger/frontend/index.html:1), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:269).

Browser reproduction: intercept non-local requests, load the home page, and perform no Fetch or Check action.

Observed: the page initiates this external stylesheet request, which the audit probe blocked:

```text
https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap
```

At the same time, the sidebar says: **External requests only when you click Fetch or Check.**

Cause: the initial HTML includes Google Fonts stylesheet and preconnect links independently of the explicit provider actions.

Impact: the displayed network-behavior promise is inaccurate. The observed request contains font-family parameters; this probe did not demonstrate transmission of genomic input.

Repair: serve fonts locally or use system fonts to satisfy the stated policy. Any retained automatic third-party traffic should be described accurately.

## 7. P3 — A test-name edit made during saving disappears

Locations: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:89), [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:184).

Browser reproduction:

1. Enter **Original submitted name** and save a new baseline.
2. Hold the successful response after the API has created the baseline.
3. The name field remains enabled. Change it to **Newer name typed while saving**.
4. Release the response.

Observed: the input disappears, the immutable case displays the original name, and the newer text is no longer accessible. No notice explains that the edit was not saved.

Cause: successful saving unconditionally replaces the creation form with the saved case, without locking the submitted name or tracking a newer name revision.

Impact: text accepted by an enabled field is silently discarded. This is separate from the already repaired discovery-versus-save race.

Repair: lock the immutable submission's name while saving, or retain the newer draft with an explicit explanation and supported next action.

## 8. P3 — A valid long test name breaks the phone layout

Locations: [style.css](D:/Creation/GenomeDebugger/frontend/src/style.css:3), [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:184).

Browser reproduction: save a baseline named with 200 consecutive `N` characters, open its investigation at a **375-pixel viewport**, and switch to Saved tests.

Observed:

```text
Overview document width: 375 px
Saved-tests document width: 1,964 px
Case record width: 1,898 px
```

The name is accepted by the documented 200-character limit. The width problem appears after the saved baseline is displayed, rather than while entering it.

Cause: `.case-record strong` has no word-breaking rule, and the surrounding grid permits its intrinsic minimum width to expand the panel.

Impact: valid names can push controls outside the phone viewport and require extensive horizontal scrolling. The earlier checks of ordinary short baseline names do not cover this case.

Repair: allow long names to wrap and constrain the affected grid items/columns to the available width. Preserve the complete name in accessible text.

## Browser-suite verification notes

The four targeted reproductions passed, and all **13 existing `workflow.spec.ts` tests passed** in a fresh isolated run. Two longer combined runs had test-service failures: one stopped after 48 passing workflows without a complete failure trace, and another reached 57 passes before a missing-option assertion followed by `ERR_CONNECTION_REFUSED` at the local Vite endpoint. A Windows helper launch also returned process initialization error `0xC0000142` during the earlier run. Their common cause has not been established.

The combined run is therefore not recorded as a clean pass. Subsequent runs passed **34/34 tests in shard 1** and **31/31 tests in shard 2**, covering all 65 existing workflows with fresh test services between groups. No application code or test assertions were changed to address these infrastructure symptoms. The cause of the combined-run service exits remains a separate investigation.
