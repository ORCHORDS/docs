# Edge Middleware for i18n Locale Routing on Cloudflare Pages

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

An app serves content in multiple languages. Locale detection and URL rewriting must happen before the HTML is returned so that crawlers index the correct `hreflang` URLs and users land on their preferred locale without a client-side redirect flash.

## Context

Cloudflare Pages Functions support a `_middleware.ts` file that runs at the edge on every request. This middleware can inspect the `Accept-Language` header, read a locale cookie, and rewrite or redirect the request to the correct locale prefix (`/en/`, `/fr/`, `/ja/`) before the static asset or SSR function responds. Running this logic at the edge avoids a round-trip to the origin and eliminates the blank-page flash caused by client-side locale detection.

## Defining Supported Locales

```typescript
// lib/i18n.ts
export type Locale = "en" | "fr" | "de" | "ja";

export const SUPPORTED_LOCALES: Locale[] = ["en", "fr", "de", "ja"];
export const DEFAULT_LOCALE: Locale = "en";

export function isSupportedLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as string[]).includes(value);
}

export function extractLocaleFromPath(pathname: string): Locale | null {
  const segment = pathname.split("/")[1] ?? "";
  return isSupportedLocale(segment) ? segment : null;
}

export function negotiateLocale(acceptLanguage: string): Locale {
  // Parse quality-weighted Accept-Language header
  const tags = acceptLanguage
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { tag: tag.trim().toLowerCase(), q: parseFloat(q ?? "1") };
    })
    .sort((a, b) => b.q - a.q);

  for (const { tag } of tags) {
    const lang = tag.split("-")[0] as Locale;
    if (isSupportedLocale(lang)) return lang;
  }

  return DEFAULT_LOCALE;
}
```

## Writing the Middleware

```typescript
// functions/_middleware.ts
import {
  extractLocaleFromPath,
  negotiateLocale,
  DEFAULT_LOCALE,
  isSupportedLocale,
} from "../lib/i18n";

const LOCALE_COOKIE = "preferred_locale";
const PUBLIC_PATHS = ["/api/", "/_next/", "/static/", "/favicon.ico"];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname.startsWith(p));
}

export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);

  // Skip locale logic for static assets and API routes
  if (isPublicPath(url.pathname)) return context.next();

  const pathLocale = extractLocaleFromPath(url.pathname);

  if (pathLocale) {
    // Already routed — persist preference and continue
    const response = await context.next();
    const headers = new Headers(response.headers);
    headers.append(
      "Set-Cookie",
      `${LOCALE_COOKIE}=${pathLocale}; Path=/; Max-Age=31536000; SameSite=Lax`
    );
    return new Response(response.body, { ...response, headers });
  }

  // Detect preferred locale
  const cookieHeader = context.request.headers.get("Cookie") ?? "";
  const cookieLocale = cookieHeader.match(
    new RegExp(`${LOCALE_COOKIE}=([^;]+)`)
  )?.[1];

  const acceptLanguage =
    context.request.headers.get("Accept-Language") ?? DEFAULT_LOCALE;

  const locale =
    (isSupportedLocale(cookieLocale ?? "") ? cookieLocale : null) ??
    negotiateLocale(acceptLanguage);

  // Redirect root to locale-prefixed URL
  const target = new URL(url);
  target.pathname = `/${locale}${url.pathname === "/" ? "" : url.pathname}`;

  return Response.redirect(target.toString(), 307);
};
```

## Serving Locale-Specific Static Pages

With Cloudflare Pages static export, locale pages live at `/en/`, `/fr/`, etc. The middleware handles detection; the static file system handles serving.

```
public/
  en/
    index.html
    about/index.html
  fr/
    index.html
    about/index.html
  de/
    index.html
```

