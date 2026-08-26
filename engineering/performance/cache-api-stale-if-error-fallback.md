# Cache API Stale-if-error Fallback Pattern in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An origin or upstream API starts returning 5xx errors. Without a fallback strategy the
Workers fetch propagates the error directly to the user. You want the Worker to serve the
most recently cached good response instead of the error, accepting slightly stale data in
exchange for availability — exactly what the `stale-if-error` Cache-Control directive
expresses but which the Cloudflare CDN layer does not honour for all response types and
which the Workers Cache API does not implement automatically.

---

## Context

`stale-while-revalidate` (covered in `workers-cache-api-stale-while-revalidate.md`) hides
revalidation latency from the user by serving a stale response while the fresh fetch runs
in the background. `stale-if-error` is a different directive: it serves a stale response
only when the upstream returns an error or is unreachable, and always attempts a fresh
fetch first. The two can be combined.

Cloudflare's CDN respects `stale-if-error` for cacheable assets served through the CDN
cache, but Workers that use `caches.default` or a named cache must implement the fallback
manually because the Cache API `match()` call does not evaluate error conditions
automatically.

example project platform use-cases:
- API gateway Worker fronting a D1-backed microservice: serve last-known-good JSON on DB
  outage.
- R2-served asset manifest: serve stale manifest when R2 returns 503 during a deploy.
- Third-party enrichment service: degrade gracefully rather than returning 500 to clients.

---

## Basic stale-if-error implementation

```typescript
const CACHE_NAME = 'example project-sie-v1';
const SIE_TTL_SECONDS = 600; // serve stale for up to 10 minutes on error

async function fetchWithStaleIfError(
  request: Request,
  ctx: ExecutionContext
): Promise<Response> {
  const cache = await caches.open(CACHE_NAME);
  const cacheKey = new Request(request.url); // strip auth headers from key

  // Always try the origin first
  let originResponse: Response;
  try {
    originResponse = await fetch(request);
  } catch (networkError) {
    // Network-level failure: fall back to cache immediately
    const stale = await cache.match(cacheKey);
    if (stale) return addStaleHeader(stale, 'network-error');
    throw networkError;
  }

  // Server-level error: try cache before propagating
  if (!originResponse.ok) {
    const stale = await cache.match(cacheKey);
    if (stale) return addStaleHeader(stale, `upstream-${originResponse.status}`);
    return originResponse; // no stale entry — surface the real error
  }

  // Success: store in cache with custom SIE TTL, return fresh
  const toCache = new Response(originResponse.clone().body, {
    status: originResponse.status,
    headers: {
      ...Object.fromEntries(originResponse.headers),
      // Overwrite cache-control so we control TTL independently of origin header
      'Cache-Control': `public, max-age=${SIE_TTL_SECONDS}, stale-if-error=${SIE_TTL_SECONDS}`,
      'X-Cached-At': new Date().toUTCString(),
    },
  });
  ctx.waitUntil(cache.put(cacheKey, toCache));

  return originResponse;
}

function addStaleHeader(response: Response, reason: string): Response {
  return new Response(response.body, {
    status: response.status,
    headers: {
      ...Object.fromEntries(response.headers),
      'X-Cache-Status': 'STALE',
      'X-Stale-Reason': reason,
    },
  });
}
```

---

## Combining stale-if-error with stale-while-revalidate

For endpoints that can tolerate slightly stale data even on success, combine both
strategies. The priority chain is: (1) fresh origin, (2) background revalidation while
serving stale, (3) on error serve stale, (4) propagate error if no cache entry.

```typescript
const MAX_STALE_MS = 30_000;     // 30 s — serve stale-while-revalidate window
const MAX_ERROR_STALE_MS = 600_000; // 10 min — serve stale-if-error window

async function fetchWithFullStaleStrategy(
  request: Request,
  ctx: ExecutionContext
): Promise<Response> {
  const cache = await caches.open(CACHE_NAME);
  const cacheKey = new Request(request.url);
  const cached = await cache.match(cacheKey);

  const cachedAt = cached
    ? Date.parse(cached.headers.get('X-Cached-At') ?? '0')
    : 0;
  const age = Date.now() - cachedAt;

  // Fresh cache hit — return immediately
  if (cached && age < MAX_STALE_MS) {
    return cached;
  }

  // Stale-while-revalidate window: return stale, revalidate in background
  if (cached && age < MAX_ERROR_STALE_MS) {
    ctx.waitUntil(revalidate(request, cache, cacheKey));
    return addStaleHeader(cached, 'swr');
  }

  // Beyond SIE window or no cache — must fetch live
  try {
    const fresh = await fetch(request);
    if (!fresh.ok && cached) return addStaleHeader(cached, `upstream-${fresh.status}`);
    if (fresh.ok) ctx.waitUntil(cache.put(cacheKey, stampResponse(fresh.clone())));
    return fresh;
  } catch {
    if (cached) return addStaleHeader(cached, 'network-error');
    throw new Error('Origin unreachable and no cached response available');
  }
}

async function revalidate(
  request: Request,
  cache: Cache,
  cacheKey: Request
): Promise<void> {
  try {
    const fresh = await fetch(request);
    if (fresh.ok) await cache.put(cacheKey, stampResponse(fresh));
  } catch {
    // Revalidation failure is silent — stale stays in cache
  }
}

function stampResponse(response: Response): Response {
  return new Response(response.body, {
    status: response.status,
    headers: {
      ...Object.fromEntries(response.headers),
      'Cache-Control': `public, max-age=30`,
      'X-Cached-At': new Date().toUTCString(),
    },
  });
}
```

---

## Cache key hygiene for SIE

Stale-if-error is only useful if the cache key matches the request the user will retry.
Strip volatile headers (Authorization, Cookie) from the key; vary only on dimensions that
actually affect the response body.

```typescript
function buildCacheKey(request: Request): Request {
  const url = new URL(request.url);
  // Remove any server-side tracking params that don't affect content
  url.searchParams.delete('_t');
  url.searchParams.delete('nocache');

  return new Request(url.toString(), {
    method: 'GET',
    // Do NOT include Authorization — stale responses must be safe to serve
    // to any authenticated user who would have received the same data.
    headers: {
      Accept: request.headers.get('Accept') ?? 'application/json',
      'Accept-Language': request.headers.get('Accept-Language') ?? '',
    },
  });
}
```

---

## Signalling staleness downstream

When serving a stale-if-error response, clients and monitoring should know. Use standard
headers plus a Cloudflare-compatible extension:

```typescript
function addStaleHeader(response: Response, reason: string): Response {
  const headers = new Headers(response.headers);
  headers.set('Age', String(computeAge(response)));   // RFC 7234 §5.1
  headers.set('Warning', '110 - "Response is Stale"'); // RFC 7234 §5.5.1
  headers.set('X-Cache-Status', 'STALE');
  headers.set('X-Stale-Reason', reason);
  return new Response(response.body, { status: response.status, headers });
}

function computeAge(response: Response): number {
  const cachedAt = Date.parse(response.headers.get('X-Cached-At') ?? '0');
  return Math.floor((Date.now() - cachedAt) / 1000);
}
```

---

## Anti-patterns

- **Serving stale 404 responses.** A cached 404 is a valid response to serve stale only
  if the resource genuinely did not exist at cache time. If 404 indicates a transient
  upstream condition, exclude 4xx from the SIE fallback.
- **Unbounded SIE window.** Without a maximum stale age, a Worker can serve data that is
  hours old. Set `MAX_ERROR_STALE_MS` to a value that reflects the data's acceptable
  staleness for your SLA.
- **Using `cache.default` for SIE without isolation.** The default cache is shared with
  Cloudflare CDN behaviour; use a named cache (`caches.open('name')`) for entries that
  carry custom SIE semantics.
- **Caching authenticated responses.** Never put user-specific data keyed only by URL into
  the shared cache. Strip auth before keying or use per-user Durable Objects instead.

---

## Gotchas

- The Workers Cache API `put()` is subject to a 512 MB per-entry size limit. Large
  responses that you want to protect with SIE should be stored in R2 instead and the
  cache used only to track metadata.
- `cache.put()` inside `waitUntil` does not guarantee delivery if the isolate is evicted
  before the promise resolves. Accept occasional cache misses.
- If the upstream returns a 5xx with `Cache-Control: no-store`, `cache.put()` will reject
  it — construct a synthetic cacheable response instead of caching the error itself.
- Workers Cache API writes are **eventually consistent** within a PoP; a second concurrent
  request on the same isolate may also miss the cache and hit origin during the brief
  window before `put()` settles.

---

## Verification

```bash
# Simulate origin failure by returning 503
wrangler dev --local &
# Hit the endpoint twice: first call populates cache
curl https://localhost:8787/api/data
# Kill mock origin, confirm stale-if-error kicks in
curl -v https://localhost:8787/api/data
# Look for: X-Cache-Status: STALE, Warning: 110
```

Use `wrangler tail` in production to monitor `X-Stale-Reason` header distributions;
alert when the `upstream-5xx` reason exceeds a threshold over a rolling window.

---

## Related

- `workers-cache-api-stale-while-revalidate.md`
- `cache-stampede-prevention.md`
- `cloudflare-cache-api-workers-mobile.md`
- `api-response-caching.md`
- `workers-request-coalescing-deduplication.md`

---

## Sources

- RFC 7234 §5.2.2.4 stale-if-error: https://datatracker.ietf.org/doc/html/rfc7234
- Cloudflare Cache API: https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare CDN stale-if-error: https://developers.cloudflare.com/cache/how-to/configure-cache-status-code/
