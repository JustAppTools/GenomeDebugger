# Mystery Lab — application 0.7.0

## How to play

1. Choose **Mystery lab** from the sidebar, then open a case file.
2. Read its assignment and clues. Use **Play replay**, stage buttons, or previous/next controls to walk through the comparison.
3. Inspect recorded evidence and choose a hypothesis. **Check hypothesis** provides feedback derived from a fresh local comparison.
4. Retry freely. Completing a case records its ID in this browser's local storage when available. Blocked storage still allows play during the current visit.
5. **Open & save investigation** explicitly saves the input through the normal comparison API and opens the full workbench. JSON, Markdown, verified bundles, and regression cases then work normally.

Practice does not add database records or make external requests. The local backend must be running; no internet connection is required. Progress belongs to the browser rather than an account.

## The three cases

| Case | Evidence lesson | Scientific boundary |
| --- | --- | --- |
| The Vanishing Transcript | An additional transcript row is present in A and absent in B. | Missing coverage does not establish why a producing pipeline omitted it. |
| Same Variant, Different Disguise | A padded substitution and a trimmed substitution match in the supplied context; representation changes are nonmeaningful. | Supplied synthetic context does not authenticate an assembly or establish general indel equivalence. |
| The Database Time Machine | Source release and consequence differ for the same selected transcript. | Release is a possible explanation; no controlled historical replay proves causation. |

All scenario data, genes, and annotations are fabricated. No clinical conclusions or live upstream observations are introduced. A supported unresolved causal conclusion completes the third trail.

## Replay behavior

The stages are Input, Reference, Transcript, Consequence, and Comparison. Values and evidence IDs are derived from the actual result. The primary variant's transcript count includes the selected transcript and additional rows; full collections remain accessible in field evidence and the workbench.

Playback advances every 1.6 seconds and pauses when it first enters a stage with an observed difference. **Play replay** continues from that point; the last stage stops playback. Manual stage selection pauses playback. Reset returns to the input stage. Hiding the page pauses playback, and unmounting cancels the timer. Reduced motion disables visual transitions and entrance animation. Keyboard-accessible controls allow the entire sequence to be inspected without playback.

This is an illustration of recorded inputs/comparator findings. It does not invoke VEP, SnpEff, NCBI, or a historical pipeline, and it does not strengthen any engine finding. It is also available on ordinary investigation overviews.

## Implementation and verification

- Fixtures: `fixtures/mysteries/*.json`; catalog and assessment rules: `backend/app/mysteries.py`.
- `GET /api/mysteries` returns the catalog; `GET /api/mysteries/{id}` returns a case and current engine result.
- `POST /api/mysteries/{id}/check` accepts `{"hypothesis_id":"..."}` and returns an assessment plus the fresh result. Unknown cases/options are rejected. Lessons refuse grading if their expected evidence no longer matches comparator output.
- The app release is 0.7.0. Engine 0.6.3 and its saved-result/bundle rules remain unchanged. Health reports both versions separately.
- Backend tests verify every choice, fixture drift, synthetic-only inputs, no practice persistence, bundle verification, and pinned replay. Frontend tests exercise playback, pause/resume, evidence navigation, and timer cleanup. Chromium tests cover all cases, wrong-answer retries, progress after reload, workbench exports, mobile width, and reduced motion.
