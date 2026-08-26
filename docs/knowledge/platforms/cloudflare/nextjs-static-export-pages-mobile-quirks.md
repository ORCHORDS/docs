# Next.js Static Export on Cloudflare Pages — Mobile Quirks

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A Next.js app built with `output: 'export'` works on desktop and
in `next dev`. On mobile, users arriving via share link, push
notification, or bookmark hit a raw 404 on routes that work fine
through client-side navigation. On mid-range Android phones on
cellular the page also flickers text, swaps fonts mid-render, or
logs hydration warnings that never appear on desktop.

## Context

`output: 'export'` tells Next.js to emit one HTML file per known
route into `out/` — no Node.js runtime. Cloudflare Pages serves
that directory as a CDN. The absence of a server is what strands
mobile direct-URL loads: Pages has nothing to fall back to, so
unmatched paths return 404. Mobile-specific issues pile on: slow
CPUs expose Suspense races, cellular networks amplify font FOUT,
Smart Placement can route asset requests away from the user, and
Rocket Loader — if enabled — reorders Next.js's dependency-ordered
scripts.

## `_next/static/` caching vs root HTML

Next.js fingerprints every JS chunk, CSS file, and font under
`_next/static/` with a content hash in the filename — safe to
cache permanently. Root HTML files carry no hash and must not
survive a redeploy. Without an explicit `_headers` file,
Cloudflare may cache stale HTML while fresh hashed chunks are
already live; returning mobile users see hydration panics because
the old HTML references filenames that no longer exist.

```
# out/_headers

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable

/*.html
  Cache-Control: no-cache, no-store, must-revalidate

/
  Cache-Control: no-cache, no-store, must-revalidate
```

## SPA routing: `_redirects` and `404.html`

`output: 'export'` writes the literal file `out/post/[slug].html`
for a dynamic segment — not one file per slug value. A mobile
user opening `/post/hello-world` from a notification gets a 404
because that filename does not exist on disk.

Fix with `_redirects` placed inside the output directory (`out/`):

```
# out/_redirects

# Rewrite dynamic routes to the bracket-named file
/post/*    /post/[slug].html    200

# Catch-all SPA fallback — MUST be the last rule
/*         /index.html          200
```

Status `200` is a URL-preserving rewrite, not a redirect. Pages
evaluates rules top-to-bottom and stops at first match; the
catch-all must be last.

Also add `app/not-found.tsx` (App Router) or `pages/404.tsx`
(Pages Router) so `next build` emits `out/404.html`. This covers
users whose mobile OS cached a 404 response before `_redirects`
was deployed, and slugs that `generateStaticParams` missed.

```
out/
├── _redirects        ← inside distDir, not repo root
├── 404.html
├── index.html
└── post/
    └── [slug].html
```

## Suspense hydration on slow mobile CPUs

On desktop, React hydration finishes in a few milliseconds. On a
mid-range Android under cellular (roughly 4× CPU slowdown),
hydration of a full-weight bundle can take 400–1 200 ms. Any
Suspense boundary that resolves to a different tree than the
server-rendered shell during that window causes React to discard
SSR HTML and re-render from scratch — a visible white flash.

Common mismatches in a static export:

```
Pattern                           Result on slow mobile
────────────────────────────────────────────────────────
typeof window outside useEffect   Server=false, client=true
Math.random() in JSX render       Diverges on every load
Date formatted client-side only   Mismatch on non-UTC locales
<ClientOnlyIsland/> in Suspense   Spinner flash before resolve
────────────────────────────────────────────────────────
```

Fixes: move `typeof window` guards into `useEffect` or use
`dynamic(Component, { ssr: false })`; use `useId()` for
deterministic IDs; pin date formatting to an explicit `timeZone`;
give Suspense fallbacks content-shaped skeletons, not spinners.

## Font FOUT on mobile networks

`next/font` bakes font files into `_next/static/media/` at build
time. On cellular the font file arrives in a separate connection
100–300 ms after the HTML, causing a flash of unstyled text even
with `font-display: swap`.

```ts
import { Inter } from 'next/font/google';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',      // visible text while font loads; FOUT risk
  preload: true,        // <link rel="preload"> fired during parse
  fallback: ['system-ui'],  // metric-adjusted via CSS size-adjust
});
```

`preload: true` fires the font fetch in parallel with HTML parse,
cutting the gap. `next/font` applies `size-adjust` automatically
so the fallback occupies the same space. Restrict preloaded
subsets to above-the-fold text; preloading unused subsets competes
with critical JS on narrow connections.

## Smart Placement and mobile static asset latency

Smart Placement moves Pages Functions (compute) closer to a
back-end database. Static assets are always served from the edge
DC nearest to the user — Smart Placement does not move them.
The mobile risk appears when a Function wraps asset delivery:

