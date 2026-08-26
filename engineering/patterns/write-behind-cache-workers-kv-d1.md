# Write-Behind Cache with Workers KV and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Write latency to D1 is adding unacceptable tail latency to your API responses, but data consistency with D1 is required for reporting, analytics, and cross-Worker queries. You want to return responses immediately after writing to KV while ensuring D1 is eventually updated durably, with automatic retry on failure and periodic reconciliation to catch any divergence.

---

## Context

The write-behind (write-back) cache pattern decouples the hot write path from the durable storage write. The Worker writes the new value to KV immediately and returns a response to the client in one round-trip. Simultaneously it enqueues a message to a Cloudflare Queue; the Queue consumer Worker picks up the message and writes the value to D1 with automatic retry semantics. A Cron Trigger runs a periodic reconciliation job that scans a sample of KV keys, compares their values against D1, and logs or re-enqueues any diverged entries. Reads use a cache-aside strategy against KV with a `Vary`-keyed cache-bust mechanism to invalidate stale CDN-edge caches when the KV value changes.

---

## Config

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "WRITE_CACHE"
id      = "<kv-namespace-id>"

[[queues.producers]]
binding    = "WRITE_QUEUE"
queue_name = "write-behind-queue"

[[queues.consumers]]
queue      = "write-behind-queue"
max_batch_size    = 20
max_batch_timeout = 5
max_retries       = 3
dead_letter_queue = "write-behind-dlq"

[triggers]
crons = ["0 * * * *"]  # reconciliation every hour
```

---

## Implementation

```typescript
// src/write-behind.ts

export interface Env {
  WRITE_CACHE: KVNamespace;
  WRITE_QUEUE: Queue;
  DB:          D1Database;
}

interface WriteMessage {
  key:       string;
  value:     unknown;
  writtenAt: number; // Unix ms — used to discard stale queue messages
}

// ── Writer (called from the hot-path fetch handler) ────────────────────────

export async function writeThrough(
  env: Env,
  key: string,
  value: unknown,
  ctx: ExecutionContext
): Promise<void> {
  const writtenAt = Date.now();

  // 1. Write to KV immediately (fast, globally replicated)
  await env.WRITE_CACHE.put(key, JSON.stringify(value), {
    // Include writtenAt in metadata so the reconciler can compare timestamps
    metadata: { writtenAt },
  });

  // 2. Enqueue the D1 write — do not await so the response is not delayed
  ctx.waitUntil(
    env.WRITE_QUEUE.send({ key, value, writtenAt } satisfies WriteMessage)
  );
}

// ── Reader ─────────────────────────────────────────────────────────────────

export async function readValue(
  env: Env,
  key: string
): Promise<{ value: unknown; source: "kv" | "d1" } | null> {
  // KV is the primary read source; D1 is the fallback (e.g., KV key evicted)
  const kvResult = await env.WRITE_CACHE.get<unknown>(key, "json");
  if (kvResult !== null) return { value: kvResult, source: "kv" };

  const row = await env.DB
    .prepare(`SELECT value FROM write_cache WHERE key = ?`)
    .bind(key)
    .first<{ value: string }>();

  if (!row) return null;
  return { value: JSON.parse(row.value), source: "d1" };
}

// ── Queue consumer ─────────────────────────────────────────────────────────

export async function handleQueue(
  batch: MessageBatch<WriteMessage>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const { key, value, writtenAt } = msg.body;

    try {
      // Check if a newer write has already landed in D1 (idempotency)
      const existing = await env.DB
        .prepare(`SELECT written_at FROM write_cache WHERE key = ?`)
        .bind(key)
        .first<{ written_at: number }>();

      if (existing && existing.written_at >= writtenAt) {
        // A newer or equal write already in D1 — discard this message
        msg.ack();
        continue;
      }

      await env.DB
        .prepare(
          `INSERT INTO write_cache (key, value, written_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE
             SET value = excluded.value,
                 written_at = excluded.written_at
           WHERE excluded.written_at > write_cache.written_at`
        )
        .bind(key, JSON.stringify(value), writtenAt)
        .run();

      msg.ack();
    } catch (err) {
      console.error(`[write-behind] D1 write failed for key=${key}:`, err);
      msg.retry(); // Queue will retry up to max_retries
    }
  }
}

// ── Cron reconciliation ────────────────────────────────────────────────────

