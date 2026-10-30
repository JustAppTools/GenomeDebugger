# Current bug audit — application 0.7.6 / comparator 0.6.3

Reviewed on **2026-10-21** against the current workspace, including the uncommitted fixes on top of commit `b085e08290dc52bf8610d3c588d037a78b3de359`.

**Ten findings were reproduced.** Application code was not changed. This is a bounded audit, not proof that every possible bug has been found.

**Repair follow-up:** all ten findings were addressed in application 0.7.7 / comparator 0.6.4; see [repairs and verification](fixes-0.7.7-2026-10-21.md). The findings below describe the audited 0.7.6 state.

## Verification and scope

- Existing checks pass: **227 backend tests, 37 frontend tests, all 47 Chromium workflows, and the production build**.
- Seven additional Chromium probes reproduced the VCF upload/check race, lookup draft loss, lookup selection loss, recent-list race, health-poll race, concurrent library paging, and concurrent baseline creation. These probes asserted defective behavior; their passing results mean the defects were reproduced. The temporary probe file was removed after inspection.
- Backend reproductions used FastAPI TestClient requests with temporary databases and captured/constructed fixtures. They demonstrated false important consequence differences, a mislinked finding, malformed nested Unicode failures, and malformed SnpEff manifest failures.
- Browser probes used isolated local test services and their temporary database. Source lookups were fulfilled with valid preserved fixture records; delayed responses were controlled locally. No live Ensembl or NCBI requests were needed.
- The SnpEff race checked both versions through the actual annotation-check API: the earlier editor text produced `agree`, while the uploaded replacement produced `disagree`. The reproduction did not alter a verdict through a response stub.
- Manifest tests redirected only the test process's environment to temporary files. The installed SnpEff configuration was not changed.
- No audit probe wrote to the user's normal database. Existing uncommitted project changes were preserved. Other browser engines, live upstream availability, and deployment were not tested.

## 1. P1 — A completed VCF upload can retain an older, contradictory AGREE check

Locations: [SnpEffPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/SnpEffPanel.tsx:23), [SnpEffPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/SnpEffPanel.tsx:46).

Reproduction:

1. Enter a matching VCF and complete the software/database declarations.
2. Select a replacement VCF with changed consequence terms and hold its byte read open.
3. While the file is loading, click **Compare SnpEff output**. The previous VCF remains in the textarea, and this action is enabled.
4. Let that API request complete with `agree`, then release the file read.

Observed: the textarea now contains the replacement VCF, but the previous **AGREE** verdict and selected check remain visible. The panel says that older check will be included in the comparison. Independently submitting the replacement text through the same API returns **disagree**.

Cause: upload start invalidates the check, but retaining the previous draft leaves check actions available during the read. A check started afterward can install its result; upload completion only calls `setVcf(content)` and does not invalidate that result or advance the check's draft revision.

Impact: the editor and selected supporting evidence describe different inputs. A user can carry an older agreeing check into a comparison while looking at a VCF that disagrees.

Repair: track file-read state, coordinate it with check actions, and treat successful replacement of the VCF as a new draft revision that invalidates incompatible pending/selected checks.

## 2. P1 — Source lookups still erase newer edits and transcript selections

Locations: [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:75), [PublicSourcePanel.tsx](D:/Creation/GenomeDebugger/frontend/src/PublicSourcePanel.tsx:87).

Two browser reproductions:

- Hold **Fetch current from Ensembl** after an existing capture is loaded. Type a newer VCF draft. Release a valid new-capture response for the same query. The SnpEff component remounts under the new record ID and its textarea becomes empty.
- Hold **Load cached** for the same capture. Select another Analysis A transcript while waiting. Release the lookup response. The selection resets to the default first transcript.

The new-capture response came from another preserved, verified fixture record; no live upstream request was made.

Cause: lookup completion checks only query revision, then replaces the record and restores default transcript selections. The shared workspace revision added in 0.7.6 guards comparison completion, but lookup completion does not use it.

