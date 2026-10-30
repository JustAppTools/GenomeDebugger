# Current bug audit — application 0.7.2 / comparator 0.6.3

Reviewed on **2026-10-20**. The reviewed state includes the existing, uncommitted 0.7.2 repairs on top of commit `b085e08290dc52bf8610d3c588d037a78b3de359`; it is not the older committed 0.7.1 tree.

**Eight findings were confirmed in the audit.** This review does not prove that all possible defects have been found. The initial audit made no application changes; the subsequent repairs are recorded below.

**Resolved in application 0.7.3:** the eight findings below describe the audited 0.7.2 behavior. Comparator engine 0.6.3 and archived comparison rules are unchanged. Repair details and verification are recorded at the end of this report.

## Verification and limits

- Existing checks pass: **150 backend tests, 27 frontend tests, all 25 Chromium workflows, and the production build**.
- Six additional browser probes reproduced the hidden cached check, saved-case discovery race, two source-file import races, deletion/pagination omission, and oversized reopened input. These probes asserted the faulty behavior; passing probes mean the defects were reproduced. The temporary probe file was removed afterward.
- Backend probes used temporary SQLite databases, captured fixtures, mocked service responses, and actual FastAPI requests. They confirmed source-origin mislabeling, duplicate annotation loss, request-size expansion, and mitochondrial scope validation failures. Constructed observations are validation fixtures, not claims about real biological findings or live service output.
- All **10 existing investigation bundles** verify on a read-only backup copied to a temporary database. Both existing pinned regression baselines pass on that copy. User records were not added, edited, or deleted.
- The normal backend at `http://127.0.0.1:8000/api/health` was not reachable (`ConnectError`) during the audit. Browser tests ran against the isolated Playwright servers on ports 5174/8001 using the current workspace code. The normal development services were not restarted.
- Live upstream service availability, other browser engines, and full production deployment were not tested.

## 1. P1 — Current and historical source data can be mislabeled in reports

Locations: [report.py](D:/Creation/GenomeDebugger/backend/app/report.py:9), [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:222), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:36), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:211).

Reproduction:

1. Preserve a current Ensembl source and generate a direct VEP transcript comparison.
2. Set `provenance.configuration.source_origin` to `historical_artifact` in both snapshots, leaving the real source record and direct VEP tool identity unchanged.
3. Create the investigation, request its report, export its bundle, and verify the bundle.
4. Repeat with a genuinely imported historical fixture, removing `source_origin` from both snapshots instead.

Observed in both directions:

| Actual preserved source origin | Report classification | Create / export / verify |
|---|---|---|
| `current_api` | `PRESERVED HISTORICAL OUTPUT (declared provenance)` | 200 / 200 / 200 |
| `historical_artifact` | `CURRENT PUBLIC SOURCE` | 200 / 200 / 200 |

The report also selects its current-versus-historical caveats from the editable flag. Actual source records retain their correct origin, so the accepted bundle contains contradictory provenance.

Cause: direct-source validation checks outputs and several provenance fields but does not reconcile the reserved origin flag with the preserved source. Report classification trusts that duplicate flag.

Repair: derive source classification from preserved source records, validate contradictory reserved metadata at API and bundle boundaries, and describe mixed current/historical comparisons explicitly. Missing legacy fields need a defined compatibility rule; declaring metadata does not authenticate historical artifacts.

## 2. P2 — Duplicate SnpEff ANN fields silently discard an earlier reference warning

Location: [snpeff.py](D:/Creation/GenomeDebugger/backend/app/snpeff.py:79).

Reproduction:

1. Take the matching two-transcript VCF fixture.
2. Make its INFO column contain two `ANN=` entries separated by a semicolon.
3. Put a conflicting annotation with `WARNING_REF_DOES_NOT_MATCH_GENOME` in the first entry and the matching, warning-free annotations in the second.
4. Submit the SnpEff comparison and export/verify a comparison bundle linked to it.

Observed: the API returns **HTTP 200 with `status: agree`**, and the bundle verifies. The warning remains visible in the preserved VCF text but never reaches the comparison's warning check. Submitting the first ANN entry alone correctly rejects it with `SnpEff ANN reports a warning or error`.

Cause: converting INFO tags directly to a dictionary silently overwrites the first ANN value with the second. The guard added for warnings on individual ANN rows only sees the surviving value.

Repair: reject duplicate ANN tags as ambiguous input, or implement an explicit parsing policy that processes every annotation and warning. Bundle replay must enforce the same rule.

## 3. P2 — A valid saved input can become too large to rerun

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:91), [models.py](D:/Creation/GenomeDebugger/backend/app/models.py:45), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:127), [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:12).

Reproduction:

1. Start with the demo input, remove the controlled lookup, and add 1,000 annotation rows to each snapshot. Each added row has gene `G`, a unique `T{index}` transcript, and a 420-character consequence. Omit optional null fields.
2. POST the compact input. The measured request is **952,995 bytes**, within the 1,000,000-byte input limit.
3. Retrieve the saved result and POST its returned `input` unchanged, or use it as a regression candidate.
4. In the browser, reopen the saved comparison and click **Run comparison**.

