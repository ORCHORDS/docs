# Tiered Cache (Origin Shield) with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your origin server receives a high number of cache-MISS requests even though the content is cacheable. Each Cloudflare PoP independently caches content, so a cache fill in Frankfurt does not help a user in Singapore. You want upper-tier PoPs to act as a shared cache layer (origin shield) so that the origin only serves a single fill request, not one per PoP per unique URL.

## Context

Cloudflare Tiered Cache (available on all plans; topology control requires Enterprise) introduces a two-layer caching hierarchy:

- **Lower-tier PoPs** — the edge closest to the end user. If they miss, they query an upper-tier PoP rather than going directly to the origin.
- **Upper-tier PoPs** — a smaller set of regionally centralised PoPs that absorb the fill traffic. Only they contact the origin on a miss.

The result: origin request volume drops by 70–95 % for cacheable assets, and cache-fill latency from the lower tier is much lower than a transatlantic origin round-trip.

In a Worker you interact with Tiered Cache through the `cf` options object on `fetch()` calls and by reading `CF-Cache-Status` from responses. Workers execute at the lower tier before the cache is consulted, which means you can programmatically influence what gets cached and how.

## Configuring Tiered Cache Hints in a Worker

```typescript
interface Env {
  ORIGIN_URL: string; // e.g. "https://api.origin.example.com"
}

/** Segment identifier derived from request properties — coarser than a full user ID. */
function getUserSegment(request: Request): string {
  const country = request.cf?.country ?? 'XX';
  const acceptLang = (request.headers.get('Accept-Language') ?? 'en').split(',')[0].trim();
  return `${country}:${acceptLang}`; // e.g. "DE:de-DE"
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // ── 1. Decide whether this request is cacheable ───────────────────────────
    const isCacheable =
      request.method === 'GET' &&
      !url.searchParams.has('nocache') &&
      !request.headers.has('Authorization');

    if (!isCacheable) {
      return fetch(request); // pass through without cache hints
    }

    // ── 2. Build the cache key for per-segment caching ────────────────────────
    //
    // cf.cacheKey overrides the URL used as the cache key inside Cloudflare's
    // internal cache.  This lets different user segments get different cached
    // responses without different URLs.
    const segment = getUserSegment(request);
    const cacheKey = `${url.origin}${url.pathname}${url.search}|segment=${segment}`;

    // ── 3. Fetch with Tiered Cache hints ─────────────────────────────────────
    const response = await fetch(url.toString(), {
      cf: {
        // Cache everything — overrides the origin's Cache-Control if it says no-store.
        cacheEverything: true,

        // Edge TTL in seconds.  Cloudflare will cache the response for this long
        // regardless of what the origin sends in Cache-Control.
        cacheTtl: 300,

        // Per-segment cache key (string, max 512 bytes).
        cacheKey,

        // Tiered Cache is enabled at the zone level; these fetch options work
        // correctly whether Smart Tiering or Custom Tiering is active.
      } satisfies RequestInitCfProperties,
    });

    // ── 4. Observability — read CF-Cache-Status ───────────────────────────────
    const cacheStatus = response.headers.get('CF-Cache-Status') ?? 'UNKNOWN';
    // Possible values: HIT | MISS | EXPIRED | REVALIDATED | UPDATING | STALE | BYPASS | DYNAMIC

    const enriched = new Response(response.body, response);
    enriched.headers.set('X-Cache-Status', cacheStatus);
    enriched.headers.set('X-Cache-Segment', segment);

    // ── 5. Emit a metric so you can graph hit rate over time ──────────────────
    ctx.waitUntil(
      Promise.resolve().then(() => {
        console.log(
          JSON.stringify({ event: 'cache_status', status: cacheStatus, segment, path: url.pathname })
        );
      })
    );

    return enriched;
  },
};
```

## `CF-Cache-Status` Values and What They Mean

| Status | Meaning |
|---|---|
| `HIT` | Served from Cloudflare cache (no origin contact) |
| `MISS` | Not in cache; fetched from origin; now stored |
| `EXPIRED` | Was in cache but past TTL; re-fetched from origin |
| `REVALIDATED` | Stale entry validated via conditional request; origin returned 304 |
| `UPDATING` | Stale entry being served while an async revalidation is in flight |
| `STALE` | Served stale because origin was unreachable |
| `BYPASS` | Caching skipped — e.g. Cookie present, or `Cache-Control: no-store` |
| `DYNAMIC` | Response marked as dynamic; never cached |

