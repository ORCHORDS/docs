# Cloudflare Cache Rules TTL Override and Workers Bypass Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Cache Rules set a global TTL for API responses (e.g. 60 seconds), but
certain Workers need to:

1. **Bypass cache** entirely for authenticated or personalized requests
2. **Override TTL** to a shorter or longer value on a per-request basis at the Worker
   level, without touching the zone-level Cache Rule
3. **Force a cache miss** for specific content keys without purging the entire zone

Cache Rules run before a Worker's `fetch` handler, so by the time Workers code executes,
the caching decision has already been made — unless the Worker overrides it via request
headers or `cf` fetch options.

---

## Context

Cloudflare caching layers and their precedence (highest to lowest):

```
1. Worker cf.cacheControl / cf.cacheTtl options  (per-subrequest override)
2. Response Cache-Control header from origin
3. Cache Rules (zone-level, dashboard or API)
4. Default edge cache behaviour
```

Workers fetch options (the `cf` object on `fetch()`) can override Cache Rules at the
subrequest level. This makes Workers the right place for conditional, per-request cache
policy without modifying zone-wide rules.

Key Cache Rule terminology:
- **Edge Cache TTL** — how long Cloudflare holds the response (independent of origin
  `Cache-Control`)
- **Browser Cache TTL** — `max-age` sent to the client
- **Cache Status** — `HIT`, `MISS`, `BYPASS`, `EXPIRED`, `REVALIDATED`, `UPDATING`,
  `STALE`, `DYNAMIC`

example project platform pattern: Cache Rules set a conservative 30 s TTL for `/api/*`; Workers
elevate TTL to 300 s for public-facing product catalogue endpoints and bypass entirely
for authenticated user-specific responses.

---

## Pattern 1 — Bypass Cache for Authenticated Requests

```typescript
// src/workers/smart-cache.ts
//
// If the request carries a session cookie or Authorization header, bypass the
// Cloudflare cache. Otherwise, serve from / populate the edge cache.

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    const isAuthenticated =
      req.headers.has('Authorization') ||
      parseCookies(req.headers.get('Cookie') ?? '').has('session');

    if (isAuthenticated) {
      // Bypass Cloudflare cache; let origin set its own Cache-Control
      return fetch(req, {
        cf: { cacheEverything: false, cacheTtl: 0 },
      });
    }

    // For unauthenticated requests, override TTL based on path
    const ttl = getTtlForPath(url.pathname);

    return fetch(req, {
      cf: {
        cacheEverything: true,
        cacheTtl: ttl,
        // Extend browser TTL to match edge TTL
        cacheKey: url.pathname + url.search, // strip host for canonical cache key
      },
    });
  },
};

function getTtlForPath(pathname: string): number {
  if (pathname.startsWith('/api/products')) return 300;  // 5 min
  if (pathname.startsWith('/api/search'))   return 60;   // 1 min
  if (pathname.startsWith('/api/prices'))   return 10;   // 10 s (volatile)
  return 30; // default
}

function parseCookies(cookieHeader: string): Map<string, string> {
  return new Map(
    cookieHeader.split(';').map(c => {
      const [k, ...v] = c.trim().split('=');
      return [k, v.join('=')];
    }),
  );
}
```

---

## Pattern 2 — Stale-While-Revalidate at the Worker Layer

