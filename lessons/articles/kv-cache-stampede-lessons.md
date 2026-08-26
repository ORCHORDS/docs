# KV Cache Stampede Incidents — Lessons Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

At 14:32 UTC our product catalogue endpoint — backed by Workers KV — spiked to 4 200 simultaneous
requests to the upstream PostgreSQL database. The database CPU hit 98 %, query latency went from
8 ms to 14 s, and three dependent services began timing out. The trigger: a routine KV key
expiration at 14:32:00 UTC, seconds after a flash sale began.

This is the textbook **thundering herd** (a.k.a. cache stampede).

---

## Context

Workers KV is an eventually-consistent edge key-value store. When a key's TTL expires, the next
read returns `null`. If thousands of Workers across hundreds of PoPs all miss the same key at the
same instant, they all race to refill the cache — and all hit the origin simultaneously.

Our architecture before the fix:

```
Edge Workers (N instances)
  │
  ├─ KV.get('catalogue:v2')  → null (expired)
  │
  └─► PostgreSQL origin  (N parallel queries)
```

Two amplifying factors:

1. **Exact TTL alignment.** We set `expirationTtl: 300` (5 min) everywhere, so keys expired in
   waves rather than being staggered.
2. **No write-coalescing.** Each Worker independently fetched from the origin and wrote to KV;
   there was no single writer.

---

## Solution

### 1. Stale-while-revalidate (SWR) with a logical TTL inside the value

Store a short hard TTL in KV (long enough to survive a replication lag) but embed a logical expiry
in the cached JSON. Serve stale immediately; revalidate in the background.

```typescript
import type { KVNamespace, ExecutionContext } from '@cloudflare/workers-types';

interface CacheEntry<T> {
  data: T;
  cachedAt: number;   // unix ms
  ttlMs: number;      // logical TTL
}

async function getWithSwr<T>(
  kv: KVNamespace,
  key: string,
  fetcher: () => Promise<T>,
  ctx: ExecutionContext,
  ttlMs = 300_000,          // 5 min logical TTL
  staleWindowMs = 60_000    // serve stale for up to 1 min while revalidating
): Promise<T> {
  const raw = await kv.get<CacheEntry<T>>(key, 'json');

  if (raw) {
    const age = Date.now() - raw.cachedAt;
    const isStale = age > raw.ttlMs;
    const isDeadStale = age > raw.ttlMs + staleWindowMs;

    if (!isDeadStale) {
      if (isStale) {
        // Revalidate in the background; serve stale data immediately
        ctx.waitUntil(revalidate(kv, key, fetcher, ttlMs));
      }
      return raw.data;
    }
  }

  // Cache miss or dead-stale: fetch synchronously
  return revalidate(kv, key, fetcher, ttlMs);
}

async function revalidate<T>(
  kv: KVNamespace,
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number
): Promise<T> {
  const data = await fetcher();
  const entry: CacheEntry<T> = { data, cachedAt: Date.now(), ttlMs };
  // Hard KV TTL is logical TTL + stale window + 60 s buffer
  await kv.put(key, JSON.stringify(entry), {
    expirationTtl: Math.ceil((ttlMs + 120_000) / 1000),
  });
  return data;
}
```

### 2. Probabilistic early expiry (jitter-based)

Instead of a sharp expiry, each cache read probabilistically decides to revalidate *early* using
the XFetch algorithm. This spreads revalidation requests over time rather than spiking them.

```typescript
/**
 * XFetch probabilistic early expiry.
 * Revalidate early with probability that increases as expiry approaches.
 *
 * @param cachedAt  unix ms when the entry was cached
 * @param ttlMs     intended TTL in milliseconds
 * @param beta      tuning factor (1.0 = conservative, 2.0 = aggressive early expiry)
 */
function shouldRevalidateEarly(
  cachedAt: number,
  ttlMs: number,
  fetchDurationMs: number,
  beta = 1.0
): boolean {
  const expiresAt = cachedAt + ttlMs;
  const now = Date.now();
  const gap = expiresAt - now; // ms until expiry
  if (gap <= 0) return true;   // already expired

  // Probability rises exponentially as gap shrinks
  const score = now - beta * fetchDurationMs * Math.log(Math.random());
  return score >= expiresAt;
}

// Usage inside getWithSwr:
const earlyExpiry = shouldRevalidateEarly(
  raw.cachedAt,
  raw.ttlMs,
  avgFetchDurationMs
);
if (earlyExpiry) {
  ctx.waitUntil(revalidate(kv, key, fetcher, ttlMs));
}
```

### 3. Background revalidation via Queues (write-coalescing)

For the most stampede-prone keys, use a Queue to ensure only **one** revalidation runs at a time:

```typescript
// Worker: on cache miss, enqueue a revalidation request
async function getWithQueue<T>(
  kv: KVNamespace,
  queue: Queue,
  key: string,
  ctx: ExecutionContext
): Promise<T | null> {
  const raw = await kv.get<CacheEntry<T>>(key, 'json');

  if (raw) {
    const age = Date.now() - raw.cachedAt;
    if (age < raw.ttlMs) return raw.data;

    // Stale — send revalidation request to queue, serve stale
    ctx.waitUntil(
      queue.send({ key, requestedAt: Date.now() }, { contentType: 'json' })
    );
    return raw.data;
  }

  // Cold miss — enqueue and return null (caller falls back to origin directly)
  ctx.waitUntil(
    queue.send({ key, requestedAt: Date.now() }, { contentType: 'json' })
  );
  return null;
}

// Queue consumer: deduplicate and refill
export const queueHandler = {
  async queue(
    batch: MessageBatch<{ key: string; requestedAt: number }>,
    env: Env
  ): Promise<void> {
    // Deduplicate: only process the latest message per key
    const latest = new Map<string, number>();
    for (const msg of batch.messages) {
      const prev = latest.get(msg.body.key) ?? 0;
      if (msg.body.requestedAt > prev) latest.set(msg.body.key, msg.body.requestedAt);
    }

    await Promise.all(
      Array.from(latest.keys()).map(async (key) => {
        const data = await fetchFromOrigin(key, env);
        await env.CACHE_KV.put(
          key,
          JSON.stringify({ data, cachedAt: Date.now(), ttlMs: 300_000 }),
          { expirationTtl: 420 }
        );
      })
    );

    batch.ackAll();
  },
};
```

---

## Implementation Details

### Incident timeline

| Time (UTC) | Event |
|---|---|
| 14:32:00 | `catalogue:v2` KV key expires across all PoPs simultaneously |
| 14:32:01 | 4 200 Workers hit KV, all get `null`, all query PostgreSQL |
| 14:32:03 | PostgreSQL CPU 98 %, query queue depth > 2 000 |
| 14:32:10 | First `catalogue:v2` write back to KV from a Worker |
| 14:32:11 | KV replication lag — some PoPs still serving `null` |
| 14:34:00 | Traffic stabilises after KV replication completes globally |
| 14:34:00–14:36:00 | Downstream timeout errors visible to 12 % of users |

### TTL staggering

Add random jitter when writing to KV so keys do not expire in waves:

```typescript
function jitteredTtl(baseTtlSeconds: number, jitterFraction = 0.2): number {
  const jitter = baseTtlSeconds * jitterFraction * (Math.random() - 0.5);
  return Math.round(baseTtlSeconds + jitter);
}

await kv.put(key, value, { expirationTtl: jitteredTtl(300) });
// TTL will be 270–330 s, staggered across keys
```

---

## Anti-patterns

| Anti-pattern | Why it hurts |
|---|---|
| Exact same TTL for all instances of a key | Synchronised expiry = synchronised stampede |
| Fetching synchronously on every cache miss | No back-pressure, no coalescing, origin hit N times |
| Ignoring KV replication lag after a write | Early reads still miss even after you refilled the cache |
| Serving dead-stale data indefinitely | Stale-while-revalidate must have a maximum stale age |
| Large KV values (> 25 MB) | KV has a 25 MB per-value limit; compression needed for big catalogues |

---

## Gotchas

1. **KV `get()` can return `null` briefly after a `put()`** because of eventual consistency
   replication across PoPs (typically < 60 s, but not guaranteed).

2. **`ctx.waitUntil()` has a wall-clock limit of 30 s** on the background task. If your refill
   fetch is slow, it may be terminated before the write completes.

3. **Queue `send()` is not synchronous** — there can be seconds of latency before the consumer
   runs. Do not rely on the Queue path for cache fills that must be warm before the next request.

4. **KV bulk write limits.** You can write at most 1 000 keys/s per account. During a mass
   revalidation, rate-limit your Queue consumer.

5. **`expirationTtl` minimum is 60 s.** You cannot use KV as a sub-minute cache.

---

## Verification

```typescript
// Integration test — verify SWR serves stale and revalidates
import { describe, it, expect, vi, afterEach } from 'vitest';
import { env, createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';

describe('getWithSwr', () => {
  afterEach(() => vi.restoreAllMocks());

  it('serves stale data and revalidates in background', async () => {
    // Pre-populate a stale entry
    const staleEntry = {
      data: { name: 'old' },
      cachedAt: Date.now() - 400_000,  // 400 s ago — past 300 s TTL
      ttlMs: 300_000,
    };
    await env.KV.put('test-key', JSON.stringify(staleEntry), { expirationTtl: 420 });

    const fetcher = vi.fn().mockResolvedValue({ name: 'new' });
    const ctx = createExecutionContext();

    const result = await getWithSwr(env.KV, 'test-key', fetcher, ctx);

    expect(result).toEqual({ name: 'old' });  // served stale immediately
    await waitOnExecutionContext(ctx);
    expect(fetcher).toHaveBeenCalledOnce(); // revalidated in background

    const updated = await env.KV.get<CacheEntry<{ name: string }>>('test-key', 'json');
    expect(updated?.data.name).toBe('new');
  });
});
```

---

## Related

- `documentation/categories/lessons/workers-queue-consumer-backpressure-lessons.md`
- `documentation/categories/architecture/caching-strategy.md`
- Cloudflare KV — Consistency model

---

## Sources

- Vattani et al., "Optimal Probabilistic Cache Stampede Prevention" (2015) — XFetch algorithm
- Cloudflare KV documentation — Limits and consistency
- Internal postmortem: `incidents/2025-09-catalogue-stampede.md`
- Cloudflare Queues documentation — Consumer concurrency
