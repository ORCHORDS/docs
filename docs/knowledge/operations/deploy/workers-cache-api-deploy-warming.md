# Workers Cache API Deploy Warming

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a new Worker version, the first wave of real user traffic hits cold cache — response times spike for 60–120 seconds and your p99 SLO breaches before the cache repopulates naturally. Error rates tick up from origin overload during the cold window. You need to pre-warm the Workers Cache API for critical paths before shifting production traffic to the new version.

## Context

Workers use the Cache API (`caches.default`) to store responses at Cloudflare edge PoPs. Cache is **local to each PoP** and is logically associated with the Worker version; a new Worker deploy can invalidate cached responses depending on how cache keys are constructed. Warming the cache before completing a gradual rollout (or before the next scheduled burst of traffic) means issuing synthetic requests to critical cacheable endpoints from the same origin domain, so subsequent user requests return `cf-cache-status: HIT` rather than `MISS`. This is distinct from cold-start prewarming, which deals with Worker process initialisation; cache warming is about the response store.

## 1. Worker-Side: Consistent Cache-Control for Warmable Responses

```typescript
// src/index.ts — responses must opt into caching for warming to take effect
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    // Normalise the cache key to strip query string variants that shouldn't differ
    const cacheKey = new Request(new URL(request.url).origin + new URL(request.url).pathname, {
      method: "GET",
      headers: { Accept: request.headers.get("Accept") ?? "*/*" },
    });

    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const response = await handleRequest(request, env);

    if (request.method === "GET" && response.status === 200) {
      const cacheable = new Response(response.clone().body, {
        status: 200,
        headers: {
          ...Object.fromEntries(response.headers),
          "Cache-Control": "public, max-age=300, s-maxage=3600",
          "Vary": "Accept-Encoding",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, cacheable));
    }
    return response;
  },
};
```

## 2. Post-Deploy Warming Script

```typescript
// scripts/warm-cache.ts — run immediately after wrangler deploy in CI
const WORKER_URL = process.env.WORKER_URL!; // e.g. https://my-worker.example.com
const CONCURRENCY = 3;

const WARM_TARGETS = [
  { path: "/",              priority: 1 },
  { path: "/api/config",   priority: 1 },
  { path: "/products",     priority: 2 },
  { path: "/categories",   priority: 2 },
  { path: "/api/featured", priority: 3 },
];

async function warmPath(path: string): Promise<void> {
  const url = `${WORKER_URL}${path}`;

  // First pass: populate cache (bypass any existing stale entry)
  await fetch(url, { headers: { "Cache-Control": "no-cache" } });

  // Second pass: confirm cache is now populated
  const r2 = await fetch(url);
  const cacheStatus = r2.headers.get("cf-cache-status") ?? "UNKNOWN";
  const age = r2.headers.get("age") ?? "0";

  if (cacheStatus !== "HIT") {
    console.warn(`  [MISS] ${path} — cache status: ${cacheStatus}`);
  } else {
    console.log(`  [HIT]  ${path} — age: ${age}s`);
  }
}

const sorted = [...WARM_TARGETS].sort((a, b) => a.priority - b.priority);
for (let i = 0; i < sorted.length; i += CONCURRENCY) {
  await Promise.all(sorted.slice(i, i + CONCURRENCY).map(t => warmPath(t.path)));
}
console.log("Cache warming complete.");
```

## 3. Scheduled Warming via Wrangler Cron

```toml
# wrangler.toml — keep the cache warm on a schedule aligned with deploy windows
[triggers]
crons = ["*/5 * * * *"]   # fires within 5 min of deploy; subsequent runs extend TTL
```

```typescript
// src/index.ts — cron handler re-warms on schedule
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const targets = ["/", "/api/config", "/products"];
    const base = `https://${env.WORKER_HOST}`;

    await Promise.all(
      targets.map(async path => {
        const res = await fetch(`${base}${path}`, {
          headers: { "Cache-Control": "no-cache", "X-Internal-Warm": "1" },
        });
        console.log(`Warmed ${path}: ${res.status} cache=${res.headers.get("cf-cache-status")}`);
      })
    );
  },

  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Ignore internal warm requests from the scheduler
    if (request.headers.get("X-Internal-Warm") === "1") {
      return new Response(null, { status: 204 });
    }
    return handleRequest(request, env, ctx);
  },
};
```

## 4. GitHub Actions — Warm After Deploy, Fail on Cold Cache

```yaml
# .github/workflows/deploy-and-warm.yml
name: Deploy and Warm Cache
on:
  push:
    branches: [main]

