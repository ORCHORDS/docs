# Cost Optimization for Cloudflare Workers at Scale

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers deployment handling 500 million+ requests per month reaches a point
where the per-request and CPU-time charges compound into material infrastructure
spend. Naive implementations double or triple cost through unnecessary subrequests,
avoidable cache misses, CPU-heavy JavaScript in the hot path, and redundant
Durable Object wake-ups. This article provides concrete patterns to reduce
Workers spend without degrading functionality.

## Context

Cloudflare Workers Standard pricing (2026):
- **Requests**: first 10M/month free, $0.30/million after
- **CPU time**: first 30M CPU-ms/month free, $0.02/million CPU-ms after
- **Subrequests (fetch)**: free up to 1M/Worker invocation; cross-PoP charged
- **KV reads**: $0.50/million; KV writes: $5.00/million
- **D1 reads**: $0.001/million rows; D1 writes: $1.00/million rows
- **R2 Class A (writes)**: $4.50/million; Class B (reads): $0.36/million
- **Durable Objects**: $0.15/million requests + $0.20/GB-month storage

The biggest levers in order of typical impact:
1. Cache hits at the CF edge (zero Worker invocation)
2. CPU time reduction in hot paths
3. KV / D1 read coalescing
4. Durable Object invocation reduction
5. Subrequest count reduction

---

## Section 1: Edge Cache and Cache API Maximization

Every request that returns a cached response never invokes a Worker. The default
`Cache-Control` header from many frameworks is `no-cache, no-store`, which defeats
edge caching entirely.

```typescript
// Pattern: explicit cache with stale-while-revalidate for dynamic content
export default {
  async fetch(req: Request, ctx: ExecutionContext): Promise<Response> {
    const cacheKey = new Request(canonicalize(req.url), {
      method: "GET", // normalize POST→GET for cacheable API patterns
      headers: { Accept: req.headers.get("Accept") ?? "application/json" },
    });

    const cache = caches.default;
    let response = await cache.match(cacheKey);
    if (response) {
      // Serve from cache, potentially revalidate in background
      const age = Date.now() - new Date(response.headers.get("Date") ?? 0).getTime();
      const maxAge = parseInt(response.headers.get("X-Cache-Max-Age") ?? "60") * 1000;
      if (age > maxAge * 0.8) {
        // Revalidate while serving stale
        ctx.waitUntil(revalidate(cacheKey, cache));
      }
      return response;
    }

    response = await generateResponse(req);
    const cacheable = new Response(response.body, response);
    cacheable.headers.set("Cache-Control", "s-maxage=60, stale-while-revalidate=30");
    cacheable.headers.set("X-Cache-Max-Age", "60");
    cacheable.headers.set("Date", new Date().toUTCString());
    ctx.waitUntil(cache.put(cacheKey, cacheable.clone()));
    return cacheable;
  },
};

function canonicalize(url: string): string {
  const u = new URL(url);
  // Remove tracking params that create spurious cache keys
  ["utm_source", "utm_medium", "utm_campaign", "fbclid", "gclid"].forEach(p =>
    u.searchParams.delete(p)
  );
  u.searchParams.sort(); // normalize param order
  return u.toString();
}

async function revalidate(key: Request, cache: Cache): Promise<void> {
  const fresh = await generateResponse(key);
  const cacheable = new Response(fresh.body, fresh);
  cacheable.headers.set("Cache-Control", "s-maxage=60, stale-while-revalidate=30");
  cacheable.headers.set("Date", new Date().toUTCString());
  await cache.put(key, cacheable);
}

async function generateResponse(req: Request): Promise<Response> {
  // Actual business logic
  return new Response(JSON.stringify({ ts: Date.now() }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

Cache hit rate target: aim for >90% on read-heavy APIs. Each 1% improvement
on 100M requests/month saves ~300K invocations = ~$90/month at standard pricing.

---

## Section 2: CPU Time Reduction in Hot Paths

CPU time is the most controllable billing lever. Target: <5 ms CPU per p95 request.

**Replace heavy JSON parsing with streaming:**

```typescript
// Expensive: parses entire body, stringifies, re-parses
const body = await req.json(); // full parse
const mutated = transform(body);
return new Response(JSON.stringify(mutated));

