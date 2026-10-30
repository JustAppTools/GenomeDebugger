# Local data, imports, and pipeline use

## Explicit tabular format v1

Each CSV/TSV file represents one analysis, with one annotation per row. Import a pair through **Enter results → Import analysis files → Import two annotated CSV/TSV files**. Use `.csv` for commas and `.tsv` for tabs. Standard quoted CSV fields and CRLF/LF line endings are supported; original UTF-8 text is retained.

Required unique headers:

```text
assembly,sequence_id,position,ref,alt,gene_id,transcript_id,consequence,tool,tool_version,source_name,source_release
```

Optional headers: `protein_consequence`, `context_start`, `reference_sequence`. Supply both context fields together or leave both empty. Tool/source metadata must agree across a file. Duplicate annotation keys, conflicting reference contexts, missing metadata, unsupported letters, and ambiguous numeric coordinates are rejected. No row is silently omitted.

Positions must be explicit positive one-based integers; reference/alternate values are uppercase A/C/G/T strings within the existing snapshot limits. No automatic assembly or coordinate conversion occurs. Different submitted variants form separate records; additional-variant matching uses exact assembly/accession/position/alleles, not inferred biological equivalence.

From 0.8.1, variant keys and gene/transcript identifiers determine a consistent row order for the overview. This display anchor does not declare a preferred transcript or an original biological selection. Sorting an otherwise identical file does not select a different transcript. The exact original UTF-8 text, including any BOM and original row order, remains preserved and hashed.

From comparator 0.6.6, complete imported row sets are compared independently of those anchors. Adding a smaller-sorting transcript or variant is a row addition, not an inferred transcript selection. Original filenames up to 255 characters are retained; only the separate display label is shortened to 150 Unicode characters. Readable HTML includes the full represented-row inventory, including unchanged outputs.

Limits: 600 KB per selected file, at most 1,500 annotation rows per file, up to 51 represented variants per analysis, and the existing 1 MB canonical input-data budget/2 MB wire budget. Primary and additional annotation limits still apply. Original file text is part of provenance and therefore contributes to the input budget. A larger pair may need splitting even when each file individually fits its file limit.

For original VEP JSON, use the preserved-output workflow with actual run metadata. For SnpEff ANN VCF, use its source-bound annotation comparison. An arbitrary VCF, CSV, or JSON document is not automatically compatible with the tabular or two-snapshot schemas.

## Pipeline adapter

Start the local application, then from the project root:

```powershell
.\.venv\Scripts\python.exe .\scripts\compare-files.py analysis-a.csv analysis-b.csv --title "Tool release comparison" --output preview.json
```

Review the output, warnings, row counts, and metadata. Add `--save` to create a completed comparison. Existing output files are not overwritten. Use `--url http://127.0.0.1:8765` for the portable workspace; the source backend defaults to port 8000. Only an explicit loopback HTTP origin is accepted.

## Backups and restoration

**Local data** provides a consistent SQLite backup download. A full database backup includes local scientific records, source captures, saved tests/runs, and organization labels. Browser-local drafts are separate and must be deliberately saved/resumed/discarded in that browser.

Stop the source application using **Stop GenomeDebugger.cmd**. From the `backend` directory, restore a backup using the project environment:

```powershell
..\.venv\Scripts\python.exe -m app.manage --db ..\data\investigations.db restore --from-backup "C:\path\to\genomedebugger-backup.db"
```

The command validates a consistent staged copy for SQLite integrity, supported tables/columns, readable typed records, and library/order metadata. Valid legacy copies are migrated in staging. Only after validation does it preserve the existing destination in a distinct before-restore backup and replace it. Invalid copies leave the destination unchanged. The command refuses active journal files and restoration while the normal local service is running. Reopen the app and review the restored records.

Application 0.8.2 also validates original scientific replay, preserved sources/checks, indexed metadata, and baseline/run/check ownership. Supported pre-versioned records use archived original formats. Every 0.8.2 server holds a database-specific OS lock; a different port cannot bypass restore protection. Stop older versions and other database-editing tools before upgrading/restoring. The `.db.lock` file may remain after shutdown; actual ownership is an OS lock, not file presence.

Application 0.8.3 additionally verifies the complete saved-test assertion set against its baseline and candidate, and checks the primary-key/uniqueness/type/nullability constraints used by workspace SQL. Altered verdicts or incomplete assertion sets reject the staged restore. Backup-response cleanup runs on completion and on exceptional transport exits. Draft save/read limits both apply to decoded UTF-8 text; serialized JSON escaping does not make a successfully saved draft unreadable.

For the portable build, stop it from Local data and run:

```powershell
.\GenomeDebugger.exe --restore-backup "C:\path\to\genomedebugger-backup.db"
```

The default portable database lives under `%LOCALAPPDATA%\GenomeDebugger\data`; it is separate from the checkout database. See [desktop-guide.md](desktop-guide.md). Archive/restore in the library organizes individual records without replacing the database. Permanent deletion is a separate operation and has no archive recovery path.

## Scientific boundaries

Original file hashes preserve supplied bytes, not external authenticity. A supplied reference context supports a local text comparison; external reference checking and controlled causal experiments have separate scopes. Identifier resolution previews mappings from the current Ensembl VEP identifier/HGVS endpoints and requires explicit selection of a supported mapping before a new source capture.

Library details edits remain recoverable in memory when switching records or app sections; save before closing/reloading. These unsaved details are separate from explicitly saved browser analysis drafts. Favorite and Archive do not overwrite text fields. Date filtering uses your selected local date's midnight; direct API callers can pass `since_instant` with a timezone, while a date-only `since` uses UTC midnight.

Official endpoint documentation: [VEP identifiers](https://rest.ensembl.org/documentation/info/vep_id_get), [VEP HGVS](https://rest.ensembl.org/documentation/info/vep_hgvs_get).
