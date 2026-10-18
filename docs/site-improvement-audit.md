# Site audit and improvement backlog

Reviewed 2026-10-13 against the local 0.4.0 application. Version 0.5.0 implements guided primary input, additional variant and annotation rows, significance overrides, transcript controls, a saved-record library, replay-checked bundles, backend status, storage backup, and a browser smoke suite. The scientific milestones below remain open where they require independently verifiable source artifacts. This is not a claim of clinical validation or exhaustive coverage of all environments.

## Verified in this review

- Synthetic demo runs directly to the investigation overview; its JSON remains editable under Snapshot JSON.
- Differences filter and evidence links open the corresponding preserved evidence.
- A pinned regression passes, and a candidate with a changed consequence fails with specific assertions and evidence drift.
- Cached Ensembl lookup, cached NCBI check, and transcript comparison work without a fresh external request.
- JSON and Markdown export download from the browser; a saved investigation reopens after a page reload.
- Malformed JSON disables comparison; schema errors identify the invalid fields.
- Desktop and 390 px layouts were inspected. The action row and public-source grid overflow found during review were fixed.
- Backend tests, frontend tests, production build, and production dependency audit pass.

## Required next improvements

### Scientific correctness and scope

1. **Independent consequence validation.** Compare VEP transcript consequences with a second annotation engine using pinned reference, transcript, and software releases. Keep cause status at `possible` until an independent replay supports it.
2. **Reference-backed variant normalization.** Add established normalization for indels and repeat contexts, then tested HGVS, SPDI, VCF, and VRS mappings. Preserve assembly and accession uncertainty rather than inferring equivalence.
3. **Multiple rows and real analysis pairs.** The 0.5.0 JSON schema accepts additional exact variant representations and annotation rows with explicit missing-row differences. Build a guided editor for multiple variants, then add validated equivalence and stronger matching across different representations.
4. **Historical reproducibility.** Save all source and tool versions needed to reproduce a result, support explicit historical inputs when available, and never imply that a current API response represents an earlier release.
5. **Significance rules.** Make meaningful-change rules configurable and evidence-linked, especially for transcript, consequence, clinical condition, and classification framework changes.
6. **Curated validation corpus.** Add independently sourced positive, negative, ambiguous, and cross-assembly cases for identity and annotation explanations; document expected outcomes and limitations.

### Product and interaction

7. **Guided input.** Provide a structured form and local file import alongside JSON, with a schema example users can understand without scrolling through a large document.
8. **Inline validation.** Validate field types and required fields before submit, show errors beside their fields or JSON paths, and keep server errors scoped to the screen that caused them. A prior comparison error can currently remain visible in Public source.
9. **Result freshness.** Keep the newly added changed-input notice, and make the current result's input hash and any draft changes more prominent so exported and regression records are never mistaken for the draft.
10. **Accessible mobile navigation.** Replace the icon-only narrow-screen sidebar with a labeled menu or bottom navigation. Verify keyboard navigation, focus indicators, contrast, screen reader labeling, and zoom at 200%.
11. **Readable density.** Increase the many 9–11 px text styles, improve contrast, and make long identifiers and evidence JSON readable on phones without page-level horizontal scrolling.
12. **Investigation management.** Add search, clear names and timestamps, filters, deliberate retention/deletion, and an obvious route to reopen saved records beyond the latest five.
13. **Public-source comparison controls.** Let users filter and select transcript rows directly from the table, explain why a pair is eligible, and preserve the selected source/check IDs clearly in the result.
14. **Regression editing.** Replace the candidate's large raw JSON editor with focused changes and a clear preview of pinned expectations; preserve the advanced JSON mode.
15. **Portable export.** Add one reproducibility bundle containing input, source responses, check responses, hashes, versions, and a manifest; verify bundle re-import.

### Reliability and operations

16. **Browser end-to-end suite.** Automate the real demo, source-cache, saved-record, export, regression, failure, and offline journeys at desktop and phone sizes; keep the existing unit and API tests.
17. **Backend state and feedback.** Drive the green local-engine/session indicators from `/api/health`; display connection loss and recovery instead of silently showing a healthy badge.
18. **Failure handling.** Test unavailable Ensembl/NCBI, malformed responses, stale cache, database errors, oversized requests, and interrupted downloads with explicit recovery paths.
19. **Storage lifecycle.** Add schema migrations, backups/export, storage-size controls, and a documented path for moving a local database between machines.
20. **Deployment hardening.** Keep the default service bound to loopback, document local data/privacy behavior, and review access controls before any network-hosted or multi-user deployment.

The current scientific development order remains in [roadmap.md](roadmap.md). Items above are implementation work, not assurances that the current tool is suitable for clinical decisions.
