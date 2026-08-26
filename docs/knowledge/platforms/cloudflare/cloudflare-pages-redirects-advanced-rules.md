# Cloudflare Pages Redirects — `_redirects` File, Transform Rules, SPA Routing & Mobile UA Redirects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) is a Next.js static export on Cloudflare Pages. Engineers need to: (a) send `/app/*` deep links to the SPA index for client-side routing, (b) redirect legacy URL paths after a redesign, (c) serve a different landing page to mobile user-agents, and (d) apply country-based redirects. They run into `_redirects` rule ordering surprises, conflict between Pages `_redirects` and dashboard-level Page Rules / Transform Rules, and mobile UA redirects that fire on desktop browsers with spoofed agents.

## Context

Pages supports three redirect mechanisms, applied in this order:

```
1. _headers / _redirects file (evaluated at edge, before Workers)
2. Pages Functions (/_middleware.ts or route-specific functions)
3. Zone-level Transform Rules (Redirect Rules in the dashboard)
```

`_redirects` is a Netlify-compatible file placed in the `out/` (static export output) directory. Cloudflare Pages processes up to **2 000 redirect rules** per project. Rules are evaluated top-to-bottom; first match wins.

example project's `next.config.js` uses `output: 'export'` — the static files land in `out/`. The `_redirects` file must be placed in `public/_redirects` so Next.js copies it into `out/_redirects` during build.

## `_redirects` File Syntax

```
# Format: <source> <destination> <status_code>

# Permanent redirect (301)
/old-landing        /          301

# Temporary redirect (302)
/sale               /promotions  302

# SPA catch-all (see SPA section below)
/app/*              /app/index.html  200

# Splat capture: :splat is the matched wildcard portion
/blog/:slug         /posts/:slug  301

# Query string preservation (automatic; no special syntax needed)
/legacy?ref=:ref    /new?source=:ref  301
```

Status codes supported: 200 (rewrite, not a redirect), 301, 302, 303, 307, 308. A 200 rewrite serves the destination content at the original URL — useful for SPA routing.

Rule processing order and limits:

| Priority | Rule type | Limit |
|---|---|---|
| 1 | Exact path match in `_redirects` | Top of file first |
| 2 | Wildcard/splat match in `_redirects` | After exact matches |
| 3 | Pages Functions route | Separate layer |
| — | Zone Redirect Rules | Evaluated after Pages response |

## SPA Routing — Next.js Static Export

Next.js `output: 'export'` generates `out/app/index.html` and static JSON chunks. Client-side navigation works only after the initial load. Deep links (`/app/recordings/abc-123`) 404 because no static file exists at that path.

Fix in `public/_redirects`:

```
# Serve all /app/* paths from the SPA entry point (200 = rewrite, not redirect)
/app/*    /app/index.html    200
```

This must come AFTER any more-specific `/app/` rules:

```
# Specific static asset paths — must come BEFORE the catch-all
/app/manifest.json    /app/manifest.json    200
/app/favicon.ico      /app/favicon.ico      200

# SPA catch-all for all other /app/ routes
/app/*    /app/index.html    200
```

Next.js generates hashed asset filenames (`_next/static/...`) which are served directly from Pages' static file serving — the `_redirects` catch-all does not interfere with `/_next/*` paths because those files exist as static assets (exact file match takes priority over `_redirects`).

## Legacy URL Migration

example project migrated from `/wam/:id` to `/recordings/:id` in June 2026. `_redirects` handles this permanently:

```
# Preserve existing deep links from old URL scheme
/wam/:id            /recordings/:id    301
/wam/:id/download   /recordings/:id/download  301
/wam/:id/embed      /embed/:id         301

# Old marketing pages
/about-old          /about             301
/pricing-beta       /pricing           301
/api-docs-v1/*      /docs/api/:splat   301
```

Test that the splat capture is correct:

```bash
curl -I https://example.com/wam/abc-123
# Expected: HTTP 301, Location: /recordings/abc-123

curl -I https://example.com/api-docs-v1/authentication
# Expected: HTTP 301, Location: /docs/api/authentication
```

## Mobile User-Agent Redirects

`_redirects` does not support header matching natively. Mobile UA redirects require either a Pages Function or a Transform Rule.

**Option A — Pages Function** (recommended for example project):

```typescript
// functions/_middleware.ts
export const onRequest: PagesFunction = async ({ request, next }) => {
  const url = new URL(request.url);

  // Only redirect the marketing homepage, not the SPA or API
  if (url.pathname === "/" || url.pathname === "") {
    const ua = request.headers.get("User-Agent") ?? "";
    const cfDevice = request.headers.get("CF-Device-Type");
    const isMobile =
      cfDevice === "mobile" || cfDevice === "tablet" ||
      /Mobi|Android|iPhone|iPad/i.test(ua);

    if (isMobile) {
      return Response.redirect("https://example.com/mobile", 302);
    }
  }

  return next();
};
```

**Option B — Cloudflare Transform Rule** (zone-level, dashboard or Terraform):

```
Rule name: Mobile homepage redirect
When: (http.request.uri.path eq "/" and http.user_agent contains "Mobi")
Then: Redirect to https://example.com/mobile (302)
```

Transform Rules run at zone level after Pages serves the response — actually they run at the same edge layer. In practice, for Pages projects, zone-level Redirect Rules intercept before Pages for the same PoP. Verify ordering with the Cloudflare Trace tool.