```typescript
// functions/[locale]/[[path]].ts — fallback SSR for dynamic pages
import type { Locale } from "../../lib/i18n";
import { isSupportedLocale } from "../../lib/i18n";

interface Env {
  ASSETS: Fetcher;
  TRANSLATIONS_KV: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const { locale } = context.params as { locale: string };

  if (!isSupportedLocale(locale)) {
    return new Response("Not Found", { status: 404 });
  }

  const t = await context.env.TRANSLATIONS_KV.get<Record<string, string>>(
    locale,
    "json"
  );

  // Forward to static asset, injecting translation metadata via HTMLRewriter
  const assetResponse = await context.env.ASSETS.fetch(context.request);

  return new HTMLRewriter()
    .on("html", {
      element(el) {
        el.setAttribute("lang", locale);
      },
    })
    .on("head", {
      element(el) {
        // Inject hreflang alternate links
        const locales: Locale[] = ["en", "fr", "de", "ja"];
        const url = new URL(context.request.url);
        const rest = url.pathname.replace(`/${locale}`, "") || "/";
        for (const l of locales) {
          el.append(
            `<link rel="alternate" hreflang="${l}" href="https://${url.host}/${l}${rest}" />`,
            { html: true }
          );
        }
      },
    })
    .transform(assetResponse);
};
```

## Client-Side Locale Switcher

```tsx
// src/components/LocaleSwitcher.tsx
import type { Locale } from "@/lib/i18n";
import { SUPPORTED_LOCALES } from "@/lib/i18n";

const LABELS: Record<Locale, string> = {
  en: "English",
  fr: "Français",
  de: "Deutsch",
  ja: "日本語",
};

interface LocaleSwitcherProps {
  current: Locale;
  path: string; // current path without locale prefix, e.g. "/about"
}

export function LocaleSwitcher({ current, path }: LocaleSwitcherProps) {
  return (
    <nav aria-label="Language selector">
      <ul role="list">
        {SUPPORTED_LOCALES.map((locale) => (
          <li key={locale}>
            <a
              href={`/${locale}${path}`}
              hrefLang={locale}
              aria-current={locale === current ? "true" : undefined}
              lang={locale}
            >
              {LABELS[locale]}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

## Caching Locale Responses at the Edge

Locale-specific HTML pages should be cached separately per locale. Use `Vary` or a cache key transformation.

```typescript
// functions/_middleware.ts (cache key addition, append after locale redirect block)
async function withLocaleCache(
  response: Response,
  locale: string
): Promise<Response> {
  const headers = new Headers(response.headers);
  // Vary on Accept-Language so Cloudflare caches per language
  headers.append("Vary", "Accept-Language");
  // Cache for 5 minutes; stale-while-revalidate for 1 hour
  headers.set(
    "Cache-Control",
    "public, max-age=300, stale-while-revalidate=3600"
  );
  headers.set("X-Detected-Locale", locale);
  return new Response(response.body, { ...response, headers });
}
```

## Anti-patterns

- Storing locale in the URL hash (`/#en`) — crawlers do not index fragment-routed content
- Doing locale detection entirely in client-side JavaScript — causes a flash of un-localised content and hurts SEO
- Redirecting with 301 (permanent) during negotiation — users who change browser language are stuck with the cached redirect
- Using `Accept-Language` as the sole source of truth without a cookie fallback — users lose their manual locale choice on every visit

## Gotchas

- `Response.redirect()` in Pages Functions returns a 307; ensure the target URL includes the trailing slash if your static export requires it
- Cloudflare caches responses keyed by URL by default; without `Vary: Accept-Language` two users with different languages may receive the same locale
- The `Set-Cookie` header on a 307 redirect is not sent by all browsers — set the cookie on the first successful locale response instead
- Workers `isSupportedLocale` type guard requires the input to be typed as `string`, not `string | undefined`; normalise before calling

## Verification

1. `curl -H "Accept-Language: fr,en;q=0.8" https://<project>.pages.dev/` should redirect to `/fr/`.
2. `curl -H "Cookie: preferred_locale=de" https://<project>.pages.dev/about` should redirect to `/de/about`.
3. Check the `<html lang>` attribute and `<link rel="alternate" hreflang>` tags in the rendered HTML.
4. Run `npx hreflang-validator https://<project>.pages.dev/en/` to audit alternate link correctness.

## Related

- [i18n-internationalization-architecture.md](i18n-internationalization-architecture.md)
- [dark-mode-edge-cookie-cloudflare-pages.md](dark-mode-edge-cookie-cloudflare-pages.md)
- [feature-flags-cloudflare-workers-kv-edge-config.md](feature-flags-cloudflare-workers-kv-edge-config.md)
- nextjs-middleware-patterns.md

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
- https://developers.google.com/search/docs/specialty/international/localized-versions
- https://www.rfc-editor.org/rfc/rfc4647 (Matching of Language Tags)
