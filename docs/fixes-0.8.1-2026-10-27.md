# GenomeDebugger 0.8.1 — fixes for the 0.8.0 audit

Application 0.8.1, comparator 0.6.5, SQLite schema 3. October 27, 2026.

All twelve findings in [the 0.8.0 audit](bug-audit-0.8.0-2026-10-27.md) are addressed. Existing scientific records, comparator replay rules, and the database schema version are preserved.

Previously saved CSV comparisons keep their immutable original inputs/results. Reimport the actual files to create a new comparison with corrected ordering and byte provenance. A BOM that an earlier import discarded cannot be reconstructed reliably from that saved text.

| Audit finding | Resulting behavior |
| --- | --- |
| 1. CSV row order invents a selection | Variants and annotations use a consistent identifier order before constructing snapshot display anchors. Reordering identical rows creates no scientific annotation changes or transcript-selection finding. Original file order/text remains preserved. The preview and result explain that the overview anchor is not a preferred transcript or a declared biological selection. |
| 2. Original BOM bytes lost | Browser CSV/TSV import explicitly preserves a UTF-8 BOM. Only the parser's working copy strips it; original text and SHA-256 retain the uploaded bytes, matching the CLI path. |
| 3. Invalid backup replaces a workspace | Restore copies the backup to a separate staged database, checks integrity and supported schema/columns, migrates that copy if needed, validates readable typed records and organization/order metadata, and only then backs up/replaces the destination. Invalid copies cannot replace the live database. Health rejects a version-3 database with missing/incompatible tables. Valid legacy backups remain supported. |
| 4. Pending save discards newer notes | Name, notes, and tag fields are disabled during the save. Failed/conflicting saves leave the editor and user text intact and editable. |
| 5. Stale flag action overwrites notes | Archive/Favorite requests contain only their changed flag; the backend atomically merges supplied fields. Full detail edits include the loaded label fingerprint. If another tab changed the details, the API returns 409 and retains both the saved data and the user's editor text. |
| 6. Generated Unicode cursor is rejected | Cursors use compact UTF-8 JSON and omit the name for date/order sorts. Name cursors retain valid Unicode, with consistent incoming/outgoing bounds; default 50-record page transitions work for maximum-length Unicode titles. Older valid cursors remain accepted. |
| 7. Filename truncation creates invalid text | Generated import titles truncate complete Unicode characters rather than UTF-16 code units. Valid supplementary characters are not split. |
| 8. Home draft offer goes stale | Saving/discarding updates the parent recovery offer immediately. Storage events also synchronize availability and draft tools when another tab changes the saved copy. Resuming does not falsely claim that the saved copy was discarded. |
| 9. Example guide describes missing evidence | Guides derive their text from each example's actual reference context, annotation values, lookup, and recorded replay. Matching/missing-evidence cases explicitly say no lookup was provided or replayed. |
| 10. Recent loses a renamed record | Re-comparison keeps cached name/date metadata while refreshing the exact saved label record. Fresh archive state is respected; delayed metadata responses cannot override newer library actions. |
| 11. Readable evidence omits its verdict | Input evidence displays the fields accompanying A/B values, including the additional-variant status and case-specific explanation, without opening JSON. |
| 12. Paging integer overflows SQLite | Query and decoded cursor numbers are bounded to SQLite's signed integer range. Invalid values return 422 before a database query. |

## Verification

- Full backend suite: **405 passed**, including 19 new regressions for ordering, byte preservation, invalid/legacy restoration, label merge/conflict behavior, complete Unicode pages, and numeric rejection.
- Full frontend unit suite: **56 passed** across 12 files, including 12 regressions converted/expanded from the diagnostic probes.
- TypeScript/Vite production compilation passes.
- Full browser suite: **101 passed** (94 Chromium, including core axe checks, and 7 WebKit). Seven new browser scenarios cover the actual import/download, draft recovery, two-tab metadata, conflict, Recent, teaching, and evidence workflows. Desktop package checks are recorded in [PROGRESS.md](../PROGRESS.md).
- Portable 0.8.1 ZIP generation, archive integrity, SHA-256, and equality of bundled/production UI assets pass. No development database, local logs, or `.env` are included. Frozen-executable launch remains unverified.
- Source desktop launcher: compiled UI, synthetic comparison saving, consistent database download, and owned-server shutdown pass against isolated data.
- All **11 development scientific records** were compared with the pre-update backup after restart and remained byte-for-byte unchanged. A consistent copy of the existing workspace also passed the new restore validator, including its saved tests, runs, and source records.

No live genetic identifier/source requests or external transmissions were used for verification. Database tests use isolated files. Invalid-restore tests assert that the destination bytes stay unchanged and no false successful restore or before-restore copy is reported.

The original diagnostic commands now run the corrected regression assertions:

```powershell
.\.venv\Scripts\python.exe scripts\audit080-probes.py
```

From `frontend`:

```powershell
node .\node_modules\vitest\vitest.mjs run --config audit080.vitest.config.ts
```

Windows executable launch and Firefox remain subject to the previously documented host/approval limitations. Generating a portable ZIP or passing the source launcher test is not a claim that the frozen executable has been launched successfully.
