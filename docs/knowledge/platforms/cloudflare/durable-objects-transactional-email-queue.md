# Durable Objects as Transactional Email Queue with Idempotency

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need to send transactional emails (order confirmations, password resets, invoice receipts) exactly-once per business event, even when a Worker retries or a downstream email API (SendGrid, Resend, Mailgun) returns a transient 5xx — without a Redis-backed deduplication store or an external message broker.

## Context
Cloudflare Queues provides at-least-once delivery with a DLQ, but email services charge per send and users are harmed by duplicates. A Durable Object with SQLite storage solves this: the DO records each email job with a stable idempotency key before calling the provider, marks it `sent` atomically, and ignores retries for already-sent keys. DO alarms drive retry back-off; the Worker is just a thin producer. This pattern requires the `durable_object_alarms` compatibility flag (enabled by default since compat date 2024-04-01).

## Wrangler Configuration

```toml
# wrangler.toml
name = "email-queue-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[durable_objects.bindings]]
name = "EMAIL_QUEUE"
class_name = "EmailQueue"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["EmailQueue"]

[vars]
EMAIL_PROVIDER_URL = "https://api.resend.com/emails"

# Set secrets:
# wrangler secret put EMAIL_API_KEY
# wrangler secret put EMAIL_QUEUE_SECRET   (shared secret for Worker→DO auth)
```

## Durable Object: Email Queue

```typescript
// src/email-queue-do.ts
import { DurableObject } from "cloudflare:workers";

export interface Env {
  EMAIL_API_KEY: string;
  EMAIL_PROVIDER_URL: string;
}

interface EmailJob {
  id: string;           // idempotency key (e.g. "order-confirm-<order_id>")
  to: string;
  subject: string;
  html: string;
  status: "pending" | "sending" | "sent" | "failed";
  attempts: number;
  scheduledAt: number;  // Unix ms
  sentAt: number | null;
  lastError: string | null;
}

const MAX_ATTEMPTS = 5;
const RETRY_DELAYS_MS = [5_000, 15_000, 60_000, 300_000, 900_000]; // 5s, 15s, 1m, 5m, 15m

export class EmailQueue extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Create schema on first access
    this.ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS email_jobs (
          id           TEXT PRIMARY KEY,
          to_addr      TEXT NOT NULL,
          subject      TEXT NOT NULL,
          html         TEXT NOT NULL,
          status       TEXT NOT NULL DEFAULT 'pending',
          attempts     INTEGER NOT NULL DEFAULT 0,
          scheduled_at INTEGER NOT NULL,
          sent_at      INTEGER,
          last_error   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_status_scheduled
          ON email_jobs (status, scheduled_at);
      `);
    });
  }

  // Enqueue: idempotent — duplicate keys are silently ignored
  async enqueue(job: Omit<EmailJob, "status" | "attempts" | "scheduledAt" | "sentAt" | "lastError">): Promise<{ queued: boolean }> {
    const now = Date.now();

    const existing = this.ctx.storage.sql
      .exec("SELECT id FROM email_jobs WHERE id = ?", job.id)
      .toArray();

    if (existing.length > 0) {
      return { queued: false }; // already enqueued or sent
    }

    this.ctx.storage.sql.exec(
      `INSERT INTO email_jobs (id, to_addr, subject, html, status, attempts, scheduled_at)
       VALUES (?, ?, ?, ?, 'pending', 0, ?)`,
      job.id, job.to, job.subject, job.html, now
    );

    // Schedule immediate processing
    await this.ctx.storage.setAlarm(now + 100);
    return { queued: true };
  }

  async alarm(): Promise<void> {
    const now = Date.now();

    // Fetch all pending/retryable jobs due now
    const rows = this.ctx.storage.sql
      .exec<EmailJob>(
        `SELECT id, to_addr AS "to", subject, html, status, attempts, scheduled_at AS "scheduledAt", sent_at AS "sentAt", last_error AS "lastError"
         FROM email_jobs
         WHERE status IN ('pending', 'failed') AND attempts < ? AND scheduled_at <= ?
         ORDER BY scheduled_at ASC
         LIMIT 10`,
        MAX_ATTEMPTS, now
      )
      .toArray();

    if (rows.length === 0) return;

    for (const job of rows) {
      await this.processJob(job);
    }

    // Reschedule if more jobs remain
    const remaining = this.ctx.storage.sql
      .exec(
        `SELECT COUNT(*) AS n FROM email_jobs WHERE status IN ('pending','failed') AND attempts < ?`,
        MAX_ATTEMPTS
      )
      .one() as { n: number };

    if (remaining.n > 0) {
      await this.ctx.storage.setAlarm(Date.now() + 1000);
    }
  }

  private async processJob(job: EmailJob): Promise<void> {
    // Mark as sending (idempotency guard)
    this.ctx.storage.sql.exec(
      "UPDATE email_jobs SET status = 'sending', attempts = attempts + 1 WHERE id = ? AND status != 'sent'",
      job.id
    );

    try {
      const res = await fetch(this.env.EMAIL_PROVIDER_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.env.EMAIL_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: "noreply@yourapp.com",
          to: [job.to],
          subject: job.subject,
          html: job.html,
        }),
      });

      if (res.ok) {
        this.ctx.storage.sql.exec(
          "UPDATE email_jobs SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ?",
          Date.now(), job.id
        );
        return;
      }

      const errorText = await res.text();
      // 4xx = permanent failure (bad address etc.); do not retry
      if (res.status >= 400 && res.status < 500) {
        this.ctx.storage.sql.exec(
          "UPDATE email_jobs SET status = 'failed', last_error = ? WHERE id = ?",
          `HTTP ${res.status}: ${errorText}`, job.id
        );
        return;
      }

      throw new Error(`Provider ${res.status}: ${errorText}`);
    } catch (err) {
      const attempts = job.attempts + 1; // already incremented above
      const delay = RETRY_DELAYS_MS[Math.min(attempts, RETRY_DELAYS_MS.length - 1)];
      const nextAt = Date.now() + delay;

      this.ctx.storage.sql.exec(
        "UPDATE email_jobs SET status = 'failed', scheduled_at = ?, last_error = ? WHERE id = ?",
        nextAt, String(err), job.id
      );

      // Reschedule alarm for the next retry
      await this.ctx.storage.setAlarm(nextAt);
    }
  }

  // HTTP interface for the Worker to call
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === "POST" && url.pathname === "/enqueue") {
      const body = (await req.json()) as Omit<EmailJob, "status" | "attempts" | "scheduledAt" | "sentAt" | "lastError">;
      const result = await this.enqueue(body);
      return new Response(JSON.stringify(result), { headers: { "Content-Type": "application/json" } });
    }

    if (req.method === "GET" && url.pathname === "/status") {
      const id = url.searchParams.get("id");
      if (!id) return new Response("id required", { status: 400 });
      const row = this.ctx.storage.sql
        .exec("SELECT * FROM email_jobs WHERE id = ?", id)
        .one();
      return new Response(JSON.stringify(row ?? null), { headers: { "Content-Type": "application/json" } });
    }

    return new Response("Not found", { status: 404 });
  }
}
```

## Worker Producer

```typescript
// src/index.ts
export interface Env {
  EMAIL_QUEUE: DurableObjectNamespace;
  EMAIL_QUEUE_SECRET: string;
}

