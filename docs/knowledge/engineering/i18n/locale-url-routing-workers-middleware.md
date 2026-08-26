# Locale-Aware URL Routing with Cloudflare Workers Middleware

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You are building a multilingual application on Cloudflare Pages or Workers and need to:

- Route `/fr/produits` to the French version of `/products`
- Redirect `/products` to `/en/products` for English-browser users
- Serve `es.example.com` from the same Worker as `en.example.com`
- Persist the user's locale choice in a cookie so repeat visits skip the redirect
- Return the correct `Vary` and `Content-Language` headers downstream

All of this must run at the edge before hitting any origin, with sub-millisecond overhead.

---

## Context

Cloudflare Workers runs before your origin. A single `fetch` event handler can inspect every request, modify headers, rewrite URLs, or return cached responses. There is no framework middleware chain in the Node.js sense; instead you compose functions that transform `Request` objects and pass them through.

Three URL localization strategies exist:

| Strategy | Example | Pros | Cons |
|---|---|---|---|
| **Path prefix** | `/fr/products` | Works on same domain, SEO-friendly | Requires path rewriting in every link |
| **Subdomain** | `fr.example.com` | Clean separation, easy CDN split | Requires wildcard DNS + TLS cert |
| **Query param** | `/products?lang=fr` | Zero routing changes | Not SEO-friendly, ugly URLs |

This article focuses on the path-prefix strategy because it is the most common Cloudflare Pages pattern and the most nuanced to implement correctly.

---

## Step 1: Locale Detection Priority Chain

```typescript
// src/middleware/locale-detect.ts

export type LocaleSource = 'path' | 'cookie' | 'accept-language' | 'default';

export interface LocaleResult {
  locale: string;
  source: LocaleSource;
}

const SUPPORTED_LOCALES = ['en', 'fr', 'de', 'ja', 'ar', 'pl'] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const DEFAULT_LOCALE: SupportedLocale = 'en';

/**
 * Detect locale from the request using the priority chain:
 *  1. Path segment  (/fr/...)
 *  2. __locale cookie
 *  3. Accept-Language header
 *  4. Default
 */
export function detectLocale(request: Request): LocaleResult {
  const url = new URL(request.url);

  // 1. Path segment
  const [, maybeLocale] = url.pathname.split('/');
  if (maybeLocale && isSupportedLocale(maybeLocale)) {
    return { locale: maybeLocale, source: 'path' };
  }

  // 2. Cookie
  const cookieLocale = getCookieLocale(request);
  if (cookieLocale) {
    return { locale: cookieLocale, source: 'cookie' };
  }

  // 3. Accept-Language
  const headerLocale = negotiateFromAcceptLanguage(
    request.headers.get('Accept-Language') ?? '',
    SUPPORTED_LOCALES as unknown as string[]
  );
  if (headerLocale) {
    return { locale: headerLocale, source: 'accept-language' };
  }

  // 4. Default
  return { locale: DEFAULT_LOCALE, source: 'default' };
}

function isSupportedLocale(s: string): s is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(s);
}

function getCookieLocale(request: Request): SupportedLocale | null {
  const cookie = request.headers.get('Cookie') ?? '';
  const match  = cookie.match(/(?:^|;\s*)__locale=([^;]+)/);
  if (!match) return null;
  const value = decodeURIComponent(match[1]);
  return isSupportedLocale(value) ? value : null;
}

/**
 * Parse Accept-Language and return the best-matching supported locale.
 * Handles q-values, wildcards, and region subtags.
 */
export function negotiateFromAcceptLanguage(
  header: string,
  supported: string[]
): string | null {
  if (!header) return null;

  const entries = header
    .split(',')
    .map((entry) => {
      const [tag, q] = entry.trim().split(';q=');
      return {
        tag:     tag.trim().toLowerCase(),
        quality: q ? parseFloat(q) : 1.0,
      };
    })
    .sort((a, b) => b.quality - a.quality);

  for (const { tag } of entries) {
    // Exact match: 'fr-CA' in supported
    if (supported.includes(tag)) return tag;
    // Base language match: 'fr-CA' → 'fr' in supported
    const base = tag.split('-')[0];
    if (supported.includes(base)) return base;
    // Wildcard
    if (tag === '*') return supported[0] ?? null;
  }

  return null;
}
```

---

## Step 2: Path Rewriting Middleware

