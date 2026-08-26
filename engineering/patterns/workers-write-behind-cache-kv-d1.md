# Write-Behind Cache Pattern with KV + D1 in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your application performs frequent small writes — counters, user profile patches, view counts, settings updates — and the write latency of a relational database (D1) is unacceptable in the hot path. Synchronous writes also mean that a D1 outage directly blocks user-facing operations. You want sub-millisecond write acknowledgement with eventual durability in D1.

## Context

KV provides globally distributed, low-latency key-value storage with strong write SLAs. D1 is SQLite-on-Cloudflare, optimised for reads with transactional consistency. The Write-Behind Cache pattern writes to KV immediately (fast, durable to Cloudflare's edge), then flushes to D1 asynchronously via a Queue. This decouples write latency from D1 latency while maintaining eventual consistency. Conflict resolution and DLQ handling prevent data loss on flush failure.

## Solution

The write path: store the mutation in KV with a version timestamp, enqueue a flush job, and return 200 immediately. The flush Worker reads KV, writes to D1, and clears the KV entry. A consistency-check endpoint compares KV and D1 state on demand.

```typescript
// wrangler.toml excerpt
// [[kv_namespaces]]
//   binding = "CACHE"
//   id = "..."
// [[queues.producers]]
//   queue = "d1-flush"
//   binding = "FLUSH_QUEUE"
// [[queues.consumers]]
//   queue = "d1-flush"
//   max_batch_size = 50
//   max_batch_timeout = 5
// [[queues.producers]]
//   queue = "d1-flush-dlq"
//   binding = "FLUSH_DLQ"

export interface Env {
  CACHE:       KVNamespace;
  DB:          D1Database;
  FLUSH_QUEUE: Queue;
  FLUSH_DLQ:   Queue;
}

// Shared types
interface CacheEntry<T = unknown> {
  value:     T;
  version:   number;  // Unix ms timestamp
  key:       string;
  tableName: string;
  pkField:   string;
  pkValue:   string;
}

interface FlushJob {
  cacheKey:  string;
  tableName: string;
  pkField:   string;
  pkValue:   string;
  enqueuedAt: number;
}

// --- Write path: API Worker ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'PATCH' && url.pathname.startsWith('/users/')) {
      const userId = url.pathname.split('/')[2];
      const patch  = await request.json<Record<string, unknown>>();
      return handleUserPatch(env, userId, patch);
    }

    if (request.method === 'GET' && url.pathname.startsWith('/users/')) {
      const userId = url.pathname.split('/')[2];
      return handleUserGet(env, userId);
    }

    if (url.pathname === '/admin/consistency-check') {
      return handleConsistencyCheck(env);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function handleUserPatch(
  env: Env,
  userId: string,
  patch: Record<string, unknown>
): Promise<Response> {
  const cacheKey = `user:${userId}`;
  const version  = Date.now();

  // Read current KV entry to merge (read-modify-write in KV)
  const existing = await env.CACHE.get<CacheEntry>(cacheKey, 'json');
  const merged   = { ...(existing?.value as object ?? {}), ...patch };

  const entry: CacheEntry = {
    value:     merged,
    version,
    key:       cacheKey,
    tableName: 'users',
    pkField:   'id',
    pkValue:   userId,
  };

  // Write to KV — fast, globally durable
  await env.CACHE.put(cacheKey, JSON.stringify(entry), {
    expirationTtl: 3600,  // 1 hour TTL; flush will clear earlier
    metadata: { version },
  });

  // Enqueue async D1 flush
  const job: FlushJob = {
    cacheKey,
    tableName: 'users',
    pkField:   'id',
    pkValue:   userId,
    enqueuedAt: version,
  };
  await env.FLUSH_QUEUE.send(job);

  return Response.json({ ok: true, version });
}

async function handleUserGet(env: Env, userId: string): Promise<Response> {
  // Serve from KV cache first (write-behind means KV has the freshest data)
  const cacheKey = `user:${userId}`;
  const cached   = await env.CACHE.get<CacheEntry>(cacheKey, 'json');
  if (cached) {
    return Response.json(cached.value, {
      headers: { 'X-Cache': 'HIT', 'X-Cache-Version': String(cached.version) },
    });
  }

  // Cache miss — read from D1
  const row = await env.DB
    .prepare('SELECT * FROM users WHERE id = ?1')
    .bind(userId)
    .first();

  if (!row) return new Response('Not found', { status: 404 });
  return Response.json(row, { headers: { 'X-Cache': 'MISS' } });
}

// --- Flush Worker (Queue consumer) ---

export const flushWorker = {
  async queue(batch: MessageBatch<FlushJob>, env: Env): Promise<void> {
    // Deduplicate: for the same cacheKey, only flush the latest version
    const latest = new Map<string, { job: FlushJob; message: Message<FlushJob> }>();
    for (const message of batch.messages) {
      const existing = latest.get(message.body.cacheKey);
      if (!existing || message.body.enqueuedAt > existing.job.enqueuedAt) {
        if (existing) existing.message.ack();  // older duplicate
        latest.set(message.body.cacheKey, { job: message.body, message });
      } else {
        message.ack();  // this message is older — skip
      }
    }

    for (const { job, message } of latest.values()) {
      try {
        await flushToD1(env, job);
        message.ack();
      } catch (err) {
        // Retry up to max_retries; on exhaustion send to DLQ
        if ((message as any).attempts >= 3) {
          await env.FLUSH_DLQ.send({ job, error: String(err), failedAt: new Date().toISOString() });
          message.ack();  // ack to prevent infinite retry loop
        } else {
          message.retry({ delaySeconds: 10 * (message as any).attempts });
        }
      }
    }
  },
};

async function flushToD1(env: Env, job: FlushJob): Promise<void> {
  const cached = await env.CACHE.get<CacheEntry>(job.cacheKey, 'json');
  if (!cached) return;  // already evicted or cleared by a later flush

  // Version guard: only flush if the cache version matches the job version
  // This prevents an older flush job from overwriting a newer write
  if (cached.version !== job.enqueuedAt) {
    // Newer write exists; a later flush job will handle it — skip
    return;
  }

  // Upsert into D1
  const fields = Object.keys(cached.value as object);
  const values = Object.values(cached.value as object);
  const setClauses = fields.map((f, i) => `${f} = ?${i + 2}`).join(', ');

  await env.DB
    .prepare(
      `INSERT INTO ${job.tableName} (${job.pkField}, ${fields.join(', ')})
       VALUES (?1, ${values.map((_, i) => `?${i + 2}`).join(', ')})
       ON CONFLICT(${job.pkField}) DO UPDATE SET ${setClauses}`
    )
    .bind(job.pkValue, ...values)
    .run();

  // Clear KV entry only after successful D1 write
  await env.CACHE.delete(job.cacheKey);
}

// --- Consistency check ---

async function handleConsistencyCheck(env: Env): Promise<Response> {
  // List all pending KV cache entries and compare with D1
  const list = await env.CACHE.list({ prefix: 'user:' });
  const results: Array<{ key: string; consistent: boolean; kvVersion: number }> = [];

  for (const kv of list.keys) {
    const entry = await env.CACHE.get<CacheEntry>(kv.name, 'json');
    if (!entry) continue;

    const row = await env.DB
      .prepare('SELECT updated_at FROM users WHERE id = ?1')
      .bind(entry.pkValue)
      .first<{ updated_at: string }>();

    const d1Ts = row ? new Date(row.updated_at).getTime() : 0;
    results.push({
      key:        kv.name,
      consistent: d1Ts >= entry.version,
      kvVersion:  entry.version,
    });
  }

  return Response.json(results);
}
```

## Implementation Details

**Version timestamps as optimistic locks.** Each KV write records a Unix-ms version. The flush job carries the version it was enqueued with. If by the time the flush job runs the KV version is different (a newer write arrived), the job is skipped. The newer job will flush the latest data.

**Read-modify-write in KV.** The patch endpoint reads the current KV entry, merges the patch, and writes back. This is not atomic in KV. Concurrent patches to the same key can lose one write (last-write-wins). For entities with high concurrent write rates, use a Durable Object as the merge coordinator instead.

**Batch deduplication in the flush consumer.** Multiple writes to the same key within a queue batch window produce multiple flush jobs. The consumer deduplicates by cacheKey, processing only the latest version and acking the rest.

**DLQ on flush failure.** After 3 retries the job is forwarded to a dead-letter queue. A separate DLQ consumer or alert mechanism can replay jobs manually after diagnosing the root cause (D1 outage, schema mismatch).

**Cache TTL as safety net.** KV entries have a 1-hour TTL. Even if the flush job is lost, the entry will be evicted eventually. For critical data this is unacceptable; in that case, use the outbox pattern instead and do not rely on TTL.

## Anti-patterns

- **Write to D1 and KV synchronously.** Defeats the purpose — write latency is the sum of both, and D1 failure blocks the user.
- **Skip version tracking.** Without version guards, an old flush job can overwrite a newer write in D1, causing data rollback.
- **Use KV as the sole store.** KV's eventual consistency means two Workers can read the same key and get different values. D1 must remain the system of record.
- **Not draining the DLQ.** Silently dropping DLQ messages causes silent data loss. Set up an alert on DLQ depth.

## Gotchas

- KV `list()` is eventually consistent — recently written keys may not appear immediately in the list.
- KV `get` with `{ type: 'json' }` returns `null` (not an error) if the key does not exist or has expired.
- D1 `ON CONFLICT DO UPDATE` requires a `UNIQUE` or `PRIMARY KEY` constraint on `pkField`. Ensure the schema has it.
- Queue deduplication is not built-in. Two flush jobs for the same key are normal; the version check handles the race.
- Workers CPU time limit is 50 ms on the free plan and 30 s on paid. Batch flush jobs accordingly.

## Verification

```bash
# Write a patch
curl -X PATCH https://api.example.com/users/usr_123 \
  -H 'Content-Type: application/json' \
  -d '{"displayName": "Alice Updated"}'

# Immediately read from KV (should reflect patch)
curl https://api.example.com/users/usr_123
# Expect X-Cache: HIT

# Wait for flush (a few seconds), then check D1
wrangler d1 execute mydb --command "SELECT display_name FROM users WHERE id = 'usr_123'"

# Check consistency
curl https://api.example.com/admin/consistency-check
```

## Related

- `workers-read-through-cache-pattern-kv` — read-through complement to this pattern
- `workers-outbox-pattern-d1-queues` — stronger durability guarantee for event publishing
- `workers-fanout-notification-queues` — using Queues for async fan-out

## Sources

- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Write-behind cache: https://docs.oracle.com/cd/E15357_01/coh.360/e15723/cache_rtwtwbra.htm
