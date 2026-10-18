# Current state - 2026-10-18

Application version 0.7.1 removes game-oriented features and simplifies the main workflow for a broader audience. Comparator engine 0.6.3 is unchanged.

## Verification

- Backend: 139 tests passed. Frontend: 27 tests passed. Browser workflows: 18 passed.
- TypeScript/Vite production build passes.
- Browser coverage includes the simpler welcome screen, plain-language summaries, optional terms and technical details, guided input on mobile, and the existing source, storage, export, and regression workflows.
- Application and comparator versions remain distinct: `/api/health.version` is the comparator version and `app_version` is 0.7.1. Archive verification and result IDs are unchanged.

## Changes

1. Removed the Mystery Lab, its API endpoints, fictional lesson fixtures, quiz/progress UI, and animation controls. Obsolete browser progress is cleared when the app opens.
2. The welcome screen explains the purpose and offers two actions: try an example or enter analysis results.
3. The default result summary explains whether supplied edits match, what changed, and whether a cause is demonstrated. Local identity and synthetic evidence are not upgraded to independently authenticated or clinical claims.
4. A glossary explains variant, transcript, predicted effect, source version, and supporting details. Detailed records and original engine findings are available in an expandable technical section.
5. Navigation and common field labels use clearer wording. Original field identifiers remain available for auditability; comparison importance is explicitly distinguished from medical significance.
6. Existing scientific, source-integrity, storage, and freshness fixes remain covered. The original example is a practical demonstration with fabricated data.

Scientific boundaries remain in `docs/scientific-validity.md`. Raw sequencing interpretation, diagnosis, full historical pipeline execution, cross-assembly mapping, VRS, and clinical interpretation remain outside the current implementation.
