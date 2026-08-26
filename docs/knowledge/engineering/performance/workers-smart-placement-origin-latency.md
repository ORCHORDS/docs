# Workers Smart Placement: Minimizing Origin Latency

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Cloudflare Worker runs close to the end user but makes heavy subrequests to a single-region origin database, adding 150–400 ms of round-trip latency on every request. Enabling Smart Placement routes the Worker invocation to the datacenter closest to the origin instead.

## Context
By default Cloudflare runs a Worker in the PoP nearest to the client. When the Worker's critical path is dominated by calls to an origin or database (not by compute), the extra hop from client → near-PoP → distant origin is slower than client → distant-PoP-near-origin. Smart Placement uses latency telemetry to automatically pick the optimal PoP. It is configured in `wrangler.toml` with a single flag and requires no code changes, but the application architecture must be compatible.

## Enabling Smart Placement

Add `smart_placement` to `wrangler.toml`:

```toml
name = "api-worker"
compatibility_date = "2025-01-01"

[placement]
mode = "smart"
```

Smart Placement is incompatible with `colo` bindings or Workers that rely on the client's geographic proximity for correctness (e.g., geo-routing logic that reads `request.cf.country`). Audit subrequest patterns before enabling.

## Measuring the Baseline

Instrument your Worker to emit server-timing headers so you can compare before/after:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const t0 = Date.now();

    // Simulate origin call
    const originRes = await fetch(env.ORIGIN_URL + new URL(request.url).pathname, {
      headers: { "x-forwarded-for": request.headers.get("cf-connecting-ip") ?? "" },
    });

    const originMs = Date.now() - t0;

    const body = await originRes.text();
    const totalMs = Date.now() - t0;

    return new Response(body, {
      status: originRes.status,
      headers: {
        "content-type": originRes.headers.get("content-type") ?? "text/plain",
        "server-timing": `origin;dur=${originMs}, total;dur=${totalMs}`,
        "x-worker-colo": (request as any).cf?.colo ?? "unknown",
      },
    });
  },
};
```

Log `x-worker-colo` to confirm Smart Placement is selecting a PoP near your origin.

## Hybrid: Smart Placement with Edge Caching

Smart Placement and the Cache API work together. Cache responses at the PoP where the Worker runs (now near origin) and serve cache hits globally without paying origin RTT:

```typescript
const CACHE_TTL = 30; // seconds

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(request.url, { method: "GET" });

    const cached = await cache.match(cacheKey);
    if (cached) {
      return new Response(cached.body, {
        status: cached.status,
        headers: { ...Object.fromEntries(cached.headers), "x-cache": "HIT" },
      });
    }

    const origin = await fetch(env.ORIGIN_URL + new URL(request.url).pathname);
    const body = await origin.arrayBuffer();

    const response = new Response(body, {
      status: origin.status,
      headers: {
        "content-type": origin.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": `public, max-age=${CACHE_TTL}`,
        "x-cache": "MISS",
      },
    });

    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
```

## Incompatibility Checks

Before enabling Smart Placement, verify no correctness dependency on client PoP:

```typescript
function usesClientGeo(request: Request): boolean {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;
  // These fields reflect where the Worker runs, not where the client is,
  // when Smart Placement moves the Worker to a distant PoP.
  const geoFields: (keyof IncomingRequestCfProperties)[] = [
    "country", "city", "continent", "latitude", "longitude", "timezone",
  ];
  return geoFields.some((f) => cf?.[f] !== undefined);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (usesClientGeo(request) && env.SMART_PLACEMENT_ENABLED === "true") {
      // Fall back to a geo-aware path or disable Smart Placement for this route
      console.warn("Smart Placement active but geo fields read — verify correctness");
    }
    // ... rest of handler
    return new Response("ok");
  },
};
```

## Anti-patterns
- Enabling Smart Placement when the Worker performs significant CPU-bound work that benefits from client proximity (e.g., video transcoding near the user)
- Reading `cf.country` or `cf.city` for routing decisions while Smart Placement is active — these values reflect the Worker's PoP, not the client's
- Using Smart Placement with Durable Objects that are pinned to a specific location; DO jurisdiction and Smart Placement are orthogonal and can conflict

## Gotchas
- Smart Placement only activates after Cloudflare collects enough latency samples; new Workers may run in default mode for up to 24 hours
- `wrangler tail` shows the actual colo the Worker ran in — use this to confirm placement shifted
- Cache API `put` stores at the Worker's PoP; with Smart Placement that PoP may be far from end users, so CDN cache hit rates for that PoP drop until other PoPs populate via tiered caching

## Verification
1. Deploy with `[placement] mode = "smart"` and instrument `server-timing` headers
2. Run `wrangler tail --format=json | jq '.outcome, .cf.colo'` to observe which colo executes
3. Compare P50/P95 `origin` timing in server-timing before and after — expect 30–60% reduction for single-region origins
4. Confirm `x-worker-colo` value shifts toward your origin's region after 24 hours of traffic

## Related
- [workers-subrequest-fanout-parallelism.md](workers-subrequest-fanout-parallelism.md)
- [workers-fetch-connection-reuse-tcp.md](workers-fetch-connection-reuse-tcp.md)
- [cloudflare-cache-rules-vs-workers-cache-api.md](cloudflare-cache-rules-vs-workers-cache-api.md)
- [ttfb-optimization.md](ttfb-optimization.md)

## Sources
- Cloudflare Docs: Smart Placement — https://developers.cloudflare.com/workers/configuration/smart-placement/
- Cloudflare Blog: Announcing Smart Placement for Cloudflare Workers
- HTTP Archive Web Almanac: CDN latency impact on TTFB 2025
