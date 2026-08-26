# KV Bulk Read and Cache Warming Strategy in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A Worker reads dozens of KV keys per request, suffering cumulative read latency of 30-100 ms per key at cold-start. You need a two-layer caching strategy — in-process `caches.default` as L1 in front of KV as L2 — plus a Cron Trigger that pre-warms the cache before peak traffic windows.

---

## Context
Cloudflare KV is globally replicated and eventually consistent, with read latency typically 5-20 ms from the nearest PoP after initial replication. However, on a cold Worker isolate the first read can be slower. Reading 50 keys sequentially accumulates 250-1000 ms of latency. `Promise.all` parallelises the reads, cutting total latency to the slowest single key. Layering `caches.default` (sub-millisecond, local PoP) in front of KV avoids repeated KV reads for hot keys. KV metadata fields provide a version/ETag for cache invalidation without reading the full value. A Cron Trigger pre-warms the cache before the morning traffic spike, ensuring the first real users hit L1.

---

## Section 1 — wrangler.toml

```toml
name = "kv-cache-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "CONFIG"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Cron Trigger for cache warm-up (runs at 07:50 UTC, 10 min before peak)
[[triggers.crons]]
cron = "50 7 * * *"
```

## Section 2 — Implementation

```typescript
import { KVNamespace, ExecutionContext, ScheduledEvent } from '@cloudflare/workers-types';

export interface Env {
  CONFIG: KVNamespace;
}

// Keys to pre-warm — in production, derive this list from KV list() or a manifest
const WARM_KEYS = [
  'feature-flags',
  'pricing-config',
  'rate-limits',
  'supported-locales',
  'maintenance-window',
];

const CACHE_TTL_SECONDS = 300; // 5 minutes in L1 cache

/** Build a canonical cache key URL from a KV key name. */
function kvCacheUrl(key: string): string {
  return `https://kv-cache.internal/keys/${encodeURIComponent(key)}`;
}

/**
 * Read a single KV key, using caches.default as L1.
 * Returns the parsed value and whether it was a cache hit.
 */
async function readWithCache(
  key: string,
  kv: KVNamespace
): Promise<{ value: unknown; source: 'l1-cache' | 'l2-kv' | 'miss' }> {
  const cache = caches.default;
  const cacheRequest = new Request(kvCacheUrl(key));

  // L1: Check caches.default first
  const cached = await cache.match(cacheRequest);
  if (cached) {
    return { value: await cached.json(), source: 'l1-cache' };
  }

  // L2: Fall through to KV
  const t0 = performance.now();
  const { value, metadata } = await kv.getWithMetadata<Record<string, unknown>>(key, 'json');
  const kvLatencyMs = performance.now() - t0;

  console.log(`KV read '${key}': ${kvLatencyMs.toFixed(1)} ms, version=${(metadata as any)?.version ?? 'n/a'}`);

  if (value === null) {
    return { value: null, source: 'miss' };
  }

  // Populate L1 cache
  const cacheResponse = new Response(JSON.stringify(value), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': `s-maxage=${CACHE_TTL_SECONDS}`,
      'X-KV-Version': String((metadata as any)?.version ?? ''),
    },
  });
  await cache.put(cacheRequest, cacheResponse);

  return { value, source: 'l2-kv' };
}

/**
 * Bulk read multiple KV keys in parallel.
 * Returns a map of key → value.
 */
async function bulkRead(
  keys: string[],
  kv: KVNamespace
): Promise<Map<string, unknown>> {
  const entries = await Promise.all(
    keys.map(async (key) => {
      const { value } = await readWithCache(key, kv);
      return [key, value] as const;
    })
  );
  return new Map(entries);
}

/**
 * Invalidate a specific key from L1 when KV is updated.
 * Call this in your write path after kv.put().
 */
async function invalidateL1(key: string): Promise<void> {
  const cache = caches.default;
  await cache.delete(new Request(kvCacheUrl(key)));
}

/**
 * Cache warm-up: read all WARM_KEYS from KV, populating L1.
 * Called by the Cron Trigger before peak traffic.
 */
