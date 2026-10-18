# Current state - 2026-10-18

Version 0.6.2 fixes all seven additional findings in `docs/bug-audit-0.6.1-2026-10-18.md`. The earlier 14 fixes remain covered by the test suite.

## Verification

- Backend: 123 tests passed. Frontend: 23 tests passed. Browser workflows: 13 passed, including delayed successful/failed opens, delayed imports, and first-attempt regression saving with a maximum-length title.
- TypeScript/Vite production build passes.
- All nine existing saved investigation exports verify under the current engine; both existing pinned regression baselines pass. Compatibility checks used a temporary database copy and left the original bytes unchanged. No existing orphan allele checks were found.
- Archived 0.5.0, 0.6.0, and 0.6.1 results retain frozen comparison rules. New 0.6.2 results receive separate IDs. Check applicability and invalid external-observation guards also apply to archived bundles.
- This release uses captured scientific fixtures and simulated malformed responses; no new live upstream scientific observations are claimed. The actual pinned SnpEff fixture remains unresolved because transcript versions do not match exactly.

## Fixes

1. Reference and annotation checks bind to the full compared primary variant, with preserved evidence required for generic API comparisons and regression candidates.
2. SnpEff warnings/errors on non-transcript ANN entries invalidate the record before feature filtering.
3. Primary promotion retains complete variant membership and compares annotations within the correct variant.
4. Selection revisions prevent older opens, failures, imports, and comparison responses from replacing newer workspace selections.
5. Investigation deletion removes owned allele checks atomically and preserves pinned baselines/shared sources; rollback is covered.
6. Contextual SPDI coordinates and deleted intervals must fit the pinned chromosome; insertion at its exact interbase end remains valid.
7. Default regression names are bounded without splitting Unicode characters, validated before saving, and show field-specific server errors.

Scientific boundaries remain in `docs/scientific-validity.md`. Cross-assembly mapping, full historical pipeline reproduction, VRS, and clinical interpretation remain outside the current implementation.
