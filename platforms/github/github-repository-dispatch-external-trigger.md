# Triggering GitHub Workflows via repository_dispatch from Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

An external system — a Cloudflare Worker handling a webhook, a D1-backed cron job, or a
third-party SaaS — needs to kick off a GitHub Actions workflow without going through a commit
or a pull request. `repository_dispatch` is the GitHub API event designed for exactly this:
send a typed event with a JSON payload, and the corresponding workflow runs.

## Context

`repository_dispatch` is a REST API endpoint (`POST /repos/{owner}/{repo}/dispatches`) that
injects a custom event into the repository's workflow engine. Workflows subscribe to it with
`on: repository_dispatch` and optionally filter on `event_type`. The caller supplies an
arbitrary `client_payload` object (up to 10 MB) that flows into workflow expressions as
`github.event.client_payload`.

Supported authentication: PAT with `repo` scope, GitHub App installation token with
`contents: write` or `actions: write` permission, or a fine-grained PAT with
"Actions: write" repository permission.

---

## Sending repository_dispatch from a Cloudflare Worker

```typescript
// src/dispatch.ts — helper used by Worker handlers
export interface DispatchOptions {
  owner:        string;
  repo:         string;
  eventType:    string;
  clientPayload: Record<string, unknown>;
  token:        string;            // GitHub App installation token or PAT
}

export async function dispatchWorkflow(opts: DispatchOptions): Promise<void> {
  const url = `https://api.github.com/repos/${opts.owner}/${opts.repo}/dispatches`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept:        "application/vnd.github+json",
      Authorization: `Bearer ${opts.token}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "orchords-worker/1.0",
    },
    body: JSON.stringify({
      event_type:     opts.eventType,
      client_payload: opts.clientPayload,
    }),
  });

  // 204 No Content = success; anything else is an error
  if (res.status !== 204) {
    const body = await res.text();
    throw new Error(`repository_dispatch failed ${res.status}: ${body}`);
  }
}
```

```typescript
// src/worker.ts — Cloudflare Worker triggered by a Stripe webhook
import { dispatchWorkflow } from "./dispatch";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/webhook/stripe") {
      return new Response("Not found", { status: 404 });
    }

    // Validate Stripe signature (abbreviated — use proper HMAC check)
    const body   = await request.text();
    const event  = JSON.parse(body) as { type: string; data: { object: { id: string } } };

    if (event.type === "checkout.session.completed") {
      await dispatchWorkflow({
        owner:        "orchords",
        repo:         "platform",
        eventType:    "stripe-checkout-completed",
        clientPayload: {
          session_id:  event.data.object.id,
          environment: "production",
          triggered_at: new Date().toISOString(),
        },
        token: env.GITHUB_DISPATCH_TOKEN,
      });
    }

    return new Response("OK", { status: 200 });
  },
} satisfies ExportedHandler<Env>;

interface Env {
  GITHUB_DISPATCH_TOKEN: string;
}
```

---

## Workflow: Receiving and Filtering the Event

```yaml
# .github/workflows/stripe-checkout.yml
name: Handle Stripe Checkout

on:
  repository_dispatch:
    types:
      - stripe-checkout-completed   # filter to one event_type

jobs:
  provision:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Print event payload
        run: |
          echo "Session ID : ${{ github.event.client_payload.session_id }}"
          echo "Environment: ${{ github.event.client_payload.environment }}"
          echo "Triggered  : ${{ github.event.client_payload.triggered_at }}"

      - name: Provision customer resources
        env:
          SESSION_ID:  ${{ github.event.client_payload.session_id }}
          CF_TOKEN:    ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT:  ${{ vars.CF_ACCOUNT_ID }}
        run: node scripts/provision.mjs
```

Without `types:` the workflow runs for **every** `repository_dispatch` event type — scope it.

---

## Using a GitHub App Token (Preferred over PAT)

Generate a short-lived installation token inside the Worker instead of storing a long-lived
PAT. This avoids token rotation headaches and scopes the credential to a single repository.