Impact: edits made after the operation started are silently discarded. The VCF loss is actual unsaved text loss.

Repair: apply operation freshness checks to lookup replacement and default selection too. Preserve newer drafts/selections, and explain when a completed capture was saved without replacing current work.

## 3. P2 — A protein-change finding links to position evidence instead

Location: [engine.py](D:/Creation/GenomeDebugger/backend/app/engine.py:225).

Reproduction: use the transcript-switch fixture, remove its controlled lookup, and make both primary consequence strings equal while retaining the different protein consequences and padded/unpadded variant representations. Submit through `/api/investigations`.

Observed: the transcript-selection finding has `affected_fields: ["protein_consequence"]`, but its only evidence is `diff-1`, whose data field is **position**. The protein comparison has its own evidence item, which is not linked by this finding.

Cause: when no `consequence` difference exists, the engine falls back to `differences[0]` regardless of what the finding explains.

Impact: following the finding's evidence link opens an unrelated field comparison. The evidence exists, so dangling-reference checks do not detect this incorrect relationship.

Repair: derive evidence links from the actual affected fields and relevant transcript selection, rather than the first available difference.

## 4. P2 — Reordering identical consequence terms creates an important effect change

Locations: [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:202), [ensembl.py](D:/Creation/GenomeDebugger/backend/app/ensembl.py:207).

Reproduction: preserve two valid historical VEP artifacts for the same query and transcript. Give one the term list `["intron_variant", "non_coding_transcript_variant"]`, and the other the same two terms in reverse order. Compare those preserved sources through the API.

Observed:

```text
field: consequence
before: intron_variant;non_coding_transcript_variant
after: non_coding_transcript_variant;intron_variant
meaningful: true
```

Cause: source annotation conversion joins terms in their supplied array order; the comparator then treats the two joined strings as distinct effect values. The SnpEff comparison elsewhere already compares these terms as sets.

Impact: an ordering-only change is counted as an important predicted-effect difference, alongside genuine changes.

Repair: compare source consequence collections canonically while preserving the original artifact bytes and declared order in the audit record. Any comparator behavior change needs versioned replay compatibility.

## 5. P2 — Malformed Unicode in nested metadata still causes HTTP 500

Locations: [models.py](D:/Creation/GenomeDebugger/backend/app/models.py:82), [limits.py](D:/Creation/GenomeDebugger/backend/app/limits.py:13).

Reproduction:

- Submit otherwise valid investigation JSON with `snapshots[0].provenance.configuration.test` set to the escaped lone surrogate `"\ud800"`.
- Separately, import an otherwise valid historical VEP artifact whose unparsed extra metadata contains that value.

Observed: both paths return **HTTP 500 Internal Server Error**. The investigation path raises `PydanticSerializationError`, reporting an underlying `UnicodeEncodeError` for a surrogate that cannot be encoded as UTF-8. The same invalid value in a directly declared title or consequence correctly returns HTTP 422 instead.

Cause: generic nested metadata containers admit a string that later fails serialization. The upload's original bytes can be valid UTF-8 because the malformed Unicode value is expressed as an ASCII JSON escape; fatal file-byte decoding therefore does not cover this case.

Impact: inconsistent input handling and an opaque server failure instead of an actionable validation error. The probe did not corrupt an existing record.

Repair: validate Unicode scalar values throughout admitted nested metadata/raw parsed responses before serialization or hashing, returning a bounded validation error without substituting analysis characters.

## 6. P2 — Two tabs can create baselines that hide earlier test history

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:435), [RegressionPanel.tsx](D:/Creation/GenomeDebugger/frontend/src/RegressionPanel.tsx:31).

Reproduction:

1. Open the same new investigation's **Saved tests** screen in two tabs. Allow both discovery requests to finish before saving either baseline.
2. Save the first baseline in tab A and run it once.
3. Save a differently named baseline in tab B, which still presents the create action.
4. Leave and reopen Saved tests in tab A.

