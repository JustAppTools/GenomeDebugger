# Additional bug audit — version 0.6.1

Reviewed on 2026-10-18 at commit `65b92c3`. These seven findings cover failure cases beyond the previous audit. This review does not establish that there are no other defects.

**Resolution:** all seven findings were fixed in version 0.6.2. The reproductions below describe the reviewed 0.6.1 behavior. Verification now passes 123 backend tests, 23 frontend tests, 13 Chromium browser workflows, and the production build. The nine existing saved exports and two pinned regression baselines also passed compatibility checks on a temporary database copy.

Existing verification still passes: **101 backend tests, 21 frontend tests, and nine browser workflows**. Additional reproductions used temporary databases, captured fixtures, and browser request interception. The user's saved records were not changed. No new live upstream scientific observations are claimed. Application code was not changed for this audit.

## 1. P1 — A reference check can remain attached to a different compared allele

Locations: [models.py](D:/Creation/GenomeDebugger/backend/app/models.py:181), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:234).

Reproduction:

1. Preserve the test Ensembl source at chr1:6524705 C>T and its matching NCBI reference/SPDI/HGVS check.
2. Generate a source-linked transcript comparison with that check summary.
3. Label both snapshots as a custom postprocessor and change their alternate allele to G, retaining the source/check references and source hash.
4. Compare, export, and verify the bundle.

Observed: verification succeeds with compared ALT `G`, preserved checked SPDI `NC_000001.11:6524704:C:T`, and check status `agree`. The schema checks the reference base and source hash but not the complete compared variant. Custom transformations legitimately may cite VEP as an input, but a check for that input allele must not silently serve as a check of a changed output allele.

Repair: bind applicable checks to assembly, accession, coordinate, reference, and alternate allele. If checks are retained as input-only observations, label their scope explicitly and keep them out of validation of the transformed variant.

## 2. P1 — A SnpEff reference warning can be skipped while reporting agreement

Location: [snpeff.py](D:/Creation/GenomeDebugger/backend/app/snpeff.py:89).

Reproduction: append a correctly shaped, same-allele non-transcript ANN entry carrying `WARNING_REF_DOES_NOT_MATCH_GENOME` to the otherwise agreeing two-transcript VCF test fixture. The parser skips non-transcript entries before examining their warning/error field.

Observed: status remains `agree` despite the explicit reference warning. This uses constructed input to exercise the parser, not a claim that the captured real run contained such a warning.

Repair: inspect warnings/errors for every ANN entry before filtering feature types; determine whether a serious record-level warning invalidates the comparison.

## 3. P2 — Changing the selected primary variant creates false missing-row differences

Location: [engine.py](D:/Creation/GenomeDebugger/backend/app/engine.py:133).

Reproduction: build two snapshots containing exactly the same pair of variants and annotations. In A, make variant 1 primary and variant 2 additional. In B, promote variant 2 to primary and retain variant 1 as additional.

Observed: the engine reports two `variant_records[...].presence` differences, even though neither variant is absent from either complete snapshot. Primary focus differences may be useful, but they should not be represented as missing variants.

Repair: match complete variant collections, including each primary variant, while reporting changes to primary selection separately.

## 4. P2 — Saved-record requests can overwrite the latest selection

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:118), [InvestigationLibrary.tsx](D:/Creation/GenomeDebugger/frontend/src/InvestigationLibrary.tsx:34).

Browser reproduction: open saved record A from the library and hold its response. Open B, allow B to display, then release A's earlier response.

Observed: A replaces B as the displayed investigation. The library's Open buttons allow overlapping requests and `openInvestigation` has no request identity/cancellation check. This is a separate workflow from the comparison-draft and public-query races covered by the previous fixes.

Repair: associate open/import actions with a current selection revision, cancel obsolete loads, or serialize the controls. Only the latest requested selection should update the workspace.

## 5. P2 — Investigation deletion leaves its allele-check data behind

Location: [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:228).

Reproduction: save an investigation with an investigation-bound `AlleleCheck`, delete the investigation through the API, and inspect `allele_checks` in the temporary database.

Observed: deletion returns HTTP 200 and removes the investigation, but its allele-check row remains, including preserved variant/reference observations. The row is no longer accessible through the ordinary investigation workflow and continues to consume storage.

Repair: remove investigation-owned allele checks in the same deletion transaction. Preserve independently shared source records according to their separate retention policy.

## 6. P2 — Impossible normalized coordinates can pass an independent allele check

Location: [allele_check.py](D:/Creation/GenomeDebugger/backend/app/allele_check.py:91).

Reproduction: use the captured repeat-deletion observations, replacing both contextual SPDI positions with `1000000000000`, far beyond the pinned chromosome length. Replay the observations and verify their exported bundle.

Observed: both the check and the verified bundle retain status `agree` with normalized position `1000000000000`. The parser checks the accession and a nonnegative coordinate, but does not ensure the normalized allele interval lies inside that accession. This is a simulated malformed upstream/cached response, not a genuine NCBI result.

Repair: validate normalized positions and deletion intervals against the pinned sequence length before comparing contextual alleles. Invalid service data should not produce agreement.

## 7. P3 — The default regression name can be invalid for a valid investigation

Location: [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:10).

Reproduction: open an investigation with a valid 200-character title, enter Regression, and save without changing the automatically generated test name.

Observed: the default `Regression: ` prefix produces a 212-character name. The controlled input's HTML maximum does not truncate its initial value, the save button stays enabled, and the API rejects it with HTTP 422. The UI displays only `Unable to save regression case (422)`.

Repair: generate a name within the API limit and validate it before submission. Surface field-specific API errors if submission still fails.

## Repair order

First address check applicability and parser warnings, then collection matching and record-selection ordering, then deletion cleanup and normalized-coordinate bounds, followed by the regression-name boundary. Add regression coverage for these specific reproductions.

## Repair verification — 0.6.2

| Finding | Implemented repair and regression coverage |
| --- | --- |
| 1 | Full primary-variant binding for NCBI and SnpEff checks in generic comparisons, regression candidates, and bundle verification; pinned aliases remain valid and transformed outputs can remove inapplicable checks. |
| 2 | Warnings/errors inspected before ANN feature filtering; otherwise agreeing records with non-transcript warnings return HTTP 422. |
| 3 | Primary variants included when matching distinct-focus collections; promotion has no false presence differences, genuine omissions remain detectable, and annotation drift remains variant scoped. |
| 4 | Selection revisions guard opens, errors, imports, and comparisons. Browser tests hold an older successful/failed open or import until after a newer record is displayed. |
| 5 | Owned allele checks deleted in the investigation transaction; rollback, pinned protection, and shared-source retention tested. No existing orphan checks were present in the user's database. |
| 6 | Normalized interval checked against pinned chromosome length before comparison; malformed observations fail replay and bundle APIs. Sequence-end insertion and deletion boundaries covered. |
| 7 | Bounded Unicode-aware default name, pre-submit validation, and detailed API validation errors; browser test saves a 200-character-title baseline on the first attempt. |

Frozen 0.6.1 comparison rules preserve replay of valid archived results; exporting an older record creates a separate current-engine replay. New applicability and malformed-observation guards reject unsafe evidence regardless of the declared archived engine version.