```typescript
// src/middleware/locale-router.ts
import { detectLocale } from './locale-detect';

export interface RoutingResult {
  /** The rewritten request to pass downstream */
  request: Request;
  /** The resolved locale (always present) */
  locale: string;
  /** If set, return this Response immediately (a redirect) */
  redirect?: Response;
}

/**
 * Main routing middleware. Call this at the top of your Worker fetch handler.
 *
 *  - Requests with a locale prefix (/fr/...) are rewritten to (/..)
 *    so the origin sees locale-agnostic paths.
 *  - Requests WITHOUT a locale prefix are redirected to the locale prefix.
 */
export function routeByLocale(request: Request): RoutingResult {
  const url    = new URL(request.url);
  const parts  = url.pathname.split('/').filter(Boolean); // ['fr', 'products', 'shoes']
  const first  = parts[0];

  // Case A: URL already has a valid locale prefix → rewrite for origin
  const isLocaled = first && isSupportedLocale(first);
  if (isLocaled) {
    const locale       = first;
    const strippedPath = '/' + parts.slice(1).join('/'); // '/products/shoes'
    const rewrittenUrl = new URL(strippedPath + url.search + url.hash, url.origin);

    return {
      locale,
      request: new Request(rewrittenUrl, request), // preserve method/headers/body
    };
  }

  // Case B: No locale prefix → detect and redirect
  const { locale } = detectLocale(request);
  const redirectUrl = new URL(
    `/${locale}${url.pathname}${url.search}${url.hash}`,
    url.origin
  );

  return {
    locale,
    redirect: Response.redirect(redirectUrl.toString(), 302),
  };
}

function isSupportedLocale(s: string): boolean {
  return ['en', 'fr', 'de', 'ja', 'ar', 'pl'].includes(s);
}
```

---

## Step 3: Cookie Persistence Middleware

```typescript
// src/middleware/locale-cookie.ts

const COOKIE_NAME    = '__locale';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year
const COOKIE_PATH    = '/';

/**
 * Attach a Set-Cookie header to persist the locale on the outgoing response.
 * Only sets the cookie when the locale changed (source !== 'cookie').
 */
export function attachLocaleCookie(
  response: Response,
  locale: string,
  forceUpdate = false
): Response {
  // Don't override if cookie is already correct, unless forced
  if (!forceUpdate) return response;

  const cookieValue =
    `${COOKIE_NAME}=${encodeURIComponent(locale)}; ` +
    `Path=${COOKIE_PATH}; Max-Age=${COOKIE_MAX_AGE}; ` +
    `SameSite=Lax; Secure`;

  const headers = new Headers(response.headers);
  headers.append('Set-Cookie', cookieValue);

  return new Response(response.body, {
    status:     response.status,
    statusText: response.statusText,
    headers,
  });
}
```

---

## Step 4: Content-Language and Vary Headers

```typescript
// src/middleware/i18n-headers.ts

/**
 * Inject i18n-related response headers:
 *  - Content-Language: signals to crawlers and CDNs the language of the body
 *  - Vary: tells caches that the response varies by Accept-Language
 *  - Link: alternate hreflang links for SEO (optional but recommended)
 */
export function addI18nHeaders(
  response: Response,
  locale: string,
  supportedLocales: string[],
  canonicalUrl: URL
): Response {
  const headers = new Headers(response.headers);

  headers.set('Content-Language', locale);

  // Only add Vary if Accept-Language is not already included
  const existingVary = headers.get('Vary') ?? '';
  if (!existingVary.toLowerCase().includes('accept-language')) {
    headers.set('Vary', existingVary ? `${existingVary}, Accept-Language` : 'Accept-Language');
  }

  // Hreflang Link headers (supplement <link> in HTML)
  for (const loc of supportedLocales) {
    const altUrl = new URL(canonicalUrl);
    altUrl.pathname = `/${loc}${canonicalUrl.pathname.replace(/^\/[a-z]{2}(?:-[A-Z]{2})?/, '')}`;
    headers.append('Link', `<${altUrl}>; rel="alternate"; hreflang="${loc}"`);
  }

  return new Response(response.body, {
    status:     response.status,
    statusText: response.statusText,
    headers,
  });
}
```

---

## Step 5: Assembling the Worker

```typescript
// src/index.ts
import { routeByLocale }    from './middleware/locale-router';
import { detectLocale }     from './middleware/locale-detect';
import { attachLocaleCookie } from './middleware/locale-cookie';
import { addI18nHeaders }   from './middleware/i18n-headers';

const SUPPORTED_LOCALES = ['en', 'fr', 'de', 'ja', 'ar', 'pl'];

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Skip middleware for static assets and internal paths
    if (isAssetPath(url.pathname)) {
      return fetch(request);
    }

    // Step 1: Route by locale
    const routing = routeByLocale(request);
    if (routing.redirect) {
      return routing.redirect;
    }

    const { locale, request: rewrittenRequest } = routing;

    // Step 2: Fetch from origin with the rewritten (locale-stripped) path
    let response = await fetch(rewrittenRequest, {
      cf: { cacheTtl: 300 },
    });

    // Step 3: Attach i18n headers
    response = addI18nHeaders(response, locale, SUPPORTED_LOCALES, url);

    // Step 4: Persist locale cookie if it came from Accept-Language or default
    const detection = detectLocale(request);
    const shouldSetCookie = detection.source !== 'cookie' && detection.source !== 'path';
    response = attachLocaleCookie(response, locale, shouldSetCookie);

    return response;
  },
};

function isAssetPath(pathname: string): boolean {
  return /\.(js|css|png|jpg|webp|svg|ico|woff2?|ttf)$/.test(pathname)
    || pathname.startsWith('/_next/')
    || pathname.startsWith('/static/');
}
```

