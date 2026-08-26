# Cloudflare Cache Reserve Persistent Cache Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your origin is expensive (database-backed renders, upstream API with per-call
billing) and Cloudflare's default Tiered Cache still misses on long-tail URLs
because the edge cache evicts unpopular assets between requests.  You want a
persistent, R2-backed cache layer that survives edge eviction and stores objects
indefinitely — without managing your own caching Worker.

---

## Context

**Cache Reserve** is an add-on to Cloudflare's CDN that places a persistent
cache tier backed by R2 object storage between the CDN edge and your origin.
When an asset is evicted from the edge cache, Cloudflare first checks Cache
Reserve before reaching the origin.  Cache Reserve is configured at the zone
level; Workers can influence it through standard cache-control directives and
the Cache API, and can inspect whether a response came from Cache Reserve via
the `CF-Cache-Status: REVALIDATED` or `CF-Cache-Status: HIT` response headers
combined with the `cf.cacheStatus` binding field.

Key facts:

- Cache Reserve stores the **full response body** including headers, not just
  metadata.
- Objects are billed per GB stored and per operation (reads + writes to R2).
- TTL is derived from the `Cache-Control: max-age` / `s-maxage` header on the
  upstream response.  Objects with no explicit TTL receive a default TTL (the
  dashboard default or a Cache Rule override).
- Cache Reserve respects **Cache Rules** — you can target specific URL patterns
  and override TTL, bypass flags, or force store.
- Workers **cannot** directly write to Cache Reserve; they write to the Cache
  API, which subsequently syncs to Cache Reserve when the edge evicts the entry
  or when TTL triggers revalidation.

---

## Enabling Cache Reserve via Wrangler / API

Cache Reserve is a zone-level feature toggled through the dashboard or the
Zones API.  There is no `wrangler.toml` key.  Enable it once per zone:

```bash
# Enable Cache Reserve for a zone
curl -sS -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/cache/cache_reserve" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}' | jq .

# Check current state
curl -sS \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/cache/cache_reserve" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

---

## Worker Pattern: Ensuring Cache Reserve Eligibility

Cache Reserve only stores responses that are cache-eligible.  Use a Worker to
guarantee correct cache headers on every origin response.

```typescript
// src/index.ts
export interface Env {
  // No special bindings needed — Cache Reserve works transparently
}

/** Minimum TTL for Cache Reserve to consider storing an object (seconds). */
const CACHE_RESERVE_MIN_TTL = 3600; // 1 hour

function isCacheableContentType(ct: string | null): boolean {
  if (!ct) return false;
  const cacheable = [
    "text/html",
    "text/css",
    "application/javascript",
    "application/json",
    "image/",
    "font/",
    "video/",
    "audio/",
    "application/wasm",
  ];
  return cacheable.some((prefix) => ct.includes(prefix));
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Only GET/HEAD are cacheable
    if (request.method !== "GET" && request.method !== "HEAD") {
      return fetch(request);
    }

    const cache = caches.default;
    const cacheKey = new Request(request.url, { headers: request.headers });

    // Check edge cache first (Cache Reserve is checked automatically on miss)
    const cached = await cache.match(cacheKey);
    if (cached) {
      return cached;
    }

    // Fetch from origin
    const originResponse = await fetch(request, {
      cf: {
        // Instruct Cloudflare to cache this response in Cache Reserve
        cacheEverything: true,
        cacheTtl: CACHE_RESERVE_MIN_TTL,
      },
    });

    const ct = originResponse.headers.get("content-type");
    if (!originResponse.ok || !isCacheableContentType(ct)) {
      return originResponse;
    }

    // Clone and rewrite headers to be Cache Reserve eligible
    const headers = new Headers(originResponse.headers);

    // Remove headers that prevent caching
    headers.delete("set-cookie");
    headers.delete("pragma");

    // Ensure s-maxage is set for Cache Reserve
    const existingCC = headers.get("cache-control") ?? "";
    if (!existingCC.includes("s-maxage") && !existingCC.includes("no-store")) {
      headers.set(
        "cache-control",
        existingCC
          ? `${existingCC}, s-maxage=${CACHE_RESERVE_MIN_TTL}`
          : `public, max-age=300, s-maxage=${CACHE_RESERVE_MIN_TTL}`,
      );
    }

    const response = new Response(originResponse.body, {
      status: originResponse.status,
      headers,
    });

    // Store in edge cache; Cloudflare will persist to Cache Reserve on eviction
    ctx.waitUntil(cache.put(cacheKey, response.clone()));

    return response;
  },
};
```

---

## Cache Reserve Bypass Pattern

For dynamic or personalised responses, explicitly bypass Cache Reserve with a
Cache Rule or via the Worker:

```typescript
// Bypass Cache Reserve for authenticated or personalised requests
async function fetchWithBypass(request: Request): Promise<Response> {
  const authHeader = request.headers.get("authorization");
  const sessionCookie = request.headers.get("cookie")?.includes("session=");

  if (authHeader || sessionCookie) {
    // cf.cacheEverything: false ensures bypass; also set the header for Cache Rules
    return fetch(request, {
      cf: {
        cacheEverything: false,
        cacheTtl: 0,
        // Adds CF-Cache-Status: BYPASS in the response
      },
    });
  }

  return fetch(request, {
    cf: { cacheEverything: true, cacheTtl: 86400 },
  });
}
```

---

## Reading Cache Reserve Status in a Response

Inspect the `CF-Cache-Status` header to understand where a response was served
from:

| Value | Meaning |
|---|---|
| `HIT` | Served from edge PoP cache |
| `MISS` | Cache Reserve checked, not found; origin fetched |
| `REVALIDATED` | Served from Cache Reserve (edge had evicted the object) |
| `EXPIRED` | Object existed but TTL passed; origin re-fetched |
| `BYPASS` | Explicitly bypassed by Worker or Cache Rule |
| `DYNAMIC` | Non-cacheable response |

```typescript
// Log Cache Reserve hits separately for billing/monitoring
async function logCacheStatus(response: Response, url: string): Promise<void> {
  const status = response.headers.get("cf-cache-status") ?? "UNKNOWN";
  if (status === "REVALIDATED") {
    console.log(`CACHE_RESERVE_HIT url=${url}`);
  } else if (status === "MISS") {
    console.log(`CACHE_MISS url=${url}`);
  }
}
```

---

## Cache Reserve + Cache Rules (Dashboard / Terraform)

Use Cache Rules to control Cache Reserve eligibility without modifying origin
headers:

```terraform
resource "cloudflare_ruleset" "cache_reserve_rules" {
  zone_id = var.zone_id
  name    = "Cache Reserve Rules"
  kind    = "zone"
  phase   = "http_response_headers_transform"

  rules {
    description = "Force Cache Reserve for static assets"
    expression  = "(http.request.uri.path matches \"^/assets/.*\")"
    action      = "set_cache_settings"
    action_parameters {
      cache           = true
      edge_ttl {
        mode    = "override_origin"
        default = 86400
      }
    }
  }

  rules {
    description = "Bypass Cache Reserve for API routes"
    expression  = "(http.request.uri.path matches \"^/api/.*\")"
    action      = "set_cache_settings"
    action_parameters {
      cache = false
    }
  }
}
```

---

## Purging Cache Reserve Objects

Purging the edge cache does **not** automatically purge Cache Reserve.  You
must explicitly purge Cache Reserve entries via the API or dashboard:

```bash
# Purge specific URLs from Cache Reserve
curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "files": ["https://example.com/assets/main.js"],
    "purge_everything": false
  }' | jq .
