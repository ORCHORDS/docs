# GitHub Issue Webhook Routing with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to receive GitHub issue webhooks in a Cloudflare Worker, verify their authenticity, route events to different downstream systems based on event type, and handle retries without processing the same event twice.

## Context

GitHub sends webhook payloads signed with HMAC-SHA256 using a shared secret. A Worker sitting at the webhook endpoint must validate each signature before processing, then fan-out to Cloudflare Queues (or other destinations) according to the `action` field inside the `issues` event. Without deduplication, GitHub's retry mechanism (3 attempts over ~1 hour) causes duplicate side-effects in downstream services.

Key constraints:
- Webhooks must respond within 10 seconds or GitHub marks the delivery failed.
- The Worker must be stateless; state lives in KV (deduplication) and Queues (async processing).
- All heavy work happens in a Queue consumer, not in the webhook handler itself.

## Solution

### 1. Wrangler configuration

```toml
# wrangler.toml
name = "issue-webhook-router"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[queues.producers]]
binding = "QUEUE_OPENED"
queue = "issues-opened"

[[queues.producers]]
binding = "QUEUE_CLOSED"
queue = "issues-closed"

[[queues.producers]]
binding = "QUEUE_LABELED"
queue = "issues-labeled"

[[queues.producers]]
binding = "QUEUE_ASSIGNED"
queue = "issues-assigned"

[[kv_namespaces]]
binding = "DEDUP_KV"
id = "<your-kv-namespace-id>"

[vars]
GITHUB_WEBHOOK_SECRET = "replace-at-deploy-time"
```

### 2. Types

```typescript
// src/types.ts
export interface Env {
  QUEUE_OPENED: Queue;
  QUEUE_CLOSED: Queue;
  QUEUE_LABELED: Queue;
  QUEUE_ASSIGNED: Queue;
  DEDUP_KV: KVNamespace;
  GITHUB_WEBHOOK_SECRET: string;
}

export interface GitHubIssuePayload {
  action: "opened" | "closed" | "labeled" | "unlabeled" | "assigned" | "unassigned" | string;
  issue: {
    id: number;
    number: number;
    title: string;
    body: string | null;
    state: "open" | "closed";
    labels: Array<{ name: string; color: string }>;
    assignees: Array<{ login: string }>;
    created_at: string;
    updated_at: string;
    closed_at: string | null;
    html_url: string;
    user: { login: string };
  };
  repository: {
    full_name: string;
    id: number;
  };
  sender: { login: string };
  label?: { name: string };
  assignee?: { login: string };
}

export type IssueQueueMessage = {
  deliveryId: string;
  receivedAt: string;
  payload: GitHubIssuePayload;
};
```

### 3. HMAC-SHA256 signature verification

```typescript
// src/verify.ts
export async function verifySignature(
  request: Request,
  body: string,
  secret: string
): Promise<boolean> {
  const sigHeader = request.headers.get("x-hub-signature-256");
  if (!sigHeader || !sigHeader.startsWith("sha256=")) return false;

  const receivedHex = sigHeader.slice(7); // strip "sha256="

  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const msgData = encoder.encode(body);

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signature = await crypto.subtle.sign("HMAC", cryptoKey, msgData);
  const computedHex = Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Constant-time comparison to prevent timing attacks
  if (computedHex.length !== receivedHex.length) return false;
  let diff = 0;
  for (let i = 0; i < computedHex.length; i++) {
    diff |= computedHex.charCodeAt(i) ^ receivedHex.charCodeAt(i);
  }
  return diff === 0;
}
```

### 4. Deduplication via KV

```typescript
// src/dedup.ts
const DEDUP_TTL_SECONDS = 60 * 60 * 6; // 6 hours — covers all GitHub retry windows

export async function isAlreadyProcessed(
  kv: KVNamespace,
  deliveryId: string
): Promise<boolean> {
  const existing = await kv.get(`dedup:${deliveryId}`);
  return existing !== null;
}

export async function markProcessed(
  kv: KVNamespace,
  deliveryId: string
): Promise<void> {
  await kv.put(`dedup:${deliveryId}`, "1", {
    expirationTtl: DEDUP_TTL_SECONDS,
  });
}
```

### 5. Main router

