# csp-headers-and-cf-waf

**Issue:** Content-Security-Policy for a Next.js app on CF Pages
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship your app. A pen test finds "XSS via unsafe-inline script"
or "clickjacking possible." You add `Content-Security-Policy` to
the response. The app breaks — inline styles, Google Fonts, and
the analytics script all blocked.

## Root cause
CSP is a powerful but blunt tool. Each `script-src`, `style-src`,
`img-src`, etc. is an allowlist. A misconfigured CSP either
allows too much (defeats the purpose) or too little (breaks
functionality). The right CSP requires knowing your dependencies.

**Source:** MDN — CSP:
https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP

> "Content Security Policy (CSP) is an added layer of security
> that helps to detect and mitigate certain types of attacks,
> including Cross-Site Scripting (XSS) and data injection
> attacks."

## Fix
A practical CSP for a Next.js + 3rd-party-integrations app:

```ts
// In a Pages Function (or _headers file)
const CSP = [
  "default-src 'self'",
  // Scripts: self + nonce-based inline + 3rd-party analytics
  "script-src 'self' 'nonce-{NONCE}' https://*.googletagmanager.com https://*.cloudflareinsights.com",
  // Styles: self + nonce + Google Fonts
  "style-src 'self' 'nonce-{NONCE}' https://fonts.googleapis.com",
  // Fonts
  "font-src 'self' https://fonts.gstatic.com data:",
  // Images: self + data: + CDN
  "img-src 'self' data: blob: https://*.cloudflare.com https://*.pages.dev",
  // Connections: fetch/XHR/WebSocket
  "connect-src 'self' https://*.example.com wss://*.example.com",
  // Frames
  "frame-src 'self' https://js.stripe.com",
  // Object/embed (block)
  "object-src 'none'",
  // Form action
  "form-action 'self'",
  // Base URI
  "base-uri 'self'",
  // Frame ancestors (anti-clickjacking)
  "frame-ancestors 'none'",
  // Upgrade insecure requests
  "upgrade-insecure-requests",
].join('; ');

headers.set('Content-Security-Policy', CSP);
headers.set('X-Content-Type-Options', 'nosniff');
headers.set('X-Frame-Options', 'DENY');
headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
headers.set('Permissions-Policy', 'geolocation=(), microphone=(), camera=()');
```

### Nonces for inline scripts

The nonce must be **unique per request**. Generate it server-side:

```ts
function generateNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}

const nonce = generateNonce();
const CSP = `script-src 'self' 'nonce-${nonce}' ...`;

// In HTML:
<script nonce={nonce}>window.appNonce = '{nonce}';</script>
```

### `unsafe-inline` is a footgun

`'unsafe-inline'` allows all inline scripts. It defeats the XSS
protection. Use nonces or hashes instead. The ONLY legitimate
use of `'unsafe-inline'` is:
- A 3rd-party script that can't be refactored (avoid if possible)
- Dev mode (not production)

### `unsafe-eval` is also bad

`'unsafe-eval'` allows `eval()`, `new Function()`, `setTimeout("code", ms)`.
This is a major XSS vector. Most modern code doesn't need it.
If you see it, you have a problem.

## Verification
- **Test:** `test/csp.test.ts > CSP header is set on all responses`
  — passes
- **Live:** Browser DevTools shows the CSP in response headers;
  no CSP violations in console
- **Pen test:** Annual third-party CSP review
- **Mozilla Observatory:** Score A+ on CSP

## Gotchas
- **CSP reports via `report-uri` or `report-to`.** Set up an
  endpoint to receive violation reports. They tell you what's
  being blocked (and might reveal attacks).
- **CSP in dev vs prod.** In dev, you might want
  `'unsafe-eval'` for hot-reload. Disable in production.
- **CSP doesn't catch stored XSS** (already in the DB). It
  catches reflected XSS (in the URL). Still essential.
- **`frame-ancestors 'none'` is the right default** for
  non-embeddable apps. For embeddable apps, use
  `frame-ancestors 'self' https://trusted-partner.com`.
- **Some browsers ignore certain directives** (e.g. `referrer`
  vs `referrer-policy`). Test in your target browsers.

## Related
- `cors-pages-functions.md` (companion for CORS)
- MDN CSP: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- CF WAF: https://developers.cloudflare.com/waf/
- Mozilla Observatory: https://observatory.mozilla.com/
