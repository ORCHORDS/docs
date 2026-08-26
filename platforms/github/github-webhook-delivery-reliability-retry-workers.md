# GitHub Webhook Delivery Reliability and Retry with Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker is the webhook endpoint for a GitHub App. Under normal
load deliveries arrive and process within milliseconds, but during traffic spikes
or Worker cold starts you see `delivery failed` entries in the GitHub App's
delivery log. You need to understand GitHub's retry model, harden the Worker
handler to respond `200` quickly, and set up a re-delivery mechanism so missed
events never cause silent data loss.

---

## Context

GitHub delivers webhooks with a **10-second timeout** per attempt. If the
endpoint does not respond with a 2xx status within that window, GitHub marks the
delivery as failed. GitHub retries automatically for **organisation and
repository webhooks** but **not for GitHub App webhooks** in the same way —
App deliveries must be manually re-delivered via the API. For a example project Worker
acting as the App's handler, the design must:

1. Respond `200 OK` immediately (before any async processing).
2. Hand off work to a Cloudflare Queue or Durable Object for durability.
3. Monitor for delivery failures and trigger re-delivery automatically.

---

## Handler Pattern — Fast Acknowledge, Async Process

```typescript
// workers/webhook-handler/src/index.ts
import { Queue } from "@cloudflare/workers-types";

export interface Env {
  WEBHOOK_SECRET: string;
  EVENTS_QUEUE: Queue<GitHubWebhookPayload>;
}

interface GitHubWebhookPayload {
  deliveryId: string;
  event: string;
  body: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // ── 1. Validate signature before touching the body ──────────────────────
    const signature = request.headers.get("x-hub-signature-256");
    const deliveryId = request.headers.get("x-github-delivery") ?? "unknown";
    const event = request.headers.get("x-github-event") ?? "unknown";

    if (!signature) {
      return new Response("Missing signature", { status: 401 });
    }

    const rawBody = await request.text();

    const valid = await verifySignature(rawBody, signature, env.WEBHOOK_SECRET);
    if (!valid) {
      return new Response("Invalid signature", { status: 401 });
    }

    // ── 2. Enqueue for async processing — respond immediately ───────────────
    await env.EVENTS_QUEUE.send(
      { deliveryId, event, body: rawBody },
      { contentType: "json" }
    );

    // GitHub requires 2xx within 10 s; 202 signals accepted-but-not-processed
    return new Response(null, { status: 202 });
  },
} satisfies ExportedHandler<Env>;

async function verifySignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const expected =
    "sha256=" +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  // Constant-time compare
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return diff === 0;
}
```

---

## Queue Consumer — Idempotent Event Processing

```typescript
// workers/webhook-handler/src/queue-consumer.ts
export default {
  async queue(
    batch: MessageBatch<GitHubWebhookPayload>,
    env: Env
  ): Promise<void> {
    for (const message of batch.messages) {
      const { deliveryId, event, body } = message.body;

      try {
        await processEvent(event, JSON.parse(body), env);
        message.ack();
      } catch (err) {
        console.error(`Failed to process delivery ${deliveryId}:`, err);
        // Retry via Queue's built-in retry (up to maxRetries)
        message.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function processEvent(
  event: string,
  payload: unknown,
  env: Env
): Promise<void> {
  // Route by event type
  switch (event) {
    case "push":
      await handlePush(payload as PushPayload, env);
      break;
    case "pull_request":
      await handlePullRequest(payload as PullRequestPayload, env);
      break;
    default:
      console.log(`Unhandled event type: ${event}`);
  }
}
```

`wrangler.toml` binding:

```toml
[[queues.producers]]
queue = "github-webhook-events"
binding = "EVENTS_QUEUE"

[[queues.consumers]]
queue = "github-webhook-events"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "github-webhook-dlq"
retry_delay = "30s"
```

---

## Monitoring Delivery Failures — GitHub API Polling

GitHub App webhook deliveries are queryable via the API. Run this as a scheduled
Worker or GitHub Actions cron to detect and re-deliver failed deliveries:

```typescript
// workers/webhook-monitor/src/index.ts
import { createAppAuth } from "@octokit/auth-app";
import { Octokit } from "@octokit/rest";

export interface Env {
  APP_ID: string;
  APP_PRIVATE_KEY: string; // PEM stored in secret
  ALERT_QUEUE: Queue<string>;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const auth = createAppAuth({
      appId: env.APP_ID,
      privateKey: env.APP_PRIVATE_KEY,
    });

    const { token } = await auth({ type: "app" });
    const octokit = new Octokit({ auth: token });

    // Fetch last 100 deliveries
    const { data: deliveries } =
      await octokit.rest.apps.listWebhookDeliveries({ per_page: 100 });

    const failed = deliveries.filter(
      (d) =>
        d.status === "Invalid HTTP Response Code" ||
        d.status === "Timed Out" ||
        (d.response_code !== null && d.response_code >= 400)
    );

    for (const delivery of failed) {
      // Only re-deliver if within last 24 hours
      const age = Date.now() - new Date(delivery.delivered_at).getTime();
      if (age > 86_400_000) continue;

      console.log(`Re-delivering ${delivery.id} (${delivery.action})`);
      await octokit.rest.apps.redeliverWebhookDelivery({
        delivery_id: delivery.id,
      });

      // Alert for visibility
      await env.ALERT_QUEUE.send(
        `Redelivered failed webhook ${delivery.id}: ${delivery.action}`,
        { contentType: "text" }
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## GitHub Actions — Scheduled Re-delivery Check

Alternative to a scheduled Worker when you don't want a second Worker deployed:

```yaml
# .github/workflows/webhook-redeliver-failed.yml
name: Re-deliver Failed Webhooks

