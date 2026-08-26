# Next.js Static Export Routing on Cloudflare Pages

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

After deploying a Next.js app with `output: 'export'` to
Cloudflare Pages, navigating directly to a path such as
`/feed/123` or `/profile/settings` returns a 404 from the
CDN edge node. The root `/` loads correctly. On mobile,
deep links opened from push notifications or share sheets
also 404 — the user lands on an error page instead of the
intended content. Client-side navigation (clicking `<Link>`
components) works fine once the app is loaded.

## Context

`output: 'export'` turns Next.js into a pure static site
generator: it emits an `out/` directory of `.html` files,
`.js` chunks, and assets. There is no Node.js server, no
middleware runtime, and no Next.js edge runtime. Cloudflare
Pages hosts the `out/` folder verbatim and serves files by
exact path match. When a user navigates directly to
`/feed/123`, the CDN looks for `out/feed/123.html` or
`out/feed/123/index.html`. If that file does not exist (e.g.
the route is dynamic), the CDN returns 404.

Cloudflare Pages has two mechanisms to fix this: a
`_redirects` file for SPA-style fallback routing and a
`_headers` file for response headers. Neither is generated
by Next.js — they must be placed manually in the `public/`
directory so the build copies them into `out/`.

## Static vs dynamic routes in the exported output

```
Route type           next.config.js                 File emitted
─────────────────────────────────────────────────────────────────────
Static segment       /about                         out/about.html
                                                    out/about/index.html
                                                    (depends on
                                                    trailingSlash)

Dynamic + SSG        /feed/[id] with                out/feed/1.html
(generateStatic      generateStaticParams()         out/feed/2.html
Params)              returns [{id:'1'},{id:'2'}]    …one file per id

Dynamic (no SSG)     /feed/[id] with no             FILE MISSING —
                     generateStaticParams()         causes 404 at edge

Catch-all            /[...slug]                     Only files from
                                                    generateStaticParams
                                                    are emitted
─────────────────────────────────────────────────────────────────────
```

Every route that is not pre-rendered at build time must be
handled by the SPA fallback redirect — the browser gets
`index.html`, React hydrates, and Next.js router resolves
the path client-side.

## _redirects file for SPA fallback

Create `public/_redirects`. Cloudflare Pages reads this file
from the root of the deployment and applies the rules in
order, top to bottom, first match wins.

```
# public/_redirects

# Preserve hard-coded 404 page (do not rewrite to /)
/404        /404.html   200

# Pass asset requests straight through — no rewrite needed
# (Cloudflare Pages matches file-first before _redirects)

# SPA fallback: rewrite all unmatched paths to index.html
/*          /index.html 200
```

The `200` status code means "serve this file but keep the
original URL in the browser" — a rewrite, not a redirect.
A `301` or `302` would change the URL to `/` and break deep
links.

**File placement in the project:**

```
my-example project-app/
├── public/
│   └── _redirects      ← Copied verbatim into out/ by Next.js
├── src/
│   └── app/
├── next.config.js
└── package.json
```

After `next build`, verify the file exists:
```sh
ls out/_redirects   # must be present
```

## next.config.js settings required for static export

```js
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',

  // Cloudflare Pages serves index.html for directory paths;
  // trailingSlash: true emits /about/index.html which
  // matches more reliably than /about.html under
  // case-sensitive CDN file matching.
  trailingSlash: true,

  // Disable Next.js image optimization — it requires a
  // server. Use Cloudflare Images or a CDN-backed loader.
  images: {
    unoptimized: true,
  },

  // If you need basePath (e.g. deploying to a sub-path):
  // basePath: '/app',
};

module.exports = nextConfig;
```

## Dynamic routes: generateStaticParams

For routes where you know the IDs at build time, supply
them so the pages are pre-rendered as static HTML. This is
always preferable to the SPA fallback — the user gets a
faster first byte with no client-side routing delay.

```ts
// src/app/feed/[id]/page.tsx
export async function generateStaticParams() {
  // Fetch only the IDs you need to pre-render.
  // For example project: top-N content items to pre-render
  // at build time; long tail falls back to SPA render.
  const featuredIds = await fetchFeaturedContentIds();
  return featuredIds.map((id) => ({ id: String(id) }));
}

// Without this export the route is omitted from the
// static export entirely — the _redirects fallback
// then serves index.html for all /feed/* paths and
// the React router handles the ID client-side.
```

## 404 handling

Cloudflare Pages looks for a `404.html` file at the root of
the deployment before falling through to `_redirects`. If
`404.html` exists it is served for any unmatched path with a
404 status — even if `_redirects` has `/* /index.html 200`.
This is the correct behaviour; the `_redirects` rule only
matches paths that have not already been matched by a real
file or the 404.html fallback.

To use a custom Next.js 404 page:

```tsx
// src/app/not-found.tsx (App Router)
export default function NotFound() {
  return (
    <main>
      <h1>404 — Page not found</h1>
    </main>
  );
}
```

Next.js exports this as `out/404.html` automatically.
Cloudflare Pages serves it with a real 404 status code.

