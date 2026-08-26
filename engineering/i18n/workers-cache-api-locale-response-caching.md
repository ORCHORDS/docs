# Workers Cache API for Locale-Specific Response Caching

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker assembles locale-specific HTML pages or JSON API responses by loading
translations from KV and formatting dates/numbers with `Intl`. The assembly is fast, but
loading KV keys on every request adds latency. The worker already has
`translation-kv-caching-ttl-strategy.md` covering in-memory module-level caches, but
those caches are per-isolate, not shared across requests to different isolates. The
**Cache API** (`caches.default`) offers a request-keyed, shared, edge-network cache
that survives across isolate instances and is invalidated explicitly.

## Context

Cloudflare Workers expose two caching surfaces:

| Surface | Scope | Key | TTL control | Invalidation |
|---------|-------|-----|-------------|--------------|
| Module-level `Map` | Single isolate instance | Custom | Process lifetime | Worker redeploy |
| **Cache API** (`caches.default`) | Edge PoP (shared) | `Request` URL | `Cache-Control` header | `cache.delete()` or URL change |
| **KV** | Global | String | TTL or explicit | `put()` with new value |

The Cache API is appropriate for assembled, rendered responses (HTML pages, JSON blobs)
that vary by locale and are expensive to regenerate. It is **not** a general-purpose
key-value store — the key must be a `Request` object (or URL string), and stored entries
respect HTTP caching semantics (`Cache-Control`, `Vary`).

**Critical**: `Vary: Accept-Language` on the cached response instructs the Cache API
to store separate copies per `Accept-Language` header value. Without this, a French user
might receive an English cached response.

## Basic Locale-Aware Response Caching Pattern

```typescript
// workers/src/locale-cache.ts
import { Env } from "./types";

/**
 * Fetch a locale-specific response from the Cache API.
 * Falls back to the provided assembler function on a miss.
 *
 * The cache key includes the locale as a query parameter to differentiate
 * responses without relying solely on Vary headers (which can be coarse).
 */
export async function withLocaleCache(
  request: Request,
  locale: string,
  ttlSeconds: number,
  assembler: () => Promise<Response>,
): Promise<Response> {
  const cache = caches.default;

  // Build a deterministic cache key that includes the locale
  const url = new URL(request.url);
  url.searchParams.set("__locale", locale);
  const cacheKey = new Request(url.toString(), { method: "GET" });

  // Cache lookup
  const cached = await cache.match(cacheKey);
  if (cached) {
    const response = new Response(cached.body, cached);
    response.headers.set("X-Cache", "HIT");
    return response;
  }

  // Cache miss — assemble the response
  const response = await assembler();

  // Only cache successful responses
  if (response.status === 200) {
    const toCache = new Response(response.clone().body, response);
    toCache.headers.set(
      "Cache-Control",
      `public, max-age=${ttlSeconds}, s-maxage=${ttlSeconds}`,
    );
    toCache.headers.set("Vary", "Accept-Language, Accept-Encoding");
    toCache.headers.set("Content-Language", locale);
    // Store without awaiting — don't block the response
    ctx.waitUntil(cache.put(cacheKey, toCache));
  }

  const miss = new Response(response.body, response);
  miss.headers.set("X-Cache", "MISS");
  return miss;
}
```

## Locale Cache Key Strategy

```typescript
// workers/src/cache-key.ts

/**
 * Compute a canonical cache key URL for a locale-specific page.
 *
 * Strategy: append the normalised BCP 47 tag to avoid:
 *  - "en-US" vs "en-us" producing duplicate cache entries
 *  - "zh-Hant-TW" vs "zh-TW" (same after likely-subtags maximisation) being cached
 *    separately
 */
export function buildLocaleCacheKey(
  originalUrl: string,
  locale: string,
): string {
  // Normalise the locale tag to a canonical form
  const canonicalLocale = new Intl.Locale(locale).toString();

  const url = new URL(originalUrl);
  // Use a private prefix to avoid colliding with real query parameters
  url.searchParams.set("_l", canonicalLocale);
  // Remove any user-specific tokens from the cache key
  url.searchParams.delete("session");
  url.searchParams.delete("token");
  url.searchParams.delete("csrf");
  return url.toString();
}

/**
 * Build separate cache keys for different content types served at the same URL.
 */
export function buildTypedCacheKey(
  originalUrl: string,
  locale: string,
  contentType: "html" | "json",
): string {
  const base = buildLocaleCacheKey(originalUrl, locale);
  const url = new URL(base);
  url.searchParams.set("_ct", contentType);
  return url.toString();
}
```

