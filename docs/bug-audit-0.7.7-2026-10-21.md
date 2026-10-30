# Current bug audit — application 0.7.7 / comparator 0.6.4

Reviewed on **2026-10-21** against the current workspace, including the uncommitted changes on top of commit `b085e08290dc52bf8610d3c588d037a78b3de359`.

**13 current findings were reproduced: eight P2 issues and five P3 issues.** Some expose remaining paths in previously repaired areas. Application code was not changed. This audit does not establish that every possible defect has been found.

**Repair follow-up:** all thirteen findings were addressed in application 0.7.8 / comparator 0.6.5; see [repairs and verification](fixes-0.7.8-2026-10-23.md). The findings below describe the audited 0.7.7 state.

## Verification and scope

- Existing checks passed: **249 backend tests, 39 frontend unit tests, all 54 Chromium workflows, and the production build**. The browser suite ran after the other suites completed.
- Four additional Chromium reproductions demonstrated unwanted comparison cancellation, an export error on a different screen, a blocked guided candidate workflow, and inconsistent Unicode name limits. A fifth exploratory browser check found no document overflow at a 375-pixel viewport in the source, overview, saved baseline, saved run, and library screens. The transcript table scrolls within its container; that was not counted as a defect.
- The temporary browser probes asserted defective behavior. Their passing results confirm the reproductions, rather than successful repairs. The temporary probe file was removed after inspection.
- Backend probes used FastAPI TestClient, the actual comparison/storage/import/bundle code, and temporary databases. Provider responses were supplied through local HTTP mock transports; no live Ensembl or NCBI requests were made.
- The quota probe filled a separate temporary database using the same storage routine used by API writes. An exact low-level reinsert was used only in that temporary database to demonstrate SQLite cell reuse after the API rejected the write. It was not a change to the application or its quota policy.
- No probe wrote to the normal application database or changed the installed SnpEff runtime. Existing uncommitted project changes were preserved. No fixes or pushes were performed. Other browser engines, live provider availability, and deployment were outside this pass.

## 1. P2 — Source-derived metadata can contradict the preserved source and still verify

Location: [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:227).

Reproduction:

1. Preserve a valid current Ensembl fixture and generate its two transcript snapshots.
2. Keep their original VEP tool, source record ID, response hash, variants, and annotations.
3. Change `configuration.assembly_accession` from `GCA_000001405.29` to `GCA_000001405.14`, and set `configuration.retrieved_at` to `1999-01-01T00:00:00Z`.
4. Submit the investigation and export its bundle.

Observed: both operations return **200**, retaining the contradictory configuration. The preserved source still carries its original assembly accession and capture time.

A second reproduction used a historical source whose preserved artifact declared generation in 2024. Its snapshots were changed to declare generation in 1999 and an all-zero artifact hash. Saving, exporting, and explicitly verifying that bundle all returned **200**.

Cause: `validate_source_snapshot` checks primary outputs and selected provenance attributes, but does not validate the recognized source-derived configuration values against the record from which they were generated.

Impact: the audit record can contain incompatible assembly, date, and artifact-hash claims while passing the product's internal consistency check. This concerns consistency between supplied records, independently of the stated limitation that imported provenance is not externally authenticated.

Repair: validate recognized derived configuration fields against their preserved source. Retain explicit compatibility rules for omitted legacy fields and distinguish genuine custom transformations.

## 2. P2 — Consequence normalization suppresses unrelated configuration changes

Locations: [engine.py](D:/Creation/GenomeDebugger/backend/app/engine.py:97), [regression.py](D:/Creation/GenomeDebugger/backend/app/regression.py:72).

Reproduction: compare otherwise identical snapshots whose configuration differs only as follows:

```json
{"consequence": "high;moderate;low"}
{"consequence": "low;moderate;high"}
```

Observed: `/api/investigations` returns **200** with **no differences and no findings**.

Cause: the new unordered consequence-term comparison applies to every field named `consequence` or ending in `.consequence`. The generated field `configuration.consequence` therefore receives annotation semantics. Configuration values are arbitrary strings and can encode an ordered setting. The regression difference normalizer uses the same broad suffix test.

Impact: a real analysis-setting change can be silently hidden. The term-order repair should apply to annotation consequence collections, not unrelated configuration strings.

Repair: select normalization by the actual annotation field/category. Preserve exact comparison of arbitrary configuration values and cover both comparison and regression assertions. Comparator changes require the project's versioned replay compatibility handling.

## 3. P2 — An additional-annotation finding still opens unrelated position evidence

Location: [engine.py](D:/Creation/GenomeDebugger/backend/app/engine.py:246).

Reproduction:

1. Use the demonstration's equivalent padded/unpadded substitution descriptions and remove its controlled lookup.
2. Give both snapshots the same primary annotation and provenance.
3. Add the same additional transcript to both snapshots, changing only that row's protein consequence.

Observed:

```text
position                                      non-important  diff-1
ref                                           non-important  diff-2
alt                                           non-important  diff-3
annotations[GENE-DEMO-1|TX-EXTRA||].protein_consequence
                                              important      diff-4

finding.affected_fields: [additional protein consequence]
finding.evidence_ids:    [diff-1]
```

