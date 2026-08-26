# Pages _headers — Mobile Security Gotchas (Next.js Static Export)

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

On desktop Chrome, example.com KYC onboarding (Identomat) presents
the camera permission prompt on first visit. On iOS Safari the
camera prompt never appears and the Identomat SDK rejects the
session with `NotAllowedError`; on some Android WebViews the
microphone check fails silently after the user taps Allow. A
separate WASM price-ticker widget that uses `SharedArrayBuffer`
for lock-free ring buffers works on desktop but throws
`TypeError: Cannot use SharedArrayBuffer` on iOS 16–17 Safari
in the installed PWA — because the `_headers` file sets COOP to
`same-origin` to enable it, and that same header breaks the
Identomat redirect-back popup on Android Chrome. None of this
surfaces on desktop; desktop stays in the same browsing context
throughout, while mobile is where cross-origin popup and
permission-API edge cases land first.

## Context

example project (example.com) is a Next.js 14+ app deployed as a static
export (`output: 'export'`) to Cloudflare Pages. There is no
server-side rendering step: every HTML file is pre-rendered once
at build time. KYC onboarding calls
`navigator.mediaDevices.getUserMedia` for camera/microphone
liveness checks via the Identomat SDK. Payment and trading
features run a WASM module that requires `SharedArrayBuffer`
and `Atomics`. Correct header configuration means threading
five constraints simultaneously: CSP without nonces (static
export makes nonces impossible), Permissions-Policy that opens
camera/mic for the KYC path, COOP that enables SharedArrayBuffer
only where needed without breaking OAuth or KYC popups,
cache headers that are immutable on hashed chunks but never
cached on HTML, and a clear mental model of which mechanism
— `_headers`, Pages Functions, or wrangler.toml — actually
wins for a given response.

## 1. Header precedence: _headers, Functions, wrangler.toml

Three mechanisms can set response headers on a Pages deployment.
Their precedence is deterministic but widely misunderstood.

```
Mechanism             Scope              Wins over what
──────────────────────────────────────────────────────────────
_headers file         static assets      nothing above it;
                      only — NOT         any header a
                      Function           Function sets on
                      responses          its own response
                                         overrides it
Pages Function /      Function-          absolute for
_middleware.ts        generated          responses that
                      responses          go through it
wrangler.toml         Workers Assets     equivalent to
[headers] table       deployments        _headers; Pages
                      (not Pages)        ignores it
──────────────────────────────────────────────────────────────
```

Critical rule: `_headers` rules are **not applied** to responses
a Pages Function generates, even when the URL pattern matches.
A Function that intercepts `/kyc/*` must re-emit every security
header itself. Conversely, a Function cannot inject headers onto
static asset responses it does not intercept — the two scopes
are disjoint. `wrangler.toml`'s `[headers]` table is a Workers
Assets concept (the Pages successor); in a pure Pages project
it has no effect; `_headers` is the only file-based mechanism.

## 2. CSP nonces are incompatible with static exports

A CSP nonce must be unique per HTTP response — that is the
security guarantee. Generating a fresh nonce per response
requires server-side rendering. `next export` pre-renders static
HTML at build time, so there is no request context in which to
generate a nonce. Any nonce baked into the HTML at build time
is public by the time the page is served; an attacker who reads
the HTML reads the nonce and can reuse it.

```
Build-time output (insecure — same value on every response):
  <script nonce="abc123">…</script>
  Content-Security-Policy: script-src 'nonce-abc123'
  ↑ nonce is now readable in the source of the static file

Request-time output (correct — requires SSR or middleware):
  nonce = crypto.getRandomValues(…)    ← new per request
  <script nonce="${nonce}">…</script>
  Content-Security-Policy: script-src 'nonce-${nonce}'
```

Practical alternatives for a static export:

1. **CSP hashes** — compute a SHA-256/384 hash of each inline
   `<script>` block at build time; emit it into `_headers`.
   Next.js does not do this automatically. A post-build script
   or a Vite-style plugin is required. Hashes survive across
   multiple requests because the inline content never changes.

2. **Move all inline scripts to external `.js` files** — then
   `script-src 'self'` covers them. This is the lowest-friction
   option and what Next.js 14 static export practically
   requires.

3. **`strict-dynamic`** — propagates trust from a hash to
   dynamically loaded scripts. Requires at least one
   `'sha256-…'` hash to bootstrap; combine with option 1.

