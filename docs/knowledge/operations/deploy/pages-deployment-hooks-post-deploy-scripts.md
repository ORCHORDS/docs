# Pages Deployment Hooks and Post-Deploy Scripts

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

After a Cloudflare Pages deployment completes you need to run tasks that cannot live inside the build itself: purging downstream caches, notifying external services, seeding a D1 database with freshly built data, invalidating a CDN edge config, updating a feature flag service with the new deployment URL, or triggering end-to-end tests in a third-party CI environment.

Pages builds run in an isolated container and produce a static asset bundle — they have no native "post-deploy hook" concept analogous to Vercel's `postInstall` or Netlify's build plugin lifecycle. The patterns below use Cloudflare's own primitives to fill that gap.

---

## Context

Cloudflare Pages exposes two hooks relevant to post-deploy automation:

1. **Deploy Hooks** (incoming) — a Pages-provided HTTPS endpoint that triggers a new deployment when called externally. Useful for CMS "on publish" webhooks pointing at Pages. These are *not* outgoing notifications.
2. **Webhook Notifications** via Cloudflare Notifications — Pages can emit events to a Worker or external URL when a deployment succeeds or fails. This is the mechanism for outgoing post-deploy automation.

The deploy lifecycle for Pages is:
```
push → queue → build → upload → deploy → activate
```

The `deployment.succeeded` notification fires after `activate`. At that point:
- The deployment URL (`deployment.url`) is live and externally reachable.
- `CF-Pages-Deployment-ID` and `CF-Pages-Branch` headers are available on the deployment.
- The associated Functions (Workers) are live alongside the static assets.

---

## Pattern 1 — Cloudflare Notifications → Worker Webhook

Configure Cloudflare Notifications (in the Cloudflare dashboard under Notifications → Create) to send a webhook to a Worker URL when a Pages deployment succeeds or fails.

```typescript
// workers/post-deploy-hook/src/index.ts
export interface Env {
  POST_DEPLOY_SECRET: string;   // shared secret to validate webhook
  D1_DB: D1Database;            // optional: seed data after deploy
  KV_CACHE: KVNamespace;        // optional: update cache keys
  NOTIFY_URL: string;           // optional: downstream notification endpoint
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Validate the shared secret Cloudflare sends in the Authorization header
    const auth = request.headers.get("Authorization") ?? "";
    if (auth !== `Bearer ${env.POST_DEPLOY_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const event = await request.json<CloudflarePageDeployEvent>();

    if (event.data?.deployment?.state !== "success") {
      // Only act on successful deployments; log failures separately
      console.log("Skipping hook for non-success state:", event.data?.deployment?.state);
      return new Response("OK", { status: 200 });
    }

    const deploymentUrl = event.data.deployment.url;
    const branch = event.data.deployment.environment;  // "production" or preview

    // Run post-deploy tasks concurrently
    await Promise.allSettled([
      purgeEdgeCache(deploymentUrl, env),
      seedD1IfProduction(branch, env),
      notifyDownstream(deploymentUrl, branch, env),
    ]);

    return new Response("OK", { status: 200 });
  },
};

interface CloudflarePageDeployEvent {
  data?: {
    deployment?: {
      state: string;
      url: string;
      environment: string;
      id: string;
    };
  };
}

