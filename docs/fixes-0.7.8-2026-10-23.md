# Repairs for the 0.7.7 audit

Application **0.7.8**, comparator **0.6.5**, 2026-10-23.

All thirteen reproduced findings in [the 0.7.7 audit](bug-audit-0.7.7-2026-10-21.md) have been addressed. Earlier uncommitted changes were preserved.

| Finding | Repair |
|---|---|
| 1. Contradictory source-derived metadata verifies | Direct VEP snapshots validate supplied assembly, capture time, artifact hash, and generation time against the preserved record. Missing legacy duplicates remain supported. Explicit custom outputs can cite a source as an input. Reimporting a historical artifact returns its actual preserved capture time. Tests cover API saves, candidate runs, bundle verification/import, both source origins, and compatibility. |
| 2. Configuration changes disappear | Unordered term comparison is restricted to annotation fields in the comparator and regression difference assertions. Arbitrary configuration strings remain exact, including keys ending in `.consequence`. |
| 3. Additional-output findings link unrelated evidence | The fallback finding derives affected fields and evidence from the same differences. Important changes take precedence; if all differences are non-important, the links still describe the listed fields. |
| 4. Numeric import data changes and prevents export | All parsed model/provider/artifact JSON rejects non-finite numbers before serialization. Valid finite metadata and original artifacts remain intact. Browser bundle download and import preserve original JSON text, avoiding changes to large integers and values such as `1.0`. |
| 5. Imported transcripts cannot be compared | Transcript admission enforces the snapshot's total-row limit and validates each converted annotation against its actual model. The 1,001-transcript boundary remains usable and exportable; excessive rows, identifiers, and joined consequence values are rejected before storage. |
| 6. Guided candidates send prohibited source claims | Preserved VEP candidate fields explain their origin and offer an explicit custom-output action. The candidate keeps the source citation and reference evidence, identifies its own tool/version, and detaches SnpEff evidence against the original output. Changed outputs reach saved regression assertions instead of failing source-consistency validation. The baseline is unchanged. |
| 7. Malformed NCBI data causes HTTP 500 | Provider JSON is validated before constructing a check. Malformed data becomes `ReferenceCheckError`, allowing cached-after-error fallback or a structured upstream error when no cache exists. |
| 8. Freed cells cannot be reused at quota | The preflight checks existing allocation without adding serialized input length. The post-insertion check enforces actual allocation inside the same transaction, retaining atomic rollback. A real full-database test deletes and replaces a record without allocating new pages. Existing concurrent quota and growth rollback tests still pass. |
| 9. Static clicks discard completed results | Draft revisions advance for actual changes rather than every click. Explicit selection/example/check changes and asynchronous historical file commits still protect newer work. Harmless heading clicks allow comparisons and lookups to finish. |
| 10. Deleted maximum row IDs are reused | Schema version 2 adds a persistent autoincrement creation sequence. Migration preserves existing order, IDs, timestamps, and result JSON. Paging uses this sequence, which is not reused after deletion or emptying the library. |
| 11. Old export errors appear on a new screen | Export feedback checks its request, navigation, and draft revisions. A requested download may finish in the background, while obsolete errors and replay notices do not replace current workspace feedback. |
| 12. Accented case searches miss records | Both library APIs use Unicode case folding while preserving literal wildcard escaping. Tests include accented case pairs, `Straße`/`STRASSE`, pagination, and literal `%`/`_` searches. |
| 13. Names are limited by UTF-16 units | Test names use the existing Unicode character-count validation with a visible 200-character counter, without the conflicting HTML code-unit cap. Long Unicode search input uses the same character policy as its API. Browser typing tests confirm full supplementary-character input. |

## Data and replay compatibility

- Comparator 0.6.4 was frozen before changing comparison behavior. Its valid bundles still verify with their original rules, alongside earlier supported versions. A current portable replay uses a new 0.6.5 ID and identifies its original saved record.
- A dedicated test imports a 0.6.4 result with the formerly hidden configuration difference, verifies it under its original rules, exports a corrected current replay, and confirms the original remains intact.
- Compatibility was checked using a temporary SQLite backup made through a read-only source connection. **All 10 existing reports and portable bundles verified, and both existing pinned cases passed** under the current comparator.
- That copy migrated from schema 1 to 2. Every investigation's serialized result remained byte-for-byte identical. Existing version 0/1 databases with noncontiguous row IDs are also covered by migration tests, including deletion and an emptied library.
- Source and check records remain immutable. Newly enforced consistency checks reject contradictory new submissions rather than rewriting saved artifacts.
- Before restarting the normal app, its database was backed up to `data/backups/investigations-before-0.7.8-2026-10-23.db`. After the live schema migration, all 10 original serialized results still matched that backup exactly and SQLite integrity was `ok`.

## Verification

- **283 backend tests passed**, including 34 new cases covering the audit findings, supported boundaries, invalid inputs, compatibility, and actual storage behavior.
- **39 frontend unit tests passed.**
- **All 65 Chromium workflows passed**, including 11 new browser checks for the reported interactions, custom candidate provenance, Unicode typing/search, deletion-safe snapshots, asynchronous file commits, export feedback, and numeric bundle download/import.
- **Production build passed.**
- Git whitespace checks passed with the repository's Windows line-ending policy.
- The first full browser run exposed an overlap with an older Unicode fixture; the new search probe was isolated by its unique title prefix. A further transfer probe reproduced numeric rounding/type changes during browser bundle serialization, then passed after original JSON text was retained for download and import. No application assertions were relaxed to obtain the final passing suite.
- The local frontend and direct/proxied health checks identify this checkout, application **0.7.8**, and comparator **0.6.5**. The site responds at **http://127.0.0.1:5173/**.
- Provider behavior was tested through preserved fixtures and local HTTP mock transports. This repair did not perform new live Ensembl/NCBI annotation or reference fetches, or a new live SnpEff execution.
