# next-static-export-pages

**Issue:** `next build` static export for CF Pages
**Date:** 2026-08-09
**Status:** documented

## Symptom
`next build` succeeds. You deploy to CF Pages. The page loads,
but every route returns 404. Or: the home page loads but locale
routes (`/de/`, `/fr/`, `/ar/`) all 404.

## Root cause
CF Pages serves files from the `pages_build_output_dir` (default
`./out`). `next build` for static export generates that
directory. But:
- **`next.config.js` may not have `output: 'export'`** — without
  it, `next build` produces a Node.js server, not static files.
- **Dynamic routes with `getServerSideProps`** can't be statically
  exported. Use `getStaticProps` or `getStaticPaths` instead.
- **Locale routes in Next.js i18n** need extra config to be
  statically exported.

**Source:** Next.js static export docs:
https://nextjs.org/docs/app/building-your-application/deploying/static-exports

> "Static HTML export ... does not support features that require
> a server. This includes ... API routes, getServerSideProps,
> Middleware."

## Fix
For a Next.js + i18n + CF Pages app:

### `next.config.js`
```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',  // REQUIRED for CF Pages static export
  trailingSlash: true,  // /about/ not /about
  images: {
    unoptimized: true,  // CF Pages doesn't support next/image optimization
  },
  // i18n config
  i18n: {
    locales: ['en', 'zh-CN', 'zh-TW', 'ja', 'ko', 'ar', 'es', 'fr', 'de', 'ru', 'pt', 'it', 'tr', 'vi', 'id', 'hi', 'pa', 'fa'],
    defaultLocale: 'en',
    localeDetection: false,  // we use middleware instead
  },
};

module.exports = nextConfig;
```

### Build command
```bash
pnpm build
# Outputs to apps/web/out/ (the default for `output: 'export'`)
```

### Locale-aware routing

With `output: 'export'`, you can't use Next.js middleware
(runs on server). Use:
- **Per-locale folder** in the `app/` directory (e.g.
  `app/[lang]/page.tsx`)
- **OR** `_redirects` in `apps/web/public/_redirects`:
  ```
  /de/* /de/:splat 200
  /fr/* /fr/:splat 200
  # ... for each locale
  ```

The `200` keeps the URL stable (the user's locale is preserved
on refresh). Without `_redirects`, CF Pages won't know that
`/de/about` is a static file in `out/de/about/index.html`.

### What works + doesn't

✅ Works in static export:
- React Server Components (RSC)
- `getStaticProps` / `getStaticPaths`
- `next/image` (unoptimized)
- `next/link` (client-side nav)
- Static metadata
- `app/` directory (App Router)

❌ Doesn't work:
- API routes (`app/api/*`) → use CF Pages Functions instead
- `getServerSideProps` → use CF Pages Functions
- Middleware → use CF Pages `_redirects` or Functions
- ISR / on-demand revalidation → use CF Workers + KV

### Build output structure
```
out/
  index.html
  about/index.html
  de/
    index.html
    about/index.html
  fr/
    index.html
  ...
  _next/
    static/
      chunks/...
  favicon.ico
```

## Verification
- **Test:** `pnpm build` produces `out/` with HTML files
- **Test:** `pnpm --filter web preview` serves the static files
  locally
- **Live:** All 20 locale root paths return 200 + translated HTML

## Gotchas
- **Don't use `next/image` with `unoptimized: false`.** CF Pages
  doesn't support the Next.js image optimizer. Either disable
  optimization or use a CF Image Resizing worker.
- **The `app/` directory supports RSC, but client components**
  need `"use client"` at the top. Server-only code (Node.js APIs)
  breaks the build.
- **For CF Workers Functions** (separate from Pages), use
  `next build` for the static part + a separate `wrangler` build
  for the worker.
- **The output dir must contain `index.html` at the root** for
  CF Pages to serve the homepage. If it's somewhere else, set
  `pages_build_output_dir` in `wrangler.toml`.

## Related
- Next.js static export: https://nextjs.org/docs/app/building-your-application/deploying/static-exports
- CF Pages + Next.js: https://developers.cloudflare.com/pages/framework-guides/nextjs/
