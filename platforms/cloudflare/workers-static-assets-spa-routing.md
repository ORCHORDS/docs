# Workers Static Assets Binding for SPA Routing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a single-page application (SPA) built with React, Vue, or similar framework deployed to Cloudflare Workers. Client-side routes like `/dashboard` or `/settings` return 404 when users navigate directly or refresh, because the file does not exist on the server. You need the Worker to serve `index.html` for all unmatched paths while still serving real static files and dynamic API routes correctly.

## Context

Cloudflare Workers now supports a first-class `[assets]` binding in `wrangler.toml` that replaces Workers Sites. The binding exposes an `assets.fetch()` method inside the Worker and supports a `not_found_handling` option that controls what happens when a requested file is missing. Setting it to `"single-page-application"` makes the runtime return `index.html` with a `200` status for any missing path, which is exactly the behaviour SPAs require. Dynamic API routes handled by the Worker itself must be matched before the asset fetch call so they are not accidentally swallowed by the SPA fallback.

## wrangler.toml Configuration

```toml
# wrangler.toml
name = "my-spa"
main = "src/worker.ts"
compatibility_date = "2026-06-01"

[assets]
directory = "./dist"              # output of your build step
binding = "ASSETS"               # name exposed inside the Worker
not_found_handling = "single-page-application"  # SPA fallback

# Optional: tune caching per asset class via custom rules
# (see Cache Headers section below)
```

## Worker Entry-point — Mixing API Routes with Static Assets

```typescript
// src/worker.ts
export interface Env {
  ASSETS: Fetcher; // injected by the [assets] binding
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // --- Dynamic API routes handled before asset lookup ---
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request, env);
    }

    // --- Health / readiness probe ---
    if (url.pathname === "/healthz") {
      return new Response("ok", { status: 200 });
    }

    // --- Static asset serving with SPA fallback ---
    // When not_found_handling = "single-page-application" the
    // runtime already returns index.html for missing paths, but
    // calling fetch() ourselves lets us add or override headers.
    const assetResponse = await env.ASSETS.fetch(request);

    // Apply cache headers based on whether the file is fingerprinted
    return applyCacheHeaders(url.pathname, assetResponse);
  },
};

async function handleApi(request: Request, env: Env): Promise<Response> {
  // Example: return JSON from a KV or D1 lookup
  return Response.json({ message: "hello from api" });
}

/**
 * Fingerprinted assets (e.g. main.a1b2c3d4.js) get a long-lived
 * immutable cache. Entry points (index.html, manifest.json) get
 * no-store so CDN always revalidates.
 */
function applyCacheHeaders(pathname: string, response: Response): Response {
  const fingerprintRe = /\.[0-9a-f]{8,}\.(js|css|woff2?|png|svg|webp)$/i;
  const noStoreRe = /\/(index\.html|manifest\.json|service-worker\.js)$/i;

  const headers = new Headers(response.headers);

  if (noStoreRe.test(pathname)) {
    headers.set("Cache-Control", "no-store");
  } else if (fingerprintRe.test(pathname)) {
    headers.set("Cache-Control", "public, max-age=31536000, immutable");
  } else {
    // Non-fingerprinted static files: revalidate after 1 hour
    headers.set("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400");
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
```

## Custom 404 Page via assets.fetch() Fallback

When `not_found_handling` is left at the default (`"none"`) you control the fallback entirely:

```typescript
// Manual 404 fallback — use when not_found_handling = "none"
async function serveWithCustom404(request: Request, env: Env): Promise<Response> {
  const assetResponse = await env.ASSETS.fetch(request);

  if (assetResponse.status === 404) {
    // Fetch your custom 404 page from the same asset bundle
    const notFoundRequest = new Request(
      new URL("/404.html", request.url).toString(),
      request
    );
    const notFoundResponse = await env.ASSETS.fetch(notFoundRequest);
    return new Response(notFoundResponse.body, {
      status: 404,
      headers: notFoundResponse.headers,
    });
  }

  return assetResponse;
}
```

## Cache Headers for Fingerprinted vs Non-fingerprinted Assets

| Asset type | Example | Cache-Control |
|---|---|---|
| SPA entry point | `index.html` | `no-store` |
| Fingerprinted JS/CSS | `main.a1b2c3.js` | `public, max-age=31536000, immutable` |
| Static images (no hash) | `logo.png` | `public, max-age=3600, stale-while-revalidate=86400` |
| Service worker | `sw.js` | `no-store` |

Modern build tools (Vite, webpack, Parcel) fingerprint all chunk files automatically. Ensure your build outputs `index.html` without a hash so the `no-store` rule fires.

## Anti-patterns

- **Serving `index.html` for `/api/` routes** — always match and handle API paths before calling `env.ASSETS.fetch()`, otherwise the SPA fallback swallows API 404s and the client receives HTML instead of JSON.
- **Setting `immutable` on unfingerprinted files** — if `logo.png` is cached forever and you update it, users see the stale version until the cache naturally expires or is purged.
- **Forgetting `service-worker.js` cache exemption** — browsers check service worker updates every 24 hours, but only if the server sets `no-store` or `no-cache` on the file; a long `max-age` silently breaks SW updates.

## Gotchas

- `not_found_handling = "single-page-application"` returns `index.html` with HTTP `200`, not `404`. Some crawlers and monitoring tools interpret this as the SPA itself being at every URL, which can skew analytics.
- The `ASSETS` binding is only injected when the Worker is deployed via `wrangler deploy`; local `wrangler dev` requires the `--remote` flag or a local `dist/` folder to emulate it.
- Large `dist/` directories (> 1 GB total or > 20 000 files) hit Workers Static Assets limits; split large bundles into R2-backed CDN delivery for media files.
- `assets.fetch()` does not support range requests for large files natively — stream video from R2 directly if you need byte-range support.

## Verification

```bash
# Build the SPA and deploy
npm run build
wrangler deploy

# Verify SPA fallback: should return 200 with index.html body
curl -si https://my-spa.example.com/dashboard | head -20

# Verify API route is NOT swallowed by SPA fallback
curl -si https://my-spa.example.com/api/health

# Verify fingerprinted asset has immutable header
curl -si https://my-spa.example.com/assets/main.a1b2c3d4.js \
  | grep -i cache-control

# Verify index.html has no-store
curl -si https://my-spa.example.com/index.html \
  | grep -i cache-control
```

## Related

- `d1-export-import-r2-archival-pipeline.md`
- `workers-tcp-socket-database-proxy.md`

## Sources

- Cloudflare Workers Static Assets docs — https://developers.cloudflare.com/workers/static-assets/
- wrangler.toml assets configuration — https://developers.cloudflare.com/workers/wrangler/configuration/#assets
- Cache-Control best practices — https://web.dev/articles/http-cache
