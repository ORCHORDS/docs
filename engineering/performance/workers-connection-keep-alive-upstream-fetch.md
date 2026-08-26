# Reusing Upstream HTTP Connections in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker that fans out multiple `fetch()` calls to the same upstream origin suffers from repeated TCP + TLS handshake overhead. Each subrequest from a cold isolate pays the full connection setup cost, inflating p95/p99 latency. Coalescing requests and using Cloudflare's built-in caching layer eliminates most of this overhead without managing a connection pool manually.

## Context

- Runtime: Cloudflare Workers (V8 isolates)
- APIs used: `fetch`, `caches`, `ExecutionContext.waitUntil`
- Cloudflare feature: subrequest coalescing, `cf` fetch options, Cache API
- Upstream: any HTTP/1.1 or HTTP/2 origin

---

## Section 1 — cf.cacheEverything for Upstream Fetch Reuse

Cloudflare reuses keep-alive connections to origins automatically when Workers use the `cf` options object. `cf.cacheEverything: true` tells the CF edge to cache the upstream response even if the origin doesn't send cache headers, turning repeated fetches into cache hits served from memory without touching the origin socket.

```typescript
export interface Env {
  UPSTREAM_ORIGIN: string; // e.g. "https://api.internal.example.com"
}

async function fetchWithCacheEverything(
  url: string,
  ttlSeconds: number,
  request: Request,
): Promise<Response> {
  return fetch(url, {
    // Pass the incoming request headers to the upstream (or build your own)
    headers: {
      'Accept': 'application/json',
      'X-Forwarded-For': request.headers.get('CF-Connecting-IP') ?? '',
    },
    cf: {
      // Cache the upstream response at the CF edge regardless of origin cache headers
      cacheEverything: true,
      // TTL for cacheable responses (2xx)
      cacheTtl: ttlSeconds,
      // Per-status-code TTL overrides
      cacheTtlByStatus: {
        '200-299': ttlSeconds,
        '404': 10,
        '500-599': 0, // never cache errors
      },
    },
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const apiUrl = `${env.UPSTREAM_ORIGIN}/data`;

    const upstream = await fetchWithCacheEverything(apiUrl, 60, request);

    if (!upstream.ok) {
      return new Response('Upstream error', { status: 502 });
    }

    const data = await upstream.json();
    return Response.json(data, {
      headers: {
        'Cache-Control': 'public, max-age=30',
        'X-Cache-Status': upstream.headers.get('CF-Cache-Status') ?? 'UNKNOWN',
      },
    });
  },
};
```

---

## Section 2 — Subrequest Coalescing with the Cache API

When multiple Workers isolates on the same PoP receive concurrent requests for the same upstream resource, coalescing prevents redundant subrequests. Use the Cache API to write the result once and serve it to all waiting isolates.

```typescript
async function coalesceOrFetch(
  cacheKey: Request,
  fetcher: () => Promise<Response>,
  ttlSeconds: number,
): Promise<Response> {
  const cache = caches.default;

  // 1. Try the cache first — a hit is a zero-subrequest path
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached;
  }

  // 2. Cache miss — make the real subrequest
  const fresh = await fetcher();

  // 3. Only cache successful responses
  if (fresh.ok) {
    // Clone before consuming: cache.put reads the body stream
    const toCache = fresh.clone();

    // Rewrite headers so the CF cache respects our TTL
    const headers = new Headers(toCache.headers);
    headers.set('Cache-Control', `public, max-age=${ttlSeconds}`);
    headers.set('Vary', 'Accept-Encoding');

    const cacheable = new Response(toCache.body, {
      status: toCache.status,
      headers,
    });

    // cache.put does not block the response path when awaited here;
    // alternatively, use ctx.waitUntil (see Section 3)
    await cache.put(cacheKey, cacheable);
  }

  return fresh;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const targetUrl = 'https://api.internal.example.com/heavy-resource';
    const cacheKey = new Request(targetUrl, { method: 'GET' });

    const response = await coalesceOrFetch(
      cacheKey,
      () => fetch(targetUrl, { cf: { cacheEverything: true, cacheTtl: 120 } }),
      120,
    );

    return new Response(response.body, {
      status: response.status,
      headers: response.headers,
    });
  },
};
```

---

## Section 3 — waitUntil for Background Prefetch Warming

`ctx.waitUntil` extends the Worker's lifetime beyond the response, allowing background subrequests to pre-warm the cache for the *next* request without adding latency to the current one.

```typescript
const PREFETCH_URLS = [
  'https://api.internal.example.com/config',
  'https://api.internal.example.com/feature-flags',
];

async function warmCache(url: string): Promise<void> {
  const cache = caches.default;
  const key = new Request(url);
  const hit = await cache.match(key);
  if (hit) return; // already warm

  const fresh = await fetch(url, {
    cf: { cacheEverything: true, cacheTtl: 300 },
  });

  if (fresh.ok) {
    const headers = new Headers(fresh.headers);
    headers.set('Cache-Control', 'public, max-age=300');
    await cache.put(key, new Response(fresh.clone().body, { status: 200, headers }));
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Respond immediately
    const mainResponse = await fetch(`${env.UPSTREAM_ORIGIN}/main`, {
      cf: { cacheEverything: true, cacheTtl: 60 },
    });

    // Fire-and-forget: warm ancillary cache entries after the response is sent
    ctx.waitUntil(
      Promise.allSettled(PREFETCH_URLS.map(warmCache))
    );

    return new Response(mainResponse.body, {
      status: mainResponse.status,
      headers: mainResponse.headers,
    });
  },
};
```

---

## Anti-patterns

- Opening a new `fetch` to the upstream per request without any cache layer — TCP+TLS cost multiplied by RPS
- Using `cache.put` inside `waitUntil` AND `await`-ing it inline — pick one; both causes double writes
- Setting `cacheEverything: true` on authenticated upstream calls — returns other users' private data
- Using `cacheTtl: 0` on a resource you intend to coalesce — zero TTL bypasses the cache entirely
- Storing upstream responses in KV instead of the Cache API for high-frequency read paths — KV has higher read latency than the Cache API at the same PoP

## Gotchas

- `cf.cacheEverything` only applies to *outgoing* subrequests, not to the Worker response itself
- Workers are limited to 50 subrequests per invocation by default (1000 on paid plans)
- `cache.put` on a URL with a `Set-Cookie` header strips the cookie before storing
- `CF-Cache-Status: MISS` on the first request is expected; subsequent requests from the same PoP should show `HIT`
- `waitUntil` callbacks that throw do not surface as errors to the client — add `.catch(console.error)` for observability

## Verification

```bash
wrangler deploy

WORKER_URL="https://your-worker.workers.dev"

# First request — expect CF-Cache-Status: MISS
curl -sI "$WORKER_URL" | grep -i 'cf-cache-status\|x-cache'

# Second request from same region — expect HIT
curl -sI "$WORKER_URL" | grep -i 'cf-cache-status\|x-cache'

# Measure latency difference (MISS vs HIT)
for i in $(seq 1 5); do
  curl -s -o /dev/null -w "Total: %{time_total}s | TTFB: %{time_starttransfer}s\n" \
    "$WORKER_URL"
done

# Check subrequest count in Wrangler logs
wrangler tail --format pretty
```

## Related

- `documentation/categories/performance/workers-cache-ttl-tiered-kv-strategy.md`
- `documentation/categories/performance/workers-brotli-compression-response-optimization.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/cache/how-to/edge-browser-cache-ttl/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/#requestinitcfproperties
