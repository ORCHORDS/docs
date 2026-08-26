# Cloudflare Pages _headers File and CSP for Mobile

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

After adding a Content Security Policy (CSP) to the example project
Cloudflare Pages deployment via the `_headers` file, inline
`<script>` tags injected by third-party SDKs are blocked in
desktop Chrome but cause a completely blank screen on iOS
Safari and some Android WebViews. The browser console (when
accessible via Safari remote debugging) shows
`Refused to execute inline script because it violates the
following Content Security Policy directive: "script-src
'self'"`. The CSP was tested and appeared to pass in
desktop Chrome, but mobile Safari has stricter CSP
enforcement for certain directive combinations. Additionally,
nonce-based CSP — the best practice for inline scripts —
cannot be used with Next.js `output: 'export'` because there
is no server to generate and inject per-request nonces.

## Context

Cloudflare Pages processes a `_headers` file placed in the
root of the build output. It allows setting arbitrary HTTP
response headers per path, including `Content-Security-Policy`
and `Content-Security-Policy-Report-Only`. This is the only
mechanism for response headers in a pure static Pages
deployment — there is no server-side middleware or edge
runtime in a Next.js static export.

CSP is complex in the static export context because:

1. **No nonces** — nonces require server-side generation
   per request. A static file has one fixed HTML content;
   every user gets the same file with the same `<script>`
   tags. Nonces would be the same for all users (defeating
   the purpose) or would require a Worker to rewrite the
   response.
2. **`unsafe-inline` is broad** — it allows all inline
   scripts, negating XSS protection.
3. **Hashes are viable** — `sha256-<base64>` hashes of
   specific inline script contents can be whitelisted. They
   survive static deployment because the content does not
   change per request.
4. **Mobile WebViews add restrictions** — iOS WKWebView
   and Android WebView have additional CSP enforcement
   quirks on top of standard browser behaviour.

## _headers file format and placement

```
# public/_headers
# This file is copied into out/ by `next build`.
# Cloudflare Pages reads it from the deployment root.
# Rules: path (glob) on its own line; headers indented.

/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

/sw.js
  Cache-Control: no-cache, no-store, must-revalidate
  Service-Worker-Allowed: /

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable
```

CSP is added as a header value on `/*` or specific paths.
A long CSP value must stay on a single line in `_headers` —
there is no line-continuation syntax.

## CSP without nonces: hash-based approach

For inline scripts in the Next.js static export, use
`sha256` hashes of the exact script content:

```sh
# Compute hash for an inline script
echo -n "window.__THEME__='dark';" | \
  openssl dgst -binary -sha256 | \
  base64
# Output: AbC123...== (use this in CSP)
```

```
# public/_headers

/*
  Content-Security-Policy: default-src 'self'; script-src 'self' 'sha256-AbC123...==' https://cdn.example.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://api.example project.example.com; frame-ancestors 'none'; upgrade-insecure-requests
```

Next.js itself generates inline scripts for hydration
(chunk manifests, theme scripts). You must hash each one.
The set of inline scripts is stable across builds if the
build output is deterministic. In practice:

```
Inline script type              Frequency of change
─────────────────────────────────────────────────────
Next.js chunk manifest          Changes on every build
  (__NEXT_DATA__ or similar)    (different chunk hashes)

Theme / dark-mode init script   Stable (hand-written)
  added via next/script

Third-party init snippets       Stable if pinned to
  (analytics, chat widget)       exact version

next/font inline CSS            Stable across builds
  (font-face declarations)       unless fonts change
──────────────────────────────────────────────────────
Next.js build-generated inline scripts change on every
build. Hashing them requires a post-build script.
```

## Post-build script to auto-hash inline scripts