## Translation Bundle Caching via Cache API

```typescript
// workers/src/translation-bundle-cache.ts
import { Env } from "./types";

type TranslationBundle = Record<string, string>;

/**
 * Load a translation bundle with a two-level cache:
 * 1. Cache API (shared across isolates, TTL-based)
 * 2. KV (durable, authoritative)
 *
 * Cache API entries are invalidated by changing the cache key version on deploy.
 */
export async function getTranslationBundle(
  locale: string,
  version: string, // e.g. a deploy hash or semver
  kv: KVNamespace,
  ctx: ExecutionContext,
): Promise<TranslationBundle | null> {
  const cache = caches.default;
  const cacheUrl = `https://internal.cache/translations/${locale}/${version}`;
  const cacheKey = new Request(cacheUrl);

  // Level 1: Cache API
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached.json<TranslationBundle>();
  }

  // Level 2: KV
  const bundle = await kv.get<TranslationBundle>(`translations:${locale}`, "json");
  if (!bundle) return null;

  // Populate Cache API for future requests in this PoP
  const response = new Response(JSON.stringify(bundle), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
  ctx.waitUntil(cache.put(cacheKey, response));

  return bundle;
}
```

## Purging Locale Cache Entries

```typescript
// workers/src/cache-purge.ts

/**
 * Purge cached responses for a specific locale and path.
 * Called from a deployment hook or an admin API endpoint.
 */
export async function purgeLocaleCache(
  basePath: string,
  locales: string[],
  contentTypes: Array<"html" | "json"> = ["html", "json"],
): Promise<{ purged: string[] }> {
  const cache = caches.default;
  const purged: string[] = [];

  for (const locale of locales) {
    for (const ct of contentTypes) {
      const key = buildTypedCacheKey(basePath, locale, ct);
      const deleted = await cache.delete(new Request(key));
      if (deleted) purged.push(key);
    }
  }

  return { purged };
}

import { buildTypedCacheKey } from "./cache-key";

/**
 * Scheduled purge handler: run via Workers Cron Trigger to force
 * translation refresh even if TTL has not expired.
 */
export async function scheduledPurge(
  event: ScheduledEvent,
  env: { SUPPORTED_LOCALES: string; SITE_URL: string },
): Promise<void> {
  const locales = env.SUPPORTED_LOCALES.split(",");
  const pages = ["/", "/products", "/checkout", "/account"];

  for (const page of pages) {
    const url = `${env.SITE_URL}${page}`;
    await purgeLocaleCache(url, locales);
  }
}
```

## Conditional Caching: Personal vs Shared Content

```typescript
// workers/src/conditional-cache.ts

/**
 * Only cache responses that do not contain personalised content.
 * Authenticated requests bypass the cache entirely.
 */
export async function handleWithConditionalCache(
  request: Request,
  locale: string,
  env: Env,
  ctx: ExecutionContext,
  assembler: () => Promise<Response>,
): Promise<Response> {
  // Never cache authenticated requests
  const authHeader = request.headers.get("Authorization");
  const sessionCookie = getCookie(request, "session");
  if (authHeader || sessionCookie) {
    return assembler();
  }

  // Never cache POST, PUT, DELETE, PATCH
  if (request.method !== "GET" && request.method !== "HEAD") {
    return assembler();
  }

  return withLocaleCache(request, locale, 300, assembler);
}