Observed: two cases exist for the same investigation. The UI loads only the newest case, showing its empty history. There is no case selector to reach the earlier baseline. Its run still exists and is retrievable through the API.

Cause: case creation allows both independent saves, while discovery uses only the first matching case. The existing discovery guard handles reopening but does not resolve concurrent creation or multiple cases.

Impact: saved test history disappears from the usable interface even though its data has not been deleted.

Repair: make baseline creation/discovery semantics consistent: provide a selector for supported multiple cases, or atomically prevent duplicates and return the existing case.

## 7. P3 — Concurrent saves repeat an investigation across library pages

Location: [InvestigationLibrary.tsx](D:/Creation/GenomeDebugger/frontend/src/InvestigationLibrary.tsx:18).

Reproduction: save 101 investigations matching one unique title prefix, load the first 100 in the library, save another matching investigation through a second client, and click **Next records**.

Observed: page 2 contains two records, and its first record repeats page 1's last record. The newly inserted record was not in the initial page snapshot.

Cause: offset-based paging shifts when another client inserts at the front. The stable cursor added for regression run history does not cover investigation-library paging.

Repair: use stable page anchors or a defined snapshot/reconciliation strategy for investigation browsing, including backward navigation.

## 8. P3 — A stale initial response removes a freshly saved item from Recent

Location: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:98).

Reproduction: hold the app's initial GET `/api/investigations` response, create a uniquely titled comparison, confirm it appears in Recent, then release the captured initial response.

Observed: the newly created comparison disappears from the sidebar's recent list. Its saved database record remains available.

Cause: initial loading replaces `recent` wholesale with the earlier server snapshot, after `showResult` has already prepended the new record.

Repair: reconcile results with newer local saves/deletions, or invalidate an obsolete initial-list response.

## 9. P3 — An old failed health request overwrites a newer healthy poll

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:104), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:113).

Reproduction: hold initial health responses, advance to the next 15-second poll, return a successful response and observe **Local engine connected**, then release an older held failure.

Observed: the badge changes to **Local engine offline** despite the more recent successful poll. It stays incorrect until another response changes it.

Cause: the polling effect guards component lifetime but does not order overlapping requests or cancel obsolete requests.

Repair: ensure only the newest health observation can update connection/version state, and bound or cancel overlapping requests.

## 10. P3 — Valid JSON with the wrong SnpEff manifest shape crashes setup inspection

Locations: [snpeff_runner.py](D:/Creation/GenomeDebugger/backend/app/snpeff_runner.py:28), [snpeff_runner.py](D:/Creation/GenomeDebugger/backend/app/snpeff_runner.py:45).

Reproduction: redirect `GENOMEDEBUGGER_SNPEFF_MANIFEST` in an isolated test process to a temporary file containing `[]`, `42`, or `{"genome": null}`; request GET `/api/tools/snpeff`.

Observed: each returns **HTTP 500**. Non-object roots reach `.get` and raise `AttributeError`; a null genome reaches `re.fullmatch` and raises `TypeError`. The status function catches neither exception class.

Impact: malformed local setup cannot be diagnosed through **Inspect local SnpEff setup**, which should report an unconfigured runtime with a useful explanation.

Repair: validate manifest shape and required field types before using them, returning a structured configuration error. The actual installed manifest was not changed during this audit.

## Suggested repair order

1. Bind VCF file-read completion to check freshness, and stop source lookups from replacing newer work.
2. Correct finding evidence selection, consequence-term comparison semantics, and nested Unicode validation.
3. Resolve multiple-baseline handling and library paging under concurrent writes.
4. Order recent-list/health responses and validate malformed runtime manifests.

The already discussed technical terminology and raw JSON evidence display remain usability limitations. They are separate from these ten reproduced defects.
