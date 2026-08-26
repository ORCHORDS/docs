# Pages Build Hook External Trigger CI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Pages site's content comes from a headless CMS (Contentful, Sanity,
Strapi) or a monorepo where the Pages project is not the only artifact. The built-in
GitHub/GitLab integration only triggers a build on code pushes; it cannot react to CMS
content updates or be invoked by an external CI system without a code commit. You need
a stable inbound webhook that triggers a Pages build on demand.

---

## Context

Cloudflare Pages **Deploy Hooks** (also called Build Hooks) are inbound HTTP webhooks that
trigger a Pages build. They differ from post-deploy hooks (scripts that run after a build):

- A **Deploy Hook** is an HTTPS endpoint managed by Cloudflare.
- `POST` to the endpoint with any body (or empty body) triggers a build for the linked
  branch.
- Each hook is scoped to one Pages project and one branch.
- Hooks are listed and created in the dashboard under **Settings → Build → Deploy Hooks**,
  or via the Cloudflare API.
- Hook URLs contain a secret token; treat them as credentials.

Supported scenarios:

- CMS "on publish" webhook firing a Pages rebuild.
- Scheduled nightly rebuilds (for stale-while-revalidate patterns).
- External CI pipeline triggering a Pages build after upstream artifact generation.
- Manual on-demand redeployment without a code push.

---

## Creating a Deploy Hook via API

```typescript
// scripts/create-pages-build-hook.ts

const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const PROJECT_NAME = process.env.PAGES_PROJECT_NAME!;

interface DeployHookResult {
  result: {
    id: string;
    name: string;
    branch: string;
    created_on: string;
    hook_token: string;
  };
  success: boolean;
  errors: Array<{ message: string }>;
}

async function createDeployHook(hookName: string, branch: string): Promise<string> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT_NAME}/deploy_hooks`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: hookName, branch }),
    }
  );

  const data = (await res.json()) as DeployHookResult;
  if (!data.success) {
    throw new Error(`Failed to create hook: ${JSON.stringify(data.errors)}`);
  }

  const hookUrl = `https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/${data.result.hook_token}`;
  console.log(`Hook created: ${hookName}`);
  console.log(`Hook URL (store as secret): ${hookUrl}`);
  return hookUrl;
}

// Create hooks for each environment
async function setupHooks(): Promise<void> {
  await createDeployHook("cms-production", "main");
  await createDeployHook("cms-staging", "staging");
  await createDeployHook("nightly-rebuild", "main");
}

setupHooks().catch((e) => { console.error(e.message); process.exit(1); });
```

---

## Triggering a Build from a CMS Webhook (Worker Adapter)

CMS systems send their own payload format on publish events. A Worker adapter validates
the signature and normalises the event before firing the Pages hook.

```typescript
// src/cms-webhook-adapter.ts
// Deploy as a standalone Worker at https://cms-hook.example.workers.dev

interface Env {
  PAGES_DEPLOY_HOOK_URL: string;     // secret: the Pages build hook URL
  CMS_WEBHOOK_SECRET: string;        // secret: shared secret from CMS config
  ALLOWED_EVENTS: string;            // e.g. "entry.publish,entry.unpublish"
}

async function verifyContentfulSignature(
  request: Request,
  secret: string
): Promise<boolean> {
  const signature = request.headers.get("x-contentful-crn-signature") ?? "";
  const body = await request.clone().text();
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const expected = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expectedHex = Array.from(new Uint8Array(expected))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return signature === expectedHex;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    // Verify CMS signature
    const valid = await verifyContentfulSignature(request, env.CMS_WEBHOOK_SECRET);
    if (!valid) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Parse event type
    const payload = await request.json<{ sys?: { type?: string; id?: string } }>();
    const topic = request.headers.get("x-contentful-topic") ?? "";
    const allowedEvents = env.ALLOWED_EVENTS.split(",");

    if (!allowedEvents.some((e) => topic.includes(e))) {
      console.log(`Ignored event: ${topic}`);
      return Response.json({ ignored: true, topic });
    }

    // Trigger Pages build
    const hookRes = await fetch(env.PAGES_DEPLOY_HOOK_URL, { method: "POST" });
    if (!hookRes.ok) {
      console.error(`Pages hook failed: ${hookRes.status}`);
      return new Response("Hook delivery failed", { status: 502 });
    }

    const hookData = await hookRes.json<{ result: { id: string } }>();
    console.log(`Pages build triggered by CMS event ${topic}. Deploy ID: ${hookData.result.id}`);

    return Response.json({ triggered: true, deployId: hookData.result.id });
  },
};
```

---

## Scheduled Nightly Rebuild (Cron Trigger)

```typescript
// src/nightly-rebuild.ts
// Triggered by a Workers cron trigger: 0 3 * * *  (03:00 UTC nightly)

