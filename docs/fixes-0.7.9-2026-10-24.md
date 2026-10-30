# Repairs for the 0.7.8 audit

Application **0.7.9**, comparator **0.6.5**, 2026-10-24.

All eight reproduced findings in [the 0.7.8 audit](bug-audit-0.7.8-2026-10-24.md) have been addressed. Earlier uncommitted work was preserved. Comparison rules and database schema version 2 remain unchanged.

| Finding | Repair and regression coverage |
|---|---|
| 1. Contradictory source assembly metadata | Source admission, conversion, cache use, and portable verification require GRCh38 or a GRCh38 patch name, a versioned GenBank/RefSeq assembly accession, and a preserved VEP response reporting GRCh38. Tests reject contradictory bundles atomically, accept supported patch names, reject inconsistent legacy cache entries without rewriting them, and exercise live-error fallback. |
| 2. Same-capture reload drops selected SnpEff evidence | Reloading the identical immutable capture retains transcript selections, NCBI/SnpEff selections, and child drafts. New captures still reset incompatible selections. Browser tests cover both cached and fetched reloads, retain the displayed AGREE result, and verify the actual comparison includes the displayed check IDs. Existing new-capture and in-flight draft guards remain covered. |
| 3. SnpEff fingerprints altered text | Subprocess capture stays binary until strict UTF-8 decoding. New `utf8_bytes` executions fingerprint exact stdout and stderr, preserve CRLF, and reject invalid bytes without saving a check. Controlled child-process tests cover LF, CRLF, Unicode diagnostics, malformed stdout/stderr, and fingerprint tampering. Legacy executions default to `legacy_text` and remain replayable without claiming original-byte fidelity. The UI identifies both formats. |
| 4. Deep JSON produces unhandled failures | Shared parsing converts decoder recursion failures into validation errors and validates provider/artifact nesting to 64 containers. Models allow additional envelope headroom for admitted data to remain exportable. Tests cover structured historical rejection, Ensembl/NCBI fallback with and without cache, the supported nesting boundary, and an admitted nested artifact's bundle round trip. Runtime manifests use the same bounded parser. |
| 5. Reads demand write locks | Initialized databases return after a read-only schema check. Only required migrations acquire `BEGIN IMMEDIATE`, rechecking the version under that lock. A held actual API save no longer blocks health or saved-record reads; a concurrent cold-initialization test retains migration safety. Existing quota/atomic rollback tests pass. |
| 6. Automatic Google Fonts requests | Removed external font links and preconnects; the app uses system fonts. The sidebar describes explicit Ensembl/NCBI actions accurately. A browser test intercepts all external resource requests on initial load and confirms none are initiated. |
| 7. Pending baseline name edits disappear | The immutable submission's name is disabled during saving and initial discovery. Browser tests hold real successful responses and simulated failures, checking the exact submitted name, successful saved value, and editable retained draft after failure. |
| 8. Long baseline names overflow phones | Grid tracks and children can shrink, while long names wrap without truncation. Browser tests preserve all 200 ASCII or supplementary Unicode characters and check document width and name bounds at 320, 375, and 1280 pixels. Replay controls stay visible. |

## Verification

- **307 backend tests passed**, including 24 new regression cases.
- **40 frontend unit tests passed**, including new-format execution labeling and legacy labeling.
- **All 72 Chromium workflows passed in one full run**, including seven new checks. The long-name phone screenshot was also visually inspected.
- **Production build passed.**
- Git whitespace checks passed with the repository's Windows line-ending policy.
- Initial new-test failures exposed an incorrect route interceptor and a shared-fixture assumption about which cached NCBI check was latest. The tests now hold the actual save route and compare against the actual loaded and displayed check ID. No application assertions were relaxed; the final complete suite passed.

## Compatibility

Compatibility was checked against a temporary SQLite backup made through a read-only source connection. All **11 existing comparisons** produced reports and replay-verified portable bundles; both existing pinned cases passed. All pre-existing rows in investigations, cases, sources, reference checks, SnpEff checks, allele checks, and run history remained byte-for-byte unchanged. The normal database was unchanged by this check, and the copy retained schema version 2 with integrity `ok`.

Before the local app restart, the normal database was backed up to `data/backups/investigations-before-0.7.9-2026-10-24.db`.

The restarted app serves application **0.7.9** / comparator **0.6.5** at **http://127.0.0.1:5173/**. Direct and proxied health responses identify this checkout, and the page returns HTTP 200 without external font links. All backed-up rows still match exactly after restart; database integrity remains `ok` and schema version remains 2.

## Limits

Source consistency does not authenticate the provider or prove a patch-to-accession mapping. Existing contradictory source records are retained for inspection and cannot be used as fallback. Compatible older source records and execution captures remain supported; legacy stdout bytes cannot be recovered retroactively. Imported execution records are not authenticated attestations.

Provider behavior was exercised with preserved fixtures and local HTTP mock transports. Runner tests used controlled child processes and temporary pinned artifacts. This repair did not fetch new live Ensembl/NCBI observations or perform a new biological SnpEff annotation.