Log `CF-Cache-Status` to Analytics Engine or Logpush to compute your real-world cache hit ratio.

## Smart Tiering vs Custom Tiering

**Smart Tiering** (all paid plans) uses Cloudflare's latency-based algorithm to automatically select the best upper-tier PoP for each lower-tier PoP. No configuration required; Cloudflare picks the topology dynamically.

**Custom Tiering** (Enterprise) lets you pin specific upper-tier PoPs. Use cases:
- Data residency requirements (e.g. all cache fills must go through an EU upper tier).
- Predictable performance budgets for specific regions.
- Reducing cross-continental fill latency for a known user geography.

From a Worker's perspective, both topologies behave identically — you set `cf.cacheEverything`, `cf.cacheTtl`, and `cf.cacheKey` the same way.

## Per-Segment Caching with `cf.cacheKey`

`cf.cacheKey` lets a single URL have multiple cached variants. Common segments:

- **Country** — serve localised prices or content without separate URLs.
- **Accept-Language** — serve language-specific responses.
- **Tier / plan** — serve different feature flags to free vs paid users without leaking premium content.

Keep the segment coarse. A `cacheKey` that encodes a full user ID produces one cache entry per user — effectively disabling caching and multiplying origin requests.

## `cacheTtl` vs `Cache-Control`

- `cf.cacheTtl` — forces Cloudflare to cache for _N_ seconds regardless of what the origin's `Cache-Control` says (even `no-store` is overridden when `cacheEverything: true`).
- The origin's `Cache-Control: s-maxage` — the standard way to control edge TTL without Worker overrides.
- **Precedence**: `cf.cacheTtl` wins over origin headers when set.

## Anti-patterns

- **Using `cf.cacheKey` with user-specific data** (session ID, email) — cardinality explosion; origin is hit once per user per PoP, defeating the purpose.
- **Setting `cacheEverything: true` on authenticated endpoints** — may cache and serve one user's private data to another. Always gate `cacheEverything` on `isCacheable` checks.
- **Expecting `CF-Cache-Status: HIT` on the very first request** — the first request to any PoP is always a MISS; the cache is populated on that request.
- **Ignoring `BYPASS`** — if most responses show `BYPASS`, check for `Set-Cookie` headers or `Authorization` request headers that cause Cloudflare to skip caching by default.

## Gotchas

- Workers execute **before** the cache is checked for the incoming request (in the `fetch` event). The `cf` options on a sub-`fetch()` call control how Cloudflare caches the origin response, not the response to the client.
- `cf.cacheTtl` values below `0` are treated as `0` (no caching). There is no negative TTL for "force bypass".
- Tiered Cache is enabled per-zone in the Cloudflare dashboard (Caching → Tiered Cache). The Worker `cf` options have no effect on whether tiering is active — they only hint TTL and key.
- `cf.cacheKey` must not exceed 512 bytes.

## Verification

```bash
# First request — expect MISS
curl -si https://example.com/api/products | grep -E 'CF-Cache-Status|X-Cache-Status'
# CF-Cache-Status: MISS

# Second request from same region — expect HIT
curl -si https://example.com/api/products | grep -E 'CF-Cache-Status|X-Cache-Status'
# CF-Cache-Status: HIT

# Verify segment isolation — different Accept-Language should produce separate entries
curl -si -H 'Accept-Language: de' https://example.com/api/products | grep X-Cache-Segment
curl -si -H 'Accept-Language: fr' https://example.com/api/products | grep X-Cache-Segment
```

## Related

- `workers-cache-api-advanced-custom-keys.md`
- `workers-ai-inference-result-caching-kv.md`
- [Tiered Cache — Cloudflare Docs](https://developers.cloudflare.com/cache/how-to/tiered-cache/)
- [CF-Cache-Status — Cloudflare Docs](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/)

## Sources

- Cloudflare Tiered Cache documentation (2025)
- Cloudflare Workers `fetch()` `cf` options reference (2025)
- Cloudflare Cache concepts — default cache behaviour (2025)