interface Env {
  PAGES_DEPLOY_HOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const res = await fetch(env.PAGES_DEPLOY_HOOK_URL, { method: "POST" });
    if (!res.ok) {
      throw new Error(`Nightly rebuild trigger failed: ${res.status}`);
    }
    const data = await res.json<{ result: { id: string } }>();
    console.log(`Nightly Pages rebuild triggered. Deploy ID: ${data.result.id}`);
  },
};
```

```toml
# wrangler.toml (nightly-rebuild Worker)
name = "nightly-rebuild"
main = "src/nightly-rebuild.ts"
compatibility_date = "2026-01-01"

[triggers]
crons = ["0 3 * * *"]

[vars]
# Do not put the hook URL here; use a secret:
# npx wrangler secret put PAGES_DEPLOY_HOOK_URL
```

---

## External CI Pipeline Triggering Pages After Upstream Artifact

```yaml
# .github/workflows/trigger-pages.yml
# Runs in the upstream repo (e.g. a design tokens package)
# after publishing an npm package; then triggers Pages rebuild.

name: Publish and Trigger Pages

on:
  push:
    tags: ["v*"]

jobs:
  publish-package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build && npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

  trigger-pages-rebuild:
    needs: publish-package
    runs-on: ubuntu-latest
    steps:
      - name: Fire Cloudflare Pages Deploy Hook
        run: |
          DEPLOY_RESPONSE=$(curl -s -X POST "${{ secrets.CF_PAGES_DEPLOY_HOOK_URL }}")
          DEPLOY_ID=$(echo "$DEPLOY_RESPONSE" | jq -r '.result.id // empty')
          echo "Triggered Pages deploy: $DEPLOY_ID"
          [ -n "$DEPLOY_ID" ] || { echo "Deploy hook failed"; exit 1; }

      - name: Poll for deploy completion
        run: |
          DEPLOY_ID="$DEPLOY_ID"  # exported from previous step via GITHUB_ENV
          for i in $(seq 1 20); do
            STATUS=$(curl -s \
              "https://api.cloudflare.com/client/v4/accounts/${{ secrets.CF_ACCOUNT_ID }}/pages/projects/${{ secrets.CF_PAGES_PROJECT }}/deployments/$DEPLOY_ID" \
              -H "Authorization: Bearer ${{ secrets.CF_API_TOKEN }}" | jq -r '.result.latest_stage.status')
            echo "Deploy status: $STATUS"
            [ "$STATUS" = "success" ] && exit 0
            [ "$STATUS" = "failure" ] && { echo "Pages deploy failed"; exit 1; }
            sleep 30
          done
          echo "Timed out waiting for Pages deploy"
          exit 1
```

---

## Managing Deploy Hooks as Infrastructure

```bash
# List existing deploy hooks for a project
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PROJECT_NAME/deploy_hooks" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, branch}'

# Delete a stale hook (by hook ID)
curl -s -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PROJECT_NAME/deploy_hooks/$HOOK_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN"

# Rotate a hook: delete old + create new, then update the secret in CMS and CI
```

---

## Anti-patterns

- **Embedding the hook URL in a public repository or CMS content** — The URL is a
  credential; anyone with it can trigger unlimited builds and incur build minutes costs.
- **No idempotency on CMS events** — A single CMS bulk-publish can fire 50+ webhook
  calls. Add a debounce (KV-backed, 60-second cooldown) in the Worker adapter to coalesce
  rapid-fire events into one build.
- **Triggering a build per individual content item update** — At scale this exhausts
  concurrent build limits. Buffer events for 30–60 seconds and trigger once.
- **Using the same hook URL across staging and production** — A CMS staging environment
  publishing to a production Pages project causes unreviewed content to go live.

---

## Gotchas

- Pages Deploy Hook URLs are immutable once created. Rotating a compromised token requires
  deleting the hook and creating a new one, then updating the CMS and all CI secrets.
- The hook POST response contains a `deployment.id` only when a new build is actually
  queued. If Pages is already building the same branch, the response may have no `id`.
- Builds triggered by a deploy hook do not carry the Git commit SHA of the triggering
  event; the deployment uses the latest commit on the configured branch at trigger time.
- Pages has a concurrent build limit per account. Rapid-fire hook triggers queue builds;
  they do not error, but builds may wait minutes before starting.
- The `branch` field on a deploy hook is set at creation time and cannot be updated.
  To change the target branch, delete and recreate the hook.

---

## Verification

```bash
# Fire the hook manually and capture the deploy ID
DEPLOY_ID=$(curl -s -X POST "$CF_PAGES_DEPLOY_HOOK_URL" | jq -r '.result.id')
echo "Deploy queued: $DEPLOY_ID"

# Poll deploy status
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PROJECT/deployments/$DEPLOY_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.latest_stage'
```

---

## Related

- `pages-deployment-hooks-post-deploy-scripts.md`
- `cloudflare-pages-preview-deployments.md`
- `deploy-notification-webhooks-slack-teams-workers.md`
- `feature-flag-deploy-coupling.md`
- `workers-cron-trigger-deployment-management.md`

---

## Sources

- https://developers.cloudflare.com/pages/configuration/deploy-hooks/
- https://developers.cloudflare.com/pages/rest-api/#deploy-hooks
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