on:
  schedule:
    - cron: "*/15 * * * *"   # every 15 minutes
  workflow_dispatch:

permissions:
  contents: read

jobs:
  redeliver:
    runs-on: ubuntu-24.04
    steps:
      - name: Re-deliver failed App webhook deliveries
        env:
          GH_TOKEN: ${{ secrets.GH_APP_TOKEN }}  # App installation token
          APP_ID: ${{ vars.GH_APP_ID }}
        run: |
          gh api /app/hook/deliveries --paginate \
            --jq '.[] | select(.status != "OK") | .id' \
          | while read id; do
              delivered_at=$(gh api /app/hook/deliveries/"$id" \
                --jq '.delivered_at')
              age=$(( $(date +%s) - $(date -d "$delivered_at" +%s) ))
              if [ "$age" -lt 86400 ]; then
                echo "Re-delivering delivery $id"
                gh api --method POST /app/hook/deliveries/"$id"/attempts
              fi
            done
```

---

## Delivery Deduplication

The same event can be delivered more than once (GitHub guarantees **at-least-once**
delivery). Use the `x-github-delivery` UUID as the idempotency key:

```typescript
// In Durable Object or D1 — idempotency check
async function isAlreadyProcessed(deliveryId: string, env: Env): Promise<boolean> {
  const result = await env.DB.prepare(
    "SELECT 1 FROM processed_deliveries WHERE delivery_id = ? LIMIT 1"
  )
    .bind(deliveryId)
    .first();
  return result !== null;
}

async function markProcessed(deliveryId: string, env: Env): Promise<void> {
  await env.DB.prepare(
    "INSERT OR IGNORE INTO processed_deliveries (delivery_id, processed_at) VALUES (?, ?)"
  )
    .bind(deliveryId, new Date().toISOString())
    .run();
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS processed_deliveries (
  delivery_id TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);

-- TTL cleanup (run periodically)
DELETE FROM processed_deliveries
WHERE processed_at < datetime('now', '-7 days');
```

---

## Anti-patterns

- **Processing the event synchronously before returning `200`**: if processing
  takes more than 10 seconds, GitHub marks the delivery failed even though your
  code succeeded. Always acknowledge first.
- **Returning `200` without verifying the HMAC signature**: an attacker can
  inject arbitrary payloads. Verify before enqueueing.
- **Storing the full payload in a Durable Object instead of a Queue**: Durable
  Objects have per-key storage limits and are not designed for high-throughput
  event buffering. Use Cloudflare Queues.
- **Re-delivering without checking the delivery age**: GitHub retains delivery
  history for 72 hours. Re-delivering deliveries older than your processing
  window causes duplicate side effects.
- **Using a single Queue consumer concurrency of 1**: this creates a processing
  bottleneck during bursts. Set `max_concurrent_consumers` appropriately.

---

## Gotchas

- GitHub App webhook deliveries have **no automatic retry** — only organisation
  and repository webhook deliveries retry up to 3× on failure. App deliveries
  need the `/app/hook/deliveries/{id}/attempts` API call.
- The delivery history endpoint returns deliveries in reverse-chronological
  order. Paginate carefully; `--paginate` in `gh` CLI loads all pages.
- `x-github-delivery` UUIDs are unique per _delivery attempt_, not per event.
  A re-delivered event gets a new `delivery_id`. Use the event payload's action
  and resource IDs for true idempotency, not the delivery UUID.
- Workers deployed behind a custom domain need the Cloudflare IP allowlist if
  GitHub's webhook IPs change. Consider using Cloudflare's IP geolocation
  header instead of restricting by source IP.

---

## Verification

```bash
# List last 10 App deliveries and their status
gh api /app/hook/deliveries --jq '.[:10] | .[] | {id, status, action: .action}'

# Check a specific delivery
gh api /app/hook/deliveries/<id>

# Manually re-deliver
gh api --method POST /app/hook/deliveries/<id>/attempts

# Check Queue dead-letter queue for unprocessable messages
wrangler queues list
wrangler tail --name github-webhook-dlq
```

---

## Related

- `github-app-webhook-workers-handler.md`
- `github-webhook-signing-verification.md`
- `github-webhooks-event-handling.md`
- `github-actions-cloudflare-queues-workers-deploy.md`

---

## Sources

- GitHub Docs — Webhook delivery guarantees: https://docs.github.com/en/webhooks/about-webhooks
- GitHub Docs — Re-delivering webhook deliveries: https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/redelivering-webhooks
- GitHub REST API — App webhook deliveries: https://docs.github.com/en/rest/apps/webhooks
- Cloudflare Docs — Queues dead-letter queues: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
