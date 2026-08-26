# pages-static-vs-functions

**Issue:** Static asset vs Pages Function — when each wins
**Date:** 2026-08-09
**Status:** documented

## Symptom
You put a `_redirects` rule to handle SPA routing. Suddenly
your `/api/foo` POST returns the `index.html` instead of
running your Pages Function. The API is broken.

## Root cause
CF Pages processes requests in this order:
1. **Static assets** (`/out` from `next build`, or
   `apps/web/public/`)
2. **Pages Functions** (`functions/` directory)
3. **`_redirects` rules** (the file, not the runtime feature)
4. **404 fallback** (default: serve `index.html` for SPAs)

If the static asset exists, it wins. If the Function exists, it
runs. If neither, the redirect rule runs. The 404 fallback is
last.

**Source:** CF Pages routing:
https://developers.cloudflare.com/pages/configuration/redirects/

> "The order of priority for Pages routing is: Functions,
> static assets, _redirects, 404. ... Functions always take
> precedence over _redirects."

## Fix
Three layers, each with its purpose:

### 1. Static assets (`apps/web/public/` or `out/`)
- HTML, CSS, JS, images, fonts, favicons
- Served directly from the edge cache (no compute)
- Use for: built bundles, public images, robots.txt, sitemap.xml,
  .well-known/* (AASA, assetlinks.json)

### 2. Pages Functions (`functions/`)
- Server-side logic (auth, DB writes, API endpoints)
- Runs on each request (not cached by default)
- Use for: `/api/*`, dynamic rendering, A/B testing at the edge

### 3. `_redirects` rules
- URL rewriting (e.g. `/old-page → /new-page`)
- Domain-level redirects (e.g. `www → apex`)
- **NEVER intercept `/api/*` if you have Functions for them**
- Use for: legacy URL redirects, marketing campaign tracking,
  www/apex normalization

### 4. 404 fallback
- Default: 404 page
- Override: a `404.html` in the static dir (custom 404)
- For SPAs: `_redirects` rule `/* /index.html 200` makes the SPA
  handle 404s client-side

## The conflict: SPA + API

The classic trap: a SPA wants client-side routing (so all unknown
paths serve `index.html`), but `/api/foo` should be a Function.

```bash
# _redirects
/* /index.html 200
# This catches /api/foo too — bad
```

The fix is to **exclude /api from the SPA fallback**:

```bash
# _redirects
/api/* /api/:splat 200   # explicit no-op for /api/* (let Functions run)
/* /index.html 200        # SPA fallback for everything else
```

The first rule explicitly forwards `/api/*` to itself with 200,
which takes precedence over the catch-all (specificity wins).
Functions for `/api/*` then run normally.

## Verification
- **Test:** `test/routing.test.ts > API endpoints are not
  intercepted by _redirects` — passes
- **Live:** `curl https://example.com/api/health` returns
  `{"ok":true}`, not the SPA HTML

## Gotchas
- **Function path with `[[path]].ts` is a catch-all.** It catches
  /api/foo and /api/foo/123. Without it, only the exact path
  matches.
- **`_redirects` is processed by the CF runtime, not the
  Pages Functions runtime.** It runs before the Function. So
  a redirect that fires first will never reach your Function.
- **The 200 vs 301/302 distinction matters.** A 200 is a server-
  side rewrite (the URL bar doesn't change). A 301/302 is a
  redirect (the URL bar changes; the browser re-fetches).
- **For marketing campaigns with UTM parameters**, prefer 302
  (temporary) so you can change the destination later. 301
  (permanent) is cached aggressively.
- **`_headers` file** is the static-asset way to set response
  headers (CSP, etc.). For Functions, set headers in the
  Response object.

## Related
- `pages-functions-exact-match-routing.md`
- `cors-pages-functions.md`
- `_redirects` syntax: https://developers.cloudflare.com/pages/configuration/redirects/