```
Path resolution order on Cloudflare Pages
──────────────────────────────────────────
1. Exact file match in the build output
2. Directory index (trailingSlash: true adds index.html)
3. 404.html (served with 404 status)
4. _redirects rules (top to bottom, first match)
5. Default Cloudflare 404 page
──────────────────────────────────────────
```

## Mobile deep link routing issues

Push notifications and share sheets open a URL directly in
the browser — there is no prior navigation that could have
loaded the SPA. On mobile, the OS resolves the URL to the
CDN directly. Common failure modes:

```
Scenario                         Symptom                   Fix
──────────────────────────────────────────────────────────────────
Dynamic route not pre-rendered   404 at CDN edge           _redirects
                                                           SPA fallback

Path with query string           Query stripped by CDN     Verified: CF
  e.g. /invite?code=abc          before routing            Pages passes
                                                           query strings
                                                           through to the
                                                           rewritten file

Hash fragments (#section)        404 on the path           Hash is client-
  e.g. /post/1#comments          before the hash           only; only the
                                                           path matters for
                                                           CDN routing

Case sensitivity                 /Feed/123 != /feed/123   Enforce lowercase
                                 on Cloudflare Pages       paths; add
                                                           redirect rule

Trailing slash mismatch          /feed/123 vs /feed/123/  Set trailingSlash
                                 can serve 404 if file     consistently in
                                 emitted under wrong name  next.config.js
──────────────────────────────────────────────────────────────────
```

For example project, push notification deep links must always use
the canonical path format (lowercase, trailingSlash: true).
Generate notification URLs from a server-side helper that
normalises the path before sending via the push service.

## Cloudflare Pages build configuration

```
Build command:    npx next build
Build output dir: out
Root directory:   (leave blank unless monorepo)
```

If using a monorepo with Turborepo:

```
Build command:    npx turbo run build --filter=example project-web
Build output dir: apps/example project-web/out
Root directory:   (leave blank)
```

## Anti-patterns

- **Omitting `_redirects`** — every dynamic route becomes a
  404 for direct navigation and deep links. The most common
  production bug after deploying a Next.js SPA to CF Pages.
- **Using `/* /index.html 301`** — a redirect changes the
  visible URL to `/`, breaking deep links and history. Always
  use status `200` for an SPA rewrite.
- **Relying on middleware** — `next.config.js` middleware
  (`middleware.ts`) does not execute in a static export.
  There is no server. Route matching must be client-side or
  handled by `_redirects`.
- **Not including `trailingSlash: true`** — inconsistent
  slash handling produces duplicate-content issues and
  occasional 404s depending on how Cloudflare Pages resolves
  the file path vs the redirect rule.
- **Dynamic segments without `generateStaticParams`** —
  the page is silently omitted from the export; the first
  clue is a 404 in production, not a build error.

## Gotchas

- **`_redirects` is Cloudflare Pages syntax**, not the
  Netlify `_redirects` format — they look identical but
  behave slightly differently. Cloudflare Pages does not
  support `!` (negation) or `:splat` placeholders.
- **File-first matching means static assets are never
  rewritten** — `_redirects` `/* /index.html 200` does not
  intercept `/favicon.ico` or `/_next/static/*` because
  those files exist in the output. No asset exclusion rules
  are needed.
- **`output: 'export'` disables several App Router features**
  — server actions, route handlers, ISR, and edge middleware
  all require a server. If any page uses them, `next build`
  fails with a clear error message.
- **`trailingSlash: false` + `_redirects`** — without
  trailing slashes, `out/about.html` is emitted. Cloudflare
  Pages serves `/about` correctly. With trailing slashes,
  `out/about/index.html` is emitted; `/about/` works and
  `/about` is redirected to `/about/` by CF Pages itself.

## Verification

- Direct navigation to a dynamic route path in a fresh
  browser tab serves the correct page (not a 404 or `/`).
- `curl -I https://your-pages-project.pages.dev/feed/123`
  returns `HTTP/2 200` with content-type `text/html`.
- `ls out/_redirects` confirms the file exists after build.
- A push notification link opened on an iOS device lands on
  the intended page, not a 404 or the home page.
- `out/404.html` exists and is served with a 404 status for
  genuinely non-existent paths.

## Related

- `documentation/categories/frontend/cloudflare-pages-headers-csp-mobile.md`
- `documentation/categories/deploy/cloudflare-pages-deployment.md`
- `documentation/categories/frontend/next-js-app-router-patterns.md`
- `documentation/categories/mobile/mobile-deep-link-routing.md`
- `documentation/categories/frontend/next-js-middleware-patterns.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Pages — Redirects —
  https://developers.cloudflare.com/pages/configuration/redirects/
- Next.js — Static Exports —
  https://nextjs.org/docs/app/building-your-application/deploying/static-exports
- Next.js — generateStaticParams —
  https://nextjs.org/docs/app/api-reference/functions/generate-static-params
- Cloudflare Pages — Build configuration —
  https://developers.cloudflare.com/pages/configuration/build-configuration/
