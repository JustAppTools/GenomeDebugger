# Bug audit — application 0.7.9 / comparator 0.6.5

Reviewed on **2026-10-24** against the current workspace, including all existing uncommitted repairs.

**Eight additional findings were reproduced.** Application code was left unchanged. This is a bounded audit; it does not establish that every possible defect has been found.

**Repair follow-up:** all eight findings were subsequently addressed in application **0.7.10**. See [repair details and verification](fixes-0.7.10-2026-10-24.md). The observations below describe the audited 0.7.9 state.

## Scope and verification

- Existing checks passed: **307 backend tests, 40 frontend unit tests, and the production build**.
- **All 72 existing Chromium workflows passed in one complete run.** The findings below are additional cases outside those existing assertions.
- Backend reproductions used temporary databases and FastAPI TestClient. Provider cases used the actual Ensembl/NCBI adapters with local HTTP mock transports and constructed responses. No reproduction fetched new live provider data or wrote to the normal application database.
- The execution-provenance probe used the existing captured MANE fixture and temporary bundle storage. It did not change the installed runtime or execute a new biological annotation.
- Three temporary Chromium probes checked supported snapshot-field lengths on a 375-pixel phone, missing/empty protein presentation, and library pagination after concurrent deletion. They asserted the observed behavior for diagnosis; passing a reproduction probe does not mean a bug is fixed. The temporary probe file was removed afterward.
- Negative controls: deeply nested request bodies were rejected with structured 422 responses, and library paging recovered correctly after concurrent deletion of the preceding page. These are not counted as bugs.
- The normal preview was not listening when checked; its saved logs did not establish why it had stopped. It was started again using the existing local startup script, without code changes. Its database SHA-256 was identical before and after startup. This runtime observation is not counted as an application bug without an established cause.

## 1. P2 — Missing NCBI notation data is saved as a disagreement

Location: [ncbi.py](D:/Creation/GenomeDebugger/backend/app/ncbi.py:163).

Reproduction:

1. Preserve a valid source and an agreeing NCBI reference/SPDI/HGVS check.
2. Perform another explicit reference check through the real adapter, using a local mock transport.
3. Return a valid matching reference base and a normal response for one notation endpoint, but return `{"data":{}}` for the other endpoint.
4. Test both the contextual-SPDI endpoint and the HGVS endpoint independently.

Observed:

```text
Missing contextual data: HTTP 200, access=fetched, status=disagree,
                        observed_spdi=null, old agreeing cache not reused
Missing HGVS data:       HTTP 200, access=fetched, status=disagree,
                        observed_hgvs=null, old agreeing cache not reused
```

Cause: the adapter admits an empty `data` object. Reconstruction only reads SPDI when every required field exists and uses `.get('hgvs')` for HGVS. Missing observations remain `None`, which compares unequal to the expected notation and becomes a saved disagreement.

Impact: absent provider data becomes apparently conflicting evidence and replaces the latest cached check. A linked comparison can then report independent allele disagreement despite no contradictory notation having been observed.

Repair: require the expected notation fields and valid values before deriving a verdict. Missing observations should enter the provider-error path, retaining cached-after-error behavior when available. Keep genuine observed disagreement distinct from unavailable data.

## 2. P2 — Edited custom outputs can retain SnpEff agreement against the original VEP output

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:60), [check_scope.py](D:/Creation/GenomeDebugger/backend/app/check_scope.py:39), [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:252).

Reproduction:

1. Preserve a VEP source and a supplied SnpEff ANN result agreeing with all of its transcripts.
2. Create the usual transcript comparison with that check selected.
3. Identify both snapshots as `Custom transformed output` and change their selected consequences to `stop_gained`, retaining their original source citations and annotation-check summary.
4. Save through the investigation API, export a bundle, and verify it.

Observed:

```text
Investigation save:    200
Bundle export:         200
Bundle verification:   200
Changed consequence:   stop_gained
Linked SnpEff status:  agree
```

Cause: custom tools may legitimately cite a source as an input, so direct VEP-output validation returns early. The separate SnpEff applicability check binds variants and source hashes but does not ensure the transformed annotations are the outputs that SnpEff compared.

Impact: the displayed supporting check remains attached to edited outputs it never checked. The guided custom-candidate action already detaches this evidence; JSON submissions, candidate validation, and portable verification still admit it.

Repair: enforce annotation-check applicability at all admission boundaries. Either detach incompatible annotation evidence or represent it explicitly as a check of the original input source, with clear scope in saved records and the UI.

## 3. P2 — Malformed local-execution provenance passes portable verification and import

Locations: [snpeff.py](D:/Creation/GenomeDebugger/backend/app/snpeff.py:31), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:105).

Reproduction: construct a valid source/check bundle from `fixtures/snpeff-mane-public-run.json`, then change only these execution fields and recompute the enclosing entry hash:

```json
{
  "started_at": "not-a-date",
  "elapsed_seconds": -5,
  "command": [],
  "java_sha256": "not-a-hash",
  "jar_sha256": "not-a-hash",
  "config_sha256": "not-a-hash"
}
```

Observed: **verification 200 and import into a fresh temporary database 200**. Preserved input/output hashes remain valid, but impossible timing and invalid artifact fingerprints are accepted as execution provenance.

