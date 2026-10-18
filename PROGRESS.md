# Current state - 2026-10-18

Application version 0.7.0 adds the Mystery Lab and recorded analysis replay. Comparator engine 0.6.3 is unchanged; earlier fixes remain covered by the test suite.

## Verification

- Backend: 146 tests passed. Frontend: 27 tests passed. Browser workflows: 19 passed, including all three mystery hypotheses/retries, browser progress, workbench/bundle export, automatic replay pauses, mobile layout, and reduced motion.
- TypeScript/Vite production build passes.
- All 10 currently saved investigation exports verify under the current engine; both existing pinned regression baselines pass. Compatibility checks used a temporary database copy and left the original bytes unchanged.
- Application and comparator versions are now distinct. `/api/health.version` remains the comparator version; `app_version` reports 0.7.0. Existing archive verification and result IDs remain unchanged.
- This release uses captured scientific fixtures and simulated malformed responses; no new live upstream scientific observations are claimed. The actual pinned SnpEff fixture remains unresolved because transcript versions do not match exactly.

## New functionality

1. Three synthetic mystery fixtures teach missing transcript coverage, padded equivalent substitutions, and limits on release-related causal claims.
2. Each hypothesis is checked against fresh comparator output; changed fixtures cannot retain a canned success. Practice performs no database writes or upstream requests.
3. Case files, clues, retryable hypotheses, evidence inspection, and browser-local completion tracking are available in Mystery Lab.
4. Explicit workbench saving uses the normal comparison endpoint. All cases export/replay and support pinned regression tests.
5. Recorded replay appears in cases and ordinary overviews: Input → Reference → Transcript → Consequence → Comparison. Playback pauses at observed differences, supports manual navigation, and respects reduced motion.
6. Desktop and mobile layouts were inspected visually. Clinical classifications and independently authenticated observations are not inferred from these synthetic lessons.

The six prior audit repairs remain documented in `docs/bug-audit-0.6.2-2026-10-18.md`. Full pipeline execution replay, an evidence graph, chromosome exploration, and additional lesson authoring remain future work.

Scientific boundaries remain in `docs/scientific-validity.md`. Cross-assembly mapping, full historical pipeline reproduction, VRS, and clinical interpretation remain outside the current implementation.