## 3. Permissions-Policy for camera and microphone (KYC)

Identomat and most WebRTC-based KYC SDKs call
`getUserMedia({ video: true, audio: true })` during liveness
checks. An overly restrictive Permissions-Policy blocks the
API call before the user is ever prompted, with no visible
error other than an SDK-internal rejection.

Correct header for the KYC path:

```
# public/_headers

/kyc/*
  Permissions-Policy: camera=(self), microphone=(self), \
    geolocation=(), payment=(self), usb=()

/*
  Permissions-Policy: camera=(), microphone=(), \
    geolocation=(), payment=(self), usb=()
```

Mobile-specific gaps in Permissions-Policy support:

```
Behavior                     Chrome Android  Safari iOS
──────────────────────────────────────────────────────
camera=(self) enforced       yes             14.5+
microphone=(self) enforced   yes             14.5+
Old Feature-Policy name      ignored         ignored
Re-prompts every page load   no              YES (OS policy)
camera=() blocks iframe      yes             15.4+
```

iOS Safari re-prompts for camera permission on every page load
because iOS grants are session-scoped at the OS level. The
Permissions-Policy header cannot change this. The KYC flow
should set user expectations upfront so the repeated prompt
is not mistaken for a bug.

## 4. COOP, COEP, and SharedArrayBuffer on mobile

`SharedArrayBuffer` and `Atomics` (required for WASM threads)
are gated behind cross-origin isolation. Enabling it requires
both headers on the page that uses them:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

COOP `same-origin` isolates the browsing context group.
Side-effect: cross-origin popups opened from the page get a
null `window.opener`, so `postMessage` from the popup back to
the page silently fails. This kills OAuth redirects and any
payment or KYC flow that relies on a popup completing its
work and notifying the opener.

```
COOP value               SharedArrayBuffer  Popup postMessage
──────────────────────────────────────────────────────────────
(not set)                blocked            works
same-origin              enabled            BROKEN
same-origin-allow-popups blocked            works
restrict-properties      blocked (†)        works (†)
──────────────────────────────────────────────────────────────
(†) restrict-properties is in origin trial as of mid-2026;
    not yet cross-origin-isolated in the SAB sense.
```

The only way to have both SharedArrayBuffer and working
OAuth/KYC popups is to host the WASM feature on a separate
sub-domain (e.g. `charts.example.com`) under COOP `same-origin`,
while the main app uses `same-origin-allow-popups` or no COOP.

Mobile isolation support as of mid-2026:

```
Browser              COOP same-origin  COEP require-corp
──────────────────────────────────────────────────────
Chrome Android 88+   supported         supported
Safari iOS 15.2+     supported         supported
Firefox Android 79+  supported         supported
Samsung Internet     12.0+             12.0+
```

COEP `require-corp` blocks any cross-origin resource that does
not respond with `Cross-Origin-Resource-Policy: cross-origin`.
Enabling it requires auditing every CDN font, Identomat SDK
asset, and R2 media URL for the CORP header — otherwise the
page simply fails to render.

## 5. Cache-Control: HTML pages vs hashed assets

Next.js static export produces two categories of output files:

```
Category             Path pattern           Correct policy
──────────────────────────────────────────────────────────
HTML entry points    /index.html            no-store
                     /kyc/index.html
JS/CSS chunks        /_next/static/chunks/  public,
(content-hashed)     app-abc123.js          max-age=31536000,
                                            immutable
Images, fonts        /_next/static/media/   public,
(content-hashed)     logo.def456.woff2      max-age=31536000,
                                            immutable
Non-hashed misc      /_next/static/build-   no-store
                     Manifest.json
──────────────────────────────────────────────────────────
```

Cloudflare Pages serves all routes with
`Cache-Control: public, max-age=0, must-revalidate` by default.
This is safe but causes avoidable round-trips for hashed assets.
Override via `_headers`:

```
# public/_headers

# HTML — never cache; filenames reuse across deploys
/*
  Cache-Control: no-store

# Content-hashed chunks — safe to cache forever in browser
/_next/static/chunks/*
  Cache-Control: public, max-age=31536000, immutable

/_next/static/css/*
  Cache-Control: public, max-age=31536000, immutable

/_next/static/media/*
  Cache-Control: public, max-age=31536000, immutable
```

