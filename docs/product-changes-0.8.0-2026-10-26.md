# GenomeDebugger 0.8.0: implementation of the product review

Application 0.8.0; comparator 0.6.5; SQLite schema 3. Updated October 27, 2026.

## Outcome

The main journey now explains what the tool needs, takes users through scientific inputs in smaller steps, and presents a specific result and readable evidence before technical records. Scientific comparison semantics and existing immutable results remain unchanged.

The implementation includes file previews, explicit local drafts, organized saved work, local bookmarks, HTML reports, source-origin explanations, scoped identifier resolution, a tabular pipeline adapter, accessibility improvements, and local desktop packaging. Conditional research/product expansion from the review is explicitly distinguished below; it has not been presented as validated capability.

## Coverage of the 44 review items

| Review item | Delivered behavior or explicit remaining dependency |
| --- | --- |
| 1. Purpose | Concrete description of comparing two existing analysis outputs; distinguishes tools, releases, and transcript selections. |
| 2. Starting paths | Example, imported/manual analyses, and public lookup have separate starting cards. |
| 3. Shorter entry | DNA change → predictions → tools/sources → review, with an optional expert view. |
| 4. Field origins | Required/optional instructions explain where assembly, accessions, coordinates, alleles, annotation fields, and versions come from. Blank inputs contain no invented scientific defaults. |
| 5. Supported imports | Existing JSON/VEP/SnpEff paths are discoverable together. New explicit tabular v1 CSV/TSV pair preview preserves original text and hashes, reports accepted rows, and rejects unsupported/conflicting values. Arbitrary CSV or VCF is not claimed to work. |
| 6. Readiness | Review shows each DNA description, transcript/effect, tool/source, row counts, and reference-context limitation before comparing. Confirmed shared descriptions can be copied explicitly. |
| 7. Specific explanation | A deterministic narrative names the actual changed effects/transcripts/tool versions. Engine findings are visible outside technical details. |
| 8. Readable evidence | Human-readable names, facts, A/B DNA descriptions, literal edit diagrams, linked conclusions, and optional original JSON. Long values remain expandable. |
| 9. Scientific terms | Reviewed short descriptions accompany exact effect terms. Public transcript browsing shows gene symbols and canonical/MANE metadata only when present in the actual captured source. |
| 10. Certainty | Separate descriptions for supplied-context identity, linked external reference checks, annotation-output checks, provenance origin, and causal findings. No invented confidence percentage. |
| 11. Next action | Results direct readers to changed outputs, input/reference review, or a readable report as appropriate. |
| 12. Navigation | Removed duplicated result-tab navigation; contextual result/expert destinations live in the workspace navigation. Added explicit new-comparison and local-link actions. |
| 13. Public lookup | Current lookup appears first; historical and annotation-execution tools are disclosed as advanced sections. |
| 14. Examples | Transcript-selection, matching-output, and insufficient-reference-evidence teaching cases remain explicitly synthetic. |
| 15. Changes view | Shown/total counts, explicit priority scope, category filters, effect explanations, expandable long values, and a Show every change action. |
| 16. Factual visuals | Supplied-reference letters and literal post-edit text are highlighted. A transcript-selection schematic is explicitly conceptual, without invented exon positions. |
| 17. Feedback | Required/optional markers, field-associated instructions, blur feedback, review errors, and focus links to affected controls. |
| 18. Limits | Help includes a workflow capability matrix; lookup and importer limits are stated before submission. |
| 19. Drafts | Explicit browser-local save/resume/discard, save date, undo/redo. Draft retention is deliberate and separate from completed investigations. |
| 20. Library | Mutable display names, notes, tags, favorites, source/date filters, sorting, compact summaries, and stable cursor navigation. Names/archive state are reflected in Recent. |
| 21. Recovery | Archive/restore keeps records recoverable. Permanent deletion is separately disclosed and still protects pinned baselines. Selected bundle archives and database backups are available. |
| 22. Routes | Saved comparison/section hash routes support reload and browser Back/Forward. Copy-link feedback explains local-only access. |
| 23. Human report | Sandboxed HTML preview and standalone escaped HTML download support browser print/PDF. Existing Markdown, JSON, and replay-checked bundles remain available. |
| 24. Saved expectations | Clearer explanation of saving an expected result and checking new outputs; immutable baselines and detailed existing assertions remain intact. |
| 25. Transcript selection | Context explains what A/B selection does, whether reported genes differ, source limitations, and available provider metadata. No universal preferred transcript is invented. |
| 26. Source history | Source cards separate local capture/import dates from declared historical run dates and expose fingerprints on demand. |
| 27. Progress/recovery | Actual operation labels and elapsed time for root/source requests; stopping response-waiting is explicitly distinguished from cancelling server work. Existing stale-response guards remain covered. |
| 28. Phone layout | Compact labeled scrolling navigation, responsive cards/fields, deliberate table scrolling, and source lookup before advanced historical text. |
| 29. Readability | Larger supporting text, stronger hierarchy, long-value wrapping, contrast corrections, and consistent focus/touch styles. |
| 30. Accessibility | Added axe checks for core screens, keyboard skip/focus tests, responsive checks, and reduced-motion rules. The skip link has explicit keyboard focusability in WebKit; initial rendering does not steal focus from someone already tabbing. Automated checks do not establish complete WCAG conformance or replace screen-reader testing with people. |
| 31. Help | Searchable glossary, field-origin guidance, supported-workflow matrix, and context-specific troubleshooting. |
| 32. Local data | Versions, schema, data location, used/configured storage, record counts, consistent backup download, and validated restoration instructions. |
| 33. Identifiers | Explicit Ensembl rsID/simple c./g. substitution resolution preview. Every supported forward-strand GRCh38 SNV choice is shown; selection is deliberate. Unsupported/ambiguous mappings are not guessed. Provider response preview is distinct from the subsequently preserved source capture. |
| 34. Multiple variants | Explicit tabular rows can form up to 51 represented variants per analysis within existing limits. Results provide exact-representation matching, unmatched-row visibility, filters, and selected-row reading export. No broad genome-scale processing claim. |
| 35. Scientific expansion | Capability matrix and boundary tests shipped. Additional validated assemblies, VRS/cross-assembly conversion, and broader independent normalization remain research work requiring reference coverage; they were not implemented by guessing. |
| 36. Historical workflows | Existing genuine artifact preservation/comparison remains functional, with clearer discovery and captured/declared source cards. New historical pipeline artifacts cannot be manufactured; wider release timelines still require actual original datasets. |
| 37. Local distribution | Setup/Start/Stop source launchers, optional desktop shortcut setup, and a portable Windows build with bundled Python and compiled UI. Source entry point was smoke-tested. Generated executable launch was rejected by automatic approval review, so frozen-binary execution is not claimed as verified. Signing/public distribution is a separate release task. |
| 38. Hosting | Kept loopback/local-first operation, consistent with the master directive. No public service or account-sharing model was enabled without a deployment target and explicit data-access design. |
| 39. Integration | `scripts/compare-files.py` previews/saves documented tabular v1 exports against an explicit loopback API, with optional JSON output. |
| 40. Languages | Clearer English and centralized explanation/glossary text delivered. Other languages remain conditional on a named audience and review of scientific translations; no unsupported language claim. |
| 41. Human comprehension | Local voluntary checklist and a representative-user test protocol delivered. Actual participant sessions have not been performed or fabricated. |
| 42. Evaluation cases | Added matching/uncertain examples, import failure/row-preservation cases, identifier ambiguity/scope cases, organization/restore tests, and report escaping checks. Existing curated/public reference fixtures remain in the suite. Wider independently sourced cases still require acquisition and review. |
| 43. Environments/scale | Chromium regression, WebKit product workflows, core accessibility checks, and bounded multi-row/library tests. Firefox suite is opt-in because this host returned `spawn UNKNOWN` when launching its downloaded browser. No Firefox pass or full assistive-technology certification is claimed. Library pages project compact fields rather than loading complete scientific records. |
| 44. Feedback/metrics | Optional local-only checklist download includes task responses and optional elapsed minutes. No genetic content, silent analytics, or external submission is collected. |

