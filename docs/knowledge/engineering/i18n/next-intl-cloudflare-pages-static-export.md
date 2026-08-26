# next-intl-cloudflare-pages-static-export

**Issue:** A Next.js project using `next-intl` is deployed to
Cloudflare Pages as a static export (`output: 'export'`). The
standard `next-intl` setup requires a middleware file for locale
detection and redirect, but Next.js middleware does not run during
static export — the build silently drops the middleware and all
locale detection stops working. Users land on the default locale
regardless of their browser's `Accept-Language` header.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
warn  - Statically exporting a Next.js application via `next export`
        disables API routes and other dynamic features.
        middleware.ts is not included in the static export.
```

After deploying, `https://example.pages.dev/` always shows English
even for French or Arabic browser sessions. Direct navigation to
`/fr/about` works, but no automatic redirect or detection fires.
The locale switcher works, but only after the user has manually
navigated once.

## Context

Next.js `output: 'export'` generates a fully static site with no
server-side execution. Cloudflare Pages serves static exports without
invoking any Next.js runtime. This means:

- `middleware.ts` is silently excluded from the export output
- `next-intl`'s `createMiddleware()` is never called
- `getRequestConfig` runs at build time only, not at request time
- Server Components' locale detection relies on middleware headers
  that never arrive

The workaround is a two-part strategy: (1) use static locale param
generation to pre-render every page in every locale at build time,
and (2) use a lightweight client-side or Cloudflare Pages Function
redirect to send users to their locale on first visit.

## next.config.js for static export with next-intl

```js
// next.config.mjs
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin(
  "./src/i18n/request.ts"
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",        // static export — no middleware
  trailingSlash: true,     // Cloudflare Pages needs this for /fr/about/
  images: {
    unoptimized: true,     // next/image optimization requires a server
  },
};

export default withNextIntl(nextConfig);
```

```ts
// src/i18n/request.ts
import { getRequestConfig } from "next-intl/server";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  // In static export, requestLocale comes from the [locale] segment
  // in the URL, not from a middleware header.
  let locale = await requestLocale;
  if (!locale || !routing.locales.includes(locale as any)) {
    locale = routing.defaultLocale;
  }
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
```

## Locale prefix routing without middleware

Define the routing object with `localePrefixMode: 'always'` so every
locale, including the default, gets a prefix. This makes the static
file structure unambiguous — `/en/`, `/fr/`, `/ar/` each map to their
own directory in the export output.

```ts
// src/i18n/routing.ts
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "fr", "ar", "de", "ja"],
  defaultLocale: "en",
  localePrefix: "always",   // /en/about, /fr/about — never /about
});
```

`localePrefix: 'as-needed'` (the middleware default) puts the default
locale at `/` with no prefix. In a static export, that means
`/about/index.html` conflicts with `/en/about/index.html` depending
on the static file router's behavior. Use `'always'` to avoid the
ambiguity.

## Static locale params generation

Every page under `app/[locale]/` must export `generateStaticParams`
returning all locales. Without this, Next.js only generates the
default locale's pages.

```ts
// app/[locale]/layout.tsx
import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}
// This causes Next.js to call generateStaticParams for each locale
// and pre-render: /en/, /fr/, /ar/, /de/, /ja/ at build time.
```

For nested dynamic routes, compose both:

```ts
// app/[locale]/blog/[slug]/page.tsx
export async function generateStaticParams() {
  const posts = await fetchAllPosts(); // called once per build
  const paths: { locale: string; slug: string }[] = [];
  for (const locale of routing.locales) {
    for (const post of posts) {
      paths.push({ locale, slug: post.slug });
    }
  }
  return paths;
}
```

Build time is O(locales × pages); a 5-locale site with 200 blog posts
generates 1000 HTML files. Budget accordingly in CI.

## Locale detection without middleware

Two options for detecting the user's locale on their first visit:

**Option A — Cloudflare Pages Functions (recommended)**

A `functions/_middleware.ts` at the Pages project root runs as a
Cloudflare Worker; it can read `Accept-Language` and redirect:

```ts
// functions/_middleware.ts
import type { PagesFunction } from "@cloudflare/workers-types";

const LOCALES = ["en", "fr", "ar", "de", "ja"] as const;
const DEFAULT = "en";

function detectLocale(request: Request): string {
  const header = request.headers.get("Accept-Language") ?? "";
  const preferred = header.split(",")[0]?.split("-")[0]?.trim() ?? "";
  return LOCALES.includes(preferred as any) ? preferred : DEFAULT;
}

export const onRequest: PagesFunction = async ({ request, next }) => {
  const url = new URL(request.url);
  const isLocaleRoute = LOCALES.some(
    (l) => url.pathname === `/${l}` || url.pathname.startsWith(`/${l}/`)
  );
  if (!isLocaleRoute && url.pathname === "/") {
    const locale = detectLocale(request);
    return Response.redirect(`${url.origin}/${locale}/`, 302);
  }
  return next();
};
```