Cause: these model fields have few structural constraints, and bundle verification checks selected input/output/database relationships without validating the remaining declared fingerprint and timing formats.

Impact: replay-checked records can contain unusable artifact fingerprints and impossible execution metadata. Internal format validation is enforceable even when externally supplied execution provenance remains unauthenticated.

Repair: validate SHA-256 formats, finite nonnegative duration, timezone-aware execution time, and a usable nonempty command record. Apply appropriate compatibility handling to legitimate older captures.

## 4. P2 — A fetched and cached source can exceed the comparison's provenance limit

Locations: [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:160), [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:214), [models.py](D:/Creation/GenomeDebugger/backend/app/models.py:88).

Reproduction: use the actual Ensembl adapter with normal reference/assembly/VEP fixtures and a release response containing `releases: [80, 81, ..., 120]`. Fetch, compare its two valid transcripts, and reload the cache.

Observed:

```text
Fetch and save:        200, 41 release numbers preserved
Transcript comparison:422, Provenance.source_release exceeds 100 characters
Cache-only reload:    200, same unusable capture
```

Cause: release admission verifies a nonempty integer list, while snapshot generation joins the entire list into `reported ...`, producing a 152-character value for a field limited to 100 characters.

Impact: the adapter announces success and preserves a source its own comparison workflow cannot use. Its latest cache entry stays unusable. The expanded response was constructed locally; this audit did not establish that current live Ensembl sends such a list.

Repair: reconcile source admission and snapshot representation limits before caching. Preserve complete metadata while ensuring admitted sources can generate valid provenance, or reject unsupported data through the normal fetch-error/fallback path.

## 5. P2 — Boolean coordinates are silently converted into genomic positions

Location: [models.py](D:/Creation/GenomeDebugger/backend/app/models.py:28).

Reproduction: start from a valid comparison, remove its optional reference contexts and controlled lookup, set both variant positions to JSON `true`, and submit it to `/api/investigations`.

Observed: **200**, with the stored positions changed to integer **1**. The input's invalid coordinate type is silently converted instead of rejected. The source-query position and reference-context start declarations also use coercing integer fields.

Cause: `StrictModel` forbids additional fields but does not make numeric fields strict; Pydantic's integer conversion accepts booleans.

Impact: an input-schema mistake changes a scientific coordinate and becomes a saved comparison. Guided validation already rejects nonnumeric positions, so JSON/API admission has a different policy.

Repair: reject booleans explicitly for coordinate/count fields or use strict integer validation where their contracts require integers. Preserve intentionally supported textual conversion only where it is explicitly part of the API.

## 6. P3 — Analysis cards still overflow phones with accepted field lengths

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:34), [style.css](D:/Creation/GenomeDebugger/frontend/src/style.css:1).

Browser reproduction: save an otherwise valid comparison with one unbroken snapshot field at its supported length, open it at a 375-pixel viewport, and expand **Show technical details**.

Observed document widths:

| Changed field | Accepted length | Document width |
|---|---:|---:|
| Analysis label | 150 | 2,332 px |
| Snapshot ID | 100 | 743 px |
| Source name | 100 | 1,212 px |

Cause: the snapshot heading, identifier row, and source row lack sufficient wrapping/shrinking rules. The earlier saved-baseline repair does not cover these cards.

Impact: supported identifiers or labels make the whole phone page scroll sideways and place content outside the viewport.

Repair: constrain the relevant tracks and children and wrap long values without dropping their accessible full text. Verify analysis cards independently from saved-baseline layouts.

## 7. P3 — A flagged protein change displays the same value on both sides

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:25), [engine.py](D:/Creation/GenomeDebugger/backend/app/engine.py:121).

Reproduction: use otherwise identical snapshots with `protein_consequence: null` in A and `protein_consequence: ""` in B. This can arise when clearing an optional field in the guided form. Save and open **See the changes**.

Observed: the comparator records a meaningful `protein_consequence` difference from null to the empty string. Chromium confirms that both visible cells contain **—**, while the row is counted as an important change.

Cause: the comparator preserves the distinct input values, while `pretty()` collapses null, undefined, and the empty string to the same display text.

Impact: users see an important change with visually identical before/after values and cannot understand what changed from the table.

Repair: define consistent missing-value semantics for optional outputs or render empty text and missing values distinctly. A display-only repair can retain existing comparison semantics.

## 8. P3 — Required names and identifiers accept whitespace-only input through JSON/API

Locations: [models.py](D:/Creation/GenomeDebugger/backend/app/models.py:55), [regression.py](D:/Creation/GenomeDebugger/backend/app/regression.py:23).

Reproduction: submit a valid comparison with its title, gene IDs, and analysis tool names set to three spaces. Then save a regression case with its name set to three spaces.

Observed: both API actions return **200**, preserving the whitespace-only values. Guided validation and the visible baseline form reject the equivalent blank values.

Cause: backend required-text fields mostly enforce character length without checking that any non-whitespace text exists.

Impact: JSON entry bypasses visible required-field checks and can create blank-looking records, unnamed immutable baselines, and missing-looking scientific/provenance identifiers.

Repair: reject whitespace-only required text consistently at API admission, preserving meaningful internal whitespace in valid names and identifiers. Existing saved records should remain inspectable.
