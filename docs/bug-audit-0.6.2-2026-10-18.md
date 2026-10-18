# Current bug audit — version 0.6.2

Reviewed on 2026-10-18 at commit `29079714847bc8b5d5896b678fc3572b441f047f`.

Six defects were reproduced beyond the previous audit. These findings do not establish that the project has no other defects. Application code was not changed during this review.

**Resolved in 0.6.3:** all six findings below describe the reviewed 0.6.2 behavior. Verification after repair passes 138 backend tests, 24 frontend tests, all 16 Chromium workflows, and the production build. All 10 currently saved investigation exports and both pinned regression baselines pass compatibility checks on a temporary database copy.

## Verification and scope

- Existing suites: **123 backend tests, 23 frontend tests, and all 13 existing Chromium workflows pass**. The production build also passes.
- Additional probes confirmed four backend defects and three browser reproductions covering the remaining two findings. The three final browser probes completed successfully and demonstrated the defects described below.
- Backend probes used temporary SQLite databases, mocked upstream responses, and captured fixtures. Browser probes used the isolated Playwright servers/database, intercepted lookups, and delayed actual comparison responses. No user investigations were added, changed, or deleted.
- Constructed malformed data and provenance changes are validation probes, not claims about genuine NCBI, Ensembl, or SnpEff output. No new live scientific observations are claimed.

## 1. P1 — Supplied SnpEff output can be labeled as recorded local execution

Locations: [engine.py](D:/Creation/GenomeDebugger/backend/app/engine.py:86), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:33), [report.py](D:/Creation/GenomeDebugger/backend/app/report.py:60), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:113).

Reproduction:

1. Preserve a source and an ordinary user-supplied SnpEff ANN check; its `execution` field is null.
2. Generate a transcript comparison linked to that check.
3. Set `provenance.configuration.annotation_check_origin` to `local_execution` in both snapshots.
4. POST the input to `/api/investigations`, export its bundle, and verify the bundle.

Observed: creation, export, and verification all return HTTP 200. The linked check still has `execution: null`. Nevertheless, evidence states that a preserved local SnpEff run has execution artifacts recorded in the check, and Markdown identifies it as “recorded local execution.”

Cause: evidence/report wording trusts editable configuration. Generic comparison validation and bundle verification validate the check but do not reconcile that origin flag with the actual execution record.

Repair: derive execution origin from the preserved check and reject contradictory provenance. Imported execution data remains user supplied and unauthenticated even when internally consistent.

## 2. P2 — Malformed transcript rows are silently omitted from declared complete sets

Locations: [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:129), [historical.py](D:/Creation/GenomeDebugger/backend/app/historical.py:56), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:89).

Reproduction: append `{"transcript_id":"LOST_TRANSCRIPT","consequence_terms":["stop_gained"]}` to an otherwise valid VEP response containing two transcripts; the added row lacks `gene_id`. Exercise both the current adapter through a mocked HTTP response and the historical importer.

Observed: the preserved response has three rows, but only two become usable transcript records. Neither adapter reports the omitted row. Historical comparison snapshots declare `source_annotation_scope: all_transcripts`, and their exported bundle verifies successfully despite the omission.

Cause: rows missing required fields are skipped before validation. Bundle verification repeats the same filtering rather than detecting incompleteness.

Repair: fail malformed transcript rows explicitly, or represent partial ingestion with rejected-row evidence and a partial scope. A silently filtered set must not be labeled complete.

## 3. P2 — The comparison API saves direct VEP claims that cannot be exported

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:263), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:42).

Reproduction: preserve a source, generate its direct VEP comparison input, and change one primary consequence to `stop_gained` while retaining the direct VEP tool name and source linkage. POST the edited input, then request its bundle.

Observed: comparison creation returns HTTP 200 and saves the investigation. Bundle export then returns HTTP 409: `VEP snapshot does not match its preserved source variant and annotation`.

This can occur when editing source-derived outputs in Snapshot JSON or the guide without also changing the tool identity. The same consistency rule is enforced at export but omitted when the saved record is created.

Repair: validate source-linked direct VEP claims before persistence, with a useful error explaining the changed annotation/provenance. Explicit custom postprocessor outputs can continue to cite a source as an input.