```typescript
// src/workers/swr-cache.ts
//
// Serve a stale cached response immediately, then revalidate in the background.
// Cloudflare's native SWR via Cache-Control can be unreliable for short TTLs;
// this pattern implements SWR explicitly using the Cache API.

const CACHE = caches.default;
const SWR_WINDOW_S = 30;   // serve stale for up to 30 s after expiry

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cacheKey = new Request(new URL(req.url).toString(), {
      method: 'GET',
      headers: { 'Cache-Control': 'no-transform' },
    });

    const cached = await CACHE.match(cacheKey);

    if (cached) {
      const age = getAgeSeconds(cached.headers);
      const maxAge = getMaxAge(cached.headers);

      if (age < maxAge) {
        // Fresh — serve directly
        return cached;
      }

      if (age < maxAge + SWR_WINDOW_S) {
        // Stale but within SWR window — serve stale, revalidate in background
        ctx.waitUntil(revalidate(cacheKey, req, env));
        return new Response(cached.body, {
          status: cached.status,
          headers: {
            ...Object.fromEntries(cached.headers),
            Age: String(age),
            'X-Cache-Status': 'STALE',
          },
        });
      }
    }

    // Cache MISS or too stale — fetch from origin
    return revalidate(cacheKey, req, env);
  },
};

async function revalidate(
  cacheKey: Request,
  req: Request,
  env: Env,
): Promise<Response> {
  const origin = await fetch(req, { cf: { cacheEverything: false } });

  if (origin.ok) {
    const clone = origin.clone();
    await CACHE.put(cacheKey, clone);
  }

  return origin;
}

function getAgeSeconds(headers: Headers): number {
  const date = headers.get('Date');
  if (!date) return 0;
  return Math.floor((Date.now() - new Date(date).getTime()) / 1000);
}

function getMaxAge(headers: Headers): number {
  const cc = headers.get('Cache-Control') ?? '';
  const match = cc.match(/max-age=(\d+)/);
  return match ? parseInt(match[1], 10) : 0;
}
```

---

## Pattern 3 — Segment Cache Keys by User Tier

```typescript
// src/workers/tier-cache.ts
//
// Free-tier users share a single cache key; paid users get uncached responses.
// Cache Rules cannot segment on JWT claims — Workers can.

import { verifyJwt } from './auth';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Only cache GET requests for the product catalogue
    if (req.method !== 'GET' || !url.pathname.startsWith('/api/catalogue')) {
      return fetch(req, { cf: { cacheTtl: 0 } });
    }

    const token = req.headers.get('Authorization')?.replace('Bearer ', '');
    const claims = token ? await verifyJwt(token, env.JWT_SECRET) : null;

    if (claims?.tier === 'paid') {
      // Paid users: never cache, always fresh
      return fetch(req, { cf: { cacheEverything: false, cacheTtl: 0 } });
    }

    // Free users / anonymous: use shared cached response, 60 s TTL
    return fetch(req, {
      cf: {
        cacheEverything: true,
        cacheTtl: 60,
        // Omit any user-identifying header from cache key
        cacheKey: url.pathname + url.search,
      },
    });
  },
};
```

---

## Pattern 4 — Programmatic Cache Purge on Data Change

```typescript
// src/lib/cache-purge.ts
//
// After a D1 write, purge the affected Cloudflare cache entries via the Purge API.

export async function purgeProductCache(
  productId: string,
  env: Env,
): Promise<void> {
  const urls = [
    `https://${env.HOSTNAME}/api/products/${productId}`,
    `https://${env.HOSTNAME}/api/catalogue`,
    `https://${env.HOSTNAME}/api/catalogue?category=all`,
  ];

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/purge_cache`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_CACHE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ files: urls }),
    },
  );

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Cache purge failed ${resp.status}: ${body}`);
  }

  console.log(`[cache] purged ${urls.length} URLs for product ${productId}`);
}

// Usage in a mutation handler:
export async function updateProduct(
  productId: string,
  data: Partial<Product>,
  env: Env,
): Promise<void> {
  await env.DB.prepare(
    'UPDATE products SET name = ?1, price = ?2 WHERE id = ?3',
  ).bind(data.name, data.price, productId).run();

  // Fire-and-forget purge (don't block the response on it)
  // If purge fails, stale content is served until TTL expires — acceptable trade-off
  purgeProductCache(productId, env).catch(err =>
    console.error('[cache] purge error:', err),
  );
}
```

---

## Pattern 5 — Debug Cache Behaviour with CF-Cache-Status

```typescript
// src/workers/cache-inspector.ts
//
// Development/staging tool: expose cache metadata in response headers.

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (env.ENVIRONMENT !== 'staging') return fetch(req);

    const start = Date.now();
    const resp = await fetch(req, { cf: { cacheEverything: true, cacheTtl: 30 } });

    return new Response(resp.body, {
      status: resp.status,
      headers: {
        ...Object.fromEntries(resp.headers),
        'X-Debug-Cache-Status': resp.headers.get('CF-Cache-Status') ?? 'unknown',
        'X-Debug-Age': resp.headers.get('Age') ?? '0',
        'X-Debug-Worker-Ms': String(Date.now() - start),
        'X-Debug-TTL-Requested': '30',
      },
    });
  },
};
```

---

## Cache Rules via Cloudflare API (Terraform / CI)

```typescript
// src/lib/cache-rules-api.ts
// Manage Cache Rules programmatically (e.g. during deploy to set environment-specific TTLs)

