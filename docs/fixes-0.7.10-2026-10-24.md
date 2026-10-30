# Repairs for the 0.7.9 audit

Application **0.7.10**, comparator **0.6.5**, 2026-10-24.

All eight reproduced findings in [the 0.7.9 audit](bug-audit-0.7.9-2026-10-24.md) have been addressed. Earlier uncommitted work was preserved. Comparison rules and database schema version 2 remain unchanged.

| Finding | Repair and regression coverage |
|---|---|
| 1. Missing NCBI data becomes disagreement | Source SNV checks require complete typed SPDI fields, a changed allele, and genomic HGVS before deriving a notation verdict. Missing/invalid observations follow provider failure, with cached-after-error fallback when a usable check exists. Cache selection replay-validates candidates and skips invalid legacy checks without rewriting them. Explicitly selected invalid checks are rejected; their stored observations remain available by ID. Tests cover both endpoints, cache/no-cache, incomplete/invalid values, and a newer invalid cache entry above an older valid check. |
| 2. Custom outputs retain an inapplicable SnpEff agreement | New investigations, candidates, and bundles validate primary-variant gene/transcript/consequence rows against the preserved source targeted by the check. Changed output must detach the annotation check. Tests cover selected and additional rows at every admission boundary, successful detached output, compatible custom metadata/protein edits, and useful JSON-entry feedback in Chromium. |
| 3. Malformed execution provenance verifies | Execution admission validates timezone-aware start time, finite nonnegative duration, a nonempty executable/valid command text, nonempty database fingerprints, and SHA-256 formats. The runner, selected saved execution checks, new linked submissions, and bundle verification enforce these checks. Tests reject malformed records atomically and verify the original legacy execution fixture without rewriting its saved bytes. Legacy model readability is retained. |
| 4. Saved sources cannot fit provenance | Release summaries retain their original wording when it fits. Expanded lists use a bounded count plus “see source record”; full release numbers remain in the immutable source and portable bundle. The 41-release reproduction now fetches, compares, reloads, exports, and verifies successfully. Existing ordinary release strings remain identical. |
| 5. Boolean coordinates become position 1 | Scientific coordinate/count fields use strict integers, including variants, reference contexts, source queries, historical releases, normalized SPDI positions, and matched-transcript counts. Captured VEP start/end coordinates are also type-checked before numeric equality can admit booleans. Tests cover true/false in primary/additional variants, source/historical requests, and provider/artifact coordinates, plus preserved rejected JSON drafts in Chromium. |
| 6. Analysis cards overflow phones | Snapshot cards and their children shrink and wrap accepted long labels, IDs, and source names. Browser tests retain the complete values, check document width and element bounds at 320, 375, and 1280 pixels, and save a phone screenshot for visual inspection. |
| 7. Missing/empty changes look identical | Display values distinguish **Not provided**, **Empty text**, and **Whitespace only**. Saved inputs, null/empty values, differences, and fingerprints remain unchanged. A browser regression verifies the distinct table cells and exact original saved result. |
| 8. Required fields accept whitespace | Admission checks reject whitespace-only required names and identifiers in investigations, candidates, bundles, historical declarations, supplied-check declarations, generated source comparisons, and new case names. Valid internal/outer spacing remains intact. These checks are separate from reading saved models, so older blank records remain inspectable and reportable. Tests cover ordinary/Unicode whitespace, valid spacing, legacy inspection, and editable browser error feedback. |

## Verification

- **371 backend tests passed**, including **64 new regression cases**.
- **40 frontend unit tests passed.**
- **Production build passed.**
- All seven new Chromium regression checks passed, including visual inspection of the long-label phone screenshot.
- **All 79 Chromium workflows passed in one complete run.**
- Git whitespace checks passed with the repository's Windows line-ending policy.

## Compatibility

Compatibility was checked using a temporary SQLite backup through a read-only source connection. All **11 existing comparisons** produced reports and replay-verified portable bundles; both existing pinned cases passed. All pre-existing rows in investigations, cases, sources, reference checks, SnpEff checks, allele checks, and run history remained byte-for-byte unchanged. The normal database was unchanged by this check; the copy retained schema version 2 with integrity `ok`.

Before restarting the local app, the normal database was backed up to `data/backups/investigations-before-0.7.10-2026-10-24.db`.

The restarted app serves application **0.7.10** / comparator **0.6.5** at **http://127.0.0.1:5173/**. Direct and proxied health identify this checkout, and the page returns HTTP 200. All database rows exactly match the pre-restart backup; integrity remains `ok` and schema version remains 2.

Invalid older observations or provenance remain stored for inspection. They cannot be reused as new validated evidence or admitted in new bundles. Whitespace-only older inputs remain available as saved JSON and reports, while new submissions must meet the current admission rules. No saved record is silently corrected or reclassified.

## Limits

SnpEff applicability covers primary-variant gene/transcript/consequence rows. Its term-agreement result does not validate protein or clinical output, or additional variants. Declared metadata and imported execution records remain externally unauthenticated. Bounded release summaries preserve the complete source metadata in the source record and bundle.

Provider behavior was exercised with preserved fixtures and local HTTP mock transports. This repair did not fetch new live Ensembl/NCBI observations or perform a new biological SnpEff annotation. The comparator stays at **0.6.5** because these changes affect admission, adapter validation, generated provenance summaries, and presentation rather than the comparison of an existing valid input.