Observed: initial creation succeeds with HTTP 200. The normalized saved input is **1,039,218 bytes** because model serialization adds optional/defaulted fields. Unchanged resubmission and candidate checking return **HTTP 413**. The browser reproduces `Input exceeds 1 MB limit` when rerunning its own reopened comparison. Bundle export and verification still succeed.

Cause: admission limits apply to the compact submitted representation, while saved records and editor initialization use an expanded representation. The saved-record and candidate workflows cannot submit some inputs the server has already accepted.

Repair: establish a round-trip size contract for accepted inputs. Possible implementations include a server-side replay endpoint for saved records plus a compatible candidate limit/serialization strategy. Preserve bounded request handling and the existing 32 MB bundle boundary; merely accepting the initial input does not guarantee it can be rerun.

## 4. P2 — Comparisons silently attach a cached check the source screen says is absent

Locations: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:100), [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:135), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:254).

Reproduction:

1. Preserve a current Ensembl source and a disagreeing NCBI reference check for it.
2. Open **Look up a DNA change** and click **Load cached**. Do not click **Load saved check**.
3. Confirm the screen says **No NCBI check is currently linked.**
4. Click **Compare** and inspect the actual comparison response.

Observed: the response includes the cached disagreeing `reference_check` and sets identity to `unresolved`, despite the screen explicitly saying no check is linked.

Cause: the UI keeps its own initially empty check state, while the request sends only transcript selectors. The backend independently attaches the latest saved NCBI and SnpEff checks. The displayed evidence selection is not bound to the submitted comparison.

Repair: load and disclose the checks that will be used, or submit explicit check selections and validate them server-side. Keep the result bound to the evidence shown to the user, including when another request saves a newer check.

## 5. P2 — Existing-case discovery can replace a newly saved test

Locations: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:24), [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:36).

Reproduction:

1. Open an investigation that already has a saved case named `Existing baseline`.
2. Hold the discovery workflow's request for that case's run history.
3. While discovery is pending, the UI still exposes the enabled **Save regression case** action. Save a case named `New baseline requested`.
4. Confirm the new name is displayed, then release the earlier discovery response.

Observed: the active case changes back to `Existing baseline`. Both cases exist in storage, but the newer user-selected case is replaced in the panel by the older discovery result. Subsequent runs target the older case and its history.

Cause: initial discovery is not represented as loading state and is not invalidated when the user saves a new case. Its `live` flag only guards component unmounting.

Repair: coordinate discovery and creation with an operation revision, or prevent creation until discovery finishes and explicitly support choosing among multiple saved cases if that is intended.

## 6. P2 — Historical and SnpEff file imports still allow older reads to overwrite newer selections

Locations: [HistoricalPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/HistoricalPanel.tsx:27), [SnpEffPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/SnpEffPanel.tsx:38).

Two browser probes confirmed the remaining source-file paths are affected:

- **SnpEff:** hold the earlier file's `File.text()` completion; select a second file and confirm its contents appear in **SnpEff annotated VCF**; release the first read. The textarea changes back to the older contents without notice.
- **Historical VEP:** hold the earlier file's `File.arrayBuffer()` completion; select a second valid same-variant artifact and enter metadata intended for it; release the first read and click **Preserve historical output**. The actual POST contains the earlier artifact bytes paired with the newer metadata, and preservation succeeds.

The historical probe used distinct `audit_marker` values to distinguish the two valid JSON artifacts. The SnpEff probe exercised the file loader, not an external annotation run.

Cause: neither source-file reader tracks request order or intervening edits. The 0.7.2 draft-preservation fix covers the main input editor but was not applied to these separate readers.

Repair: apply request and draft revisions to both readers, including read failures. Preserve the latest selection and prevent metadata from being silently paired with a superseded artifact.

## 7. P2 — Unsupported mitochondrial input passes the nuclear-only check boundary

Locations: [allele_check.py](D:/Creation/GenomeDebugger/backend/app/allele_check.py:65), [allele_check.py](D:/Creation/GenomeDebugger/backend/app/allele_check.py:109), [scientific-validity.md](D:/Creation/GenomeDebugger/docs/scientific-validity.md:22).

The documented scope excludes mitochondrial HGVS and limits this check to primary nuclear sequences. Nevertheless, `_target` accepts `NC_012920.1`/`MT` because it searches the entire pinned chromosome manifest without excluding the mitochondrial entry.

Reproduction with constructed responses:

1. Compare two non-synthetic, manually supplied `NC_012920.1` substitutions.
2. Call the independent checker with a mocked matching FASTA, matching contextual SPDI, and HGVS using the mitochondrial `m.` prefix.
3. Repeat with a constructed response using the `g.` prefix instead.