function getCookie(request: Request, name: string): string | null {
  const cookieHeader = request.headers.get("Cookie") ?? "";
  const match = cookieHeader.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

import { withLocaleCache } from "./locale-cache";
```

## Anti-patterns

- **Using `Vary: Accept-Language` alone without the locale in the key**: `Accept-Language`
  can be a long, uncanonicalized string like `"en-US,en;q=0.9,fr;q=0.8"`. Two semantically
  identical locale preferences expressed differently will produce two cache entries.
  Always canonicalise the locale and embed it in the URL key.
- **Caching authenticated or session-specific content**: the Cache API is shared across
  users — caching a personalised response leaks it to other users.
- **Blocking the response on `cache.put()`**: always wrap cache writes in
  `ctx.waitUntil()` to avoid extending response latency.
- **Caching without `Cache-Control` headers**: an entry stored without `Cache-Control`
  may be subject to the CF default caching behaviour, which may not match your intent.
- **Relying on Cache API for durable storage**: the Cache API is a best-effort PoP-level
  cache. Entries can be evicted. Always keep KV or D1 as the authoritative source.
- **Mixing `__locale` parameter with URL canonicalisation**: ensure robots/sitemaps do
  not index URLs containing `__locale` or `_l` parameters.

## Gotchas

- `caches.default` is available in Workers but not in Pages Functions without explicit
  configuration. Pages Functions use a different caching model.
- The Cache API key is matched by URL including query string — a single extra character
  in the URL produces a cache miss. Use `url.searchParams.sort()` before building the
  key to handle parameter ordering variance.
- `cache.put()` requires the response to be `public` (no `Cache-Control: private` or
  `Authorization` header on the response). A response with `Set-Cookie` is not cacheable
  in the Cache API.
- `cache.match()` returns `undefined` (not `null`) on a miss. Check with `if (cached)`.
- Cache invalidation via `cache.delete()` only deletes from the PoP that processes that
  request — a global purge requires calling Cloudflare's Cache Purge API or changing the
  cache key (e.g. version hash).
- `s-maxage` in `Cache-Control` controls the shared cache TTL; `max-age` controls
  browser caching. Set both explicitly.

## Verification

```typescript
// tests/locale-cache.test.ts
// Use Miniflare or Wrangler dev for Cache API testing — Vitest cannot mock caches.default.
// Run: wrangler dev --test

describe("Locale cache key", () => {
  it("normalises locale tag", () => {
    const k1 = buildLocaleCacheKey("https://example.com/page", "en-US");
    const k2 = buildLocaleCacheKey("https://example.com/page", "en-us");
    // Both should resolve to the same canonical locale
    const u1 = new URL(k1);
    const u2 = new URL(k2);
    expect(u1.searchParams.get("_l")).toBe(u2.searchParams.get("_l"));
  });

  it("strips session tokens from cache key", () => {
    const key = buildLocaleCacheKey(
      "https://example.com/page?token=abc123",
      "fr",
    );
    expect(key).not.toContain("token=abc123");
  });
});
```

To test cache hit/miss in integration, check the `X-Cache` response header in `wrangler dev`.

## Related

- `translation-kv-caching-ttl-strategy.md` — KV-level caching for translation bundles
- `i18n-content-fallback-chain-kv-workers.md` — KV fallback chains
- `cloudflare-workers-geolocation-locale-routing.md` — Locale routing via `cf.country`
- `locale-negotiation-accept-language.md` — Accept-Language negotiation
- `multi-locale-ab-testing-workers.md` — A/B testing with locale awareness
- `content-negotiation-vary-header.md` — `Vary` header mechanics

## Sources

- Cloudflare Workers: Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Cache: How it works — https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
- HTTP Caching: `Vary` header — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Vary
- HTTP `Cache-Control` — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
- Cloudflare Workers: `ExecutionContext.waitUntil()` — https://developers.cloudflare.com/workers/runtime-apis/context/
- BCP 47 `Intl.Locale` canonicalization — https://tc39.es/ecma402/#sec-intl.locale
