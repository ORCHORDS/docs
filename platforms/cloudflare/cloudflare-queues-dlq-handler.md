# Cloudflare Queues Dead Letter Queue (DLQ) Handler

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Messages in a Cloudflare Queue occasionally fail processing (transient errors, malformed payloads, downstream service outages) and exhaust their retry budget. Without a dead letter queue (DLQ), those messages are silently dropped. You need a separate DLQ consumer Worker that captures failed messages, persists them to D1, alerts your team via Slack, and exposes a replay endpoint to re-enqueue them after the root cause is resolved.

---

## Context

Cloudflare Queues support a `dead_letter_queue` field in `wrangler.toml` that routes undeliverable messages to a second queue after all retries are exhausted. The DLQ consumer receives the original message body wrapped in a DLQ envelope that includes retry metadata. Persisting failed messages to D1 enables structured querying (filter by queue name, time window, error class) and provides the source of truth for the replay endpoint. Slack webhook notifications give on-call engineers an immediate signal without requiring a full observability stack. The replay endpoint re-enqueues messages from D1 back onto the original queue so you can reprocess them after a hotfix.

---

## Section 1 — wrangler.toml

```toml
name = "main-processor"
main = "src/processor.ts"
compatibility_date = "2024-09-23"

# Primary queue — your normal message producer sends here
[[queues.consumers]]
queue = "jobs"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "jobs-dlq"   # Messages go here after 3 retries

# D1 for failed message persistence
[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<your-d1-id>"

---

# wrangler.dlq.toml  (separate Worker for the DLQ consumer)
name = "dlq-handler"
main = "src/dlq.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "jobs-dlq"
max_batch_size = 5
max_batch_timeout = 30
max_retries = 1              # DLQ itself retries once then drops

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<your-d1-id>"

[vars]
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T.../B.../xxx"
ORIGINAL_QUEUE = "jobs"

# Queues producer binding so DLQ worker can re-enqueue for replay
[[queues.producers]]
queue = "jobs"
binding = "JOBS_QUEUE"
```

---

## Section 2 — Implementation

```typescript
// src/dlq.ts
export interface Env {
  DB: D1Database;
  JOBS_QUEUE: Queue;
  SLACK_WEBHOOK_URL: string;
  ORIGINAL_QUEUE: string;
}

interface DlqMessage {
  // Cloudflare wraps the original body inside a DLQ envelope
  body: unknown;
  id: string;
  timestamp: Date;
  attempts: number;
}

export default {
  /**
   * DLQ consumer: called when messages from jobs-dlq are ready.
   */
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    const inserts: D1PreparedStatement[] = [];

    for (const msg of batch.messages) {
      const dlq = msg as unknown as DlqMessage;
      const bodyStr = JSON.stringify(dlq.body);

      inserts.push(
        env.DB.prepare(
          `INSERT INTO failed_messages
             (message_id, queue_name, body, attempts, failed_at)
           VALUES (?, ?, ?, ?, unixepoch())`
        ).bind(dlq.id, env.ORIGINAL_QUEUE, bodyStr, dlq.attempts)
      );
    }

    // Persist all failed messages atomically
    await env.DB.batch(inserts);

    // Alert Slack once per batch (avoid per-message noise)
    await notifySlack(env.SLACK_WEBHOOK_URL, batch.messages.length, env.ORIGINAL_QUEUE);

    // Acknowledge — prevents infinite DLQ re-delivery
    batch.ackAll();
  },

  /**
   * Replay endpoint: POST /replay?limit=50
   * Re-enqueues unresolved failed messages from D1.
   */
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || !new URL(request.url).pathname.startsWith("/replay")) {
      return new Response("Not found", { status: 404 });
    }

    const limit = parseInt(
      new URL(request.url).searchParams.get("limit") ?? "50",
      10
    );

    const { results } = await env.DB.prepare(
      `SELECT id, body FROM failed_messages
       WHERE resolved = 0
       ORDER BY failed_at ASC
       LIMIT ?`
    )
      .bind(Math.min(limit, 200))
      .all<{ id: number; body: string }>();

    if (results.length === 0) {
      return Response.json({ requeued: 0 });
    }

    // Send all messages back to the original queue
    await env.JOBS_QUEUE.sendBatch(
      results.map((row) => ({ body: JSON.parse(row.body) }))
    );

    // Mark as resolved in D1
    const ids = results.map((r) => r.id);
    await env.DB.prepare(
      `UPDATE failed_messages SET resolved = 1, resolved_at = unixepoch()
       WHERE id IN (${ids.map(() => "?").join(",")})`
    )
      .bind(...ids)
      .run();

    return Response.json({ requeued: results.length });
  },
};

async function notifySlack(
  webhookUrl: string,
  count: number,
  queue: string
): Promise<void> {
  const payload = {
    text: `*DLQ Alert*: ${count} message(s) failed permanently on queue \`${queue}\` and have been saved to D1 for replay.`,
  };

  const resp = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    console.error(`Slack notification failed: ${resp.status}`);
  }
}
```

---

## Section 3 — D1 Schema & Integration Testing

```sql
-- migrations/0002_failed_messages.sql
CREATE TABLE IF NOT EXISTS failed_messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT    NOT NULL,
  queue_name  TEXT    NOT NULL,
  body        TEXT    NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0,
  failed_at   INTEGER NOT NULL DEFAULT (unixepoch()),
  resolved    INTEGER NOT NULL DEFAULT 0,
  resolved_at INTEGER
);

