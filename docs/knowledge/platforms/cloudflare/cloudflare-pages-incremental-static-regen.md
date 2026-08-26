# Incremental Static Regeneration (ISR) on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a Cloudflare Pages site with server-side rendered pages that are expensive to generate (database queries, external API calls) but whose content changes infrequently. You want to serve cached HTML instantly to most visitors while silently regenerating stale pages in the background — the same "stale-while-revalidate" pattern popularised by Next.js ISR, but implemented entirely on Cloudflare Pages Functions with the Cache API and R2.

---

## Context

Cloudflare Pages Functions run as edge Workers and have access to the Cache API (keyed by URL), R2 for durable HTML storage, and `ctx.waitUntil()` to run background work after the response is sent. ISR is implemented as: (1) check the Cache API for a fresh entry and serve it immediately, (2) if the cache is missing or stale, serve the last-known-good HTML from R2 while scheduling a background revalidation via `ctx.waitUntil()`, (3) the revalidation renders fresh HTML, stores it in R2 with a timestamp, and repopulates the Cache API. This avoids blocking any visitor on a full render. The TTL is controlled by the `Cache-Control: s-maxage` value stored alongside the R2 object's metadata.

---

## Section 1 — Config / wrangler.toml (Pages)

```toml
# wrangler.toml (at repo root for Pages Functions)
name = "my-pages-site"
compatibility_date = "2025-01-01"
pages_build_output_dir = "dist"

[[r2_buckets]]
binding = "HTML_CACHE"
bucket_name = "isr-html-cache"

[vars]
ISR_TTL_SECONDS = "60"   # revalidate after 60 seconds
ISR_STALE_SECONDS = "86400"  # serve stale for up to 24 h while revalidating
```

---

## Section 2 — Pages Function with ISR logic

```typescript
// functions/[[path]].ts  — catch-all Pages Function
import type { PagesFunction } from "@cloudflare/workers-types";

export interface Env {
  HTML_CACHE: R2Bucket;
  ISR_TTL_SECONDS: string;
  ISR_STALE_SECONDS: string;
}

interface CacheMetadata {
  cachedAt: number;   // Unix ms
  ttl: number;        // seconds until "fresh" expires
  stale: number;      // seconds after ttl during which we serve stale
}

function r2Key(url: URL): string {
  // Normalize: strip query params for the HTML store key
  return `html${url.pathname === "/" ? "/index" : url.pathname}.html`;
}

async function renderPage(url: URL): Promise<string> {
  // Replace this with your actual SSR render call:
  // e.g. import { render } from '../src/server';
  const upstream = await fetch(`https://origin.example.com${url.pathname}`, {
    headers: { "X-ISR-Render": "1" },
  });
  if (!upstream.ok) throw new Error(`Origin ${upstream.status}`);
  return upstream.text();
}

