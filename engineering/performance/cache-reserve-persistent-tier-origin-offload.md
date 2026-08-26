# Cache Reserve: Persistent Caching Tier to Offload Origin

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Long-tail URLs and infrequently accessed assets miss the short-lived Cloudflare edge cache and hit the origin on every request, driving up origin bandwidth costs and TTFB for cold users. Cache Reserve adds a persistent R2-backed caching layer that keeps assets cached indefinitely until explicitly purged.

## Context
Cloudflare's standard edge cache evicts assets based on LRU and local storage pressure — popular assets stay warm, but long-tail content (old blog posts, rarely accessed PDFs, locale-specific images) gets evicted within hours. Cache Reserve stores a durable copy in R2 object storage behind the edge cache. When the edge cache misses, Cloudflare checks Cache Reserve before going to the origin, converting origin misses into sub-50 ms R2 reads. Cache Reserve is enabled per-zone in the Cloudflare dashboard and is automatic once turned on; Workers can interact with it via the standard `Cache-Control` response headers and the Cache API.

## Enabling Cache Reserve in Workers

Cache Reserve respects standard `Cache-Control` headers. Set aggressive TTLs in your Worker response:

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Only cache GET/HEAD — POST, PUT, DELETE are not cacheable
    if (request.method !== "GET" && request.method !== "HEAD") {
      return fetch(request);
    }

    const originRes = await fetch(env.ORIGIN_URL + url.pathname + url.search, {
      cf: {
        // Tell Cloudflare to cache this at the edge AND in Cache Reserve
        cacheEverything: true,
        cacheTtl: 86400 * 30, // 30 days at the edge
      },
    });

    return new Response(originRes.body, {
      status: originRes.status,
      headers: {
        ...Object.fromEntries(originRes.headers),
        // Cache Reserve will persist this for the stated max-age
        "cache-control": "public, max-age=2592000, stale-while-revalidate=86400",
        "cdn-cache-control": "max-age=2592000",
      },
    });
  },
};
```

## Selective Cache Reserve with Cache-Control Vary

Reserve long-duration caching for static assets; keep short TTLs for dynamic content:

```typescript
const ASSET_EXTENSIONS = new Set([".js", ".css", ".woff2", ".png", ".webp", ".avif", ".svg"]);

function getCacheDirective(pathname: string): string {
  const ext = pathname.slice(pathname.lastIndexOf(".")).toLowerCase();
  if (ASSET_EXTENSIONS.has(ext)) {
    // Static assets: long-lived, immutable if hash in filename
    const isHashed = /\.[a-f0-9]{8,}\.[a-z]+$/.test(pathname);
    if (isHashed) return "public, max-age=31536000, immutable";
    return "public, max-age=2592000, stale-while-revalidate=86400";
  }
  // HTML pages: short-lived so Cache Reserve doesn't serve stale markup
  return "public, max-age=300, stale-while-revalidate=60";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const originRes = await fetch(env.ORIGIN_URL + url.pathname);
    return new Response(originRes.body, {
      status: originRes.status,
      headers: {
        "content-type": originRes.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": getCacheDirective(url.pathname),
      },
    });
  },
};
```

## Cache Reserve Hit Detection

Detect whether a response came from Cache Reserve vs. origin via the `CF-Cache-Status` header:

```typescript
async function fetchWithCacheInstrumentation(
  url: string,
  env: Env,
): Promise<{ response: Response; tier: "edge" | "reserve" | "origin" }> {
  const res = await fetch(url, { cf: { cacheEverything: true } });

  const status = res.headers.get("cf-cache-status") ?? "";
  let tier: "edge" | "reserve" | "origin";

  if (status === "HIT") {
    tier = "edge";
  } else if (status === "REVALIDATED" || status === "EXPIRED") {
    // Cache Reserve served the content; the edge cache was stale
    tier = "reserve";
  } else {
    tier = "origin";
  }

  return { response: res, tier };
}
```

`CF-Cache-Status` values relevant to Cache Reserve:
- `HIT` — served from edge PoP (fastest)
- `REVALIDATED` — edge was stale, Cache Reserve was fresh; response served from R2
- `EXPIRED` — Cache Reserve entry expired; origin was fetched and Cache Reserve repopulated
- `MISS` — neither edge nor Cache Reserve had it; full origin fetch

## Programmatic Purge via Cache API

Purge a specific URL from Cache Reserve using the Cache API in a Worker:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { url: targetUrl } = await request.json<{ url: string }>();
    if (!targetUrl || typeof targetUrl !== "string") {
      return new Response("Bad Request", { status: 400 });
    }

    const cache = caches.default;
    const deleted = await cache.delete(new Request(targetUrl));

    return Response.json({
      purged: deleted,
      url: targetUrl,
      // Note: cache.delete() purges from the edge PoP; Cache Reserve purge
      // requires the Cloudflare API /zones/{zone}/purge_cache endpoint
    });
  },
};
```

For Cache Reserve purge (not edge-only), call the Cloudflare REST API from a Worker:

```typescript
async function purgeFromCacheReserve(
  zoneId: string,
  apiToken: string,
  files: string[],
): Promise<boolean> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ files }),
    },
  );
  const data = await res.json<{ success: boolean }>();
  return data.success;
}
```

## Anti-patterns
- Setting `Cache-Control: no-store` or `private` on assets — these bypass both edge cache and Cache Reserve
- Using Cache Reserve for personalized or authenticated content — Cache Reserve is a shared cache; never store user-specific data in it
- Relying on Cache Reserve as a CDN origin without monitoring `CF-Cache-Status` — stale-while-revalidate masks cache misses; monitor origin request rates separately
- Not setting `immutable` on content-hashed assets — Cache Reserve will still attempt revalidation after `max-age` expires

## Gotchas
- Cache Reserve incurs R2 Class A (write) and Class B (read) operations — audit costs before enabling on high-traffic zones
- Cache Reserve purge via the Cloudflare API is eventual; it may take up to 30 seconds to propagate globally
- Workers deployed with `cf.cacheEverything: false` (the default) bypass Cache Reserve even when it is enabled on the zone
- `Vary` headers that include `Accept-Encoding` or `Cookie` can inflate Cache Reserve storage by creating many variations per URL

## Verification
1. Enable Cache Reserve in Cloudflare dashboard → Caching → Cache Reserve
2. Fetch a long-tail URL and check `CF-Cache-Status: MISS` → wait for Cache Reserve write → fetch again and confirm `REVALIDATED` or `HIT`
3. Monitor origin request rate in Cloudflare Analytics; expect 60–90% reduction for static asset traffic after Cache Reserve warms
4. Use `curl -sI <url> | grep -i cf-cache-status` to spot-check specific URLs

## Related
- [cloudflare-cache-api-workers-mobile.md](cloudflare-cache-api-workers-mobile.md)
- [cloudflare-cache-rules-vs-workers-cache-api.md](cloudflare-cache-rules-vs-workers-cache-api.md)
- [edge-caching-patterns.md](edge-caching-patterns.md)
- [r2-range-request-large-file-optimization.md](r2-range-request-large-file-optimization.md)
- [cache-stampede-prevention.md](cache-stampede-prevention.md)

## Sources
- Cloudflare Docs: Cache Reserve — https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
- Cloudflare Blog: Introducing Cache Reserve
- Cloudflare Docs: CF-Cache-Status header — https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
