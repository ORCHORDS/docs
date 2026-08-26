# Write-Behind Cache: KV Async Persistence to D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You have a high-write workload where every mutation immediately hits D1 (SQLite). Writes feel slow because each request waits on the D1 round-trip. You want writes to feel instant to the caller while the data eventually lands in the authoritative store without losing it.

Classic signs:
- D1 write latency > 50 ms added to every request
- Burst writes overwhelm D1 connection limits
- You're rate-limited by D1's row-write throughput
- Tolerable eventual consistency (session counters, view counts, analytics events, draft autosaves)

---

## Context

Write-behind (also called write-back) cache inverts the write-aside pattern. The caller writes to the fast store (KV) and receives an immediate 200. A background process drains the fast store into the authoritative store (D1) asynchronously. Workers Queues act as the durable bridge so nothing is dropped even if the D1 write fails on the first attempt.

```
Client → Worker → KV (ack) → Queue message → Consumer Worker → D1
```

This differs from write-through (caller waits for both stores) and write-around (caller bypasses cache entirely).

---

## Queue Setup in `wrangler.toml`

```toml
[[queues.producers]]
queue = "write-behind"
binding = "WRITE_QUEUE"

[[queues.consumers]]
queue = "write-behind"
max_batch_size = 50
max_batch_timeout = 5        # seconds; flush at most every 5 s
max_retries = 3
dead_letter_queue = "write-behind-dlq"
```

---

## Write Path: Worker Accepting Mutations

```typescript
// src/worker.ts
export interface Env {
  KV: KVNamespace;
  WRITE_QUEUE: Queue<WriteEvent>;
  DB: D1Database;
}

interface WriteEvent {
  table: string;
  key: string;
  payload: Record<string, unknown>;
  ts: number;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { table, key, payload } = await request.json<WriteEvent>();

    // 1. Write to KV for immediate reads (optimistic view)
    const kvKey = `${table}:${key}`;
    await env.KV.put(kvKey, JSON.stringify({ ...payload, _dirty: true }), {
      expirationTtl: 86400, // 24 h safety net
    });

    // 2. Enqueue for async D1 persistence (fire-and-forget from caller's perspective)
    await env.WRITE_QUEUE.send({ table, key, payload, ts: Date.now() });

    return new Response(JSON.stringify({ ok: true, cached: true }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Read Path: KV-First with D1 Fallback

```typescript
async function readRecord(
  env: Env,
  table: string,
  key: string
): Promise<Record<string, unknown> | null> {
  const kvKey = `${table}:${key}`;

  // Prefer KV (may be dirty/pending flush)
  const cached = await env.KV.get(kvKey, { type: "json" });
  if (cached !== null) return cached as Record<string, unknown>;

  // Fallback to D1 (authoritative)
  const row = await env.DB.prepare(`SELECT data FROM ${table} WHERE id = ?`)
    .bind(key)
    .first<{ data: string }>();
  if (!row) return null;

  const parsed = JSON.parse(row.data);
  // Backfill KV so next read is fast
  await env.KV.put(kvKey, row.data, { expirationTtl: 3600 });
  return parsed;
}
```

---

## Consumer Worker: Batch Flush to D1

```typescript
// src/consumer.ts
export default {
  async queue(batch: MessageBatch<WriteEvent>, env: Env): Promise<void> {
    // Deduplicate: last-write-wins per key within the batch
    const latest = new Map<string, WriteEvent>();
    for (const msg of batch.messages) {
      const { table, key } = msg.body;
      const existing = latest.get(`${table}:${key}`);
      if (!existing || msg.body.ts > existing.ts) {
        latest.set(`${table}:${key}`, msg.body);
      }
    }

    const stmt = env.DB.prepare(
      `INSERT INTO records (id, table_name, data, updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         data = excluded.data,
         updated_at = excluded.updated_at`
    );

    const statements = [...latest.values()].map(({ key, table, payload, ts }) =>
      stmt.bind(key, table, JSON.stringify(payload), new Date(ts).toISOString())
    );

    try {
      await env.DB.batch(statements);

      // Clear the dirty flag in KV now that D1 is authoritative
      await Promise.all(
        [...latest.keys()].map((k) =>
          env.KV.put(k, JSON.stringify({ ...(latest.get(k)?.payload ?? {}), _dirty: false }), {
            expirationTtl: 3600,
          })
        )
      );

      batch.ackAll();
    } catch (err) {
      // Let the queue retry the whole batch
      batch.retryAll();
      console.error("write-behind flush failed", err);
    }
  },
};
```

---

## Anti-patterns

- **Writing mutable objects to KV without a key scheme**: KV is eventually consistent across regions. Two Workers in different data centres writing the same key concurrently can silently clobber each other. Use Durable Objects as the KV writer if you need serialised last-write-wins guarantees.
- **Acknowledging messages before the D1 write succeeds**: If you `ackAll()` and then D1 throws, data is lost. Only ack after a confirmed write or let the queue retry.
- **Unbounded queue growth**: If D1 is degraded for hours, the queue can balloon. Set `max_retries` and a dead-letter queue, and alert on DLQ depth.
- **Skipping deduplication in the consumer**: Without dedup, a chatty key generates N identical D1 upserts. Batch and collapse before writing.
- **Using write-behind for financial data**: Any pattern with eventual consistency is wrong for money, inventory, or anything requiring strict read-your-writes.

---

## Gotchas

- KV TTL and queue max_batch_timeout must be coordinated. If KV evicts a key before the consumer flushes, a read between eviction and flush returns stale D1 data that looks like no dirty state exists.
- `ctx.waitUntil()` is NOT available inside a Queue consumer—the consumer's lifetime is managed by the runtime, not by `waitUntil`.
- D1 `batch()` is atomic per call but there is no cross-batch transaction. A partial batch failure leaves some rows committed and some not; that is fine for upserts but matters for dependent rows.
- Queue messages have a 128 KB body limit. Large payloads must be stored in R2 or KV and referenced by ID in the queue message.

---

## Verification

1. Write a record and immediately read it back—should return KV data with `_dirty: true`.
2. Wait for the consumer to flush (up to `max_batch_timeout` seconds) and read again—`_dirty` should be `false`.
3. Query D1 directly: `SELECT * FROM records WHERE id = '<key>';` — row should exist.
4. Kill the consumer mid-batch and confirm the queue retries delivery and D1 eventually receives the write.
5. Write 200 records with the same key in rapid succession and confirm D1 has only the latest value after flush.

---

## Related

- `cache-aside-kv-d1-fallback.md` — read-aside counterpart
- `outbox-pattern-d1-reliable-publishing.md` — reliable event publishing from D1
- `dead-letter-queue-pattern.md` — handling persistent consumer failures
- `fan-out-queues-workers.md` — broadcasting a single write to multiple consumers
- `idempotency-key-pattern-workers-d1.md` — making retried writes safe

---

## Sources

- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/prepared-statements/#batch-statements
- Martin Fowler — Write-Behind Cache: https://martinfowler.com/bliki/WriteBehindCache.html