async function revalidate(
  url: URL,
  bucket: R2Bucket,
  ttl: number,
  stale: number
): Promise<void> {
  let html: string;

  try {
    html = await renderPage(url);
  } catch (err) {
    // Revalidation failed — leave the existing R2 object in place
    console.error("ISR revalidation failed:", err);
    return;
  }

  const meta: CacheMetadata = { cachedAt: Date.now(), ttl, stale };
  await bucket.put(r2Key(url), html, {
    httpMetadata: { contentType: "text/html; charset=utf-8" },
    customMetadata: { isr: JSON.stringify(meta) },
  });

  // Also populate the Cache API so the next visitor gets a cache hit
  const cache = caches.default;
  const cacheResponse = new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": `public, s-maxage=${ttl}, stale-while-revalidate=${stale}`,
      "X-ISR-Revalidated-At": new Date().toISOString(),
    },
  });
  await cache.put(url.toString(), cacheResponse.clone());
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, waitUntil } = context;
  const url = new URL(request.url);
  const ttl = Number(env.ISR_TTL_SECONDS ?? "60");
  const stale = Number(env.ISR_STALE_SECONDS ?? "86400");

  // 1. Check the Cache API (fastest path — in-datacenter memory)
  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) {
    const age = Number(cached.headers.get("Age") ?? 0);
    if (age < ttl) {
      // Fully fresh — serve as-is
      return cached;
    }
    // Stale — serve immediately, revalidate in background
    waitUntil(revalidate(url, env.HTML_CACHE, ttl, stale));
    const staleResponse = new Response(cached.body, cached);
    staleResponse.headers.set("X-ISR-Status", "stale-revalidating");
    return staleResponse;
  }

  // 2. Cache miss — check R2 for last-known-good HTML
  const obj = await env.HTML_CACHE.get(r2Key(url));
  if (obj) {
    const meta: CacheMetadata = JSON.parse(
      obj.customMetadata?.["isr"] ?? "{\"cachedAt\":0,\"ttl\":0,\"stale\":86400}"
    );
    const ageSeconds = (Date.now() - meta.cachedAt) / 1000;
    const html = await obj.text();

    // Serve stale from R2 and schedule background revalidation
    waitUntil(revalidate(url, env.HTML_CACHE, ttl, stale));

    return new Response(html, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": `public, s-maxage=${Math.max(0, ttl - ageSeconds)}, stale-while-revalidate=${stale}`,
        "X-ISR-Status": ageSeconds < ttl ? "fresh-r2" : "stale-r2-revalidating",
        "X-ISR-Age": String(Math.round(ageSeconds)),
      },
    });
  }

  // 3. Nothing cached — render synchronously (cold start)
  let html: string;
  try {
    html = await renderPage(url);
  } catch (err) {
    return new Response("Service unavailable", { status: 503 });
  }

  // Store in R2 and Cache API for future requests
  waitUntil(revalidate(url, env.HTML_CACHE, ttl, stale));

  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": `public, s-maxage=${ttl}, stale-while-revalidate=${stale}`,
      "X-ISR-Status": "cold",
    },
  });
};
```

---

## Section 3 — Purge a single page

```typescript
// functions/api/purge.ts
import type { PagesFunction } from "@cloudflare/workers-types";
import type { Env } from "../[[path]]";

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const { pathname } = await request.json<{ pathname: string }>();
  if (!pathname) return new Response("Missing pathname", { status: 400 });

  const url = new URL(request.url);
  url.pathname = pathname;

  // Delete from R2 so next visit triggers a cold render
  const key = `html${pathname === "/" ? "/index" : pathname}.html`;
  await env.HTML_CACHE.delete(key);

  // Purge Cache API (only works for same-origin URLs)
  await caches.default.delete(url.toString());

  return new Response(JSON.stringify({ purged: pathname }), {
    headers: { "Content-Type": "application/json" },
  });
};
```

---

## Anti-patterns

- **Using `Cache-Control: no-store` on ISR responses** — This tells Cloudflare's edge to bypass the Cache API entirely; the whole ISR system then falls to R2 on every request, which is slower.
- **Storing rendered HTML in KV instead of R2** — KV has a 25 MB value limit and higher per-write cost for large HTML; R2 has no per-operation charge for storage and a 5 GB object limit.
- **Running the full render inside `waitUntil` on every request** — `waitUntil` should only fire when the cached version is actually stale; always check age before scheduling revalidation.
- **Not including a purge endpoint** — ISR without purge means content updates only propagate after TTL expiry; always expose an authenticated purge route for deploy hooks.

---

## Gotchas

- The Cache API in Pages Functions is scoped to the current Cloudflare datacenter; R2 is globally consistent. On the first visit to a new colo, R2 is the fallback even if other colos have a warm cache.
- `caches.default.put()` requires the URL to be the same origin as the Worker; for Pages sites this is the `pages.dev` or custom domain URL — use `request.url` rather than a hardcoded string.
- `ctx.waitUntil()` budget is 30 seconds of CPU across all deferred tasks; if revalidation takes longer, it is terminated silently.
- R2 `customMetadata` values must be strings; serialize the `CacheMetadata` object as JSON.
- Pages Functions have a 1 MB script size limit; if your SSR renderer is large, use a separate Worker accessed via a service binding.

---

## Verification

```bash
# Deploy Pages project
npx wrangler pages deploy dist --project-name my-pages-site

# First visit (cold) — should return X-ISR-Status: cold
curl -I https://my-pages-site.pages.dev/blog/hello-world

# Second visit (fresh from Cache API)
curl -I https://my-pages-site.pages.dev/blog/hello-world
# Expected: X-ISR-Status: fresh (or via CDN cache HIT)

# Wait > ISR_TTL_SECONDS, then request — stale served, revalidation triggered
curl -I https://my-pages-site.pages.dev/blog/hello-world
# Expected: X-ISR-Status: stale-revalidating

# Purge a page
curl -X POST https://my-pages-site.pages.dev/api/purge \
  -H 'Content-Type: application/json' \
  -d '{"pathname":"/blog/hello-world"}'
```

---

## Related

- `cloudflare-d1-time-series-analytics.md`
- `workers-geo-routing-cf-request.md`

---

## Sources

- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/
- Cloudflare Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare R2 — https://developers.cloudflare.com/r2/
- stale-while-revalidate RFC 5861 — https://www.rfc-editor.org/rfc/rfc5861
