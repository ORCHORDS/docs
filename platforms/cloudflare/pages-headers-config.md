# pages-headers-config

**Issue:** Setting custom HTTP response headers in Cloudflare Pages using `_headers`
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The `_headers` file lets you declare per-path response headers without writing a Pages Function. It is processed before Functions and is the right place for security headers, cache control, and CORS on static assets.

## Pattern / Solution

```
# public/_headers

# Security headers for all pages
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), microphone=(), camera=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'

# Cache static assets aggressively (hashed filenames)
/assets/*
  Cache-Control: public, max-age=31536000, immutable

# CORS for API proxy path (if using Pages Functions as API)
/api/*
  Access-Control-Allow-Origin: https://app.example.com
  Access-Control-Allow-Methods: GET, POST, OPTIONS
  Access-Control-Allow-Headers: Content-Type, Authorization

# HSTS — force HTTPS for one year
/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload

# Specific file — disable caching for HTML
/*.html
  Cache-Control: no-cache, no-store, must-revalidate
```

**File location:**
```
dist/
├── _headers     ← inside the output directory
├── index.html
└── assets/
```

**Syntax rules:**
- Line 1: URL pattern (glob supported).
- Subsequent indented lines: `Header-Name: value`.
- Multiple patterns can set the same header — headers are merged.
- Later patterns override earlier ones for the same header name.

## Gotchas
- Headers in `_headers` are **merged** with Cloudflare's default headers; they do not replace them entirely.
- To **remove** a default header, you cannot — use a Pages Function for that.
- The `Content-Security-Policy` header value must be on a **single line** (no line breaks in the value).
- CORS preflight (`OPTIONS`) requests are not automatically handled by `_headers` alone; you need a Function for `OPTIONS` method handling.
- Max 100 header rules per project.
- `_headers` applies to static file responses only; Pages Functions return their own headers.
- Use `Cache-Control: immutable` only for files with content-hashed names (e.g., `app.abc123.js`).

## Related
- `pages-redirects-config.md`
- `cors-pages-functions.md`
- `csp-headers-and-cf-waf.md`
- `pages-best-practices.md`
