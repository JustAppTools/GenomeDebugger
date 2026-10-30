# Repairs for the 0.7.6 audit

Application **0.7.7**, comparator **0.6.4**, 2026-10-21.

All ten reproduced findings in [the 0.7.6 audit](bug-audit-0.7.6-2026-10-21.md) have been addressed. Earlier uncommitted changes were preserved. Stored comparisons, source artifacts, and baselines were not rewritten.

| Finding | Repair |
|---|---|
| 1. New VCF retains an older AGREE check | File reading has an explicit status and blocks check actions. Both read start and successful replacement invalidate incompatible checks. Manual edits supersede pending reads, and failed reads retain the previous draft. The browser test verifies a real agreeing old check, replaces its VCF, and verifies that only the new disagreeing check is selected and linked. |
| 2. Lookup completion erases newer edits | Lookups capture the shared source-workspace revision and retain the existing capture while pending. A stale completion or failure preserves newer drafts and selections and explains why it did not replace the editor. Query-change guards remain in place. |
| 3. Protein finding links to position evidence | Annotation findings gather evidence for their affected fields and relevant transcript selection. The protein-only regression now links the protein and transcript comparisons, excluding unrelated position differences. |
| 4. Term reordering appears as an effect change | Comparator 0.6.4 compares consequence collections independently of semicolon term order. Original snapshot strings and captured artifacts stay intact. Controlled replay and candidate output assertions use the same semantics, while input drift still records the original edits. |
| 5. Nested Unicode causes HTTP 500 | An iterative Unicode validator checks model input dictionaries, including keys and generic metadata containers. Parsed historical artifacts and upstream adapter JSON are checked before hashing or serialization. Invalid surrogates return a bounded validation error; valid Unicode and emoji round-trip without replacement. |
| 6. Multiple baselines hide earlier histories | Saved tests now include a baseline selector and Refresh baselines action. Discovery includes every result page, switching loads the corresponding case and history, and refresh retains the selected case. Concurrently saved cases remain separately accessible. |
| 7. Concurrent inserts shift library pages | A new investigation-page API returns a continuation anchor and upper browsing bound. Forward and backward navigation reuse these values; deletion refills pages and can return from an emptied last page. Search and Refresh records begin a new browsing session. The original offset list API remains available for existing clients. |
| 8. Initial response removes fresh Recent entries | Initial list results merge with newer local saves, deduplicate IDs, and respect deletion tombstones. A delayed response cannot replace the fresh Recent list wholesale or resurrect locally deleted entries. |
| 9. Old health result overrides a newer one | Health observations carry ordered request revisions. Obsolete requests are aborted, requests have a ten-second timeout, and only the newest live observation updates connection/version state. |
| 10. Malformed runtime configuration crashes inspection | Runtime loading validates the manifest root, genome, paths, version, hashes, database file mapping, and optional source mapping before use. Inspection returns an unconfigured result with an explanation; execution rejects invalid configurations before launching a process. |

## Replay and data compatibility

- The complete 0.6.3 comparator was frozen before changing the current engine. Bundle verification selects those archived rules for declared 0.6.3 results, alongside earlier supported versions.
- Exporting an older result produces a separate current-engine replay with its original record ID identified. Existing stored bytes and result IDs remain unchanged.
- Compatibility was checked against a temporary SQLite backup made through a read-only connection to the normal database: **all 10 saved reports and portable bundles verified**, and **both pinned cases passed** under the current comparator. No compatibility test wrote to the normal database.
- A dedicated archive test imports a 0.6.3 bundle, verifies it, exports its distinct 0.6.4 replay, and confirms that its original saved result remains intact.

## Final verification

- **249 backend tests passed.** New tests cover evidence selection, historical consequence ordering and original artifact retention, candidate semantics and input drift, archived replay, nested invalid/valid Unicode, malformed runtime configuration, and stable library paging with concurrent insertion and anchor deletion.
- **39 frontend tests passed.** Added coverage includes failed-lookup draft retention and baseline discovery beyond the first 100 cases. Existing pagination mocks were updated to the new page API contract.
- **All 54 Chromium workflows passed**, including seven new browser workflows reproducing the original timing/concurrency conditions with correct outcomes. Existing mobile, import/export, deletion/refill, source-selection, and regression workflows still pass.
- **Production build passed**, and Git whitespace checks passed.
- One simultaneous test/build run lost its local browser-test server and produced connection-reset/refused failures. After the other test/build processes completed, the entire browser suite was rerun successfully on its own. No application assertions were relaxed to obtain that result.
- The checked startup script restarted the local backend. Direct backend health and frontend-proxied health both identify this checkout, application 0.7.7, and comparator 0.6.4.

These results cover the reproduced defects and tested workflows. Live upstream biological services and browser engines other than Chromium were not exercised in this repair pass. Changes remain local and unpushed.
