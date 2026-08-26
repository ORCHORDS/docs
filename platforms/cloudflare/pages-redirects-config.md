# pages-redirects-config

**Issue:** Configuring static redirects in Cloudflare Pages using `_redirects`
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Pages processes a `_redirects` file at the root of the output directory. Redirects defined here are applied before Pages Functions run and are ideal for URL migrations, canonical redirects, and SPA fallbacks.

## Pattern / Solution

```
# public/_redirects

# Basic 301 redirect
/old-path  /new-path  301

# 302 temporary
/promo     /sale      302

# Splat — redirect entire path prefix
/blog/*    /posts/:splat  301

# SPA fallback — serve index.html for all unmatched routes
/*         /index.html    200

# Redirect with query string preservation (automatic — splat preserves QS)
/search/*  /find/:splat   301

# Country-based redirect using Cloudflare geo
/           /en/    302  Country=US
/           /de/    302  Country=DE

# Proxying (200 rewrite — content served from /index.html but URL stays)
/app/*     /index.html    200

# Force HTTPS — not needed; Cloudflare does this at the edge
```

**File location:**
```
my-project/
├── public/          ← output directory
│   ├── _redirects   ← here
│   ├── index.html
│   └── ...
```

**Limits:**
- Maximum **2000** redirect rules per project.
- Each rule: source, destination, status code, optional condition.
- Processed top-to-bottom; first match wins.

**Via `wrangler.toml` (Pages):**
```toml
# Alternatively configure via pages_build_output_dir
[pages_build_output_dir]
output_dir = "dist"
```
The `_redirects` file must be inside the output directory.

## Gotchas
- The `200` status code is a **rewrite** (proxy), not a redirect — the browser URL does not change.
- A `/*  /index.html  200` SPA fallback must be the **last** rule; put it at the bottom.
- `_redirects` rules apply **before** Pages Functions; a matching redirect short-circuits the Function.
- Cloudflare ignores lines starting with `#` (comments) and blank lines.
- Query strings are preserved automatically — no need to append `?:query`.
- Country conditions use ISO 3166-1 alpha-2 codes and require a paid plan to function correctly.
- The `_redirects` format is the same as Netlify's — migration is usually a copy-paste.

## Related
- `pages-headers-config.md`
- `pages-best-practices.md`
- `pages-functions-routing.md`
