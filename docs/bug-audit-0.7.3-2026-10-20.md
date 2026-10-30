# Current bug audit — application 0.7.3 / comparator 0.6.3

Reviewed on **2026-10-20**, including the existing uncommitted repairs on top of commit `b085e08290dc52bf8610d3c588d037a78b3de359`.

**Four new findings were reproduced.** This is an audit, not a claim that every possible defect has been found. The initial audit made no application changes; subsequent repairs are recorded below.

**Resolved in application 0.7.4.** Comparator 0.6.3 and archived comparison rules remain unchanged. The numbered findings describe the audited 0.7.3 behavior.

## Verification and scope

- Existing checks pass: **162 backend tests, 30 frontend tests, all 32 Chromium workflows, and the production build**.
- Two additional Chromium probes reproduced draft loss and a disallowed-origin browser write. These probes asserted the defective behavior; their passing means the bugs were reproduced. The temporary test file was removed after the audit.
- Backend probes used temporary SQLite databases, captured fixtures, and actual FastAPI requests. They reproduced contradictory SnpEff links, dangling SnpEff links, an untrusted Origin/Host write, and two failures while rendering validation errors.
- No user records were created, changed, or deleted. No external biological service was queried. The normal frontend and backend both respond with HTTP 200; health identifies application 0.7.3 / engine 0.6.3.
- Live upstream availability, other browser engines, and deployment were not tested. The security browser reproduction uses another loopback origin; behavior from a public website also depends on the browser's local-network restrictions.

## 1. P1 — A delayed source comparison silently erases a newer draft

Locations: [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:250), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:116).

Reproduction:

1. Load a preserved current Ensembl source with **Look up a DNA change → Load cached**.
2. Click **Compare**, holding its successful response before delivery to the browser.
3. Navigate to **Enter results** and enter `My newer draft must survive` as the investigation title.
4. Release the source comparison response.

Observed: the application navigates to the old comparison's overview. Opening **Input JSON** shows `Current Ensembl transcript comparison: 1:6524705 C>T` instead of the newer title. The draft is replaced without a stale-input warning.

Cause: unmounting the source screen does not invalidate its pending callback. The callback checks only the root selection epoch, which ordinary tab changes and draft edits do not increment. It then unconditionally replaces the input and calls `showResult` without the submitted-draft guard used by the main comparison flow. The historical source screen shares this root callback, though the browser reproduction exercised the current-source path.

Repair: bind source completions to the active screen/operation and draft revision. Preserve intervening edits and prevent an unmounted source request from taking over navigation. A completed comparison may remain saved in the library without replacing a newer draft.

## 2. P2 — Unapproved browser origins can perform local writes

Locations: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:33), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:87).

Reproduction:

1. From the isolated browser origin `http://127.0.0.1:5174`, which is absent from the configured CORS allowlist, send a POST directly to `http://127.0.0.1:8001/api/investigations`.
2. Use `body: new Blob([JSON.stringify(input)])` with no explicit Content-Type. This sends a browser request without requiring a JSON Content-Type preflight.
3. Inspect the database through the application's permitted same-origin API proxy.

Observed: browser JavaScript gets a CORS failure when reading the response, but the investigation **is saved**. The test confirmed the new title and record ID through the API. A separate API request with `Origin: https://untrusted.example`, an untrusted Host, and no Content-Type also returned HTTP 200 and saved its record.

Cause: CORS controls response access; it does not reject this POST before application processing. The custom middleware checks the TCP peer's loopback address and request size, but does not enforce trusted Origin/Host values for mutations. A browser accessing a local service has a loopback peer address even when another page initiated the request.

Impact: another browser origin that can reach the local API can create local records without an action in GenomeDebugger. This audit did not demonstrate reading private records from a public origin or bypassing browser local-network permissions.

Repair: enforce trusted browser origins before processing mutations and validate allowed Host values. Preserve intentional local CLI/API access under an explicit policy; do not rely solely on CORS or an exact Content-Type check.

## 3. P2 — SnpEff provenance can contradict the evidence and still verify

Locations: [check_scope.py](D:/Creation/GenomeDebugger/backend/app/check_scope.py:8), [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:41), [bundle.py](D:/Creation/GenomeDebugger/backend/app/bundle.py:217), [App.tsx](D:/Creation/GenomeDebugger/frontend/src/App.tsx:46).

Reproduction:

1. Save the existing matching two-transcript SnpEff fixture and create a linked source comparison. Its real annotation summary reports `agree`.
2. In both snapshots, change `provenance.configuration.annotation_check_id` to `nonexistent-check` and `annotation_check_status` to `disagree`. Keep the actual top-level annotation summary unchanged.
3. POST the input, export its bundle, and verify the bundle.
4. Repeat after removing the top-level `annotation_check` summary while retaining those configuration fields.

Observed: creation, bundle export, and bundle verification all return **HTTP 200** in both cases. The first result contains an agreeing preserved check plus contradictory configuration. The second contains a check claim without any linked summary/check. Snapshot cards display the configuration's nonexistent SnpEff check ID; the actual summary/report can identify a different check or none.

Cause: reserved NCBI check IDs/statuses are reconciled by `validate_reference_provenance`, but the equivalent SnpEff fields are not. SnpEff origin is checked only when a real summary/check is present. The frontend reads the duplicated configuration ID for display.

Repair: reconcile reserved SnpEff ID, status, and origin fields with the actual linked summary/record at creation, candidate validation, and bundle boundaries. Derive displayed links from the actual summary. Define compatibility for omitted legacy flags without accepting contradictory or dangling claims.

## 4. P3 — Invalid input can crash validation-error rendering

Location: [main.py](D:/Creation/GenomeDebugger/backend/app/main.py:30), where FastAPI is configured without an application validation-error handler that safely serializes rejected input.

Two independent reproductions use the normal investigation endpoint:

- Set the title in the demo JSON to the escaped string `"bad\ud800"` and POST the UTF-8 JSON bytes with `Content-Type: application/json`.
- In the demo's first variant, replace position `101` with the numeric token `1e999` and POST the JSON bytes.

Observed: both return **HTTP 500 / Internal Server Error**, rather than an actionable validation response. Neither creates a record.

Cause: validation correctly rejects the values, but the default FastAPI validation handler includes the rejected input in its JSON response. Serializing the lone surrogate raises `UnicodeEncodeError`; serializing the overflowed numeric value raises `ValueError: Out of range float values are not JSON compliant: inf`. Tracebacks end in the validation exception handler and Starlette JSON response renderer.

Repair: return bounded, safely serialized validation details, avoiding raw invalid values that cannot be represented in UTF-8 JSON. Retain useful field paths/messages and cover both malformed Unicode and non-finite/overflowed numbers across input routes.

## Suggested order

1. Prevent source completions from destroying newer drafts.
2. Reject untrusted browser mutations before side effects.
3. Reconcile SnpEff links with preserved evidence.
4. Make invalid-input error responses safe and actionable.

The previously discussed clarity gaps—raw JSON in the evidence inspector and technical fields that need better explanations—remain separate known usability work and are not counted as new bugs here.

## Repair verification — application 0.7.4

All four findings have been repaired:

1. Current and historical source completions pass through a mount-lifetime guard. Leaving and reopening the source screen cannot reactivate an old callback. The root also checks the draft revision before accepting source results. Completed comparisons remain saved without replacing newer drafts or navigation.
2. The API validates local Host values on reads and writes and rejects untrusted mutation Origins before request processing. CORS shares the configured trusted origins. The API's own origin remains available for `/docs`; local CLI clients without browser headers remain supported. Alternate trusted frontend origins require explicit `GENOMEDEBUGGER_ALLOWED_ORIGINS` configuration, including the isolated test frontend.
3. SnpEff reserved IDs/statuses must match the linked summary; dangling ID/status/origin claims are rejected. Origin flags must match preserved execution records. Creation, candidate checking, and bundle verification/import enforce these rules. Missing legacy flags remain accepted. Technical cards display the actual summary's check ID and status.
4. A global request-validation handler returns bounded field paths, messages, and error types without raw rejected input or exception context. Lone surrogates, overflowed numbers, and non-finite values return HTTP 422 instead of failing error serialization.

Verification passes **194 backend tests, 30 frontend tests, all 37 Chromium workflows, and the production build**. New coverage includes both source screens, leaving/reopening during a request, browser Blob writes from an unapproved origin, preventing upstream calls and deletion from untrusted origins, local/IPv6 and invalid Hosts, CLI/allowed-origin access, contradictory and dangling SnpEff claims at all validation boundaries, legacy summary display, and bounded error rendering across investigation, candidate, and historical import routes.

An older transformed-output test was updated to remove SnpEff configuration flags when removing its top-level check, matching the stricter consistency contract. The IPv6 Host test supplies its Host directly because the installed TestClient transport cannot split an IPv6 base URL correctly.

On a temporary read-only-backed-up copy of the user database, all **10 saved comparisons** produce reports and verified bundles, and both existing pinned baselines pass and save runs. User records were not changed. No push was performed.