```ts
// scripts/generate-csp-hashes.ts
import { readFileSync, writeFileSync } from 'fs';
import { createHash } from 'crypto';
import { JSDOM } from 'jsdom';
import { glob } from 'glob';

const htmlFiles = glob.sync('out/**/*.html');
const hashes = new Set<string>();

for (const file of htmlFiles) {
  const dom = new JSDOM(readFileSync(file, 'utf-8'));
  const scripts = dom.window.document.querySelectorAll(
    'script:not([src])'
  );
  for (const script of scripts) {
    const content = script.textContent ?? '';
    if (!content.trim()) continue;
    const hash = createHash('sha256')
      .update(content)
      .digest('base64');
    hashes.add(`'sha256-${hash}'`);
  }
}

// Read the _headers template and inject the hashes
const template = readFileSync('public/_headers.template', 'utf-8');
const csp = template.replace(
  '__SCRIPT_HASHES__',
  [...hashes].join(' ')
);
writeFileSync('out/_headers', csp);
console.log(`Wrote ${hashes.size} script hashes to out/_headers`);
```

```json
// package.json
{
  "scripts": {
    "build": "next build && tsx scripts/generate-csp-hashes.ts"
  }
}
```

## Mobile WebView CSP differences

```
Behaviour               iOS WKWebView         Android WebView
────────────────────────────────────────────────────────────────
CSP enforcement         Strict — follows      Varies by WebView
                        WebKit CSP spec       version; older
                                              Android < 5.0
                                              ignores CSP

'unsafe-eval'           Blocked               Blocked on modern;
                        Required by some      older WebViews may
                        older JS engines —    allow it silently
                        avoid any eval()-
                        based code

Blob: URLs in CSP       Requires              Requires
  (for Web Workers)     worker-src blob:      worker-src blob:
                        or script-src blob:   or default-src blob:

Service Worker scope    Blocked if            Blocked if
  registration          script-src missing    script-src missing
                        the SW script hash    the SW script hash
                        or 'self'             or 'self'

data: URIs in           Requires              Requires
  img-src               img-src data:         img-src data:
                        explicitly            explicitly

Inline event handlers   Blocked by default    Blocked by default
  onclick="…"           even with             even with
                        'unsafe-inline'       'unsafe-inline' in
                        in some              some WebView
                        WKWebView configs     configurations
────────────────────────────────────────────────────────────────
```

## Recommended CSP for example project static export

This is a starting template — hashes must be replaced with
actual values from the post-build script:

```
/*
  Content-Security-Policy: default-src 'self'; script-src 'self' __SCRIPT_HASHES__ https://cdn.mxpnl.com https://js.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https:; media-src 'self' blob: https://cdn.example project.example.com; connect-src 'self' https://api.example project.example.com https://o0.ingest.sentry.io wss://realtime.example project.example.com; worker-src 'self' blob:; frame-src https://js.stripe.com; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests; report-uri https://o0.ingest.sentry.io/api/csp-report
```

Notes on specific directives:

```
Directive        Value             Reason
──────────────────────────────────────────────────────────────
worker-src       'self' blob:      SW registration requires
                                   'self'; Workbox uses
                                   blob: URLs for the SW
                                   script on some paths

connect-src      wss://            WebSocket connections to
                                   Cloudflare Durable Objects
                                   or Pusher must be listed

frame-ancestors  'none'            Prevents clickjacking;
                                   equivalent to X-Frame-
                                   Options: DENY but with
                                   broader browser support

report-uri       Sentry DSN        CSP violations are sent to
                                   Sentry for monitoring; use
                                   report-to for modern syntax
──────────────────────────────────────────────────────────────
```

## CSP-Report-Only for staged rollout

Deploy `Content-Security-Policy-Report-Only` first to
collect violations without breaking the app, then switch to
`Content-Security-Policy` once the violation report is clean.

```
# public/_headers (report-only phase)

/*
  Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' __SCRIPT_HASHES__; report-uri https://o0.ingest.sentry.io/api/csp-report
```