```typescript
// src/github-app-auth.ts
import { SignJWT, importPKCS8 } from "jose";           // bundled with Worker

export async function getInstallationToken(
  appId: string,
  privateKeyPem: string,
  installationId: string
): Promise<string> {
  // 1. Build JWT signed with the app private key
  const key = await importPKCS8(privateKeyPem, "RS256");
  const now = Math.floor(Date.now() / 1000);

  const jwt = await new SignJWT({})
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt(now - 60)
    .setExpirationTime(now + 600)
    .setIssuer(appId)
    .sign(key);

  // 2. Exchange JWT for an installation access token
  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Accept:        "application/vnd.github+json",
        Authorization: `Bearer ${jwt}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "orchords-worker/1.0",
      },
    }
  );

  if (!res.ok) throw new Error(`Token exchange failed: ${res.status}`);
  const json = (await res.json()) as { token: string };
  return json.token;
}
```

Cache the installation token in a KV namespace (TTL 55 minutes; tokens last 60) to avoid an
extra API call per dispatch.

---

## Passing Structured Data and Accessing Nested Paths

`client_payload` is a plain JSON object. Access nested values with standard expression syntax:

```yaml
# Access nested payload keys
- run: echo "${{ github.event.client_payload.metadata.customer_id }}"
```

```typescript
// Deep payload example from the Worker
clientPayload: {
  session_id: "cs_live_abc123",
  metadata: {
    customer_id: "cust_xyz",
    plan:        "pro",
  },
  idempotency_key: crypto.randomUUID(),
},
```

Include an `idempotency_key` in every dispatch payload so the receiving workflow can detect
and skip duplicate events stored in D1.

---

## Rate Limits and Retries

The dispatches endpoint is subject to the REST API secondary rate limit (typically 100
requests/minute for authenticated app tokens). For high-volume triggers, fan out via a
Cloudflare Queue: write events to the Queue, and a Consumer Worker batches dispatches at a
controlled rate.

```typescript
// Consumer Worker — batch dispatch with exponential back-off
export default {
  async queue(batch: MessageBatch<DispatchOptions>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await dispatchWorkflow({ ...msg.body, token: env.GITHUB_DISPATCH_TOKEN });
        msg.ack();
      } catch (err) {
        // Queue retries with back-off on nack
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Using `workflow_dispatch` when external systems are the caller** — `workflow_dispatch`
  requires a `ref` and targets a specific branch; `repository_dispatch` is for external
  triggers and does not tie the payload to a branch.
- **Storing a `repo`-scoped PAT in Worker secrets long-term** — the token grants broad write
  access. Prefer a GitHub App installation token cached in KV and rotated automatically.
- **Including secrets in `client_payload`** — the payload is visible in the Actions run
  log. Pass an opaque reference (session ID, record key) and have the workflow fetch the
  secret from its own store.
- **Omitting `event_type` filtering in the workflow** — a workflow without `types:` receives
  all `repository_dispatch` events, including ones from unrelated systems.

---

## Gotchas

- The response is always `204 No Content` on success; there is no `run_id` in the response
  body. To trace which run was triggered, embed a UUID in `client_payload` and search
  workflow runs by input after a delay.
- `repository_dispatch` only runs workflows on the **default branch**. There is no way to
  dispatch to a feature branch via this event — use `workflow_dispatch` for that.
- Workflows triggered by `repository_dispatch` show actor as the token owner (PAT user or
  app bot), not the original event actor.
- The 10 MB `client_payload` limit sounds large but Actions expression strings have a 256 KB
  cap; avoid putting very large objects in deeply nested fields accessed via expressions.

---

## Verification

```bash
# Manual dispatch with curl
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/example-org/example-repo \
  -d '{"event_type":"stripe-checkout-completed","client_payload":{"session_id":"test-123"}}'
# Expect HTTP 204

# List recent workflow runs triggered by repository_dispatch
gh run list --workflow=stripe-checkout.yml --limit 5
```

---

## Related

- `github-actions-workflow-dispatch.md` — user-triggered manual dispatches
- `github-actions-cloudflare-deploy-workflow.md` — Workers deploy workflows
- `github-app-webhook-workers-handler.md` — GitHub App webhook handling in Workers
- `github-webhook-signing-verification.md` — securing inbound webhooks

---

## Sources

- https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#repository_dispatch
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- https://developers.cloudflare.com/queues/
