# Custom HTTP Response Headers via the `_headers` File on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to ship security headers (`X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy`, `Permissions-Policy`) with every response from a Cloudflare Pages site, override `Cache-Control` for specific routes, and do it without adding a Pages Function or modifying framework code.

## Context

Cloudflare Pages supports a plain-text `_headers` file placed at the **output root** of your build (e.g., `dist/`, `public/`, `.next/` depending on framework). The file is parsed at deploy time and applied at the edge for every matching request — zero runtime overhead, no Function invocation cost. Headers set in `_headers` are merged with Cloudflare's default headers but can be overridden by a Pages Function that explicitly sets the same header on the response.

---

## `_headers` File Syntax and Global Security Headers

```
# _headers  (place in your build output root, e.g. dist/_headers)
# Lines starting with # are comments.
# Format:
#   /path/or/pattern
#     Header-Name: value
#
# The wildcard /* matches every route.

/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://api.example.com; frame-ancestors 'none'

# Static assets: long-lived immutable cache
/assets/*
  Cache-Control: public, max-age=31536000, immutable
  X-Frame-Options: DENY

# HTML pages: always revalidate
/*.html
  Cache-Control: no-cache, must-revalidate

# API proxy route (if served from Pages): no caching
/api/*
  Cache-Control: no-store
  Access-Control-Allow-Origin: https://app.example.com
  Access-Control-Allow-Methods: GET, POST, OPTIONS
  Access-Control-Allow-Headers: Content-Type, Authorization

# Specific file override
/robots.txt
  Cache-Control: public, max-age=86400
  X-Robots-Tag: noarchive
```

---

## Path Matching Rules

| Pattern | Matches |
|---|---|
| `/*` | Every path (global wildcard) |
| `/assets/*` | Any path under `/assets/` |
| `/*.html` | Files with `.html` extension at root |
| `/blog/:slug` | Named segment (single path component) |
| `/docs/**` | Any depth under `/docs/` |

Rules are applied **top-to-bottom**; the **last matching rule wins** for a given header. If two rules both set `Cache-Control`, the lower rule in the file takes precedence for paths matched by both.

---

## Precedence: `_headers` vs Pages Functions

When a Pages Function also runs for the same route, header precedence is:

1. **Pages Function response headers** (set via `response.headers.set(...)`) win if the Function explicitly sets a header.
2. **`_headers` file** applies to headers the Function did not set.
3. **Cloudflare default headers** fill remaining gaps.

This means a Function can *override* `_headers` for a specific route without removing the global defaults for all other routes.

```typescript
// functions/api/data.ts  — only Cache-Control is overridden here;
// security headers from _headers still apply.
export const onRequestGet: PagesFunction = async ({ request }) => {
  const data = await fetchData();
  return new Response(JSON.stringify(data), {
    headers: {
      "Content-Type": "application/json",
      // This overrides the /* Cache-Control from _headers for /api/data
      "Cache-Control": "public, max-age=60, stale-while-revalidate=300",
    },
  });
};
```

---

## Setting Up in Common Frameworks

**Vite / React / Vue** — place `_headers` in `public/`. Vite copies `public/` verbatim to `dist/`.

**Next.js on Pages** — place `_headers` in the project root (Pages picks it up from the output dir automatically via the `@cloudflare/next-on-pages` adapter).

**Astro** — place in `public/`; Astro copies it to `dist/`.

```bash
# Verify the file is in your build output before deploying
ls -la dist/_headers
```

---

## Anti-patterns

- **Duplicating headers in both `_headers` and framework config** — e.g., setting `X-Frame-Options` in `next.config.js` `headers()` *and* in `_headers`. Pick one; duplication can cause double-header responses which confuse browsers.
- **Using `/*` for CORS headers on a public site** — overly broad CORS opens security holes. Scope CORS rules to `/api/*` only.
- **Omitting `includeSubDomains` from HSTS** — if any subdomain serves HTTP, omitting this leaves a downgrade vector.
- **Setting `Cache-Control: public` on `/api/*`** — CDN-cached API responses bypass authentication checks on subsequent requests.

## Gotchas

- The `_headers` file must be in the **build output directory**, not the project root, unless your output dir *is* the root.
- Cloudflare Pages strips the `Set-Cookie` header from `_headers` — use a Function if you need to set cookies.
- Header names are case-insensitive per HTTP spec, but use canonical Title-Case in `_headers` for readability.
- The `Content-Security-Policy` value must be on a **single line** — line continuation is not supported.
- Maximum 100 rules and 100 headers per file; beyond this, use a Function.

## Verification

```bash
# Check that security headers are present on the live site
curl -si https://your-site.pages.dev/ | grep -E \
  '(x-frame-options|strict-transport|permissions-policy|content-security-policy|cache-control)'

# Expected output (headers present, values correct):
# x-frame-options: DENY
# strict-transport-security: max-age=31536000; includeSubDomains; preload
# permissions-policy: camera=(), microphone=(), geolocation=(), payment=()
# cache-control: no-cache, must-revalidate

# Check a static asset route
curl -si https://your-site.pages.dev/assets/app.js | grep cache-control
# Expected: cache-control: public, max-age=31536000, immutable
```

## Related

- `cloudflare-pages-functions-middleware.md`
- `workers-security-headers-middleware.md`
- `cloudflare-images-transform-workers.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/headers/
- https://developers.cloudflare.com/pages/functions/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy
