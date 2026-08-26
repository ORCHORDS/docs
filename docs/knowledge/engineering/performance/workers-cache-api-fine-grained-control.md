# Fine-Grained Cache API Control in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

The default Cloudflare CDN cache either caches too aggressively (stale personalised content served to wrong users) or not at all (dynamic Workers responses bypass the cache). You need precise control: custom cache keys that strip cookies and normalise query parameters, per-route TTLs, programmatic purge triggered by content updates, and instrumentation to track hit rates.

## Context

Cloudflare Workers expose two cache interfaces:
1. **`caches.default`** — the same shared cache the CDN uses. Entries are keyed by URL and are zone-scoped.
2. **`caches.open(name)`** — a named cache, logically separate from the default CDN cache. Useful for sub-keying or namespacing.

The Cache API follows the [Service Worker Cache spec](https://w3c.github.io/ServiceWorker/#cache-interface): `cache.match(request)`, `cache.put(request, response)`, `cache.delete(request)`. The `request` argument acts as the cache key and can be a synthesised `Request` object with a custom URL — this is the foundation of custom cache-key logic.

Important constraints:
- `cache.put` only accepts responses with a 2xx status and appropriate `Cache-Control` headers (or the `cf` property on the Response).
- The cache is regional; a `PUT` in one PoP is not immediately visible in another.
- Cache storage is best-effort — the cache may evict entries at any time. Never treat it as a source of truth.

## Solution

### Normalised cache key construction

```typescript
// src/cache-key.ts

/**
 * Build a canonical cache-key URL by:
 * 1. Stripping cookies and auth headers (personalisation signals).
 * 2. Sorting query parameters for canonical order.
 * 3. Removing tracking parameters (utm_*, fbclid, gclid, etc.).
 * 4. Optionally lowercasing the host.
 */
const TRACKING_PARAMS = new Set([
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
  'fbclid', 'gclid', 'msclkid', 'ref', '_ga',
]);

export function buildCacheKey(request: Request): Request {
  const url = new URL(request.url);

  // Remove tracking query parameters.
  for (const key of [...url.searchParams.keys()]) {
    if (TRACKING_PARAMS.has(key)) {
      url.searchParams.delete(key);
    }
  }

  // Sort remaining params for canonical ordering.
  url.searchParams.sort();

  // Lower-case hostname (some origins are case-sensitive by accident).
  url.hostname = url.hostname.toLowerCase();

  // Return a new Request with no credentials — strip cookies / auth.
  return new Request(url.toString(), {
    method: 'GET',
    headers: {
      // Carry Accept-Encoding so the cache can store compressed variants.
      'accept-encoding': request.headers.get('accept-encoding') ?? 'gzip',
    },
  });
}
```

### Core cache read / write helpers

```typescript
// src/cache-helpers.ts
import { buildCacheKey } from './cache-key';

const DEFAULT_CACHE = caches.default;

export interface CacheOptions {
  /** Time-to-live in seconds stored in Cache-Control max-age. */
  ttl: number;
  /** Optional surrogate / cache-tag header for grouped purging. */
  surrogateKey?: string;
  /** Force-bypass even when a cached entry exists. */
  bypassCondition?: (request: Request) => boolean;
}

export async function cacheGet(
  request: Request,
  opts: Pick<CacheOptions, 'bypassCondition'> = {}
): Promise<Response | undefined> {
  if (opts.bypassCondition?.(request)) {
    return undefined;
  }
  const key = buildCacheKey(request);
  const cached = await DEFAULT_CACHE.match(key);
  return cached ?? undefined;
}

export async function cachePut(
  request: Request,
  response: Response,
  opts: CacheOptions
): Promise<void> {
  if (!response.ok) return; // Never cache error responses.

  const key = buildCacheKey(request);

  // Clone before consuming — response body can only be read once.
  const responseToCache = new Response(response.clone().body, {
    status: response.status,
    headers: {
      ...Object.fromEntries(response.headers),
      // Override / set Cache-Control explicitly.
      'cache-control': `public, max-age=${opts.ttl}, s-maxage=${opts.ttl}`,
      // Surrogate-Key allows Cloudflare Cache Purge API to purge by tag.
      ...(opts.surrogateKey
        ? { 'surrogate-key': opts.surrogateKey }
        : {}),
      // Vary header: only vary on Accept-Encoding (strip Cookie / Authorization).
      'vary': 'Accept-Encoding',
    },
  });

  await DEFAULT_CACHE.put(key, responseToCache);
}

export async function cacheDelete(request: Request): Promise<boolean> {
  const key = buildCacheKey(request);
  return DEFAULT_CACHE.delete(key);
}
```

### Cache bypass conditions

```typescript
// src/bypass.ts

/** Returns true when the request should bypass the cache. */
export function shouldBypassCache(request: Request): boolean {
  const url = new URL(request.url);

  // Always bypass for non-GET methods.
  if (request.method !== 'GET' && request.method !== 'HEAD') return true;

  // Bypass when the client sends a no-cache directive.
  const cc = request.headers.get('cache-control') ?? '';
  if (cc.includes('no-cache') || cc.includes('no-store')) return true;

  // Bypass for authenticated / personalised requests.
  if (request.headers.has('authorization')) return true;
  if (request.headers.has('cookie')) {
    const cookies = request.headers.get('cookie') ?? '';
    // Only bypass when a _session cookie is present (allow analytics cookies).
    if (/\b(session|auth|jwt)=/i.test(cookies)) return true;
  }

  // Bypass for preview / draft mode.
  if (url.searchParams.has('preview') || url.searchParams.has('draft')) return true;

  return false;
}
```

### Worker fetch handler with hit-rate measurement

```typescript
// src/worker.ts
import { cacheGet, cachePut, CacheOptions } from './cache-helpers';
import { shouldBypassCache } from './bypass';
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    const bypass = shouldBypassCache(request);
    let cacheHit = false;

    if (!bypass) {
      const cached = await cacheGet(request);
      if (cached) {
        cacheHit = true;
        // Record hit in Analytics Engine (non-blocking).
        ctx.waitUntil(
          recordCacheMetric(env, url.pathname, 'hit')
        );
        return new Response(cached.body, {
          status: cached.status,
          headers: {
            ...Object.fromEntries(cached.headers),
            'x-cache': 'HIT',
          },
        });
      }
    }

    // Cache miss or bypass — fetch from origin.
    const originResponse = await fetch(request);

    const cacheOpts: CacheOptions = {
      ttl: getTtlForPath(url.pathname),
      surrogateKey: getSurrogateKey(url.pathname),
    };

    // Populate cache in the background; don't block the response.
    if (!bypass && originResponse.ok) {
      ctx.waitUntil(
        cachePut(request, originResponse.clone(), cacheOpts)
          .then(() => recordCacheMetric(env, url.pathname, 'miss'))
      );
    }

    return new Response(originResponse.body, {
      status: originResponse.status,
      headers: {
        ...Object.fromEntries(originResponse.headers),
        'x-cache': bypass ? 'BYPASS' : 'MISS',
      },
    });
  },
};

function getTtlForPath(pathname: string): number {
  if (pathname.startsWith('/static/')) return 86_400;  // 1 day
  if (pathname.startsWith('/api/public/')) return 60;  // 1 minute
  if (pathname.startsWith('/blog/')) return 3_600;     // 1 hour
  return 300; // default 5 minutes
}

function getSurrogateKey(pathname: string): string {
  // Group pages under a surrogate key for bulk purge.
  if (pathname.startsWith('/blog/')) return 'blog';
  if (pathname.startsWith('/api/')) return 'api';
  return 'general';
}

async function recordCacheMetric(
  env: Env,
  pathname: string,
  outcome: 'hit' | 'miss'
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: [pathname, outcome],
    doubles: [1],
    indexes: ['cache_outcome'],
  });
}
```

### Surrogate key purging

```typescript
// src/purge.ts
// Called from an admin endpoint or a webhook when content is updated.

export async function purgeBySurrogateKey(
  surrogateKey: string,
  zoneId: string,
  apiToken: string
): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ tags: [surrogateKey] }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Purge failed (${res.status}): ${text}`);
  }
}
```

## Implementation Details

**Vary header handling.** Setting `Vary: Cookie` causes the cache to store a separate entry per unique `Cookie` header value — combinatorially explosive. Instead, strip the `Cookie` header from the cache key entirely and handle personalisation in the Worker logic after the cache check.

**Named caches vs default cache.** `caches.open('my-cache')` creates a cache namespace that is **not** purged by standard Cloudflare purge APIs (which only affect `caches.default`). Use named caches for auxiliary data (e.g. coalesced upstream responses) and `caches.default` for user-facing HTML/API responses you want to purge via the dashboard or API.

**`waitUntil` for background writes.** `cache.put` is async and must not block the response. Always wrap it in `ctx.waitUntil(...)` so the Worker can return the response while the cache write completes.

## Anti-patterns

- **Caching responses without inspecting `Cache-Control`.** If the origin sends `Cache-Control: private`, respect it — never override to `public` without understanding the implications.
- **Using `request.url` directly as the cache key** without normalisation — tracking parameters or cookie variance cause cache fragmentation.
- **Storing `Set-Cookie` headers in the cache.** Serving another user's `Set-Cookie` is a session-hijacking bug. Strip `Set-Cookie` before calling `cache.put`.
- **Caching non-2xx responses.** A 500 error cached for 5 minutes means 5 minutes of downtime. Only cache `response.ok` (200–299).

## Gotchas

- `caches.default.match` returns `undefined` (not `null`) on a miss. Use `?? undefined` in TypeScript to satisfy type checkers.
- Cache API `put` has a body size limit of 512 MB but Workers have a subrequest response size limit of 512 MB as well; very large responses may need to be chunked or stored in R2 instead.
- `Surrogate-Key` purging requires Cloudflare Enterprise or a Cache Rules add-on. Verify your plan supports tag-based purge before building the purge flow.
- Cache entries are specific to the PoP where `put` was called. Expect misses on first request to each PoP globally; the cache warms per-PoP organically.

## Verification

```bash
# Confirm cache HIT/MISS via response header:
curl -si https://your-worker.example.com/blog/my-post | grep -i 'x-cache'

# Second request should hit:
curl -si https://your-worker.example.com/blog/my-post | grep -i 'x-cache'
# Expected: x-cache: HIT

# Purge all blog entries:
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"tags":["blog"]}'

# Query hit rate from Analytics Engine:
# SELECT outcome, count() FROM cache_outcome WHERE timestamp > now() - 1h GROUP BY outcome
```

Target: cache hit rate > 80% for public, unauthenticated paths.

## Related

- `workers-request-coalescing-durable-objects.md` — coordinate cache fills under burst load.
- `workers-streaming-response-time-to-first-byte.md` — serve cached responses as streams.
- `workers-bundle-size-optimization-esbuild.md` — smaller bundles reduce Worker startup time, complementing cache strategy.

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/
- https://developers.cloudflare.com/workers/examples/cache-api/
- https://w3c.github.io/ServiceWorker/#cache-interface