jobs:
  deploy-and-warm:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env production

      - name: Wait for propagation
        run: sleep 12

      - uses: actions/setup-node@v4
        with: { node-version: "22" }

      - name: Warm cache
        run: npx tsx scripts/warm-cache.ts
        env:
          WORKER_URL: https://my-worker.example.com

      - name: Assert cache warm for critical paths
        run: |
          for path in "/" "/api/config" "/products"; do
            STATUS=$(curl -sI "https://my-worker.example.com${path}" \
              | grep -i "cf-cache-status" | awk '{print $2}' | tr -d '\r')
            echo "${path}: ${STATUS}"
            if [ "$STATUS" != "HIT" ]; then
              echo "::warning::Cache not warm for ${path} (status: ${STATUS})"
            fi
          done
```

## 5. Tracking Cache Hit Rate Post-Deploy

```typescript
// src/index.ts — emit cache metrics to Cloudflare Analytics Engine
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(new URL(request.url).origin + new URL(request.url).pathname);
    const cached = await cache.match(cacheKey);

    const isHit = cached !== undefined;
    // Write to Analytics Engine for cache hit rate monitoring post-deploy
    ctx.waitUntil(
      (env.ANALYTICS as AnalyticsEngineDataset | undefined)?.writeDataPoint({
        blobs: [new URL(request.url).pathname],
        doubles: [isHit ? 1 : 0],
        indexes: ["cache_hit_rate"],
      }) ?? Promise.resolve()
    );

    return cached ?? handleAndCache(request, env, ctx, cacheKey);
  },
};
```

## Anti-patterns

- Warming against the `workers.dev` subdomain — Cloudflare may cache differently at `workers.dev` than at your custom domain; always warm the production domain.
- Not waiting after deploy before warming — the new Worker version may not be fully propagated to all PoPs in under 10 seconds; issue a sleep before firing warming requests.
- Using `Cache-Control: no-store` on responses intended to be cacheable — warming has no effect because the response is never stored.
- Warming from a single geographic location — cache is PoP-local; a single probe only warms one or a few edge locations.
- Caching responses that contain user-specific data (auth tokens, session info) — cache poisoning risk; always gate caching on `request.method === "GET"` and verify there is no `Authorization` header before storing.

## Gotchas

- `cf-cache-status: BYPASS` means a `Cache-Control: no-store`, `Set-Cookie`, or `Authorization` response header is preventing storage — fix response headers before warming.
- Cache eviction after deploy is not universal; Workers deployed via gradual rollout (`--percent`) preserve the old version's cached responses for the traffic still routed to it until the rollout completes.
- `caches.default` is shared across all Workers serving the same hostname at a PoP — a warming request from a co-located scheduled Worker is cache-equivalent to a real user request.
- Responses larger than 512 MB cannot be stored in the Workers Cache API.
- `Vary: Accept-Encoding` causes Brotli and gzip compressed responses to be cached separately — warm with `Accept-Encoding: br` in addition to no encoding header for full coverage.
- Cache TTL countdown begins at first storage; a warm response with `max-age=300` expires 5 minutes after the warming request, not 5 minutes after the next user request.

## Verification

```bash
# First request: should be MISS
curl -sI https://my-worker.example.com/ | grep -i "cf-cache-status"
# Expected: cf-cache-status: MISS  (or EXPIRED on redeploy)

# After warming — second request should be HIT
curl -sI https://my-worker.example.com/ | grep -i "cf-cache-status"
# Expected: cf-cache-status: HIT

# Check TTL remaining via Age header
curl -sI https://my-worker.example.com/api/config | grep -i "^age:"
# Expected: age: <N>  where N > 0

# Full warming run
WORKER_URL=https://my-worker.example.com npx tsx scripts/warm-cache.ts
```

## Related

- `deploy-cold-start-prewarming.md`
- `worker-versioning-gradual-rollout.md`
- `workers-version-rollback-automation-health-check.md`
- `workers-placement-score-monitoring-post-deploy.md`
- `synthetic-monitoring-deploy.md`
- `cloudflare-smart-placement-deploy-optimization.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/cache/concepts/cache-status/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