## 4. P2 — A running allele check can recreate owned data after deletion

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:287), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:149), [storage.py](D:/Creation/GenomeDebugger/backend/app/storage.py:228).

Reproduction:

1. Start `/api/investigations/{id}/allele-check` in fetch mode and hold the upstream check after the investigation has been loaded.
2. Delete that investigation through the API.
3. Release the check response.

Observed: deletion returns HTTP 200. The older check request subsequently returns HTTP 200 and inserts an `allele_checks` row for the now nonexistent investigation. A direct database query confirms one owned check row remains while the parent is absent.

The sequential deletion cleanup from 0.6.2 works; this failure happens when the external request crosses the deletion transaction.

Repair: enforce parent existence inside the same transaction that saves owned checks. Coordinate deletion with in-flight persistence so a late response cannot restore orphan observations.

## 5. P2 — Changing transcripts during comparison silently loses the newer selection

Locations: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:98), [HistoricalPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/HistoricalPanel.tsx:43).

Browser reproduction, confirmed separately in both source workflows:

1. Choose two transcripts and click Compare.
2. Hold the comparison response after the backend finishes.
3. Change analysis A to a different transcript; the selector is still enabled.
4. Release the earlier response.

Observed: the workspace opens the earlier result, replaces the input with its old selection, and displays no stale-result warning. In the public-source probe, A changed from `ENST00000377705` to `ENST00000377740`, but the resulting input contained `ENST00000377705`. In the preserved-source probe, the newer `ENST00000675812` selection was similarly discarded.

Cause: public-source request revisions track coordinate/query changes but not transcript changes. Historical comparisons have no selection revision. The root workspace selection guard does not cover either in-panel edit.

Repair: include all comparison selectors in request freshness checks and preserve the newer selection, or disable relevant selectors while submitting. If older results are displayed, clearly mark them as stale.

## 6. P3 — Guided text limits disagree with API limits for Unicode

Location: [GuidedInput.tsx](D:/Creation/GenomeDebugger/frontend/src/GuidedInput.tsx:90).

Browser reproduction: submit a valid demo with a title consisting of 150 DNA emoji characters. The API accepts it with HTTP 200. Paste the same input into Snapshot JSON and switch to Guided form.

Observed: guided mode reports `Title exceeds 200 characters` and disables comparison. JavaScript counts the string as 300 UTF-16 code units; the API correctly accepts its 150 Unicode code points. Other guided text fields use the same length helper. The Unicode-aware regression-name fix does not cover this validator.

Repair: apply consistent Unicode character counts to frontend text limits and verify boundary cases against the backend schema.

## Suggested repair order

Correct execution provenance and incomplete-source handling first, then validate source claims before saving. Address the deletion race and both transcript-selection races next, followed by Unicode validation consistency. Add regression coverage for these reproductions; the currently passing suites do not exercise these failure conditions.

## Repair verification — 0.6.3

1. Origin contradictions fail comparison creation and bundle verification. Valid supplied/local checks and legacy missing origin flags remain supported. Reports derive execution provenance from preserved records, and comparator evidence no longer trusts origin flags.
2. A shared strict transcript parser rejects missing IDs/genes/terms, empty or invalid terms, invalid row types, and duplicate IDs. Existing malformed source records cannot generate new complete-set snapshots.
3. Direct VEP output/provenance consistency is checked before saving a source-linked generic comparison or running its candidate. Explicit custom postprocessor results remain exportable.
4. Atomic owned-check saves require the parent investigation and matching input hash, including during bundle import. The held-response deletion reproduction now returns HTTP 404 with no investigation or owned check left behind.
5. Browser tests hold actual comparison responses, change transcripts, then release the responses. Both panels retain the newer selection, display a retry notice, and successfully compare that newer selection on retry. Source selectors in the preserved-source panel use the same revision guard.
6. Guided text validation uses Unicode code points. Unit tests cover title and gene-ID boundaries; the browser accepts and compares the previously rejected 150-emoji title.

Valid 0.6.2 archives retain frozen comparison rules. New engine results use separate IDs; exported older records are replayed under the current engine. The new evidence-consistency checks reject contradictory or malformed observations in bundles regardless of their engine version.