CREATE INDEX idx_fm_resolved   ON failed_messages (resolved, failed_at);
CREATE INDEX idx_fm_queue_name ON failed_messages (queue_name);
```

```typescript
// test/dlq.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";

// Minimal mock of a MessageBatch
function makeBatch(messages: unknown[]) {
  return {
    messages: messages.map((body, i) => ({
      id: `msg-${i}`,
      body,
      timestamp: new Date(),
      attempts: 3,
      ack: vi.fn(),
      retry: vi.fn(),
    })),
    ackAll: vi.fn(),
    retryAll: vi.fn(),
    queue: "jobs-dlq",
  };
}

describe("DLQ handler", () => {
  it("persists failed messages to D1", async () => {
    const batch = makeBatch([{ orderId: 42 }, { orderId: 99 }]);

    // Import and call the queue handler
    const { default: worker } = await import("../src/dlq");
    await worker.queue(batch as never, env as never);

    const { results } = await env.DB.prepare(
      "SELECT * FROM failed_messages ORDER BY id"
    ).all();

    expect(results).toHaveLength(2);
    expect(JSON.parse((results[0] as { body: string }).body)).toEqual({ orderId: 42 });
    expect(batch.ackAll).toHaveBeenCalledOnce();
  });
});
```

---

## Anti-patterns

- **Setting `max_retries` too high on the DLQ consumer** — If the DLQ Worker itself fails (e.g., D1 is unavailable), a high retry count on the DLQ causes the message to loop; keep DLQ retries at 1.
- **Re-enqueuing from the DLQ consumer automatically** — Auto-replay without human review can amplify a bug across your entire backlog; always gate replay behind an explicit HTTP call.
- **Storing raw binary bodies as TEXT** — Queue message bodies can contain arbitrary data; JSON-serialize before storing and validate the shape on replay.
- **Sending one Slack notification per message** — Under load, a DLQ burst generates hundreds of Slack messages; batch the notification to once per `queue()` invocation.

---

## Gotchas

- `batch.ackAll()` must be called even inside the DLQ consumer; failing to acknowledge causes re-delivery up to `max_retries` times on the DLQ itself.
- The DLQ envelope does not carry the original queue name; bind it from `env.ORIGINAL_QUEUE` in `wrangler.toml` or hard-code per Worker.
- `Queue.sendBatch()` accepts at most 100 messages per call; chunk larger replays accordingly.
- D1 `IN (?, ?, ...)` placeholders must match the exact count of `bind()` arguments; build the placeholder string dynamically from the result array length.
- Slack incoming webhooks have a rate limit of 1 request per second; for high-volume DLQs, aggregate the message count and send a single summary.

---

## Verification

```bash
# Apply migration
wrangler d1 execute app-db --file=migrations/0002_failed_messages.sql --remote

# Inspect failed messages
wrangler d1 execute app-db \
  --command "SELECT id, queue_name, attempts, failed_at, resolved FROM failed_messages ORDER BY failed_at DESC LIMIT 10;" \
  --remote

# Trigger replay
curl -X POST "https://dlq-handler.<your-subdomain>.workers.dev/replay?limit=10"

# Confirm resolved flag
wrangler d1 execute app-db \
  --command "SELECT COUNT(*) AS unresolved FROM failed_messages WHERE resolved = 0;" \
  --remote
```

---

## Related

- `workers-d1-foreign-keys-cascade-delete.md`
- `workers-ai-gateway-cache-budget.md`

---

## Sources

- Cloudflare Queues Dead Letter Queues — https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Queues Consumer Configuration — https://developers.cloudflare.com/queues/configuration/configure-queues/
- Slack Incoming Webhooks — https://api.slack.com/messaging/webhooks