async function warmCache(kv: KVNamespace): Promise<void> {
  console.log(`[cache-warm] Starting warm-up for ${WARM_KEYS.length} keys`);
  const t0 = performance.now();
  const results = await bulkRead(WARM_KEYS, kv);
  const elapsed = performance.now() - t0;
  const hits = [...results.values()].filter((v) => v !== null).length;
  console.log(`[cache-warm] Done: ${hits}/${WARM_KEYS.length} keys populated in ${elapsed.toFixed(1)} ms`);
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/config') {
      const t0 = performance.now();
      const config = await bulkRead(WARM_KEYS, env.CONFIG);
      const elapsedMs = performance.now() - t0;

      return Response.json({
        elapsedMs: parseFloat(elapsedMs.toFixed(2)),
        config: Object.fromEntries(config),
      });
    }

    if (url.pathname.startsWith('/config/') && request.method === 'PUT') {
      const key = decodeURIComponent(url.pathname.replace('/config/', ''));
      const body = await request.json<Record<string, unknown>>();
      const version = Date.now();

      await env.CONFIG.put(key, JSON.stringify(body), {
        metadata: { version },
      });

      // Invalidate L1 so next read pulls fresh KV value
      await invalidateL1(key);

      return Response.json({ ok: true, key, version });
    }

    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await warmCache(env.CONFIG);
  },
};
```

## Section 3 — KV Latency Benchmark Script

```bash
#!/usr/bin/env bash
# bench-kv.sh — measure L1 vs L2 read latency

WORKER_URL="https://my-worker.example.com/config"

echo "=== Cold request (likely L2-KV) ==="
curl -w "\nTotal: %{time_total}s\n" -s "$WORKER_URL" | jq '{elapsedMs: .elapsedMs}'

echo ""
echo "=== Warm request (likely L1 cache) ==="
curl -w "\nTotal: %{time_total}s\n" -s "$WORKER_URL" | jq '{elapsedMs: .elapsedMs}'

echo ""
echo "=== Trigger cache invalidation for feature-flags ==="
curl -s -X PUT "$WORKER_URL/feature-flags" \
  -H 'Content-Type: application/json' \
  -d '{"newFeature": true}' | jq .

echo ""
echo "=== Post-invalidation request (back to L2-KV) ==="
curl -w "\nTotal: %{time_total}s\n" -s "$WORKER_URL" | jq '{elapsedMs: .elapsedMs}'
```

---

## Anti-patterns
- **Sequential KV reads in a loop** — `for (const key of keys) { await kv.get(key) }` accumulates latency multiplicatively; always use `Promise.all`.
- **Ignoring KV metadata for versioning** — reading the full value just to check freshness wastes bandwidth; store a `version` or `etag` in metadata.
- **Warming cache inside the fetch handler** — warm-up is slow; doing it on the first user request adds latency for that user; use Cron Triggers instead.
- **Putting `caches.default` entries without `Cache-Control`** — entries without `Cache-Control: s-maxage` may be evicted immediately; always set a TTL.

---

## Gotchas
- `caches.default` is per-PoP; warming from a Cron Trigger fires in *one* PoP. Real global warming requires warming requests from each major region or using KV with a short TTL as the sole layer.
- KV `getWithMetadata` counts as one subrequest, same as `get`; metadata does not come free.
- `performance.now()` in Workers returns a monotonic timestamp relative to the start of the request, not wall-clock epoch time.
- KV reads inside `scheduled()` handlers also count toward the 1 000-subrequest limit.
- Cron Triggers are fired at most once per minute; `wrangler dev` must use `--test-scheduled` to trigger the `scheduled` handler locally.

---

## Verification

```bash
# Trigger the cron handler manually via wrangler
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=50+7+*+*+*"

# Inspect Worker logs for warm-up output
wrangler tail --format pretty | grep cache-warm

# Confirm KV metadata is stored
wrangler kv:key get --binding=CONFIG feature-flags --metadata
```

---

## Related
- `workers-cache-api-stale-while-revalidate.md`
- `workers-subrequest-parallelism-promise-all.md`
- `workers-streaming-large-d1-result-set.md`

---

## Sources
- Cloudflare KV runtime API — https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- Cloudflare Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- KV metadata — https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
