# KV Pipeline Bulk Operations in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker performs multiple KV reads or writes sequentially — waiting for each `get` or `put` to resolve before issuing the next. Under load this serialisation multiplies latency: 10 sequential KV reads at ~20 ms each add 200 ms to the response time. The fix is to pipeline reads in parallel with `Promise.all`, batch writes into concurrent groups, and coalesce related writes to stay within KV API rate limits while maximising throughput.

## Context

KV is eventually consistent and designed for high-read, low-write workloads. Each `KV.get()` incurs a network round-trip to the KV store closest to the Worker PoP; each `KV.put()` propagates asynchronously across the network. The Workers runtime supports concurrent subrequests (up to 1000 per invocation), so multiple KV operations can be in-flight simultaneously at zero additional CPU cost. The key limits: KV write rate is 1 write/second per key globally; bulk reads are bounded by the 50-subrequest soft limit for free plans (6-plan accounts get higher limits). Treat writes as fire-and-forget via `ctx.waitUntil` wherever strong consistency is not required.

## 1. Parallel Bulk Read

```typescript
// lib/kv-bulk-read.ts

/**
 * Reads multiple KV keys in parallel and returns a Map of key → value.
 * Missing keys are omitted from the result.
 */
export async function kvBulkGet(
  kv: KVNamespace,
  keys: string[]
): Promise<Map<string, string>> {
  if (keys.length === 0) return new Map();

  const pairs = await Promise.all(
    keys.map(async (key) => {
      const value = await kv.get(key);
      return [key, value] as [string, string | null];
    })
  );

  return new Map(
    pairs.filter((pair): pair is [string, string] => pair[1] !== null)
  );
}

// Usage
const userData = await kvBulkGet(env.USER_KV, [
  "user:1001:profile",
  "user:1001:prefs",
  "user:1001:tokens",
]);
const profile = userData.get("user:1001:profile");
```

## 2. Chunked Parallel Read for Large Key Sets

When the key count exceeds the subrequest budget or you want to control concurrency:

```typescript
// lib/kv-chunked-read.ts

async function* chunks<T>(arr: T[], size: number): AsyncGenerator<T[]> {
  for (let i = 0; i < arr.length; i += size) {
    yield arr.slice(i, i + size);
  }
}

/**
 * Reads keys in concurrent chunks of `chunkSize` to stay inside subrequest limits.
 * Default chunk size of 25 is safe on free-tier Workers.
 */
export async function kvChunkedGet(
  kv: KVNamespace,
  keys: string[],
  chunkSize = 25
): Promise<Map<string, string>> {
  const result = new Map<string, string>();

  for await (const chunk of chunks(keys, chunkSize)) {
    const entries = await Promise.all(
      chunk.map(async (key) => {
        const val = await kv.get(key);
        return [key, val] as [string, string | null];
      })
    );
    for (const [k, v] of entries) {
      if (v !== null) result.set(k, v);
    }
  }

  return result;
}
```

## 3. Parallel Bulk Write with Background Flush

Writes are fire-and-forget when eventual consistency is acceptable. Group them and flush via `ctx.waitUntil` to avoid blocking the response:

```typescript
// lib/kv-bulk-write.ts

export interface KVWriteEntry {
  key:        string;
  value:      string;
  expirationTtl?: number; // seconds
}

/**
 * Writes all entries in parallel. Call inside ctx.waitUntil to keep writes
 * off the critical response path.
 */
export async function kvBulkPut(
  kv: KVNamespace,
  entries: KVWriteEntry[]
): Promise<void> {
  await Promise.all(
    entries.map(({ key, value, expirationTtl }) =>
      kv.put(key, value, expirationTtl ? { expirationTtl } : undefined)
    )
  );
}

// In the fetch handler:
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const response = await buildResponse(env);

    // Write session counters and analytics in the background
    ctx.waitUntil(
      kvBulkPut(env.ANALYTICS_KV, [
        { key: "hit:homepage",      value: String(Date.now()) },
        { key: "hit:homepage:day",  value: String(Date.now()), expirationTtl: 86400 },
        { key: "hit:homepage:week", value: String(Date.now()), expirationTtl: 604800 },
      ])
    );

    return response;
  },
};
```

## 4. Read-Modify-Write with Optimistic Concurrency

KV has no native atomic compare-and-swap, but a lightweight optimistic pattern covers many use cases:

```typescript
// lib/kv-optimistic-update.ts

interface VersionedValue<T> {
  value:   T;
  version: number;
}

/**
 * Read-modify-write with optimistic versioning.
 * Retries up to `maxRetries` times if a concurrent writer changed the value.
 */
export async function kvOptimisticUpdate<T>(
  kv: KVNamespace,
  key: string,
  updater: (current: T | null) => T,
  maxRetries = 3
): Promise<void> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const raw = await kv.get<VersionedValue<T>>(key, { type: "json" });
    const next: VersionedValue<T> = {
      value:   updater(raw?.value ?? null),
      version: (raw?.version ?? 0) + 1,
    };

    // Write with a short expiry on the version key to detect conflicts
    await kv.put(key, JSON.stringify(next));

    // Verify: re-read and confirm version incremented as expected
    const verify = await kv.get<VersionedValue<T>>(key, { type: "json" });
    if (verify?.version === next.version) return; // success

    // Back off before retry
    await new Promise((r) => setTimeout(r, 20 * (attempt + 1)));
  }
  throw new Error(`kvOptimisticUpdate: failed after ${maxRetries} retries for key "${key}"`);
}
```

## 5. Metadata-Only Reads for Hot Paths

When only metadata (TTL, custom fields) is needed — not the value — use `getWithMetadata` with `cacheTtl` to avoid fetching the full value body:

```typescript
// lib/kv-metadata-check.ts

interface UserMeta {
  tier:      "free" | "pro" | "enterprise";
  expiresAt: number;
}

export async function getUserTier(
  kv: KVNamespace,
  userId: string
): Promise<UserMeta | null> {
  // Fetches ONLY the metadata; value body is not transferred
  const { metadata } = await kv.getWithMetadata<UserMeta>(
    `user:${userId}:session`,
    { cacheTtl: 60 } // cache at the edge for 60 s
  );
  return metadata;
}
```

## 6. KV List + Bulk Delete Pipeline

```typescript
// scripts/kv-bulk-delete.ts — run as a scheduled Worker cron
export async function deleteExpiredKeys(
  kv: KVNamespace,
  prefix: string
): Promise<number> {
  let cursor: string | undefined;
  let deleted = 0;

  do {
    const page = await kv.list({ prefix, cursor, limit: 100 });

    // Parallel deletes within the page
    await Promise.all(page.keys.map((key) => kv.delete(key.name)));
    deleted += page.keys.length;

    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  return deleted;
}
```

## Anti-patterns

- **Awaiting KV writes before returning the Response** — writes are eventually consistent; there is no benefit in blocking the response on `put`. Use `ctx.waitUntil` instead.
- **Sequential `await kv.get()` in a loop** — each iteration waits for network round-trip before issuing the next. Replace with `Promise.all`.
- **High-frequency per-key increments** — KV allows ~1 write/second globally per key; a counter incremented on every request will drop writes silently. Use Durable Objects or Analytics Engine for high-frequency counters.
- **Using KV as a lock mechanism** — there is no atomic test-and-set; two Workers can simultaneously read the same value and both believe they hold the lock. Use Durable Objects for mutual exclusion.
- **Storing large values in KV without chunking** — KV has a 25 MB per-value limit, but reads of multi-MB values block the Worker until fully transferred. Chunk large objects or use R2.

## Gotchas

- `kv.list()` is significantly slower than `kv.get()` — listing is a metadata scan, not a point lookup. Never list on the hot request path.
- `cacheTtl` in `kv.get()` options refers to the edge cache TTL for the metadata; the value itself is always fetched fresh unless the edge cache holds it.
- On the free Workers plan, KV is subject to a 100,000 read/day limit and 1,000 write/day limit. Parallel reads consume from the read budget proportionally.
- `Promise.all` rejection is all-or-nothing; wrap individual promises in a settle helper if partial failure is acceptable.

## Verification

```typescript
// Benchmark sequential vs parallel reads
async function benchmarkKvReads(kv: KVNamespace): Promise<void> {
  const keys = Array.from({ length: 10 }, (_, i) => `bench:key:${i}`);

  // Sequential baseline
  const t0 = Date.now();
  for (const key of keys) await kv.get(key);
  console.log("Sequential:", Date.now() - t0, "ms");

  // Parallel
  const t1 = Date.now();
  await Promise.all(keys.map((k) => kv.get(k)));
  console.log("Parallel:  ", Date.now() - t1, "ms");
}
```

Expected: parallel reads complete in roughly the time of a single read; sequential reads multiply single-read latency by key count.

## Related

- `kv-bulk-get-batching.md`
- `kv-metadata-only-reads-optimization.md`
- `kv-read-performance.md`
- `durable-objects-rpc-batch-coalescing.md`
- `workers-request-coalescing-deduplication.md`

## Sources

- Cloudflare KV API reference — developers.cloudflare.com/kv/api
- KV limits and quotas — developers.cloudflare.com/kv/platform/limits
- Workers subrequest limits — developers.cloudflare.com/workers/platform/limits#subrequests
- Durable Objects for atomic updates — developers.cloudflare.com/durable-objects