The finding's only evidence opens the coordinate comparison, although it explains the additional protein change. The relevant evidence exists as `diff-4`.

Cause: the generic unexplained-change finding still takes the first difference's evidence, including differences excluded from its own affected-field list. The 0.7.7 primary-annotation repair does not cover this fallback.

Impact: users following the finding are directed to evidence for a different change. A valid evidence ID alone does not establish a correct relationship.

Repair: derive fallback evidence from the affected differences, including additional annotation and variant rows.

## 4. P2 — Numeric metadata can turn into null during import and prevent bundle export

Location: [historical.py](D:/Creation/GenomeDebugger/backend/app/historical.py:44).

Reproduction: add `"extension":1e400` to an otherwise usable historical VEP JSON artifact. Preserve it, compare its two transcripts, and export the resulting bundle.

Observed:

```text
Historical import:                 200
Returned source_response.extension: null
Transcript comparison:             200
Bundle export:                     409
Historical source does not match its preserved artifact and provenance
```

The original artifact text still contains `1e400`. A separate probe using the nonstandard JSON token `NaN` produced the same outcome.

Cause: Python's JSON parser can produce non-finite floats from these inputs. The Unicode validator does not reject them, and Pydantic serializes the parsed non-finite value as `null`. The stored parsed record then disagrees with reconstruction from the retained original text.

Impact: import reports success and comparisons can be saved, but their supporting data has changed and their portable bundle cannot be exported.

Repair: reject unsupported/non-finite numeric values before saving, with a useful validation response, or preserve a lossless numeric representation consistently through parsing, hashing, storage, and replay.

## 5. P2 — Historical import accepts transcript sets the comparison model cannot use

Locations: [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:46), [historical.py](D:/Creation/GenomeDebugger/backend/app/historical.py:38).

Two reproductions:

- An artifact with **1,002 unique transcript rows**, totaling **89,316 bytes**, imports with **200**. Comparing two of its transcripts returns **422** because a snapshot would contain 1,001 additional annotations, exceeding the 1,000-row limit.
- An artifact containing a **101-character transcript ID** also imports with **200**. Comparison then returns **422** because the annotation model permits at most 100 characters.

Cause: `parse_transcripts` validates row shape, nonempty values, and uniqueness, but not all downstream annotation and collection limits. Import saves the source before its usability as a supported snapshot has been established.

Impact: the interface accepts and lists an artifact as preserved, then cannot perform its advertised comparison. The row-count reproduction is well below the file size limit.

Repair: validate downstream limits during admission and explain unsupported source sizes/fields before saving. Preserve complete-set semantics; silently dropping excess rows would create a different scientific defect.

## 6. P2 — The guided candidate editor cannot submit changed public-source outputs

Locations: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:140), [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:163).

Browser reproduction:

1. Compare two transcripts from a valid preserved Ensembl capture.
2. Save/open its regression baseline.
3. Change Analysis A's consequence through the visible candidate field.
4. Click **Check candidate**.

Observed: the request returns **422**, instructing the user to restore the source output or identify transformed output as a custom tool. The visible candidate form has no field or mode for making that required provenance change.

Cause: the editor changes the annotation while retaining the original direct-VEP provenance and source claims. The API correctly rejects that contradiction. The guided workflow does not produce a valid request for the task it offers.

Impact: users following the form's instruction to edit outputs cannot complete this workflow for a public-source comparison without understanding and editing advanced JSON.

Repair: provide an explicit supported candidate workflow, such as selecting a newer preserved source or declaring a custom transformed output with suitable provenance. Keep the API's source-consistency protection.

## 7. P2 — A malformed NCBI response bypasses cached fallback and causes HTTP 500

Locations: [ncbi.py](D:/Creation/GenomeDebugger/backend/app/ncbi.py:108), [ncbi.py](D:/Creation/GenomeDebugger/backend/app/ncbi.py:192), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:254).

Reproduction:

1. Save a valid NCBI reference check for a valid preserved source.
2. Fetch another check using the actual provider adapter with local mock HTTP responses.
3. Include an escaped lone Unicode surrogate in an otherwise irrelevant extension of the HGVS response.

Observed: the live-check route returns **500 Internal Server Error**. A subsequent cache-only request returns **200** with the valid earlier check.

Cause: unlike the Ensembl JSON boundary, NCBI JSON handling does not validate Unicode before constructing the check. A model validation error escapes `fetch_reference_check`; the route's fallback catches `ReferenceCheckError`, not this error.

Impact: a malformed upstream response produces a server error and bypasses the available cached-after-error workflow. The cached record remains intact.

Repair: validate provider responses at their boundary and convert malformed-data failures into the provider's structured error type so the existing fallback can run. Keep raw invalid text out of error serialization.

## 8. P2 — Deleting a record may not recover usable capacity at the database limit

Location: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:38).

Reproduction in a temporary database with the supported 10 MB limit:

1. Save small valid comparisons until the database reaches its limit. The probe stored 4,897 records.
2. Delete an interior comparison whose SQLite page also contains another record.
3. Submit exactly the deleted comparison again.

