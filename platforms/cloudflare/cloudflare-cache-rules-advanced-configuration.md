# Cloudflare Cache Rules Advanced Configuration with Workers Integration

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need fine-grained, per-route caching behaviour — different TTLs for API responses vs. HTML pages, cache bypass for authenticated sessions, cache key normalisation to improve hit rates, and stale-while-revalidate for zero-downtime deploys — all without touching origin code.

## Context
Cache Rules (the successor to Page Rules for caching) let you define ordered, expression-based rules in the Cloudflare dashboard or via the Rulesets API. They operate at the Cloudflare network layer, before a Worker executes, but Workers can observe and influence caching via `Cache-Control` headers, the Cache API (`caches.default`), and `fetch()` with `cf.cacheKey` / `cf.cacheTtl` options. Combining both layers gives you the most flexible edge caching strategy available.

## Cache Rules Configuration (Rulesets API)

```typescript
// scripts/deploy-cache-rules.ts — run with tsx for CI/CD automation
const ZONE_ID = process.env.ZONE_ID!;
const CF_TOKEN = process.env.CF_API_TOKEN!;
const BASE = `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets`;

interface CacheRule {
  description: string;
  expression: string;
  action: "set_cache_settings";
  action_parameters: {
    cache?: boolean;
    edge_ttl?: { mode: "fixed" | "bypass_by_default" | "respect_origin"; default?: number; status_code_ttl?: { status_code?: number; value: number }[] };
    browser_ttl?: { mode: "bypass" | "fixed" | "respect_origin"; default?: number };
    cache_key?: { ignore_query_strings_order?: boolean; custom_key?: { query_string?: { include?: string[]; exclude?: string[] }; header?: { include?: string[]; check_presence?: string[] }; cookie?: { include?: string[] } } };
    serve_stale?: { disable_stale_while_updating?: boolean };
  };
}

const rules: CacheRule[] = [
  {
    description: "Cache static assets for 1 year",
    expression: `(http.request.uri.path matches "^/static/.*\\.(js|css|woff2|png|webp|svg)$")`,
    action: "set_cache_settings",
    action_parameters: {
      cache: true,
      edge_ttl: { mode: "fixed", default: 31536000 },
      browser_ttl: { mode: "fixed", default: 31536000 },
      cache_key: {
        ignore_query_strings_order: true,
        custom_key: {
          query_string: { exclude: ["*"] }, // strip query strings for immutable assets
        },
      },
    },
  },
  {
    description: "Cache API GET responses for 60 s, bypass for authenticated users",
    expression: `(http.request.method eq "GET" and http.request.uri.path matches "^/api/public/")`,
    action: "set_cache_settings",
    action_parameters: {
      cache: true,
      edge_ttl: { mode: "fixed", default: 60, status_code_ttl: [{ status_code: 200, value: 60 }, { status_code: 404, value: 10 }] },
      browser_ttl: { mode: "bypass" }, // clients always revalidate
      cache_key: {
        custom_key: {
          // Vary cache by Accept-Language header
          header: { include: ["Accept-Language"] },
          // Exclude auth cookies from cache key (cached response is public)
          cookie: { include: [] },
          query_string: { include: ["page", "limit", "sort"] },
        },
      },
    },
  },
  {
    description: "Bypass cache for authenticated sessions",
    expression: `(http.cookie contains "session=")`,
    action: "set_cache_settings",
    action_parameters: {
      cache: false,
      edge_ttl: { mode: "bypass_by_default" },
      browser_ttl: { mode: "bypass" },
    },
  },
  {
    description: "HTML pages: stale-while-revalidate 5 s, edge TTL 30 s",
    expression: `(http.request.uri.path matches "^/[^.]*$" and not http.cookie contains "session=")`,
    action: "set_cache_settings",
    action_parameters: {
      cache: true,
      edge_ttl: { mode: "fixed", default: 30 },
      browser_ttl: { mode: "fixed", default: 5 },
      serve_stale: { disable_stale_while_updating: false }, // enable stale-while-revalidating
    },
  },
];

async function deployCacheRuleset() {
  // Get or create the cache ruleset for this zone
  const listRes = await fetch(`${BASE}?phase=http_request_cache_settings`, {
    headers: { Authorization: `Bearer ${CF_TOKEN}` },
  });
  const { result: rulesets } = (await listRes.json()) as { result: { id: string; phase: string }[] };
  const existing = rulesets.find((r) => r.phase === "http_request_cache_settings");

  const method = existing ? "PUT" : "POST";
  const url = existing ? `${BASE}/${existing.id}` : BASE;

  const body = {
    name: "Cache Rules",
    kind: "zone",
    phase: "http_request_cache_settings",
    rules,
  };

  const res = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${CF_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`Failed to deploy cache ruleset: ${await res.text()}`);
  console.log("Cache ruleset deployed:", (await res.json() as any).result?.id);
}

deployCacheRuleset().catch(console.error);
```

## Workers Cache API for Programmatic Control

