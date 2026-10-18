# Current state - 2026-10-18

Version 0.6.1 fixes all 14 findings in `docs/bug-audit-2026-10-18.md`.

## Verification

- Backend: 101 tests passed. Frontend: 21 tests passed. Browser workflows: 9 passed, including both request races and omitted defaults.
- TypeScript/Vite production build passes.
- Existing saved investigations remain readable; their exports verify under the current engine. Both existing pinned regression baselines pass.
- Archived 0.5.0 and 0.6.0 results retain frozen verification rules. New 0.6.1 results receive separate IDs.
- A real pinned SnpEff run completed with validated GRCh38 assembly metadata and exact input-byte hashing. Its bundle verified. The captured fixture was refreshed; transcript-version coverage still correctly remains unresolved.
- Local runtime setup supports safe assembly-metadata migration for the known existing installation without replacing its pinned files.

## Fixes

1. VEP source/snapshot consistency and declared complete annotation-set checks.
2. Immutable artifact conflicts rejected instead of silently ignored.
3. Exact Windows input-byte hashing for local SnpEff.
4. Reviewed database/build and source-assembly validation before execution.
5. Atomic bundle import with full rollback on failure.
6. Reusable SQLite pages included in storage capacity; identical imports need no new capacity.
7. Later draft edits remain visibly stale when an earlier comparison completes.
8. Changed queries invalidate pending source/check/comparison responses.
9. Clinical assertion dates retained as metadata differences.
10. Strict bundle-manifest validation returns HTTP 422 for invalid types.
11. Derived SnpEff explanations checked against replay.
12. Regression discovery filtered by investigation; older lists have pagination.
13. All generated difference-path lengths supported by overrides within the request budget.
14. Guided mode applies the optional synthetic default while rejecting invalid explicit values.

Scientific boundaries remain in `docs/scientific-validity.md`. Cross-assembly mapping, full historical pipeline reproduction, VRS, and clinical interpretation remain outside the current implementation.
