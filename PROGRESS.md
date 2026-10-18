# Current state - 2026-10-18

Version 0.6.3 fixes all six findings in `docs/bug-audit-0.6.2-2026-10-18.md`. Earlier fixes remain covered by the test suite.

## Verification

- Backend: 138 tests passed. Frontend: 24 tests passed. Browser workflows: 16 passed, including selection changes during both source comparisons, retry with the newer selection, and Unicode titles.
- TypeScript/Vite production build passes.
- All 10 currently saved investigation exports verify under the current engine; both existing pinned regression baselines pass. Compatibility checks used a temporary database copy and left the original bytes unchanged.
- Archived 0.5.0, 0.6.0, 0.6.1, and 0.6.2 results retain frozen comparison rules. New 0.6.3 results receive separate IDs. Evidence-consistency and malformed-source guards also apply to archived bundles.
- This release uses captured scientific fixtures and simulated malformed responses; no new live upstream scientific observations are claimed. The actual pinned SnpEff fixture remains unresolved because transcript versions do not match exactly.

## Fixes

1. SnpEff origin flags must match the preserved execution record. Evidence wording is neutral; reports use preserved records rather than editable flags, including for older saved inputs.
2. Shared strict transcript parsing rejects every malformed row in current retrieval, historical import, source comparison, and bundle verification.
3. Source-linked direct VEP claims are validated before generic API persistence and candidate regression runs. Explicit custom transformations remain supported.
4. Parent existence and matching input hashes are checked inside the owned-check save transaction. Late external responses return HTTP 404 after deletion instead of recreating orphan data.
5. Both source panels preserve transcript/source selection edits made while comparison is pending, show a retry notice, and suppress stale results/errors.
6. Guided text lengths count Unicode code points, including titles and annotation identifiers, consistently with backend limits.

Scientific boundaries remain in `docs/scientific-validity.md`. Cross-assembly mapping, full historical pipeline reproduction, VRS, and clinical interpretation remain outside the current implementation.