**Option B — client-side redirect (fallback)**

Add a thin `app/page.tsx` at the root that redirects in the browser:

```tsx
// app/page.tsx  (only rendered for the bare / route)
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { routing } from "@/i18n/routing";

export default function RootPage() {
  const router = useRouter();
  useEffect(() => {
    const lang = navigator.language.split("-")[0];
    const locale = routing.locales.includes(lang as any)
      ? lang
      : routing.defaultLocale;
    router.replace(`/${locale}/`);
  }, [router]);
  return null;
}
```

Client-side redirect adds a flash and is not SEO-friendly; prefer
the Pages Function when the project uses Pages.

## Locale switcher in static export

```tsx
// components/LocaleSwitcher.tsx
import Link from "next/link";
import { useLocale } from "next-intl";
import { routing } from "@/i18n/routing";

export function LocaleSwitcher() {
  const currentLocale = useLocale();
  return (
    <nav aria-label="Language">
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href={`/${locale}/`}  // hard path, not next-intl Link — no router in static export
          hrefLang={locale}
          aria-current={locale === currentLocale ? "true" : undefined}
        >
          {locale.toUpperCase()}
        </Link>
      ))}
    </nav>
  );
}
```

Use a plain `<Link >` rather than `next-intl`'s
`<Link>` component when `output: 'export'` is set — the intl Link
relies on the middleware-set cookie for locale, which does not exist
in the static export context.

## Anti-patterns

- **`localePrefix: 'as-needed'` with static export** — the default
  locale generates `/index.html` and the prefixed locale generates
  `/en/index.html`; Cloudflare Pages serves `/` from the root, making
  language negotiation impossible without a redirect layer.
- **Putting locale detection in `getRequestConfig`** — this function
  runs at build time in static export, not at request time; any
  `Accept-Language` header reading silently returns `undefined`.
- **Using `next-intl`'s `<Link>` for locale switching** — it requires
  the locale to be set via middleware cookie; use native `<Link href>`
  with explicit locale path instead.
- **`images.unoptimized: false`** — Next.js image optimization
  requires a server; it causes a build error in static export mode.

## Gotchas

- `trailingSlash: true` is required for Cloudflare Pages to serve
  `/fr/about/` from `fr/about/index.html`; without it, navigating to
  `/fr/about` returns a 404 because Pages looks for `fr/about.html`.
- The Pages Function `_middleware.ts` only runs when deployed; local
  `wrangler pages dev` must have the `functions/` directory in its
  project root. Running `next dev` locally does not invoke it at all
  — test locale redirect with `wrangler pages dev ./out`.
- Locale cookie set by `next-intl` middleware in non-export mode is
  called `NEXT_LOCALE`; in static export, this cookie is never set,
  so any component reading `cookies().get('NEXT_LOCALE')` returns
  `undefined` — remove such calls.
- Arabic (`ar`) and Hebrew (`he`) require `dir="rtl"` on the `<html>`
  element; set it in the `[locale]/layout.tsx` based on the locale
  param, not via middleware headers.

## Verification

```bash
# Build and inspect output structure
pnpm next build
ls out/
# Expected: en/  fr/  ar/  de/  ja/  (no bare /about directory)

# Serve locally with wrangler to test Pages Function
wrangler pages dev ./out --compatibility-date=2024-04-04
curl -H "Accept-Language: fr,en;q=0.9" http://localhost:8788/
# Expected: HTTP 302 → /fr/

# Confirm all locale pages exist
for locale in en fr ar de ja; do
  test -f out/$locale/index.html && echo "$locale OK" || echo "$locale MISSING"
done
```

## Related

- `documentation/docs/policies/i18n/next-js-app-router-i18n.md`
- `documentation/docs/policies/i18n/hreflang-seo-2026.md`
- `documentation/docs/policies/i18n/locale-detection-browser.md`
- `documentation/docs/policies/i18n/bidi-rtl-layout-css.md`
- `documentation/docs/policies/devtools/typescript-cloudflare-workers-strict.md`

## Sources

- https://next-intl-docs.vercel.app/docs/getting-started/app-router/without-i18n-routing
- https://nextjs.org/docs/pages/building-your-application/deploying/static-exports
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/framework-guides/nextjs/ssr/get-started/