async function purgeEdgeCache(deploymentUrl: string, env: Env): Promise<void> {
  // Example: purge a downstream Varnish or BunnyCDN cache
  if (!env.NOTIFY_URL) return;
  await fetch(`${env.NOTIFY_URL}/purge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origin: deploymentUrl }),
  });
}

async function seedD1IfProduction(branch: string, env: Env): Promise<void> {
  if (branch !== "production") return;
  // Mark latest deploy timestamp in D1 for audit trail
  await env.D1_DB.prepare(
    "INSERT INTO deploy_log (deployed_at, branch) VALUES (?, ?)",
  )
    .bind(new Date().toISOString(), branch)
    .run();
}

async function notifyDownstream(
  deploymentUrl: string,
  branch: string,
  env: Env,
): Promise<void> {
  if (!env.NOTIFY_URL) return;
  await fetch(env.NOTIFY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event: "pages.deploy.success",
      url: deploymentUrl,
      branch,
      timestamp: new Date().toISOString(),
    }),
  });
}
```

Deploy this Worker and point the Cloudflare Notification webhook at its URL. Set the shared secret in Cloudflare Notifications configuration and as a Worker secret:

```bash
wrangler secret put POST_DEPLOY_SECRET --env production
# Enter the same secret you configured in the Cloudflare Notifications webhook
wrangler deploy --env production
```

---

## Pattern 2 — Pages Functions onRequest Activation Probe

Pages Functions run on the same deployment as static assets and activate simultaneously. A lightweight activation probe can fire from client-side JavaScript immediately after the first page load, acting as a pseudo post-deploy hook:

```typescript
// functions/api/post-deploy-ping.ts
// Called by the site's first-load JavaScript after a new deployment is detected
export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const body = await request.json<{ deployId: string }>();

  // Record deploy ID in KV to trigger downstream revalidation
  const prev = await env.KV_CACHE.get("last-deploy-id");
  if (prev === body.deployId) {
    return Response.json({ status: "already-processed" });
  }

  await env.KV_CACHE.put("last-deploy-id", body.deployId, { expirationTtl: 604800 });

  // Trigger async revalidation (do not await — must respond quickly)
  env.waitUntil(revalidateDownstream(env));

  return Response.json({ status: "queued" });
};

async function revalidateDownstream(env: Env): Promise<void> {
  // Invalidate any stale API responses or search indexes
  await fetch("https://search.example.com/reindex", { method: "POST" });
}
```

```javascript
// site-entry.js — runs in the browser on first load
const deployId = document.head.querySelector('meta[name="deploy-id"]')?.content;
if (deployId && localStorage.getItem("last-deploy-id") !== deployId) {
  localStorage.setItem("last-deploy-id", deployId);
  navigator.sendBeacon("/api/post-deploy-ping", JSON.stringify({ deployId }));
}
```

Inject the deployment ID into the HTML `<head>` during the Pages build:

```bash
# _build.sh (called from Pages build command)
echo '<meta name="deploy-id" content="'${CF_PAGES_COMMIT_SHA}'">' >> dist/_head_inject.html
```

---

## Pattern 3 — GitHub Actions Post-Deploy Step Calling Pages API

Use the Cloudflare Pages REST API to poll for deployment completion, then run post-deploy scripts in GitHub Actions without depending on Cloudflare's outgoing webhooks.

```yaml
# .github/workflows/post-deploy.yml
name: Pages Post-Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-and-hook:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Pages via Wrangler
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: pages deploy dist --project-name=my-site --branch=main
        id: deploy

      - name: Wait for deployment to activate
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PAGES_PROJECT: my-site
        run: |
          echo "Polling for deployment activation..."
          for i in $(seq 1 30); do
            STATUS=$(curl -s \
              -H "Authorization: Bearer $CF_API_TOKEN" \
              "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PAGES_PROJECT/deployments" \
              | jq -r '.result[0].latest_stage.status')
            echo "Attempt $i: $STATUS"
            [ "$STATUS" = "success" ] && break
            [ "$STATUS" = "failure" ] && echo "Deployment failed" && exit 1
            sleep 10
          done

      - name: Run post-deploy smoke test
        run: |
          DEPLOY_URL=$(curl -s \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PAGES_PROJECT/deployments" \
            | jq -r '.result[0].url')
          curl -sf "$DEPLOY_URL/api/health" || exit 1

      - name: Notify downstream services
        env:
          NOTIFY_WEBHOOK: ${{ secrets.DOWNSTREAM_WEBHOOK }}
        run: |
          curl -X POST "$NOTIFY_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d '{"event":"deploy","project":"my-site","branch":"main"}'
```

---

## Pattern 4 — Deploy Hooks as Inbound Triggers (CMS → Pages)

Cloudflare Pages Deploy Hooks are inbound — a URL that, when called via POST, triggers a new deployment. Wire a headless CMS "on publish" event to the deploy hook to rebuild the site on content change:

```bash
# Create a deploy hook in the Cloudflare dashboard:
# Pages project → Settings → Builds & deployments → Deploy Hooks → Add hook
# Copy the generated URL, e.g.:
# https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/<token>

# Test it manually:
curl -X POST "https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/<token>"
```

In a Sanity CMS webhook configuration, point the hook URL at the Pages deploy hook. For Contentful: Settings → Webhooks → Add webhook → URL = Pages deploy hook URL, trigger on "Entry published".

Protect the hook from abuse: Cloudflare provides a unique, unguessable URL per hook, but if the URL is ever leaked, regenerate it in the dashboard. Do not embed deploy hook URLs in client-side code or commit them to version control.

---

## Anti-patterns

- **Running long-lived tasks synchronously in the post-deploy Worker**: the Cloudflare Notifications webhook must receive a 200 response within 10 seconds or the delivery is marked failed and retried. Use `waitUntil()` for work that may take longer.
- **Depending on deployment URL for cache warming before DNS propagates**: the deployment URL under `pages.dev` is immediately live, but a custom domain alias may take up to 60 seconds to propagate to all edges. Smoke tests should target the `pages.dev` URL, not the custom domain.
- **Using Deploy Hooks (inbound) for post-deploy notifications**: Deploy Hooks trigger a new *incoming* build; they do not emit notifications. Use Cloudflare Notifications for outgoing events.
- **Not validating the webhook payload signature**: anyone who discovers your Worker URL can trigger your post-deploy logic. Always validate the shared secret or a Cloudflare-issued HMAC signature.

---

## Gotchas

- The Cloudflare Notifications webhook payload schema differs between Pages deployment events. Always check `data.deployment.state` before acting — retried deliveries arrive with the same `id` but a potentially different state.
- Pages Functions on preview deployments share the same Worker namespace as production Functions; post-deploy hooks should filter by `branch === "production"` to avoid running production actions on preview builds.
- Pages deploy hooks do not transmit a build status back to the originating system — they fire-and-forget. If the triggered build later fails, the CMS is not notified. Build a polling mechanism or use the Pages REST API to query build status asynchronously.
- The Pages REST API deployment list endpoint returns deployments in reverse-chronological order; `result[0]` is always the latest deployment, but be aware that in a race with a second parallel deployment this may not be the one your CI triggered.

---

## Verification

```bash
# Confirm the Cloudflare Notification webhook was delivered
# (Dashboard: Notifications → Alert history)

# Check the Worker received and processed the event
wrangler tail post-deploy-hook --env production --format json | jq '.logs[].message'

# Verify downstream side-effects
curl -sf https://my-site.pages.dev/api/health
curl -sf https://search.example.com/status | jq '.last_reindexed'
```

---

## Related

- `cloudflare-pages-preview-deployments.md`
- `cloudflare-pages-build-cache-optimization.md`
- `deployment-verification-smoke-tests.md`
- `deployment-notification-slack.md`

---

## Sources

- Cloudflare Pages — Deploy Hooks documentation (developers.cloudflare.com/pages/configuration/deploy-hooks)
- Cloudflare Notifications — Webhook alerts (developers.cloudflare.com/notifications/get-started/configure-webhooks)
- Cloudflare Pages REST API — Deployments endpoint (developers.cloudflare.com/api/resources/pages)
- Cloudflare Workers — waitUntil() documentation (developers.cloudflare.com/workers/runtime-apis/context)
