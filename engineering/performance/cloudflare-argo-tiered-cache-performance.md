# Cloudflare Argo Tiered Cache Performance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Origin hit rate is high despite a long `Cache-Control: max-age`. Cloudflare's distributed PoP network has ~300 edge nodes; a fresh asset cached at one PoP still triggers origin fetches from all other PoPs during the first-hit window. With Argo Tiered Cache, inter-PoP cache fills travel through upper-tier PoPs — reducing origin load by 50–80 % and cutting cross-continent latency for cold-PoP requests. Workers need to emit the right cache headers and leverage the Cache API correctly to cooperate with the tiering topology.

## Context

Argo Tiered Cache adds a two-layer hierarchy: **upper-tier** PoPs (regional concentrators) serve **lower-tier** PoPs (edge PoPs closest to users). A lower-tier miss goes to the upper-tier before reaching the origin. Smart Tiered Cache automatically selects the optimal upper-tier based on historical request patterns; Custom Tiered Cache lets you fix the upper-tier PoP. Workers interact with this system through `Cache-Control` headers and, when generating responses directly, via the `cf.cacheTtl` / `cf.cacheKey` request options.

Key insight: `Cache-Control` alone controls Cloudflare tiered behaviour; `cf.cacheTtl` overrides only at the edge without influencing the tier hierarchy. To maximally cooperate with tiering, Workers must not strip `Cache-Control`, must set correct `Vary` keys, and must set `s-maxage` when origin and CDN TTLs differ.

## 1. Cooperative Cache Headers from a Worker

```typescript
// lib/tiered-cache-headers.ts

export interface TieredCacheOptions {
  /** CDN TTL in seconds (upper and lower tiers) */
  cdnTtl: number;
  /** Browser TTL in seconds */
  browserTtl: number;
  /** Allows stale-while-revalidate at the CDN tier */
  swrTtl?: number;
  /** Surrogate key for targeted purge (comma-separated tags) */
  surrogateKey?: string;
}

export function applyTieredCacheHeaders(
  headers: Headers,
  opts: TieredCacheOptions
): void {
  const { cdnTtl, browserTtl, swrTtl = 0, surrogateKey } = opts;

  // s-maxage: CDN tier TTL. max-age: browser TTL.
  let cc = `public, s-maxage=${cdnTtl}, max-age=${browserTtl}`;
  if (swrTtl > 0) cc += `, stale-while-revalidate=${swrTtl}`;

  headers.set("Cache-Control", cc);

  // Surrogate-Key enables grouped purge without purging the whole zone
  if (surrogateKey) headers.set("Surrogate-Key", surrogateKey);

  // Argo Tiered Cache respects must-revalidate; avoid it unless stale serving
  // is genuinely unacceptable — it forces synchronous revalidation at each tier.
}
```

## 2. Worker Fetch Handler with Tier-Aware Caching

```typescript
// worker.ts
import { applyTieredCacheHeaders } from "./lib/tiered-cache-headers";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Pass cf fetch options to cooperate with the upper tier
    const originResponse = await fetch(request, {
      cf: {
        // cacheTtl: how long Cloudflare stores this response at the edge
        cacheTtl: 300,
        // cacheEverything: cache even non-HTML assets with Cache-Control
        cacheEverything: true,
        // Tiered cache is enabled zone-wide; no Worker flag needed
      },
    });

    const response = new Response(originResponse.body, originResponse);
    applyTieredCacheHeaders(response.headers, {
      cdnTtl:       300,
      browserTtl:   60,
      swrTtl:       120,
      surrogateKey: "product listing",
    });

    return response;
  },
};
```

## 3. Cache Key Sharding for Tiered Efficiency

When response content varies by a small number of dimensions (locale, device class), build a normalised cache key so the upper tier can serve all lower tiers from a single stored entry:

```typescript
// lib/cache-key.ts

/**
 * Normalises request variations to a small, stable set of cache keys
 * so the upper-tier hit rate is maximised.
 */
export function buildCacheKey(request: Request): Request {
  const url    = new URL(request.url);
  const locale = request.headers.get("Accept-Language")?.slice(0, 2) ?? "en";
  const device = /Mobi/i.test(request.headers.get("User-Agent") ?? "")
    ? "mobile"
    : "desktop";

  // Encode variant dimensions as stable query params — not headers —
  // so Cloudflare's cache key is deterministic across PoPs.
  url.searchParams.set("_cf_ck_locale", locale);
  url.searchParams.set("_cf_ck_device", device);
  // Strip all other query params that don't affect the response
  url.searchParams.delete("utm_source");
  url.searchParams.delete("utm_medium");
  url.searchParams.delete("fbclid");

  return new Request(url.toString(), {
    method:  request.method,
    headers: request.headers,
  });
}
```

## 4. Bypassing Tiered Cache for Personalised Responses