Run report-only for 1–2 weeks covering mobile users. Review
the Sentry CSP report for any violations from:
- In-app browsers (Instagram, TikTok add injected scripts)
- WebView-based OAuth flows
- Third-party scripts that call `eval()`

## Anti-patterns

- **`script-src 'unsafe-inline' 'unsafe-eval'`** — disables
  practically all XSS protection. If you need this to make
  the app work, the root cause is an inline script or an
  `eval()`-using library that should be replaced or
  isolated in a sandboxed iframe.
- **Nonce-based CSP in a static export** — the nonce in
  the HTML source is static; all users get the same nonce,
  making it meaningless. Any attacker can read the nonce
  from the HTML and use it in an injected script. Use hashes
  instead for static deployments.
- **Forgetting `worker-src 'self' blob:`** — the Service
  Worker script will fail to register with a CSP violation,
  silently breaking offline support and push notifications.
  This is one of the most common mobile-specific CSP bugs.
- **Very long `_headers` lines** — Cloudflare Pages has a
  maximum line length in `_headers`. Extremely long CSP
  strings (> 4 KB) should be validated — break the CSP into
  multiple `Content-Security-Policy` headers if needed (CF
  Pages supports multiple values for the same header key).
- **Not testing CSP on mobile** — Safari on iOS has
  historically enforced CSP directives differently from
  Chrome. Always validate on a real iOS device using
  Safari's remote debugger, not just Chrome DevTools.

## Gotchas

- **`_headers` does not support comments** — lines starting
  with `#` are ignored but some CSP tools output `#`-
  prefixed annotations. Verify the generated `_headers`
  file contains no comments after the post-build script
  writes to `out/_headers`.
- **Cloudflare Pages merges headers** — if a path matches
  multiple rules (e.g. `/*` and `/index.html`), Cloudflare
  Pages merges the headers. Two `Content-Security-Policy`
  headers on the same response means the browser applies
  the intersection — the stricter of the two wins.
- **Stripe.js requires `frame-src js.stripe.com`** —
  Stripe's payment element renders in an iframe from
  `js.stripe.com`. Without this directive the payment
  modal is completely blank on mobile Safari, with no
  console error (the iframe itself is blocked silently).
- **In-app browsers inject scripts** — Instagram and TikTok
  WebViews inject additional JavaScript for their SDK. This
  can violate a strict CSP and break the app. You cannot
  whitelist these injected scripts by hash (they change).
  Use `report-only` to measure the frequency and consider
  detecting the in-app browser to show a "open in Safari"
  prompt for CSP-sensitive flows (age verification, payment).

## Verification

- `curl -I https://example project.example.com | grep -i content-security`
  returns the full CSP header.
- No CSP violations appear in Sentry for 48 hours after
  switching from `Report-Only` to enforced mode.
- Service Worker registers successfully on mobile (DevTools
  → Application → Service Workers shows "activated").
- Stripe payment element renders on iOS Safari and Android
  Chrome — frame-src is correct.
- `REPORT-ONLY` CSP violations from in-app browsers are
  monitored and documented; a "open in browser" prompt is
  shown for payment flows.

## Related

- `documentation/docs/policies/frontend/nextjs-static-export-cloudflare-pages-routing.md`
- `documentation/docs/policies/frontend/service-worker-caching-cloudflare-cdn-conflict.md`
- `documentation/docs/policies/security/content-security-policy.md`
- `documentation/docs/policies/cloudflare/pages-headers-configuration.md`
- `documentation/docs/policies/payments/stripe-csp-integration.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Pages — Headers —
  https://developers.cloudflare.com/pages/configuration/headers/
- MDN — Content-Security-Policy —
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
- web.dev — CSP: A strict policy —
  https://web.dev/articles/strict-csp
- Stripe — CSP requirements —
  https://docs.stripe.com/security/guide#content-security-policy
- W3C CSP Level 3 spec —
  https://www.w3.org/TR/CSP3/