```typescript
// src/index.ts — Worker that augments Cache Rules with runtime logic
export interface Env {
  ORIGIN: Fetcher;
}

const CACHE = caches.default;

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);

    // Only cache GET/HEAD
    if (req.method !== "GET" && req.method !== "HEAD") {
      return env.ORIGIN.fetch(req);
    }

    // Derive a normalised cache key (strip UTM params, sort remaining)
    const cacheUrl = normaliseCacheKey(url);
    const cacheReq = new Request(cacheUrl, req);

    // Check Worker cache (L2 after Cloudflare edge cache)
    const cached = await CACHE.match(cacheReq);
    if (cached) {
      const res = new Response(cached.body, cached);
      res.headers.set("X-Cache-Hit", "worker");
      return res;
    }

    // Fetch from origin with cf options
    const originRes = await env.ORIGIN.fetch(req, {
      cf: {
        // Override Cache-Control for cacheable paths at the Cloudflare layer
        cacheTtlByStatus: { "200-299": 60, "404": 10, "500-599": 0 },
        cacheKey: cacheUrl,
        cacheTtl: 60,
      },
    });

    // Store in Worker cache only for 200 OK with cacheable content type
    if (
      originRes.status === 200 &&
      (originRes.headers.get("Content-Type") ?? "").startsWith("application/json")
    ) {
      const cacheRes = new Response(originRes.body, originRes);
      cacheRes.headers.set("Cache-Control", "public, max-age=60, stale-while-revalidate=10");
      ctx.waitUntil(CACHE.put(cacheReq, cacheRes.clone()));
      cacheRes.headers.set("X-Cache-Hit", "miss");
      return cacheRes;
    }

    return originRes;
  },
} satisfies ExportedHandler<Env>;

function normaliseCacheKey(url: URL): string {
  const normalised = new URL(url.toString());
  // Remove tracking params
  ["utm_source", "utm_medium", "utm_campaign", "utm_content", "fbclid", "gclid"].forEach((p) =>
    normalised.searchParams.delete(p)
  );
  // Sort remaining query params for consistent cache keys
  normalised.searchParams.sort();
  return normalised.toString();
}
```

## Cache Purge Automation

```typescript
// src/purge.ts — call after content deployments
export async function purgeByTags(
  zoneId: string,
  token: string,
  tags: string[]
): Promise<void> {
  // Cache tags must be set on responses via `Cache-Tag` header at origin or in Worker
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tags }),
    }
  );
  if (!res.ok) throw new Error(`Purge failed: ${await res.text()}`);
}

export async function purgeByURLs(
  zoneId: string,
  token: string,
  urls: string[]
): Promise<void> {
  // Chunk into 30-URL batches (API limit)
  for (let i = 0; i < urls.length; i += 30) {
    const batch = urls.slice(i, i + 30);
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ files: batch }),
      }
    );
    if (!res.ok) throw new Error(`Purge batch ${i} failed: ${await res.text()}`);
  }
}
```

## Anti-patterns
- **Caching POST, PUT, DELETE, or PATCH responses** — these methods are never cached by Cloudflare by default; enabling caching for them breaks idempotency semantics.
- **Using `Cache-Control: no-store` at origin and expecting Cache Rules to override it** — Cache Rules' `edge_ttl` with `mode: "fixed"` overrides `Cache-Control` from origin; however, if the Worker sets `no-store` in the response headers that takes precedence over Cache Rules.
- **Conflating the Worker Cache API (`caches.default`) with Cloudflare's edge cache** — they are separate layers; `caches.default.put()` stores in the Worker's local cache partition, not in the shared CDN cache that Cache Rules manage.
- **Cache key divergence between Cache Rules and Workers** — if the Cache Rule normalises the cache key differently from your Worker's `cf.cacheKey`, you get double-miss penalties; keep normalisation logic consistent.
- **Setting very long browser TTLs on mutable resources** — even if you purge the edge cache, browsers retain stale copies until the browser TTL expires; use `immutable` in `Cache-Control` only for content-addressed URLs.

## Gotchas
- Cache Rules apply in **rule order** — the first matching rule wins; put the most specific rules (auth bypass) before broad rules (HTML caching).
- `serve_stale: { disable_stale_while_updating: false }` enables serving stale content while the edge revalidates; this is the opt-in default — `true` disables the behaviour.
- `caches.default.match()` in a Worker returns `undefined`, not `null`, on a miss — use `if (cached)` not `if (cached !== null)`.
- Cache purge by tag requires the `Cache-Tag` header to be set in the **response** (from origin or Worker); values are comma-separated strings, max 1 KB total per response.
- The Rulesets API returns 409 if you try to POST a new ruleset when one already exists for the phase; always GET-then-PUT as shown above.

## Verification
1. Deploy the cache ruleset script: `ZONE_ID=xxx CF_API_TOKEN=yyy npx tsx scripts/deploy-cache-rules.ts`.
2. `curl -I https://yourdomain.com/api/public/products` — response should include `CF-Cache-Status: HIT` after the second request.
3. `curl -I -b "session=abc" https://yourdomain.com/api/public/products` — `CF-Cache-Status: BYPASS` or `DYNAMIC` confirms auth bypass rule fired.
4. `curl -I https://yourdomain.com/static/app.js?v=1.2.3&utm_source=email` — confirm query string is stripped and `CF-Cache-Status: HIT` appears.
5. Post a purge: `curl -X POST .../purge_cache -d '{"tags":["products"]}'` and confirm the next request shows `CF-Cache-Status: MISS`.

## Related
- `cache-stale-while-revalidate-control-boundary.md`
- `workers-cache-api.md`
- `r2-custom-domains-cache-rules.md`
- `cloudflare-managed-transforms-request-response-headers.md`
- `cloudflare-pages-redirects-advanced-rules.md`

## Sources
- https://developers.cloudflare.com/cache/how-to/cache-rules/
- https://developers.cloudflare.com/cache/how-to/cache-rules/settings/
- https://developers.cloudflare.com/api/operations/zone-rulesets-create-a-zone-ruleset
