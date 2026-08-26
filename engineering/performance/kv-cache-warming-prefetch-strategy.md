# KV Cache Warming and Prefetch Strategy — Eliminating Cold Read Latency

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

After a deployment or a KV namespace flush, the first wave of users experiences read
latency spikes of 40–120 ms on paths that normally serve from the KV edge cache in
<5 ms. Worker logs show `cf-cache-status: MISS` for several minutes post-deploy.
The app serves configuration data, feature flags, or semi-static content from KV and
cannot tolerate the cold-start read penalty on production traffic.

## Context

Workers KV propagates values to edge PoP caches on first read (or via explicit
`cacheTtl` hints). A fresh deployment, namespace migration, or forced expiry leaves
every PoP's local cache cold until organic traffic warms it. For low-traffic PoPs the
cache may never warm; for burst traffic patterns (marketing campaigns, cron-driven
jobs) the thundering-herd on a cold namespace causes cascading latency. Proactive
prefetch Cron Triggers or deploy hooks can pre-populate the edge cache before real
traffic arrives.

## Strategy 1 — Cron-Driven Namespace Warm

Read all critical keys immediately after a deploy to push values to all active PoPs.

```typescript
// src/warmer.ts
const CRITICAL_KEYS = [
  'config:feature-flags',
  'config:rate-limits',
  'content:homepage-hero',
  'content:nav-items',
] as const;

async function warmKeys(kv: KVNamespace): Promise<void> {
  // Fan out reads in parallel — each triggers a PoP-level cache fill
  const reads = CRITICAL_KEYS.map((key) =>
    kv.get(key, { cacheTtl: 300 }), // 5-minute edge cache TTL
  );
  const results = await Promise.allSettled(reads);

  const misses = results.filter((r) => r.status === 'rejected' || r.value === null);
  if (misses.length > 0) {
    console.warn(`Warm: ${misses.length} keys missing from KV`);
  } else {
    console.log(`Warm: all ${CRITICAL_KEYS.length} keys populated`);
  }
}

export default {
  // Triggered by Cron: "*/5 * * * *" for the first hour post-deploy
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await warmKeys(env.CONFIG_KV);
  },
};
```

## Strategy 2 — Deploy Hook via Wrangler Deploy Callback

Trigger a warm request immediately after `wrangler deploy` completes using a Workers
endpoint that fans out KV reads.

```typescript
// src/admin/warm.ts  — protected by a deploy secret header
export async function handleWarm(
  request: Request,
  env: Env,
): Promise<Response> {
  const secret = <redacted-secret>'X-Deploy-Secret');
  if (secret !== env.DEPLOY_SECRET) {
    return new Response('Forbidden', { status: 403 });
  }

  const keys = await listAllKeys(env.CONFIG_KV); // see Strategy 3
  const results = await Promise.allSettled(
    keys.map((key) => env.CONFIG_KV.get(key, { cacheTtl: 600 })),
  );

  const warmed = results.filter((r) => r.status === 'fulfilled').length;
  return Response.json({ warmed, total: keys.length });
}
```

```bash
# In CI pipeline, after wrangler deploy:
curl -X POST https://myapp.example.com/admin/warm \
  -H "X-Deploy-Secret: $DEPLOY_SECRET"
```

## Strategy 3 — Enumerate Keys for Full Namespace Warm

```typescript
async function listAllKeys(kv: KVNamespace): Promise<string[]> {
  const keys: string[] = [];
  let cursor: string | undefined;

  do {
    const page = await kv.list({ cursor, limit: 1000 });
    keys.push(...page.keys.map((k) => k.name));
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  return keys;
}
```

> For large namespaces (>10 k keys), filter by prefix and warm only hot-path keys
> to stay within Cron CPU limits (15 min wall-clock).

## Strategy 4 — Prefetch on Request Miss with `ctx.waitUntil`

When a request encounters a cache miss, pre-warm adjacent keys in the background
so the *next* request hits cache without blocking the current response.

```typescript
async function getWithPrefetch(
  kv: KVNamespace,
  key: string,
  adjacentKeys: string[],
  ctx: ExecutionContext,
): Promise<string | null> {
  const value = await kv.get(key, { cacheTtl: 300 });

  if (value === null) {
    // Key missing — nothing to prefetch
    return null;
  }

  // Prefetch siblings without blocking the response
  ctx.waitUntil(
    Promise.all(
      adjacentKeys.map((k) => kv.get(k, { cacheTtl: 300 })),
    ),
  );

  return value;
}
```

## Strategy 5 — Staggered Warm to Avoid KV Write Rate Limits

When re-populating after a flush, stagger writes across time to avoid hitting the
KV 1 write/s/key rate limit.

```typescript
async function staggeredRepopulate(
  kv: KVNamespace,
  entries: Array<{ key: string; value: string; ttl?: number }>,
  delayMs = 100,
): Promise<void> {
  for (const entry of entries) {
    await kv.put(entry.key, entry.value, {
      expirationTtl: entry.ttl ?? 3600,
    });
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
}
```

## Anti-patterns

- **Warming with `cacheTtl: 0`** — a TTL of 0 disables the edge cache entirely;
  reads always go to the KV storage tier. Always set `cacheTtl >= 60`.
- **Using `kv.list()` on the hot request path** — `list()` is slow and not cached;
  pre-enumerate keys in a Cron or deploy hook, not in request handlers.
- **Warming all keys in a single synchronous loop** — blocks CPU; use
  `Promise.all()` in batches of 20–50 to parallelise without overwhelming the
  sub-request budget (1000 subrequests/invocation).
- **Re-warming on every Cron tick indefinitely** — only warm during the post-deploy
  window (first 30–60 minutes) or when a `PUT` write is detected; constant reads
  generate unnecessary billing.

## Gotchas

- `cacheTtl` is a *hint* to the edge PoP; Cloudflare may cache for a shorter time if
  the PoP is under memory pressure or the value is very large (>25 MB total namespace
  limit per key is 25 MB but effective cache may be smaller).
- KV reads during Cron Triggers count against subrequest limits (1000 per invocation);
  a namespace with >1000 critical keys requires multiple Cron invocations or chunking.
- The KV global replication delay is up to 60 s after a `PUT`. Warm reads issued
  within that window may still see stale/missing values even after the write resolves.
- `ctx.waitUntil` extends the Worker beyond response delivery; very large prefetch
  fans can consume significant CPU-ms on the tail, which is billed.

## Verification

```bash
# Check cache hit rate after warming
wrangler tail --format=json | jq '.logs[] | select(.message | test("cf-cache-status"))' | \
  jq -s 'group_by(.message) | map({status: .[0].message, count: length})'

# Curl a warmed key and inspect response headers
curl -I https://myapp.example.com/api/config | grep -i 'cf-cache-status'
# Expected: HIT  (after warm), MISS (before)
```

## Related

- `kv-read-performance.md` — baseline KV read latency characteristics
- `kv-bulk-get-batching.md` — batching multiple KV reads per request
- `kv-metadata-only-reads-optimization.md` — lightweight reads using metadata
- `workers-cold-start-optimization.md` — reducing Worker cold start overhead

## Sources

- Cloudflare KV Docs: https://developers.cloudflare.com/kv/
- KV caching behaviour: https://developers.cloudflare.com/kv/api/read-key-value-pairs/#cachettl-parameter
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
