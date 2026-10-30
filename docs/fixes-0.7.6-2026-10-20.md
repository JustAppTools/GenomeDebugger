# Repairs for the 0.7.5 audit

Application **0.7.6**, comparator **0.6.3**, 2026-10-20.

All eleven findings in [the audit](bug-audit-0.7.5-2026-10-20.md) have been addressed. Existing uncommitted work was preserved; comparator behavior and stored record formats were not revised.

| Finding | Repair |
|---|---|
| 1. Unrelated process restart / false readiness | Both ports are checked before any termination or launch. Backend ownership requires an explicit project module directory, or a project launcher plus matching project identity. New launches specify the module directory. Backend health and frontend HTML carry a matching checkout fingerprint; HTTP 200 alone is insufficient. Unknown ownership produces a port-conflict error. |
| 2. Sibling source forms lose newer drafts | A shared source-workspace revision covers edits, file selections, and interactions in both forms. Older completions remain saved without replacing newer work. Existing transcript-selection guards retain their specific notices. |
| 3. Malformed UTF-8 becomes substituted data | Main JSON, portable bundles, and annotated VCF use fatal UTF-8 decoding. Invalid JSON/bundles are rejected before submission or draft replacement; invalid VCF keeps the previous draft. Optional UTF-8 BOM is consumed for these text inputs. Historical artifacts retain their existing fatal decoding with BOM preservation for original-byte hashing. |
| 4. SnpEff declaration ID collision | New observation IDs include the complete submitted declaration and timestamp. Frozen-clock tests vary software version, database name, and database hash. Existing IDs remain replayable without rewriting their contents. |
| 5. Missing database backup/check succeeds | Both CLI commands require an existing source and return actionable errors. Source connections use SQLite read-only mode; backups do not migrate the source. Destination creation is exclusive, and connections close explicitly. |
| 6. Reports endorse invalid legacy allele evidence | A shared validator reconstructs and compares saved checks for reports, offline cache access, and export. Reports mark invalid evidence unavailable; exports reject it. Original stored bytes remain intact. Valid older exports can still rebind evidence to the current comparator replay after original-check validation. |
| 7. Dangling or wrong evidence links pass pinned tests | Every run checks reference integrity and unique evidence IDs. Pinned runs additionally compare identity, difference, and finding evidence relationships. Description-only wording changes remain exempt. |
| 8. Refresh loses older-page source selections | Selected records outside the first refreshed page are retrieved independently, with 404 distinguished from transient failure. Valid transcript choices remain selected. Server page offsets are tracked independently of retained rows, and appended pages are deduplicated. |
| 9. Report Markdown injection | Submitted headings, labels, provenance, conclusions, and table values are flattened and escaped as literal text. Code values use safe code contexts. Generated section headings remain separate from submitted content. |
| 10. Concurrent runs duplicate history | History uses a case-bound `before` run anchor, unaffected by newer inserts. The UI deduplicates appended and newly created entries. Existing offset clients remain supported. |
| 11. Search treats literal characters as wildcards | Ordinary substring searches escape percent, underscore, and backslash before parameterized SQLite LIKE matching. |

## Verification

- Final results: **227 backend tests, 37 frontend tests, all 47 Chromium workflows, and the production build passed**. The startup script also passed against the running local app after restart.
- Backend regression tests include missing-source CLI failures, untouched legacy backups, frozen-clock SnpEff declarations and legacy replay, invalid/out-of-scope stored evidence, report formatting injection, evidence-link fault injection, cursor paging under concurrent inserts, literal searches, and fully mocked Windows ownership/readiness checks. The mocks include an unrelated application using this project's venv.
- Frontend unit tests cover older-page selection retention, server offsets independent of retained rows, unique history entries and stable anchors, UTF-8 rejection, and BOM policy.
- Chromium tests exercise both directions of sibling-form draft preservation, historical uploads and metadata, malformed JSON/bundle rejection before posting, and VCF draft retention, alongside the existing desktop/mobile workflows.
- Compatibility checks used a SQLite backup made through a read-only source connection into a temporary database: all **10 saved comparison reports and portable bundles verified**, and **both pinned cases passed**. No compatibility test wrote to the original database.
- The local backend was restarted through the checked startup script. Backend and frontend-proxied health identify this checkout and application 0.7.6.

The completed checks do not establish that every possible bug has been found. Live upstream biological services and additional browser engines were not exercised in this repair pass. The earlier audit's disclosed residual temporary files were not touched.