Observed: the first case makes three requests before failing with **NCBI HGVS accession does not match the pinned sequence**, despite its matching accession. The second case returns **`agree`**, can be saved, and its bundle verifies. The nuclear-only boundary therefore neither rejects the unsupported target up front nor prevents an out-of-scope check from verifying.

The distinction between mitochondrial `m.` and linear-genomic `g.` reference types is specified by the [official HGVS reference-sequence recommendations](https://hgvs-nomenclature.org/stable/background/refseq/#reference-sequence-types). These probes establish a scope/validation defect; they do not claim genuine NCBI output used the wrong prefix.

Repair: reject mitochondrial targets before creating a client or making requests, consistently during fetching and offline replay. Supporting mitochondrial normalization would require an explicit, separately validated scope expansion.

## 8. P2 — Deleting from a full library page skips a remaining record

Locations: [InvestigationLibrary.tsx](D:/Creation/GenomeDebugger/frontend/src/InvestigationLibrary.tsx:25), [InvestigationLibrary.tsx](D:/Creation/GenomeDebugger/frontend/src/InvestigationLibrary.tsx:33).

Reproduction:

1. Create 101 unpinned investigations matching one search and open the first library page, which displays 100.
2. Delete a record on the first page.
3. Click the still-enabled **Next records** button.

Observed: page one has only 99 displayed rows after deletion. The remaining record originally at position 101 is not brought forward. Next advances the offset to 100 and shows **No saved investigations match this search**, although the API confirms 100 matching investigations remain. The oldest remaining row is skipped until the list is refreshed or navigation back causes a refetch.

Cause: deletion filters the current array locally without refreshing the page or `hasMore`. The fixed offset advances past the unseen record that shifted into the previous page.

Repair: refetch the current page and continuation state after deletion, adjusting the offset when the last page becomes empty. Preserve request freshness when deletion crosses a pending list request.

## Other current limitations, separate from these eight bugs

The previously discussed usability problems remain: the evidence inspector exposes JSON by default, and the guided form expects technical fields without explaining each field's source. Blank input also supplies placeholder variant coordinates and alleles. These were not redesigned during this audit and are not counted as newly discovered functional defects.

## Suggested repair order

1. Source-origin consistency and duplicate annotation parsing.
2. Bind displayed checks to comparison requests; preserve source-file selections and active saved tests.
3. Make accepted inputs rerunnable within a defined size contract.
4. Enforce the documented nuclear-only check scope and repair deletion pagination.

## Repair verification — application 0.7.3

All eight findings have been repaired:

1. Reports classify origins from preserved source records, including mixed current/historical inputs. Contradictory source-origin flags are rejected during creation and bundle verification. Missing legacy flags remain supported; reports without preserved sources identify provenance as unavailable.
2. Duplicate SnpEff INFO tags are rejected before annotation parsing, so an earlier warning cannot be overwritten. Imported checks and bundle replay use the same parser.
3. Comparison data retains a 1 MB budget, measured with optional defaults excluded. A bounded 2 MB request/import envelope accommodates normalized defaults and candidate wrapping. Generic inputs, source-generated comparisons, candidates, and bundles enforce the same data budget. Reopened default-expanded inputs now rerun and pass unchanged candidate checks.
4. Browser requests explicitly send the displayed NCBI/SnpEff check IDs or null to exclude them. IDs are validated against the selected source and remain pinned when newer checks are saved. Legacy API clients may omit selectors to retain latest-check behavior.
5. Saved-case discovery disables creation until it finishes, preventing a delayed discovery response from replacing a competing user-created case.
6. Historical and SnpEff file reads track selection revisions. Old completions and failures cannot overwrite the latest file. Manual VCF edits also supersede pending reads, and edited SnpEff drafts clear selected checks and invalidate pending check results.
7. Mitochondrial targets are rejected before client creation or requests, during bundle replay, and when loading old cached checks. Cached allele checks are replayed before being returned. Existing stored data is preserved.
8. Successful deletion invalidates pending list responses and refreshes both rows and continuation state. An emptied final page returns to the previous page.

Verification passes **162 backend tests, 30 frontend tests, all 32 Chromium workflows, and the production build**. Focused tests cover both source origins and mixed reports, duplicate ANN ordering, expanded-input reruns/candidates and over-budget rejection, explicit/omitted/wrong-source check selection, mitochondrial fetch/replay/cache boundaries, baseline discovery, source-file races including failures, stale selected checks, library request/deletion races, page refills, and empty final pages.

The browser harness was corrected to use an explicitly uncached query for its empty-cache test and release all development-mode duplicate discovery requests. The final full browser run passes without retries.

Compatibility was checked through the API on a temporary, read-only-backed-up copy of the user database: all **10 saved comparisons** produce reports and verified bundles, and both pinned baselines pass and save their new run records on the copy. User records were not changed. Existing 0.7.2 repairs and other user work were preserved. No push was performed.