```

Cache Reserve purges propagate within ~5 minutes.  There is no instant
consistency guarantee; budget 10 minutes for full propagation before
re-testing.

---

## Anti-patterns

- **Setting `max-age` but not `s-maxage`** — Cache Reserve uses `s-maxage` (the
  shared-cache directive), not `max-age`.  Responses with only `max-age` may not
  be stored.
- **Caching `set-cookie` responses** — responses with `Set-Cookie` headers are
  not eligible for Cache Reserve.  Strip the header or use a Cache Rule to store
  a version without it.
- **Enabling Cache Reserve without Tiered Cache** — Cache Reserve works best
  with Tiered Cache enabled.  Without it, every edge PoP independently evicts
  objects to Cache Reserve, multiplying read costs.
- **Treating `REVALIDATED` as a cache miss** — `REVALIDATED` means the object
  was served from Cache Reserve, which is a hit from a billing standpoint.
  Your origin was not contacted.
- **Using Cache Reserve for private/user-specific data** — Cache Reserve is a
  shared cache.  Never cache responses containing session-specific data, tokens,
  or PII.

---

## Gotchas

- Cache Reserve adds a **$0.015/GB stored/month** and **$0.01/million reads**
  cost on top of the R2 costs.  Audit your stored object sizes in the dashboard
  before enabling on high-volume zones.
- Objects stored in Cache Reserve are not visible in R2 bucket listings — they
  are managed by Cloudflare internally in a dedicated R2 namespace.
- Cache Reserve has a **per-object size limit** (currently 512 MB).  Large video
  files or binary downloads exceeding this limit fall back to origin on edge
  eviction.
- The `cf.cacheEverything: true` flag in a Worker fetch overrides the default
  non-caching behaviour for HTML but does not override Cache Rules marked
  `Bypass`.  Cache Rules take precedence.
- Enabling Cache Reserve may surface bugs in `Vary` header handling — if your
  origin sends `Vary: Accept-Encoding` inconsistently, you may see stale
  compressed/uncompressed variants served from Cache Reserve.

---

## Verification

```bash
# Confirm Cache Reserve is enabled
curl -sS \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/cache/cache_reserve" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.result.value'
# Expected: "on"

# Check CF-Cache-Status on a static asset after first miss, then second request
curl -sI https://example.com/assets/main.js | grep -i cf-cache-status
# After first request: CF-Cache-Status: MISS
# After second request (from edge): CF-Cache-Status: HIT
# After edge eviction (from Cache Reserve): CF-Cache-Status: REVALIDATED
```

---

## Related

- `cloudflare-cache-rules-advanced-configuration.md` — Cache Rule syntax for
  targeting specific URL patterns
- `argo-tiered-cache-global-mobile-latency.md` — enabling Tiered Cache, which
  Cache Reserve depends on for optimal operation
- `workers-cache-api.md` — direct Cache API usage from Workers
- `cache-stale-while-revalidate-control-boundary.md` — stale-while-revalidate
  interaction with Cache Reserve TTLs
- `r2-best-practices.md` — R2 pricing and storage class details underlying
  Cache Reserve

---

## Sources

- Cache Reserve overview:
  https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
- Cache Reserve API reference:
  https://developers.cloudflare.com/api/operations/zone-cache-settings-change-cache-reserve-setting
- Cache Rules documentation:
  https://developers.cloudflare.com/cache/how-to/cache-rules/
- Cloudflare Cache pricing:
  https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/#pricing