Caveat: UA-based redirects are unreliable for bot traffic. Bots can send any UA string. Combine with `CF-Device-Type` (Cloudflare's own device detection) for higher confidence.

## Country-Based Redirects

`_redirects` does not support country matching. Use a Pages Function:

```typescript
// functions/_middleware.ts
const BLOCKED_COUNTRIES = new Set(["XX", "YY"]); // ISO 3166-1 alpha-2

export const onRequest: PagesFunction = async ({ request, next }) => {
  const country = (request as any).cf?.country as string | undefined;

  if (country && BLOCKED_COUNTRIES.has(country)) {
    return new Response("Service unavailable in your region", { status: 451 });
  }

  // Redirect specific countries to localised pages
  if (country === "DE") {
    const url = new URL(request.url);
    if (url.pathname === "/") {
      return Response.redirect("https://example.com/de/", 302);
    }
  }

  return next();
};
```

`request.cf.country` is available in Workers / Pages Functions from the Cloudflare request object (not on the standard `Request` type — cast or use `(request as any).cf`).

## Pages Rules vs Transform Rules vs `_redirects`

| Feature | `_redirects` | Pages Functions | Transform/Redirect Rules |
|---|---|---|---|
| Wildcard/splat | Yes | Full code | Pattern match |
| Header matching | No | Yes | Yes |
| Country/IP matching | No | Yes (via `cf.*`) | Yes |
| UA matching | No | Yes | Yes (limited) |
| Rule limit | 2 000 | No hard limit | Free: 3, Pro: 20+, Biz: 50+ |
| Latency | None (static) | ~0ms (same edge) | ~0ms (same edge) |
| Applies to | Pages project only | Pages project only | Entire zone |
| Config location | `public/_redirects` | `functions/` dir | Cloudflare Dashboard/Terraform |

Classic Page Rules are deprecated in favour of Transform Rules. Do not create new Page Rules; migrate existing ones.

## `_headers` File — Security and Cache Headers

`_headers` is processed alongside `_redirects`. Useful for mobile-specific cache control:

```
# Disable caching for API routes (served by Workers, but belt-and-suspenders)
/api/*
  Cache-Control: no-store

# Long-term cache for hashed Next.js assets
/_next/static/*
  Cache-Control: public, max-age=31536000, immutable

# Security headers on all pages
/*
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
```

## Anti-patterns

- Placing the SPA catch-all `/*    /index.html  200` before specific static file paths — this swallows asset 404s and serves the SPA shell instead of a real 404 response.
- Creating zone-level Page Rules that conflict with `_redirects` — Pages `_redirects` is processed at the Pages edge handler; zone rules run at zone level. The interaction order varies and is hard to reason about without the Trace tool.
- Using 301 for temporary redirects during testing — browsers cache 301s aggressively; use 302 until the redirect is permanent.
- Relying on UA strings alone for mobile detection — server-side UA detection is fragile. Prefer `CF-Device-Type` with UA as a fallback, and progressive enhancement on the client.
- Having > 2 000 rules in `_redirects` — Cloudflare silently truncates beyond the limit; the last rules are dropped without warning.

## Gotchas

- **`_redirects` file must be in `out/` root after build**: place it in `public/` in Next.js — Next copies `public/` into `out/` during `next build`. Verify with `ls out/_redirects` after build.
- **Splat (`:splat`) vs named segments (`:param`)**: `:splat` captures everything after the `*` wildcard including slashes; named `:param` matches a single path segment. Use `*` + `:splat` for multi-segment captures.
- **`200` rewrites vs `301` redirects**: a `200` rewrite serves the destination content but the browser URL does not change. SPA routing requires `200`; canonical URL consolidation requires `301`.
- **Query strings are preserved automatically**: `_redirects` does not drop query strings. If you need to strip them, use a Pages Function with `url.search = ''`.
- **Transform Rule evaluation happens at zone edge, not Pages edge**: a zone Redirect Rule targeting `/app/*` fires before Pages' own routing, potentially bypassing `_redirects` entirely.

## Verification

```bash
# Test SPA deep link rewrite (should return 200, not 404)
curl -I https://example.com/app/recordings/abc-123
# Expected: HTTP/2 200

# Test legacy redirect
curl -I https://example.com/wam/abc-123
# Expected: HTTP/2 301, location: /recordings/abc-123

# Test that /_next/ assets are NOT caught by SPA rewrite
curl -I "https://example.com/_next/static/chunks/main.js"
# Expected: HTTP/2 200 (real asset, not SPA shell)

# Local build verification
ls out/_redirects  # must exist
cat out/_redirects | head -20
```

## Related

- `pages-redirects-config.md` — foundational `_redirects` patterns
- `pages-headers-config.md` — `_headers` file reference
- `pages-functions-routing.md` — Pages Functions route matching
- `pages-functions-middleware.md` — `_middleware.ts` patterns
- `nextjs-static-export-pages-mobile-quirks.md` — Next.js export on Pages
- `cache-device-type-segmentation-mobile-desktop.md` — CF-Device-Type details

## Sources

- Cloudflare Pages redirects: https://developers.cloudflare.com/pages/configuration/redirects/
- Pages Functions middleware: https://developers.cloudflare.com/pages/functions/middleware/
- Transform Rules: https://developers.cloudflare.com/rules/transform/
- CF-Device-Type: https://developers.cloudflare.com/rules/transform/managed-transforms/reference/
- `_headers` file: https://developers.cloudflare.com/pages/configuration/headers/