Observed:

```text
Delete:             200
Resubmit:           507 Local database size limit reached
Before deletion:    2,560 pages, 0 freelist pages, 10,485,760 used bytes
After deletion:     2,560 pages, 0 freelist pages, 10,485,760 used bytes
```

An exact low-level reinsert in that temporary database succeeded with the **same 2,560 pages and the same used-byte count**. The record's serialized payload was 1,861 bytes.

Cause: the preflight budget counts allocated non-freelist pages, then adds the incoming JSON size. It does not account for reusable free cells within allocated pages. It rejects the write before the later actual-allocation check can establish that it fits.

Impact: the application tells users to delete records to recover capacity, but can reject an exact replacement despite enough space having been freed. Whole-page reclamation tests do not cover this case.

Repair: enforce the quota using actual transactional allocations, or account for reusable page cells in the preflight estimate. Retain the atomic post-insertion allocation check and rollback behavior.

## 9. P3 — Clicking a heading prevents a pending comparison from opening

Location: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:131).

Browser reproduction: start a current-source comparison, hold its successful response, click the **Choose two transcripts** heading without editing anything, then release the response.

Observed: the screen reports that the source workspace changed and retains the source form. The completed comparison is saved, but its results do not open.

Cause: the shared source container increments its draft revision on every captured click, including clicks on headings, static text, and other controls that do not change a draft.

Impact: an ordinary click while waiting can prevent a successful operation from showing its result. The new draft-protection mechanism interprets an interaction as an edit even when all submitted values remain unchanged.

Repair: advance the shared revision for actual draft, file, selection, or check changes. Preserve the guards that protect genuine newer work.

## 10. P3 — Reused SQLite row IDs admit new records into an older browsing snapshot

Location: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:287).

Reproduction:

1. Save four investigations and request a two-item page. Its `ceiling` is 4, and it contains records 3 and 2.
2. Delete the newest investigation from another client.
3. Save a new investigation.
4. Request the first page again using the original `ceiling=4`.

Observed: the old browsing snapshot now contains the newly saved investigation followed by record 2.

Cause: the upper browsing bound is SQLite's `MAX(rowid)`, but this table does not prevent row-ID reuse after deleting the maximum row. The new investigation receives a value inside the old bound.

Impact: backward navigation can admit a comparison saved after the browsing session began, even though the caller retains the original snapshot bound. The simpler concurrent-insert case fixed in 0.7.7 still works; deletion followed by reuse exposes this separate case.

Repair: use a persistent sequence that remains monotonic after deletion, or another stable creation cursor with equivalent guarantees, while preserving existing record IDs.

## 11. P3 — An old export error appears on a different workspace screen

Location: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:202).

Browser reproduction: start **Text report** export, hold its response, navigate to **Look up a DNA change**, and then complete the export request with an error.

Observed: the new source screen acquires the root **Report unavailable** alert, although no action on that screen requested a report.

Cause: export completion/error handling does not use the navigation revision checks applied to comparison, opening, and import operations.

Impact: late feedback from an earlier screen pollutes the current workspace and can replace its more relevant root feedback. The reproduction confirmed the misplaced text-report error; it did not establish incorrect downloaded file contents.

Repair: scope export feedback to its originating request/workspace, or present it as clearly identified background-export feedback.

## 12. P3 — Case matching is inconsistent for non-ASCII investigation titles

Locations: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:274), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:287).

Reproduction: save `Café export` and `CAFÉ export`, then query the library API with `q=café`.

Observed: only **Café export** is returned. The equivalent ASCII case changes match, but the uppercase accented letter does not.

Cause: the search relies on SQLite's default `LIKE` case behavior, which does not provide general Unicode case folding.

Impact: users searching titles containing accented or other non-ASCII case pairs can miss saved comparisons. Literal wildcard escaping works and should remain intact.

Repair: apply an explicit Unicode case-folding policy consistently to search input and indexed/stored searchable text.

## 13. P3 — The test-name field silently limits supplementary Unicode characters to 100

Location: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:160).

Browser reproduction: enter a name consisting of 110 emoji characters through normal sequential typing. Submit the same 110-character name directly to the regression-case API for comparison.

Observed: the browser retains only **100 characters**; the API accepts and preserves all **110**. The UI gives no explanation for the shorter limit.

Cause: HTML `maxLength=200` counts UTF-16 code units, while `validName`, default-name truncation, and the backend count Unicode characters. Each tested emoji occupies two UTF-16 units.

Impact: a valid name within the advertised model limit cannot be entered completely through the normal field. The corrected default-name generator does not address manual typing.

Repair: enforce the same Unicode character-count policy in the input handler and backend, without splitting a surrogate pair or silently applying a different limit.

## Suggested repair order

1. Protect source consistency and comparison correctness: findings 1–3.
2. Reject unusable/corrupted imports and restore valid user workflows: findings 4–8.
3. Tighten browser interaction, paging, and text behavior: findings 9–13.

The fixes should add regression coverage for these specific reproductions. Existing passing checks are useful gates, but currently do not exercise the failures above.