// Cheaper: use TransformStream for large payloads
function streamingTransform(input: ReadableStream): ReadableStream {
  const { readable, writable } = new TransformStream({
    transform(chunk, controller) {
      // Process chunk without materializing full object
      controller.enqueue(processChunk(chunk));
    },
  });
  input.pipeTo(writable);
  return readable;
}
```

**Avoid regexp in the hot path:**

```typescript
// Expensive: compiled regexp on every request
const ROUTE_RE = /^\/api\/v\d+\/([^/]+)\/(\d+)$/;
function route(path: string) {
  return path.match(ROUTE_RE);
}

// Cheaper: URLPattern (compiled once at module scope)
const ROUTE = new URLPattern({ pathname: "/api/v:version/:resource/:id" });
function route(path: string) {
  return ROUTE.exec({ pathname: path });
}
```

**Lazy-initialize expensive objects:**

```typescript
let _cryptoKey: CryptoKey | undefined;
async function getSigningKey(env: Env): Promise<CryptoKey> {
  if (!_cryptoKey) {
    _cryptoKey = await crypto.subtle.importKey(
      "raw",
      hexToBytes(env.SIGNING_KEY),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign", "verify"]
    );
  }
  return _cryptoKey;
}
// Module-level initialization persists across invocations in the same isolate.
// Workers isolates are reused for ~30 seconds to minutes, so this saves
// repeated importKey calls.
```

**Profile with the Workers CPU timer:**

```typescript
export default {
  async fetch(req: Request): Promise<Response> {
    const t0 = Date.now();
    const result = await expensiveOperation();
    const cpuMs = Date.now() - t0;
    console.log(JSON.stringify({ path: new URL(req.url).pathname, cpu_ms: cpuMs }));
    return new Response(JSON.stringify(result));
  },
};
// Tail logs with: wrangler tail --format json | jq 'select(.logs[].message | contains("cpu_ms"))'
```

---

## Section 3: KV, D1, and Durable Object Cost Reduction

**KV: batch reads and aggressive TTLs:**

```typescript
// Expensive: 10 separate KV reads = 10 billed operations
const [a, b, c, d, e, f, g, h, i, j] = await Promise.all([
  env.KV.get("k1"), env.KV.get("k2"), /* ... */
]);

// Better: store related keys as a single JSON blob
const bundle = await env.KV.get("config-bundle", { type: "json" });
// 1 read instead of 10

// Cache KV values in-memory for the isolate lifetime
const _kvCache = new Map<string, { val: unknown; exp: number }>();
async function cachedKvGet(kv: KVNamespace, key: string, ttlMs = 30_000) {
  const hit = _kvCache.get(key);
  if (hit && hit.exp > Date.now()) return hit.val;
  const val = await kv.get(key, { type: "json" });
  _kvCache.set(key, { val, exp: Date.now() + ttlMs });
  return val;
}
```

**D1: use prepared statements and batch API:**

```typescript
// Expensive: 5 separate D1 reads
await env.DB.prepare("SELECT * FROM users WHERE id=?").bind(1).first();
await env.DB.prepare("SELECT * FROM users WHERE id=?").bind(2).first();
// ...

// Cheap: single batch call
const results = await env.DB.batch([
  env.DB.prepare("SELECT * FROM users WHERE id=?").bind(1),
  env.DB.prepare("SELECT * FROM users WHERE id=?").bind(2),
  env.DB.prepare("SELECT * FROM orders WHERE user_id=?").bind(1),
]);
// 3 operations billed as 1 batch unit
```

**Durable Objects: coalesce with alarm and in-memory state:**

```typescript
// Expensive pattern: one DO request per user action
// Cheap pattern: accumulate in-memory, flush on alarm

export class WriteCoalescer implements DurableObject {
  private pending: Record<string, unknown>[] = [];
  private alarmSet = false;

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const body = await req.json<Record<string, unknown>>();
    this.pending.push(body);

    if (!this.alarmSet) {
      await this.state.storage.setAlarm(Date.now() + 1_000); // flush after 1s
      this.alarmSet = true;
    }