```typescript
// src/index.ts
import { verifySignature } from "./verify";
import { isAlreadyProcessed, markProcessed } from "./dedup";
import type { Env, GitHubIssuePayload, IssueQueueMessage } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const eventType = request.headers.get("x-github-event");
    const deliveryId = request.headers.get("x-github-delivery");

    if (!eventType || !deliveryId) {
      return new Response("Missing required GitHub headers", { status: 400 });
    }

    // Only handle issue events from this endpoint
    if (eventType !== "issues") {
      return new Response("Ignored", { status: 200 });
    }

    const body = await request.text();

    // Signature check
    const valid = await verifySignature(request, body, env.GITHUB_WEBHOOK_SECRET);
    if (!valid) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Deduplication check
    if (await isAlreadyProcessed(env.DEDUP_KV, deliveryId)) {
      console.log(`Duplicate delivery ${deliveryId} — skipping`);
      return new Response("Already processed", { status: 200 });
    }

    let payload: GitHubIssuePayload;
    try {
      payload = JSON.parse(body) as GitHubIssuePayload;
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const message: IssueQueueMessage = {
      deliveryId,
      receivedAt: new Date().toISOString(),
      payload,
    };

    // Route to the correct Queue by action
    switch (payload.action) {
      case "opened":
        await env.QUEUE_OPENED.send(message);
        break;
      case "closed":
        await env.QUEUE_CLOSED.send(message);
        break;
      case "labeled":
      case "unlabeled":
        await env.QUEUE_LABELED.send(message);
        break;
      case "assigned":
      case "unassigned":
        await env.QUEUE_ASSIGNED.send(message);
        break;
      default:
        // Unhandled action — acknowledge without queuing
        console.log(`Unhandled issue action: ${payload.action}`);
    }

    // Mark as processed only after successful enqueue
    await markProcessed(env.DEDUP_KV, deliveryId);

    return new Response("Accepted", { status: 202 });
  },
} satisfies ExportedHandler<Env>;
```

### 6. Queue consumer example (issues-opened)

```typescript
// src/consumer-opened.ts
import type { Env, IssueQueueMessage } from "./types";

export default {
  async queue(batch: MessageBatch<IssueQueueMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { payload, deliveryId } = msg.body;
      try {
        console.log(
          `Processing opened issue #${payload.issue.number} in ${payload.repository.full_name} (delivery ${deliveryId})`
        );
        // Insert your downstream logic here: e.g., post to Slack, create a D1 record, etc.
        msg.ack();
      } catch (err) {
        console.error(`Failed to process ${deliveryId}:`, err);
        msg.retry(); // Queues will retry with exponential backoff
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

**Signature verification flow:**
1. Read the raw request body as text (before any JSON parsing — parsing changes byte ordering in some edge cases).
2. Re-encode with `TextEncoder` and sign with `crypto.subtle` using the shared secret.
3. Compare with constant-time XOR loop to prevent timing side-channels.

**Queue routing rationale:**
- Separate queues per action type allow independent scaling, DLQ configuration, and consumer isolation.
- If you only need one downstream system, a single queue with the action embedded in the message body is simpler.

**KV deduplication TTL:**
- GitHub retries up to 3 times over ~1 hour. A 6-hour TTL comfortably covers this.
- KV eventual consistency means a very tight race (two deliveries within milliseconds) could slip through. For strict exactly-once, use a D1 `INSERT OR IGNORE` with a unique index on `delivery_id`.

**Response timing:**
- `Queue.send()` is non-blocking from the Worker's perspective (fire-and-queue). Total handler time stays well under 10 seconds even for high-throughput repos.
- Heavy work (API calls, DB writes) belongs in the queue consumer, not the webhook handler.

## Anti-patterns

- **Do not parse JSON before verifying the signature.** The raw body bytes must be used for HMAC.
- **Do not use `crypto.subtle` with `verify` on the received hex directly.** Convert hex to a `Uint8Array` correctly or compare hex strings with a constant-time loop.
- **Do not ignore the `x-github-event` header.** The same endpoint may receive `push`, `pull_request`, and other events depending on your webhook configuration.
- **Do not store dedup keys without TTL.** KV has per-namespace storage limits; stale keys accumulate quickly on busy repos.
- **Do not acknowledge the message before the downstream work completes.** Call `msg.ack()` only inside a try block after success.

## Gotchas

- GitHub sends a `ping` event when a webhook is first registered. Return 200 for `ping` events to avoid false failure notifications in the GitHub UI.
- `x-github-delivery` is a UUID per delivery attempt, not per logical event. The same logical event (e.g., issue #<number> closed) retried three times will have three different delivery IDs but the same `issue.id` + `action`.
- Queue consumers run in a separate Worker invocation. The `Env` bindings available to the consumer must be declared in `wrangler.toml` under `[[queues.consumers]]`.
- If the Worker throws before `markProcessed`, the next retry will re-process. Design consumers to be idempotent regardless of the KV dedup layer.
- Workers AI and Vectorize calls inside webhook handlers add latency. Always defer them to queue consumers.

## Verification

```bash
# 1. Deploy
npx wrangler deploy

# 2. Send a test webhook using the GitHub CLI (requires repo admin)
gh api \
  --method POST \
  -H "x-github-event: issues" \
  -H "x-hub-signature-256: sha256=$(echo -n '{"action":"opened"}' | openssl dgst -sha256 -hmac 'your-secret' | awk '{print $2}')" \
  -H "x-github-delivery: test-delivery-001" \
  https://<your-worker>.workers.dev

# 3. Check Queue metrics in the Cloudflare dashboard
# Workers & Pages > Queues > issues-opened > Messages delivered

# 4. Confirm dedup entry in KV
npx wrangler kv key get --binding DEDUP_KV "dedup:test-delivery-001"
```

## Related

- `workers-issue-sla-tracker-d1.md` — consuming the opened/closed events for SLA tracking
- `workers-issue-deduplication-embedding.md` — using the opened event payload for duplicate detection
- `workers-issue-template-enforcement.md` — validating template completeness on the opened event

## Sources

- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
