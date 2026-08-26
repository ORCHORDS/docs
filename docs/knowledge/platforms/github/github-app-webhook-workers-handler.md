# GitHub App Webhook Handler in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have a GitHub App that receives webhook events and want to run the handler
entirely inside a Cloudflare Worker — no server, no Lambda. The Worker must
verify the HMAC signature, route events by type, store state in D1, and return
a 200 within GitHub's 10-second delivery timeout.

## Context

GitHub App webhooks carry an `X-Hub-Signature-256` header that contains an
HMAC-SHA256 of the raw body keyed by the App's webhook secret. Cloudflare
Workers expose the Web Crypto API, so signature verification is native with no
npm deps. Event routing, idempotency (duplicate delivery protection), and async
fan-out to Queues are the patterns that matter here.

## Signature Verification

```typescript
// src/verify.ts
export async function verifySignature(
  secret: string,
  body: string,
  sigHeader: string | null,
): Promise<boolean> {
  if (!sigHeader?.startsWith("sha256=")) return false;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const expected = "sha256=" + Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  // Constant-time compare
  if (expected.length !== sigHeader.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ sigHeader.charCodeAt(i);
  }
  return diff === 0;
}
```

## Event Router

```typescript
// src/router.ts
import { verifySignature } from "./verify";

export interface Env {
  WEBHOOK_SECRET: string;
  DB: D1Database;
  EVENT_QUEUE: Queue;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await req.text();
    const sig = req.headers.get("X-Hub-Signature-256");
    if (!(await verifySignature(env.WEBHOOK_SECRET, body, sig))) {
      return new Response("Unauthorized", { status: 401 });
    }

    const event = req.headers.get("X-GitHub-Event") ?? "unknown";
    const deliveryId = req.headers.get("X-GitHub-Delivery") ?? crypto.randomUUID();
    const payload = JSON.parse(body);

    // Idempotency guard
    const dup = await env.DB.prepare(
      "SELECT 1 FROM webhook_deliveries WHERE delivery_id = ?",
    ).bind(deliveryId).first();
    if (dup) return new Response("Already processed", { status: 200 });

    await env.DB.prepare(
      "INSERT INTO webhook_deliveries (delivery_id, event, received_at) VALUES (?, ?, ?)",
    ).bind(deliveryId, event, new Date().toISOString()).run();

    // Fan-out to Queue for async processing
    await env.EVENT_QUEUE.send({ event, deliveryId, payload });

    return new Response("Accepted", { status: 202 });
  },
};
```

## D1 Schema

```sql
-- migrations/0001_webhook_deliveries.sql
CREATE TABLE IF NOT EXISTS webhook_deliveries (
  delivery_id TEXT PRIMARY KEY,
  event       TEXT NOT NULL,
  received_at TEXT NOT NULL,
  processed   INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_wd_received ON webhook_deliveries(received_at);
```

## Queue Consumer for Async Handlers

```typescript
// src/consumer.ts
export default {
  async queue(batch: MessageBatch<{ event: string; deliveryId: string; payload: unknown }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { event, deliveryId, payload } = msg.body;
      try {
        await dispatch(event, payload as Record<string, unknown>, env);
        await env.DB.prepare("UPDATE webhook_deliveries SET processed = 1 WHERE delivery_id = ?")
          .bind(deliveryId).run();
        msg.ack();
      } catch (err) {
        console.error("handler error", event, deliveryId, err);
        msg.retry();
      }
    }
  },
};

async function dispatch(event: string, payload: Record<string, unknown>, env: Env): Promise<void> {
  if (event === "pull_request" && payload.action === "opened") {
    await handlePROpened(payload, env);
  }
  if (event === "push") {
    await handlePush(payload, env);
  }
}

async function handlePROpened(payload: Record<string, unknown>, _env: Env): Promise<void> {
  console.log("PR opened", (payload.pull_request as Record<string, unknown>)?.number);
}

async function handlePush(payload: Record<string, unknown>, _env: Env): Promise<void> {
  console.log("push to", payload.ref);
}
```

## wrangler.toml

```toml
name = "github-app-webhook"
main = "src/router.ts"
compatibility_date = "2025-09-01"

[[queues.consumers]]
queue = "github-events"
max_batch_size = 10
max_batch_timeout = 5

[[queues.producers]]
queue = "github-events"
binding = "EVENT_QUEUE"

[[d1_databases]]
binding = "DB"
database_name = "github-webhooks"
database_id = "YOUR_D1_ID"
```

## Anti-patterns

- **Reading `req.body` twice** — clone the request or cache `req.text()` in a variable before passing to verifier and parser.
- **Async handler in the fetch handler** — returning 200 after awaiting slow logic risks GitHub marking the delivery as failed. Use Queue fan-out.
- **String comparison for HMAC** — early-exit `===` leaks timing. Use the constant-time loop above.
- **Storing raw payload in D1** — large payloads bloat the DB. Store only the delivery ID and event type; fetch from GitHub API if full payload is needed later.

## Gotchas

- GitHub retries unacknowledged deliveries (no 2xx within 10s) up to 3 times with exponential back-off; idempotency guard in D1 prevents double-processing.
- `X-GitHub-Event` is the event name; `X-GitHub-Delivery` is the UUID for that specific delivery — both headers are required for routing and dedup.
- Workers' `crypto.subtle` requires the secret as a `BufferSource`, not a string — always `TextEncoder.encode()` first.
- Queue `msg.retry()` respects the queue's max-retries setting; set `max_retries = 3` in wrangler.toml for dead-letter behavior.

## Verification

```bash
# Local smoke test with correct signature
SECRET="my-secret"
BODY='{"action":"opened"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print "sha256="$2}')
curl -X POST http://localhost:8787 \
  -H "X-Hub-Signature-256: $SIG" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-GitHub-Delivery: test-1" \
  -H "Content-Type: application/json" \
  -d "$BODY"
# Expect: 202 Accepted
```

## Related

- `github-webhook-signing-verification.md`
- `github-apps-installation-tokens.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`

## Sources

- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