Personalised content must never be stored at any cache tier. Signal this explicitly:

```typescript
function isPersonalised(request: Request): boolean {
  return (
    request.headers.has("Cookie") ||
    request.headers.has("Authorization") ||
    new URL(request.url).pathname.startsWith("/account")
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (isPersonalised(request)) {
      const response = await fetch(request);
      const out = new Response(response.body, response);
      out.headers.set("Cache-Control", "private, no-store");
      return out;
    }
    // ... tiered cache path
  },
};
```

## 5. Surrogate Key Purge via Cloudflare API

Tiered cache stores entries at both upper and lower tiers. A standard URL purge only clears lower-tier entries; to evict both tiers, purge by Surrogate-Key or use the Cache-Tag purge endpoint:

```typescript
// scripts/purge-surrogate-key.ts
async function purgeSurrogateKey(
  zoneId: string,
  apiToken: string,
  tags: string[]
): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method:  "POST",
      headers: {
        "Authorization": `Bearer ${apiToken}`,
        "Content-Type":  "application/json",
      },
      body: JSON.stringify({ tags }),
    }
  );
  if (!res.ok) throw new Error(`Purge failed: ${res.status} ${await res.text()}`);
}

// Usage
await purgeSurrogateKey(ZONE_ID, API_TOKEN, ["product listing", "homepage"]);
```

## 6. Observing Tier Hits

Cloudflare exposes cache tier information via the `CF-Cache-Status` header (`HIT`, `MISS`, `EXPIRED`, `REVALIDATED`, `UPDATING`) and, in Enterprise, `Cf-Cache-Tier`. Log these in Analytics Engine to measure upper-tier hit rate:

```typescript
// lib/cache-metrics.ts
export function recordCacheHit(
  ae: AnalyticsEngineDataset,
  request: Request,
  response: Response
): void {
  const status = response.headers.get("CF-Cache-Status") ?? "UNKNOWN";
  const tier   = response.headers.get("Cf-Cache-Tier") ?? "unknown";
  ae.writeDataPoint({
    indexes: [status, tier],
    blobs:   [new URL(request.url).pathname],
    doubles: [1],
  });
}
```

## Anti-patterns

- **Setting `Cache-Control: no-cache` in Workers** — this prevents the upper tier from storing anything, eliminating all tiering benefit. Reserve `no-cache` for genuinely uncacheable paths.
- **Varying on `User-Agent` directly** — the User-Agent string space is enormous; this produces effectively zero upper-tier hit rate. Normalise to a small enum (mobile / desktop) as shown above.
- **Purging by URL after content updates** — URL purge clears only lower-tier nodes. Always purge via Surrogate-Key / Cache-Tag when Argo Tiered Cache is active.
- **Using `cf.cacheTtl = 0` as a "cache bypass"** — set `Cache-Control: no-store` instead; `cacheTtl = 0` is undefined behaviour in some runtime versions.

## Gotchas

- Argo Smart Routing and Tiered Cache are separate Argo features billed differently; enabling smart routing does not automatically enable tiered cache. Verify both are active in the Cloudflare dashboard.
- `stale-while-revalidate` is honoured at the lower tier but not always propagated to the upper tier; test with a cache-purge cycle to confirm SWR behaviour at the upper tier in your zone.
- Workers' `caches.default.put()` stores at the **local PoP only**, not at the upper tier. To populate the tiered hierarchy, return a cacheable response from the Worker's `fetch` handler rather than manually calling `cache.put`.
- `Surrogate-Key` header values are stripped before the response reaches the browser; they are used only by Cloudflare and are safe to include on public responses.

## Verification

```bash
# First request — expect MISS
curl -s -I https://example.com/api/products | grep cf-cache-status

# Second request from same PoP — expect HIT
curl -s -I https://example.com/api/products | grep cf-cache-status

# From a different region (use a proxy or Cloudflare Tunnel from a different region)
# First request from new region — expect MISS or REVALIDATED (upper tier serves body)
# Second request — expect HIT at lower tier
```

Target: upper-tier hit rate > 70 % for stable assets. Measure via Analytics Engine `CF-Cache-Status` distribution or via Cloudflare Cache Analytics in the dashboard.

## Related

- `cloudflare-tiered-cache-parent-selection.md`
- `cache-stampede-prevention.md`
- `workers-cache-api-stale-while-revalidate.md`
- `targeted-cdn-cache-control-precedence.md`
- `cache-reserve-persistent-tier-origin-offload.md`

## Sources

- Cloudflare Argo Tiered Cache — developers.cloudflare.com/cache/how-to/tiered-cache
- Cloudflare Cache-Tag purge API — developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tag
- RFC 9111 Cache-Control (s-maxage, stale-while-revalidate) — rfc-editor.org/rfc/rfc9111
- Cloudflare Surrogate-Key header — developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tag#surrogate-key