interface EnqueueRequest {
  idempotencyKey: string;
  to: string;
  subject: string;
  html: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST" || new URL(req.url).pathname !== "/send-email") {
      return new Response("Not found", { status: 404 });
    }

    // Verify caller auth (e.g. internal service-to-service secret)
    if (req.headers.get("X-Internal-Secret") !== env.EMAIL_QUEUE_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const { idempotencyKey, to, subject, html } = (await req.json()) as EnqueueRequest;

    // Route all emails to a single named DO instance per account shard
    // For high volume, shard by first char of idempotencyKey
    const shardKey = idempotencyKey.charAt(0).toLowerCase();
    const doId = env.EMAIL_QUEUE.idFromName(`shard-${shardKey}`);
    const stub = env.EMAIL_QUEUE.get(doId);

    const doRes = await stub.fetch(new Request("https://do/enqueue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idempotencyKey, to, subject, html }),
    }));

    return new Response(await doRes.text(), {
      status: doRes.status,
      headers: { "Content-Type": "application/json" },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Cleanup Cron (Optional)

```typescript
// Purge sent jobs older than 7 days to keep SQLite storage lean
// Add to alarm() or run as a scheduled Worker with a service binding to the DO
async function purgeOldJobs(stub: DurableObjectStub): Promise<void> {
  const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
  // Exposed via DO fetch handler /purge endpoint (omitted for brevity)
  await stub.fetch(new Request(`https://do/purge?before=${cutoff}`, { method: "DELETE" }));
}
```

## Anti-patterns
- **Using a plain KV key as an idempotency guard** — KV has eventual consistency; two concurrent Workers can both read "not seen" and both call the email API before either writes the guard.
- **Calling the email API directly from the Worker** — no retry, no deduplication, no delivery guarantee if the Worker times out after sending but before returning a response.
- **Using one Durable Object instance for all emails** — a single DO processes requests sequentially; shard by a prefix of the idempotency key or customer ID for high-volume workloads.
- **Storing large HTML blobs in DO SQLite without compression** — SQLite in DOs has a 128 MB storage budget per instance; compress large HTML bodies with `CompressionStream` and store as BLOB.
- **Not setting a DLQ alert for permanently failed jobs** — `status = 'failed'` and `attempts >= MAX_ATTEMPTS` rows will silently accumulate; add a monitoring query or a Tail Worker alert.

## Gotchas
- `ctx.storage.sql.exec()` runs in a transaction by default within a single `fetch()` or `alarm()` call; wrap multiple statements in `BEGIN/COMMIT` only if you need explicit multi-statement atomicity.
- DO alarms fire **at most once per scheduled time** — if the alarm handler throws, the alarm is not automatically rescheduled; re-set the alarm inside a `try/finally` block.
- `this.ctx.blockConcurrencyWhile()` in the constructor blocks all incoming requests until the schema migration completes; keep it fast (DDL only, no data mutations).
- The `idFromName()` call is deterministic — the same name always routes to the same DO instance globally; this is what makes the idempotency guarantee work across retried Worker requests.
- Resend/SendGrid return 2xx for accepted emails but delivery failures come via webhook asynchronously — `status = 'sent'` means the API accepted, not that the inbox received it.

## Verification
1. POST `/send-email` twice with the same `idempotencyKey` — the second call returns `{"queued":false}`.
2. Check DO `/status?id=<key>` after ~1 second — `status` should be `"sent"`.
3. Point `EMAIL_PROVIDER_URL` at a mock that returns 503; confirm retries fire at increasing intervals via DO `/status` polling.
4. After `MAX_ATTEMPTS` retries, confirm `status = "failed"` and no further alarm fires.

## Related
- `durable-objects-alarms-scheduling.md`
- `durable-objects-sqlite-storage.md`
- `cloudflare-queues-dead-letter-dlq.md`
- `workers-email-routing.md`
- `cloudflare-workers-micropayment-metering-d1.md`

## Sources
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/durable-objects/api/storage-api/#sql-api
- https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-from-a-worker/
