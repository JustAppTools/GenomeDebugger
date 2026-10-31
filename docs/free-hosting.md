# Public preview with a $0 hosting budget

The public preview runs the React interface and Python API together on a **Render Free web service**, using the root `Dockerfile` and `render.yaml`. The source repository can remain private. GitHub stores the source; Render supplies the running application's HTTPS address. GitHub Pages alone cannot run this backend.

**Live application: [genomedebugger.onrender.com](https://genomedebugger.onrender.com).** Deployed and verified on October 31, 2026. The existing service is Free, with no disk, external database, or payment method. See [deployment details and live verification](deployment-2026-10-31.md). Account connection and initial deployment are complete; the steps below document setup for another installation.

## Connect the accounts

1. Create a free account at [Render](https://dashboard.render.com/register), using the JustAppTools GitHub account.
2. In Render, open **Account Settings → Account Security → Git Deployment Credentials → Add credential → GitHub**. If GitHub asks which repositories Render may access, select **Only select repositories → GenomeDebugger**.
3. In the ChatGPT/Codex desktop app, open **Plugins**, find **Render**, install it with the plus button, then connect it to that Render account when prompted.
4. Return to the project chat and confirm that Render is connected. Account connection is required before an agent can create or inspect the hosted service. Do not paste passwords or API keys into the chat.

References: [Render's Git-provider connection instructions](https://render.com/docs/git-provider), [official plugin connection instructions](https://learn.chatgpt.com/docs/plugins).

## Deploy the prepared configuration

The owner can use [Deploy to Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FJustAppTools%2FGenomeDebugger) after authorizing Render's GitHub app for this private repository. Review the configuration before creation:

- Repository: `JustAppTools/GenomeDebugger`, branch `main`.
- One Docker web service, **Free** compute, no other paid resources.
- No persistent disk, paid database, or separate frontend service.
- Provider-generated `GENOMEDEBUGGER_SESSION_SECRET`; it never belongs in source control.
- The public origin comes from Render's `RENDER_EXTERNAL_URL` at runtime.
- Automatic deployment is off to conserve included build minutes. Blueprint Auto Sync is also off. Deploy a selected commit deliberately when updating.
- Health check: `/healthz`.

The existing service returned [https://genomedebugger.onrender.com](https://genomedebugger.onrender.com), and its deployed behavior has been verified. Reuse this service for updates rather than creating duplicate resources.

## Keep the budget at zero

Select Free compute and keep the Render account without a payment method. Free service hours and traffic/build allowances are limited; accounts with a payment method can incur supplementary usage charges. Without one, exceeded allowances can suspend service or builds. Do not upgrade a resource to restore availability. Review Render's current [free-service limits](https://render.com/docs/free) before creating the service.

## Visitor data and supported behavior

- Each visitor receives a signed, secure, HttpOnly workspace cookie. Separate browser workspaces have separate SQLite files. Another visitor cannot retrieve a record just by knowing its scientific result ID.
- There are no accounts or recovery passwords. A link refers to the current browser's workspace; share a full bundle or report to transfer data.
- All hosted records are **temporary**. They can disappear when the free server sleeps, restarts, or redeploys. Inactive workspace directories also expire after 24 hours. The interface explains this before comparisons are run.
- Download full bundles to keep reproducible comparisons. A database backup can be restored with the local app's validated offline restore command. Explicit browser drafts remain in that browser's storage, separately from hosted records.
- The hosted preview processes submitted inputs on the server. It does not claim that they remain on the visitor's computer. No personal development database is included in the container.
- Core comparisons, supported imports, saved-test checks, public-source captures, supplied SnpEff output, readable reports, and bundle transfers use the Python backend. Installing/running a pinned local Java/SnpEff database remains a local-app operation; the public host does not execute that tool.
- Hosted SQLite limits are 16 MB per workspace. Aggregate storage is bounded at 256 MB with at most 200 temporary workspace directories. At capacity, existing visitors can still download their records; additional writes or new visitors may have to wait. These are resource limits for a free preview, not a durable production-storage design.

## Validation and release scope

Application 0.10.0 keeps comparator 0.6.7 and SQLite schema 3. Its [guided workspace redesign](guided-workspace-0.10.0-2026-10-31.md) retains the hosting/data boundaries introduced in 0.9.0. Existing local installations still accept loopback connections only and retain their existing database. Public mode is explicit and refuses to start without an exact HTTPS origin and a sufficiently long session secret.

Validation logs under `.build/hosting-*` cover backend/unit checks, HTTPS browser isolation, exports/imports, readable reports, and core accessibility. Render successfully built the Docker image and deployed the service. Actual live checks passed for health, comparisons, separate visitor records/notes, saved baseline/replay, report and bundle transfer, backups, and disabled local-only actions. The browser also fetched the public Ensembl example and compared its transcript outputs. The live HTTP summary is retained locally in `.build/render-live-verification.json`; the [deployment report](deployment-2026-10-31.md) records the verified scope.