---

## Subdomain Variant

For `fr.example.com` → Worker with `locale = 'fr'`:

```typescript
// src/middleware/subdomain-locale.ts

export function detectLocaleFromSubdomain(request: Request): string | null {
  const hostname = new URL(request.url).hostname;
  // fr.example.com → 'fr'
  const sub = hostname.split('.')[0];
  return ['en', 'fr', 'de', 'ja'].includes(sub) ? sub : null;
}
```

In `wrangler.toml`, add routes for each subdomain:

```toml
routes = [
  { pattern = "en.example.com/*", zone_name = "example.com" },
  { pattern = "fr.example.com/*", zone_name = "example.com" },
  { pattern = "de.example.com/*", zone_name = "example.com" },
]
```

---

## Anti-Patterns

- **Redirecting assets.** Applying locale redirects to `.js`, `.css`, or image files breaks asset loading. Always exclude static asset paths first.
- **307 Temporary Redirect instead of 302.** A 307 preserves the HTTP method (POST stays POST), which is wrong for locale redirects. Use 302 for GET-based redirects.
- **Setting Vary: Accept-Language globally.** Only set it on responses whose content actually differs by language. Setting it on static assets causes unnecessary cache fragmentation.
- **Parsing Accept-Language with a simple `.split('-')[0]`.** `zh-Hant-TW` (Traditional Chinese, Taiwan) must not collapse to `zh` if `zh-Hant` is supported. Use a proper BCP 47 matching algorithm.
- **Storing locale in the URL hash (`#lang=fr`).** The hash is not sent to the server; the Worker never sees it.
- **Infinite redirect loops.** If the rewritten path `/en/` again triggers the locale-prefix check, you loop. Always check that `first` is a supported locale before rewriting, and strip it only once.

---

## Gotchas

- **`new Request(url, init)` clones the body.** For POST requests with a body, pass the original `request` as the second argument rather than spreading headers manually, or the body stream is consumed twice.
- **302 redirect caching.** Cloudflare's edge caches 302 responses by default if the upstream sets `Cache-Control: max-age`. Add `Cache-Control: no-store` to locale redirect responses to prevent one user's locale from being served to another.
- **Wildcard TLS for subdomains** requires a `*.example.com` certificate. Cloudflare issues this automatically with a proxied subdomain but only if the apex domain is also proxied.
- **Prerender and Googlebot.** Googlebot follows 302 redirects but may not correctly associate hreflang if the redirect target is also behind another redirect. Ensure `/fr/` is the canonical URL, not a redirect target that itself redirects.
- **`cf.country` vs. Accept-Language.** Country code (e.g. `CA`) is not a locale (e.g. `fr-CA`). A user in Canada may prefer English. Use `cf.country` only as a fallback signal, not a locale override.

---

## Verification

```bash
# 1. No locale prefix → redirects to /en/ (default)
curl -sI https://example.com/products | grep -i location
# Location: https://example.com/en/products

# 2. Accept-Language: fr → redirects to /fr/
curl -sI -H 'Accept-Language: fr-FR,fr;q=0.9' https://example.com/products | grep -i location
# Location: https://example.com/fr/products

# 3. Cookie set → no redirect, cookie honoured
curl -sI -H 'Cookie: __locale=de' https://example.com/products | grep -i location
# Location: https://example.com/de/products

# 4. Valid locale prefix → no redirect, Content-Language set
curl -sI https://example.com/fr/products | grep -i content-language
# Content-Language: fr

# 5. Asset path → no locale middleware applied
curl -sI https://example.com/static/app.js | grep -i location
# (empty – no redirect)
```

---

## Related

- `locale-negotiation-accept-language.md`
- `locale-persistence-cookies-storage-2026.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `hreflang-seo-2026.md`
- `content-negotiation-vary-header.md`

---

## Sources

- [Cloudflare Workers Fetch Handler](https://developers.cloudflare.com/workers/runtime-apis/fetch-event/)
- [RFC 7231 – Accept-Language](https://datatracker.ietf.org/doc/html/rfc7231#section-5.3.5)
- [RFC 4647 – BCP 47 Language Tag Matching](https://datatracker.ietf.org/doc/html/rfc4647)
- [Google: Multi-regional and multilingual sites](https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites)
- [Cloudflare: Request object](https://developers.cloudflare.com/workers/runtime-apis/request/)