    return new Response("queued");
  }

  async alarm(): Promise<void> {
    if (this.pending.length === 0) return;
    const batch = [...this.pending];
    this.pending = [];
    this.alarmSet = false;

    // Single D1 batch instead of N individual writes
    await this.env.DB.batch(
      batch.map(item =>
        this.env.DB.prepare("INSERT INTO events (data) VALUES (?)").bind(
          JSON.stringify(item)
        )
      )
    );
  }
}
```

This pattern reduces DO requests by 10–50x for write-heavy workloads.

---

## Anti-patterns

- **Warm-cache invalidation on every write**: calling `cache.delete()` for every
  data mutation kills cache hit rates. Use versioned URLs (`/api/v1/users?v=<etag>`)
  or TTL-based expiry instead.
- **Creating a new Durable Object per request**: DO creation has overhead and storage
  cost. Share one DO across many requests using a shard key.
- **Awaiting non-critical subrequests**: logging, analytics pings, and event emissions
  should use `ctx.waitUntil()` not `await`. Otherwise they extend billable CPU time
  for the main response path.
- **Storing large blobs in KV**: KV values max out at 25 MB. Storing anything
  over ~1 MB in KV inflates read costs. Use R2 for large objects; store only the R2
  key in KV.
- **Using `wrangler dev` to benchmark CPU cost**: local dev uses a different V8
  isolate configuration than production. Always measure CPU time from `wrangler tail`
  on a staging deployment.
- **Ignoring tail Worker overhead**: Tail Workers run on every request for
  observability. If the tail Worker itself does expensive work (JSON parsing,
  fetch calls), it doubles the effective CPU cost of every invocation.

---

## Gotchas

- Workers isolates are reused but not guaranteed to persist. Module-level caches
  (like `_kvCache` or `_cryptoKey`) can disappear at any time. Never use them for
  consistency guarantees, only for performance hints.
- The `waitUntil()` execution counts toward the account's aggregate CPU time even
  though the user response has been sent. High-volume background tasks still appear
  in billing.
- Cache API does not cache responses with `Set-Cookie` headers by default. Strip or
  anonymize cookies before caching authenticated responses.
- D1 batch operations count as a single row-read unit for the API call but individual
  SQL row reads still sum toward D1 row billing. Batch reduces *API call* overhead,
  not SQL row reads.
- KV `get` with `cacheTtl` option avoids repeated reads to the KV store within the
  same region during the TTL window—useful but not a substitute for in-memory caching
  (which is zero-cost per read).

---

## Verification

```bash
# Check current month CPU time usage
curl -s -X POST "https://api.cloudflare.com/client/v4/graphql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { accounts(filter:{accountTag:\"'"$CF_ACCOUNT_ID"'\"}) { workersInvocationsAdaptive(limit:1 orderBy:[datetimeHour_DESC]) { sum { cpuTime requests } } } } }"}' | \
  jq '.data.viewer.accounts[0].workersInvocationsAdaptive[0].sum'

# Measure cache hit rate by checking the CF-Cache-Status header distribution
wrangler tail my-worker --format json | \
  jq -r '.response.headers["cf-cache-status"] // "MISS"' | \
  sort | uniq -c | sort -rn

# Profile specific endpoint CPU time
wrangler tail my-worker --format json | \
  jq 'select(.logs != null) | .logs[] | select(.message | type == "string") | .message' | \
  jq -r 'fromjson? | select(.cpu_ms) | "\(.path)\t\(.cpu_ms)"' | \
  sort -k2 -rn | head -20

# Estimate monthly cost from current sample
# (requests × $0.30/M) + (cpu_ms × $0.02/M)
```

---

## Related

- `/documentation/docs/policies/infra/workers-analytics-billing-monitoring.md`
- `/documentation/docs/policies/infra/cloudflare-workers-limits-resource-planning.md`
- `/documentation/docs/policies/infra/cloudflare-cost-attribution-tagging.md`
- `/documentation/docs/policies/infra/keda-cloudflare-queue-consumers.md`
- `/documentation/docs/policies/infra/cache-invalidation-strategies.md`

---

## Sources

- Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Cache API: https://developers.cloudflare.com/workers/runtime-apis/cache/
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Durable Objects pricing: https://developers.cloudflare.com/durable-objects/platform/pricing/
- Workers performance tuning: https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
- URLPattern API: https://developer.mozilla.org/en-US/docs/Web/API/URLPattern