## Data compatibility and preservation

- Database migration adds only `investigation_labels` in schema 3. It does not rewrite saved investigation JSON or canonical input hashes.
- Library labels and archive flags are outside scientific inputs and portable investigation identity.
- Original tabular UTF-8 text and its hash are retained in input provenance. File bookkeeping changes are explicitly deprioritized through comparison overrides, without hiding them from the complete record. Editing an imported snapshot marks it as edited.
- Portable bundles continue using the existing replay/checksum rules and archived comparators. The comparator version remains 0.6.5.
- The development database was backed up before migration to `data/backups/before-product-0.8.0-2026-10-26-41ab9731.db`.
- Automated browser tests use isolated databases and supplied synthetic/public fixtures. No live personal variant queries were performed during implementation verification.

## Validation

Final checks: **386 backend tests, 44 frontend unit tests, and 94 browser tests passed** (87 Chromium and 7 WebKit). TypeScript/Vite production compilation also passed. The browser suite includes core axe accessibility checks and keyboard navigation; it does not establish complete WCAG conformance. The source desktop launcher verified compiled UI serving, comparison saving, database download, and shutdown against isolated data. Detailed commands and bounded performance measurements are recorded in `PROGRESS.md`.

After restarting the development application, all 11 saved investigation JSON records were compared against the pre-migration backup and remained byte-for-byte unchanged, with no records added or removed.

The portable executable package was generated successfully. Automatic approval review rejected its launch test with the stated reason **“blocked by policy.”** Verification from source does not establish that the frozen executable starts correctly. Firefox launch similarly failed at the host/browser level with `spawn UNKNOWN`; WebKit and Chromium are evaluated separately.

## Intentional remaining work

Recruit and observe representative users, complete assistive-technology/manual accessibility evaluation, validate Firefox in a host that can launch it, and test/sign the frozen Windows executable before public release. Broader scientific coverage, newly sourced historical pipeline datasets, localization, and hosted collaboration remain explicit follow-on work rather than fabricated or silently activated features.
