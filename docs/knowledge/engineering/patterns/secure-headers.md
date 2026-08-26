# secure-headers

**Issue:** HTTP security headers — comprehensive checklist
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. A pen test reports "missing security
headers." You add `X-Frame-Options: DENY`. Another test
finds "missing CSP." You add a CSP. The cycle never ends.

## Root cause
**Security headers are a list, not a single thing.** The right
set depends on the app's needs, but a baseline is universal.

**Source:** OWASP Secure Headers Project:
https://owasp.org/www-project-secure-headers/

## The baseline (for a consumer app)

```ts
// In a Pages Function middleware
const securityHeaders = {
  // Anti-clickjacking
  'X-Frame-Options': 'DENY',

  // Anti-MIME-sniffing
  'X-Content-Type-Options': 'nosniff',

  // XSS protection (legacy, but still good)
  'X-XSS-Protection': '1; mode=block',

  // Referrer policy
  'Referrer-Policy': 'strict-origin-when-cross-origin',

  // HTTPS only
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',

  // Permissions policy (disable unused features)
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=(), payment=()',

  // Content-Security-Policy
  'Content-Security-Policy': "default-src 'self'; script-src 'self' 'nonce-...'; ...",

  // Cross-Origin isolation
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
  'Cross-Origin-Resource-Policy': 'same-origin',
};
```

## Per-header explained

### `X-Frame-Options: DENY`
Prevents your site from being embedded in an iframe. Anti-
clickjacking. Use `Content-Security-Policy: frame-ancestors
'none'` as the modern equivalent.

### `X-Content-Type-Options: nosniff`
Prevents the browser from MIME-sniffing (guessing the content
type). Forces the browser to use the declared type.

### `X-XSS-Protection: 1; mode=block`
Legacy XSS filter. Modern browsers ignore it. Still set for
old browsers.

### `Referrer-Policy: strict-origin-when-cross-origin`
Sends the origin (not the full URL) on cross-origin requests.
Privacy-friendly.

### `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
Forces HTTPS for 1 year. `preload` submits to the browser's
HSTS preload list (irreversible). Only set `preload` if you're
committed to HTTPS forever.

### `Permissions-Policy: geolocation=(), ...`
Disables browser features you don't need. Each `()` disables
the feature. `self` allows same-origin only.

### `Content-Security-Policy: ...`
See `csp-headers-and-cf-waf.md` for full details. The most
powerful + most complex header.

### `Cross-Origin-*`
A family of headers for cross-origin isolation:
- `Cross-Origin-Opener-Policy: same-origin` — windows from
  your site can't interact with windows from other sites
- `Cross-Origin-Embedder-Policy: require-corp` — resources
  must opt-in to being embedded
- `Cross-Origin-Resource-Policy: same-origin` — your resources
  can only be loaded by your site

These enable `SharedArrayBuffer` and other high-resolution
timers (needed for some crypto + multithreaded JS).

## Per-app customization

For a Next.js app with `next/image`, `next/font`, and Google
Analytics:
```ts
'Content-Security-Policy': [
  "default-src 'self'",
  "script-src 'self' 'nonce-{NONCE}' https://*.googletagmanager.com https://*.cloudflareinsights.com",
  "style-src 'self' 'nonce-{NONCE}' https://fonts.googleapis.com 'unsafe-inline'",  // Next.js needs unsafe-inline for styles
  "font-src 'self' https://fonts.gstatic.com data:",
  "img-src 'self' data: blob: https://*.cloudflare.com",
  "connect-src 'self' https://*.example.com",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join('; '),
```

## Set in CF Pages

The cleanest way is via `_headers` file in `apps/web/public/`:

```
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Permissions-Policy: geolocation=(), microphone=(), camera=()
```

For CSP with per-request nonce, set in a Pages Function:
```ts
export const onRequest: PagesFunction = async (context) => {
  const nonce = generateNonce();
  const response = await context.next();
  response.headers.set(
    'Content-Security-Policy',
    buildCsp(nonce)
  );
  return response;
};
```

## Verification
- **Test:** `test/security-headers.test.ts > all responses have
  baseline headers` — passes
- **Live:** Mozilla Observatory score A+
- **Pen test:** Annual third-party review

## Gotchas
- **`Strict-Transport-Security` with `preload` is irreversible.**
  You can't unsubmit from the preload list. Only enable
  `preload` if you're 100% committed to HTTPS.
- **CSP with `unsafe-inline` is much weaker.** Use nonces if
  you can.
- **`Cross-Origin-Embedder-Policy: require-corp` breaks
  third-party embeds** that don't set `Cross-Origin-Resource-
  Policy`. Test before enabling.
- **Some headers are deprecated** (`X-XSS-Protection`,
  `Public-Key-Pins`). Modern equivalent is in CSP.
- **The `Permissions-Policy` syntax has changed** over the
  years. The current syntax is `feature=()` or `feature=(self)`.

## Related
- `csp-headers-and-cf-waf.md`
- `cors-pages-functions.md`
- OWASP: https://owasp.org/www-project-secure-headers/
- Mozilla Observatory: https://observatory.mozilla.com/
- securityheaders.com: https://securityheaders.com/