`immutable` is a browser directive only; Cloudflare edge
ignores it and honours `max-age` / `s-maxage` instead.
`no-store` is the correct value for HTML: `no-cache` still
issues a conditional revalidation request, which adds a
measurable round-trip penalty on high-latency mobile networks.

## Anti-patterns

- **Expecting `_headers` rules to cover Pages Function
  responses.** The two scopes are disjoint. A HSTS or CSP
  entry in `_headers` disappears on any path a Function
  handles. Set security headers inside the Function or the
  root `_middleware.ts`.

- **Setting COOP `same-origin` on the main app to unlock
  SharedArrayBuffer.** It severs every OAuth popup, payment
  popup (Stripe, on-chain wallet), and Identomat redirect
  flow. Isolate the WASM route to a separate sub-domain.

- **Generating a nonce at build time.** A static nonce in
  a public HTML file is no nonce. Switch to CSP hashes or
  move all inline code to external scripts.

- **`Cache-Control: immutable` on HTML files.** HTML filenames
  do not change between deploys; a browser that caches
  `/kyc/index.html` as immutable will serve stale markup
  until the OS evicts it.

- **Using the legacy `Feature-Policy` header name.** All
  current browsers ignore it. Use `Permissions-Policy` only.

## Gotchas

- `_headers` is capped at 100 rules and 2,000 characters per
  header value. A long CSP string that exceeds the character
  limit is truncated silently. Verify with
  `curl -sI https://example.com/ | grep -i content-security`
  and count bytes.

- iOS Safari re-prompts for camera and microphone on every
  page load regardless of Permissions-Policy. This is an OS-
  level constraint; inform users at the start of KYC so
  repeated prompts read as expected, not broken.

- COEP `require-corp` silently breaks any cross-origin asset
  (Identomat SDK files, CDN fonts, R2 presigned URLs) that
  does not serve `Cross-Origin-Resource-Policy: cross-origin`.
  Audit every third-party resource before enabling COEP.

- A `_middleware.ts` Pages Function generates its own
  response and replaces the static asset response entirely.
  Any security header set in `_headers` for that path is
  not applied; the middleware must re-emit it.

- `no-store` on HTML is preferred over `no-cache`. Both
  prevent serving a stale page, but `no-cache` still sends
  a conditional GET on every navigation, adding a round-trip
  that mobile users notice on lossy cellular connections.

## Verification

- `curl -sI https://example.com/` → `cache-control: no-store`
  and full CSP visible in response headers.
- `curl -sI https://example.com/_next/static/chunks/<any>.js`
  → `cache-control: public, max-age=31536000, immutable`.
- DevTools on the `/kyc` page → `permissions-policy:
  camera=(self), microphone=(self)` in response headers.
- On an Android device, complete the Identomat KYC flow;
  the camera prompt appears and the liveness check completes
  without `NotAllowedError`.
- On the WASM chart sub-domain, run
  `self.crossOriginIsolated` in DevTools console → `true`.
  On the main app domain → `false`.
- Pick one Pages Function route (e.g. `/api/health`);
  confirm its response includes HSTS and CSP in DevTools —
  these come from the Function, not from `_headers`.

## Related

- `documentation/docs/policies/cloudflare/pages-headers-config.md`
- `documentation/docs/policies/cloudflare/csp-headers-and-cf-waf.md`
- `documentation/docs/policies/cloudflare/cors-pages-functions.md`
- `documentation/docs/policies/cloudflare/pages-functions-middleware.md`
- `documentation/docs/policies/security/permissions-policy-header.md`

## Source URLs (verified 2026-08-17)

- Cloudflare Pages headers — https://developers.cloudflare.com/pages/configuration/headers/
- Cloudflare Pages limits — https://developers.cloudflare.com/pages/platform/limits/
- Next.js CSP guide — https://nextjs.org/docs/app/guides/content-security-policy
- Next.js static CSP discussion — https://github.com/vercel/next.js/discussions/44907
- MDN Permissions-Policy: camera — https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/camera
- Cross-origin isolation with COOP/COEP — https://web.dev/articles/coop-coep
- COOP restrict-properties (Chrome blog) — https://developer.chrome.com/blog/coop-restrict-properties
- SharedArrayBuffer updates in Chrome — https://developer.chrome.com/blog/enabling-shared-array-buffer
- Cloudflare Pages caching guide — https://randombits.dev/articles/tips/cloudflare-pages-caching