```
Setup                              Asset served from
──────────────────────────────────────────────────────────
Pure static export, no Functions   Nearest edge DC — fastest

Middleware on /* + Smart           Middleware DC (may be in a
Placement enabled                  different continent from user)

Function calling                   Function's placed DC, not the
env.ASSETS.fetch()                 user's nearest edge
──────────────────────────────────────────────────────────
```

For a static-only export, do not enable Smart Placement. If a
thin auth Function is required, serve assets via `_redirects`
rewrites rather than via `env.ASSETS.fetch()` inside the Function.

## Rocket Loader — hydration ordering breakage

Rocket Loader rewrites `<script>` tags to
`type="xxxxx-text/javascript"` and re-executes them via its CDN
loader after paint. On a slow mobile CPU the reordering breaks the
assumption that React's root bundle runs after its chunk
dependencies — producing `Minified React error #130` or silently
corrupted component trees. Rocket Loader also injects an inline
script that invalidates CSP nonces.

Detect rewriting:

```bash
curl -sA "Mozilla/5.0 (Linux; Android 13)" \
  https://yourdomain.pages.dev/ \
  | grep -o 'rocket-loader\|xxxxx-text\|data-cfasync'
```

Any match means Rocket Loader is active. Disable it:
`Speed → Optimization → Rocket Loader: OFF`.

If the zone cannot be changed globally, exempt the hydration
entry point (must be in origin HTML, not injected at runtime):

```html
<script data-cfasync="false"
        ></script>
```

## Anti-patterns

- **Relying on client-side navigation to mask the 404 problem** —
  mobile notification taps open a fresh tab with no router state.
- **Caching HTML with long TTLs** — stale HTML referencing new
  chunk hashes produces hydration panics on returning mobile users.
- **Placing `_redirects` in the repo root** — it must be inside
  the Pages output directory (`out/`). Silently ignored elsewhere.
- **Calling `env.ASSETS.fetch()` inside a Function for all
  routes** — routes asset delivery through the Function's DC,
  adding intercontinental RTTs for mobile users near other colos.
- **Testing mobile routing via DevTools emulation** — emulation
  shares navigation state with desktop. Direct-URL 404s only
  reproduce in a cold incognito tab, the same context as a
  notification tap.

## Gotchas

- **`_redirects` catch-all must be the last rule** — any rule
  after `/*  /index.html  200` is unreachable.
- **`404.html` and the catch-all serve different purposes** — the
  catch-all is a 200 rewrite; `404.html` fires on a true 404
  with a 404 status. Both are needed for full mobile coverage.
- **Rocket Loader rewrite survives in browser cache** — after
  disabling, run Cloudflare Cache → Purge Everything to evict
  cached pages that still carry the rewritten script tags.

## Verification

- `ls out/_redirects` exits 0 after `next build`; final line is
  `/*  /index.html  200`.
- `curl -sI https://yourdomain.pages.dev/post/hello-world`
  returns `HTTP/2 200` and `content-type: text/html`.
- `GET /zones/:id/settings/rocket_loader` returns `{"value":"off"}`.
- `curl -sI .../index.html | grep cache-control` shows `no-cache`;
  on `/_next/static/chunks/` shows `immutable`.
- Real-device incognito tab (Android + iOS) opens a deep link
  from clipboard — 200, no hydration console errors.
- Lighthouse mobile run (6× CPU, Fast 3G): no console errors,
  LCP font listed as preloaded in the Opportunities panel.

## Related

- `documentation/docs/policies/cloudflare/pages-redirects-config.md`
- `documentation/docs/policies/cloudflare/pages-headers-config.md`
- `documentation/docs/policies/cloudflare/rocket-loader-mirage-mobile-breakage.md`
- `documentation/docs/policies/cloudflare/smart-placement-best-practices.md`
- `documentation/docs/policies/cloudflare/http3-quic-mobile-network-irregularities.md`

## Source URLs (verified 2026-08-17)

- Next.js static exports guide —
  https://nextjs.org/docs/pages/guides/static-exports
- Deploy a static Next.js site on Cloudflare Pages —
  https://developers.cloudflare.com/pages/framework-guides/nextjs/deploy-a-static-nextjs-site/
- Cloudflare Pages routing and SPA fallback —
  https://developers.cloudflare.com/pages/functions/routing/
- Cloudflare Pages Smart Placement —
  https://developers.cloudflare.com/pages/functions/smart-placement/
- Cloudflare Rocket Loader —
  https://developers.cloudflare.com/speed/optimization/content/rocket-loader/
- Cloudflare static site generation / 404 handling —
  https://developers.cloudflare.com/workers/static-assets/routing/static-site-generation/