export async function setCacheRule(
  expression: string,
  edgeTtl: number,
  env: Env,
): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/cache/rules`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_CACHE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        action: 'set_cache_settings',
        expression,
        action_parameters: {
          cache: true,
          edge_ttl: {
            mode: 'override_origin',
            default: edgeTtl,
          },
        },
      }),
    },
  );

  if (!resp.ok) throw new Error(`Cache rule creation failed: ${await resp.text()}`);
}
```

---

## Anti-patterns

- **Setting `cacheEverything: true` on POST/PUT requests** — Cloudflare will not cache
  non-GET/HEAD requests but the option being set can cause unexpected behaviour with
  downstream caches.
- **Using `cf.cacheKey` with user-identifiable values** — a per-user cache key defeats
  the purpose of shared caching and fragments the cache into N single-use entries.
- **Relying on `Cache-Control: no-store` from the origin to bypass edge cache** — Cache
  Rules that set `Override origin` mode ignore origin Cache-Control headers. Always
  use Worker `cf.cacheTtl: 0` or `cf.cacheEverything: false` to guarantee bypass.
- **Purging by URL without scheme+host** — the purge API requires full absolute URLs
  including `https://`. Relative paths are silently ignored.
- **Forgetting that `cf` fetch options only apply to subrequests from Workers** —
  they have no effect on the initial request from the client to Cloudflare; use
  Cache Rules or `Cache-Control` response headers for the outer response.

---

## Gotchas

- `CF-Cache-Status: BYPASS` in the response does NOT mean the Worker bypassed it —
  it means Cache Rules or origin headers prevented caching. Check `X-Cache-Miss-Reason`
  for detail.
- `cacheTtl: -1` is the documented way to bypass caching via `cf` options, but
  `cacheTtl: 0` is more portable and consistently supported. Prefer `0` or
  `cacheEverything: false`.
- Workers running on routes with Cache Rules: the Cache Rule fires at the **zone level**
  before the Worker; the Worker's `cf` fetch option on the subrequest can override the
  **subrequest's** caching, not the initial request's caching decision.
- `caches.default.put()` stores the response in Cloudflare's shared cache keyed by
  the URL — this is zone-global and visible to all Workers on the zone.
- After a `wrangler dev --remote` session, locally written `caches.default` entries
  may persist in the remote edge cache. Use unique prefixed keys for dev testing.

---

## Verification

```bash
# Check cache status on repeated requests
for i in 1 2 3; do
  curl -si "https://example.com/api/products?page=1" \
    | grep -E "^(cf-cache-status|age|cache-control):" ;
  echo "---";
done

# Expected output pattern:
# cf-cache-status: MISS   → age: 0    (first request populates cache)
# cf-cache-status: HIT    → age: 1    (second request served from edge)
# cf-cache-status: HIT    → age: 2    (third request)
```

```typescript
// Vitest unit test for TTL selection logic
import { describe, it, expect } from 'vitest';

function getTtlForPath(pathname: string): number {
  if (pathname.startsWith('/api/products')) return 300;
  if (pathname.startsWith('/api/search'))   return 60;
  if (pathname.startsWith('/api/prices'))   return 10;
  return 30;
}

describe('getTtlForPath', () => {
  it('returns 300 for product paths', () => {
    expect(getTtlForPath('/api/products/42')).toBe(300);
  });
  it('returns 10 for prices', () => {
    expect(getTtlForPath('/api/prices/usd')).toBe(10);
  });
  it('returns 30 for unknown paths', () => {
    expect(getTtlForPath('/api/users')).toBe(30);
  });
});
```

---

## Related

- `cloudflare-cache-rules-advanced-configuration.md`
- `cache-stale-while-revalidate-control-boundary.md`
- `workers-cache-api.md`
- `r2-custom-domains-cache-rules.md`
- `cache-device-type-segmentation-mobile-desktop.md`
- `workers-fetch-api-patterns.md`

---

## Sources

- https://developers.cloudflare.com/cache/how-to/cache-rules/
- https://developers.cloudflare.com/workers/examples/cache-api/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/#cfrequestinit
- https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-url/
- https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