export async function reconcile(env: Env): Promise<void> {
  // Sample up to 100 D1 rows written in the last 2 hours
  const cutoff = Date.now() - 2 * 60 * 60 * 1_000;
  const { results } = await env.DB
    .prepare(
      `SELECT key, value, written_at FROM write_cache
       WHERE written_at > ? ORDER BY written_at DESC LIMIT 100`
    )
    .bind(cutoff)
    .all<{ key: string; value: string; written_at: number }>();

  let diverged = 0;

  for (const row of results) {
    const { value: kvValue, metadata } =
      await env.WRITE_CACHE.getWithMetadata<unknown, { writtenAt: number }>(row.key, "json");

    if (kvValue === null) {
      // KV key evicted — re-populate from D1
      await env.WRITE_CACHE.put(row.key, row.value, {
        metadata: { writtenAt: row.written_at },
      });
      diverged++;
      continue;
    }

    const kvWrittenAt = metadata?.writtenAt ?? 0;
    if (kvWrittenAt > row.written_at) {
      // KV is newer than D1 — re-enqueue D1 write
      await env.WRITE_QUEUE.send({
        key:       row.key,
        value:     kvValue,
        writtenAt: kvWrittenAt,
      });
      diverged++;
    }
  }

  console.log(`[reconcile] checked ${results.length} rows, diverged=${diverged}`);
}

// src/index.ts
import { writeThrough, readValue, handleQueue, reconcile, type Env } from "./write-behind";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { method, pathname } = Object.assign(new URL(request.url), {});
    const key = pathname.slice(1);

    if (method === "PUT") {
      const value = await request.json();
      await writeThrough(env, key, value, ctx);
      return new Response(null, { status: 204 });
    }

    if (method === "GET") {
      const result = await readValue(env, key);
      if (!result) return new Response(null, { status: 404 });
      return Response.json(result);
    }

    return new Response("Method Not Allowed", { status: 405 });
  },

  async queue(batch: MessageBatch<WriteMessage>, env: Env): Promise<void> {
    return handleQueue(batch, env);
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(reconcile(env));
  },
};
```

---

## Integration / Testing

```bash
# Apply D1 migration
npx wrangler d1 execute DB --command \
  "CREATE TABLE IF NOT EXISTS write_cache (
     key        TEXT PRIMARY KEY,
     value      TEXT NOT NULL,
     written_at INTEGER NOT NULL
   )"

# Write a value
curl -X PUT http://localhost:8787/my-key \
  -H 'Content-Type: application/json' \
  -d '{"name":"Alice","score":99}'
# Expect 204

# Read back from KV
curl http://localhost:8787/my-key
# {"value":{"name":"Alice","score":99},"source":"kv"}

# Verify D1 write (allow a few seconds for Queue consumer)
sleep 3
npx wrangler d1 execute DB --command "SELECT * FROM write_cache WHERE key = 'my-key'"

# Trigger reconciliation manually
npx wrangler dispatch-scheduled-event --trigger-name reconcile
```

---

## Anti-patterns

- **Awaiting the Queue send in the hot path** — this defeats the purpose; queue the write with `ctx.waitUntil` and return the response immediately.
- **No timestamp comparison in the consumer** — without comparing `writtenAt`, a slow-delivered old message can overwrite a newer D1 record, reverting the value.
- **Reconciliation without a cutoff window** — scanning the entire `write_cache` table on every cron is expensive; scope the scan to recent writes.
- **Treating KV as the source of truth** — KV can evict keys without warning; D1 is the authoritative store; KV is the acceleration layer.

---

## Gotchas

- KV `getWithMetadata` counts as a separate read operation from `get`; budget reads accordingly.
- Queue consumers have a maximum batch timeout of 30 seconds; keep D1 writes simple and fast.
- D1 `ON CONFLICT DO UPDATE WHERE` requires SQLite 3.38+; Cloudflare D1 supports this as of mid-2024.
- Wrangler's local Queue simulation (`wrangler dev`) does not persist queue messages across restarts; test the consumer in isolation with unit tests.

---

## Verification

```bash
# Check DLQ for failed writes
npx wrangler queues list
# Look for write-behind-dlq message count

# Monitor queue consumer logs
npx wrangler tail --format pretty | grep write-behind

# Reconciliation report from cron
npx wrangler tail --format pretty | grep reconcile
```

---

## Related

- `token-bucket-rate-limit-workers-kv.md`
- `compensating-transaction-workers-d1.md`
- `request-coalescing-durable-objects.md`

---

## Sources

- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Write-behind cache pattern — https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-using-redis/write-behind-lazy-loading.html
