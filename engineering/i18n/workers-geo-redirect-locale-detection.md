# Geo-Based Locale Detection and Redirect with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Users land on `example.com/` and see the wrong language. You want to automatically redirect them to `example.com/ar/` or `example.com/de/` based on their country, Accept-Language header, or a stored preference — whichever is most specific. You also want search engines to discover all locale variants via `hreflang` tags without duplicating content.

---

## Context

Cloudflare Workers receive every request before it reaches the origin. The `request.cf` object exposes geo data (country, continent, timezone) populated by Cloudflare's global network. Combined with `Accept-Language` header parsing and KV-stored user preferences, a Worker can:

1. Detect locale with a clear priority order
2. Redirect to the localised URL (once, on first visit)
3. Inject `hreflang` alternate links into HTML for SEO
4. Store preference in a cookie or KV so subsequent visits are direct

---

## Solution

### 1. Country-to-Locale Mapping

```typescript
// src/i18n/geo.ts

/**
 * Map Cloudflare cf.country (ISO 3166-1 alpha-2) to a canonical BCP 47 locale.
 * This is a commercial-coverage set — extend for your markets.
 */
export const COUNTRY_TO_LOCALE: Record<string, string> = {
  // Arabic-speaking countries
  SA: 'ar', AE: 'ar', KW: 'ar', BH: 'ar', QA: 'ar',
  EG: 'ar', JO: 'ar', LB: 'ar', MA: 'ar', DZ: 'ar',
  // European
  DE: 'de', AT: 'de', CH: 'de',
  FR: 'fr', BE: 'fr', LU: 'fr',
  ES: 'es', MX: 'es', AR: 'es', CO: 'es', CL: 'es',
  IT: 'it',
  PT: 'pt-PT', BR: 'pt-BR',
  NL: 'nl',
  PL: 'pl',
  SE: 'sv',
  NO: 'nb',
  DK: 'da',
  FI: 'fi',
  // East Asian
  JP: 'ja',
  KR: 'ko',
  CN: 'zh-CN',
  TW: 'zh-TW',
  HK: 'zh-HK',
  // South Asian
  IN: 'hi',
  PK: 'ur',
  // English-speaking (explicit to avoid ambiguous fallback)
  US: 'en', GB: 'en', AU: 'en', NZ: 'en', CA: 'en', IE: 'en',
  ZA: 'en', SG: 'en',
  // Hebrew
  IL: 'he',
  // Persian
  IR: 'fa',
  // Turkish
  TR: 'tr',
  // Russian
  RU: 'ru', BY: 'ru', KZ: 'ru',
  // Thai
  TH: 'th',
  // Vietnamese
  VN: 'vi',
};

export function localeFromCountry(country: string | undefined): string | null {
  if (!country) return null;
  return COUNTRY_TO_LOCALE[country.toUpperCase()] ?? null;
}
```

### 2. Accept-Language Header Parsing with Quality Weights

```typescript
// src/i18n/accept-language.ts

export interface LocaleQuality {
  locale: string;
  q: number;
}

/**
 * Parse the Accept-Language header into a sorted list of locale+quality pairs.
 *
 * Input:  'ar,en-US;q=0.9,en;q=0.8,*;q=0.5'
 * Output: [
 *   { locale: 'ar',    q: 1.0 },
 *   { locale: 'en-US', q: 0.9 },
 *   { locale: 'en',    q: 0.8 },
 * ]  (* wildcard is excluded)
 */
export function parseAcceptLanguage(header: string | null): LocaleQuality[] {
  if (!header) return [];

  return header
    .split(',')
    .map((part): LocaleQuality | null => {
      const [tag, qPart] = part.trim().split(';q=');
      const locale = tag.trim();
      if (!locale || locale === '*') return null;
      const q = qPart !== undefined ? parseFloat(qPart) : 1.0;
      if (Number.isNaN(q) || q <= 0) return null;
      return { locale, q };
    })
    .filter((entry): entry is LocaleQuality => entry !== null)
    .sort((a, b) => b.q - a.q);
}

/**
 * Return the highest-quality locale the site supports.
 *
 * @param supported - Set of supported locale tags (canonical form)
 * @param parsed    - Output of parseAcceptLanguage
 */
export function negotiateLocale(
  supported: Set<string>,
  parsed: LocaleQuality[],
): string | null {
  for (const { locale } of parsed) {
    if (supported.has(locale)) return locale;
    // Try language-only fallback: 'en-GB' → 'en'
    const lang = locale.split('-')[0];
    if (supported.has(lang)) return lang;
  }
  return null;
}
```

### 3. Locale Resolution with Priority Chain

```typescript
// src/i18n/resolver.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import { localeFromCountry } from './geo';
import { parseAcceptLanguage, negotiateLocale } from './accept-language';

export const SUPPORTED_LOCALES = new Set([
  'en', 'de', 'fr', 'es', 'pt-BR', 'pt-PT',
  'ja', 'ko', 'zh-CN', 'zh-TW',
  'ar', 'he', 'fa',
  'ru', 'pl', 'nl', 'sv', 'tr',
]);

export const DEFAULT_LOCALE = 'en';

export interface ResolvedLocale {
  locale: string;
  source: 'preference' | 'accept-language' | 'geo' | 'default';
}

/**
 * Resolve the best locale for a request.
 * Priority: KV stored preference > Accept-Language negotiation > geo > default.
 */
export async function resolveLocale(
  request: Request,
  kv: KVNamespace,
): Promise<ResolvedLocale> {
  // 1. KV user preference (stored on previous visit or explicit user selection)
  const prefCookie = getCookieValue(request, 'locale_pref');
  if (prefCookie && SUPPORTED_LOCALES.has(prefCookie)) {
    return { locale: prefCookie, source: 'preference' };
  }

  // 2. Accept-Language header
  const parsed = parseAcceptLanguage(request.headers.get('accept-language'));
  const negotiated = negotiateLocale(SUPPORTED_LOCALES, parsed);
  if (negotiated) {
    return { locale: negotiated, source: 'accept-language' };
  }

  // 3. Geo-based detection from cf.country
  const cf = (request as any).cf as { country?: string } | undefined;
  const geoLocale = localeFromCountry(cf?.country);
  if (geoLocale && SUPPORTED_LOCALES.has(geoLocale)) {
    return { locale: geoLocale, source: 'geo' };
  }

  return { locale: DEFAULT_LOCALE, source: 'default' };
}

function getCookieValue(
  request: Request,
  name: string,
): string | null {
  const cookie = request.headers.get('cookie') ?? '';
  const match = cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`, ));
  return match ? decodeURIComponent(match[1]) : null;
}
```

### 4. Redirect Logic — 302 vs Cookie Strategy

```typescript
// src/i18n/redirect.ts
import type { ResolvedLocale } from './resolver';

/**
 * Determine whether to redirect and to which URL.
 *
 * Strategy:
 * - If the URL already has a locale prefix (/ar/...), do not redirect.
 * - If locale is 'en' (default), do not add a prefix (canonical is /).
 * - Otherwise, redirect to /{locale}{path}.
 */
export function shouldRedirect(
  url: URL,
  resolved: ResolvedLocale,
  supportedLocales: Set<string>,
): { redirect: true; targetUrl: string } | { redirect: false } {
  const pathParts = url.pathname.split('/').filter(Boolean);
  const firstSegment = pathParts[0];

  // Already on a locale-prefixed path — no redirect
  if (firstSegment && supportedLocales.has(firstSegment)) {
    return { redirect: false };
  }

  // Default locale — serve at root, no prefix
  if (resolved.locale === 'en') {
    return { redirect: false };
  }

  const targetPath = `/${resolved.locale}${url.pathname === '/' ? '' : url.pathname}`;
  const targetUrl = `${url.origin}${targetPath}${url.search}`;
  return { redirect: true, targetUrl };
}

/**
 * Build a 302 redirect response that also sets a locale preference cookie.
 */
export function buildRedirectResponse(
  targetUrl: string,
  locale: string,
): Response {
  return new Response(null, {
    status: 302,
    headers: {
      location: targetUrl,
      // Cookie persists for 1 year; subsequent visits skip geo detection
      'set-cookie': [
        `locale_pref=${encodeURIComponent(locale)}`,
        'Path=/',
        'Max-Age=31536000',
        'SameSite=Lax',
        // Add Secure in production (HTTPS-only)
      ].join('; '),
      'cache-control': 'no-store', // Do not cache redirects
      'x-i18n-source': 'geo-redirect',
    },
  });
}
```

### 5. hreflang Injection via HTMLRewriter

```typescript
// src/i18n/hreflang-rewriter.ts

interface HreflangConfig {
  currentLocale: string;
  baseUrl: string; // e.g., 'https://example.com'
  supportedLocales: string[];
  currentPath: string;
}

/**
 * Injects <link rel="alternate" hreflang="..."> tags into <head>.
 * Also adds x-default pointing to the English (default locale) URL.
 *
 * Example output in <head>:
 *   <link rel="alternate" hreflang="en"    href="https://example.com/" />
 *   <link rel="alternate" hreflang="de"    href="https://example.com/de/" />
 *   <link rel="alternate" hreflang="ar"    href="https://example.com/ar/" />
 *   <link rel="alternate" hreflang="x-default" href="https://example.com/" />
 */
class HreflangInjector implements HTMLRewriterElementContentHandlers {
  private readonly config: HreflangConfig;

  constructor(config: HreflangConfig) {
    this.config = config;
  }

  element(el: Element): void {
    const { baseUrl, supportedLocales, currentPath } = this.config;

    // Strip existing locale prefix from path for reconstruction
    const basePath = currentPath.replace(/^\/[a-z]{2}(-[A-Z]{2})?\//i, '/') || '/';

    const links = supportedLocales.map((locale) => {
      const href = locale === 'en'
        ? `${baseUrl}${basePath}`
        : `${baseUrl}/${locale}${basePath === '/' ? '' : basePath}`;
      return `<link rel="alternate" hreflang="${locale}"  />`;
    });

    // x-default points to the default locale URL
    const defaultHref = `${baseUrl}${basePath}`;
    links.push(`<link rel="alternate" hreflang="x-default"  />`);

    el.append(links.join('\n'), { html: true });
  }
}

export function buildHreflangRewriter(
  config: HreflangConfig,
): HTMLRewriter {
  return new HTMLRewriter().on('head', new HreflangInjector(config));
}
```

### 6. Worker Entry Point — Full Pipeline

```typescript
// src/index.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import { resolveLocale, SUPPORTED_LOCALES } from './i18n/resolver';
import { shouldRedirect, buildRedirectResponse } from './i18n/redirect';
import { buildHreflangRewriter } from './i18n/hreflang-rewriter';

export interface Env {
  USER_PREFS: KVNamespace;
}

const BASE_URL = 'https://example.com';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Skip non-page assets
    if (
      url.pathname.startsWith('/_worker') ||
      /\.(js|css|png|jpg|ico|svg|woff2|json)$/.test(url.pathname)
    ) {
      return fetch(request);
    }

    // Resolve locale
    const resolved = await resolveLocale(request, env.USER_PREFS);

    // Redirect if needed
    const redirectDecision = shouldRedirect(url, resolved, SUPPORTED_LOCALES);
    if (redirectDecision.redirect) {
      return buildRedirectResponse(redirectDecision.targetUrl, resolved.locale);
    }

    // Fetch origin response
    const origin = await fetch(request);
    if (!origin.headers.get('content-type')?.includes('text/html')) {
      return origin;
    }

    // Inject hreflang tags
    const rewriter = buildHreflangRewriter({
      currentLocale: resolved.locale,
      baseUrl: BASE_URL,
      supportedLocales: [...SUPPORTED_LOCALES],
      currentPath: url.pathname,
    });

    const transformed = rewriter.transform(origin);

    const headers = new Headers(transformed.headers);
    headers.set('vary', 'Accept-Language');
    headers.set('x-i18n-locale', resolved.locale);
    headers.set('x-i18n-source', resolved.source);

    return new Response(transformed.body, {
      status: transformed.status,
      statusText: transformed.statusText,
      headers,
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

### `request.cf` Availability

`request.cf` is populated by Cloudflare's network and available in all Workers (free and paid tiers). In local development with `wrangler dev`, it is either absent or contains mock data — always null-check before reading `cf.country`.

### 302 vs 301 for Locale Redirects

Use **302** (temporary). Using 301 causes browsers to cache the redirect permanently. If a user switches their browser language, they'll be stuck on the cached wrong locale because the browser never re-issues the request to the Worker. 302 forces browsers to re-check every time, but in practice the cookie prevents re-running the detection logic.

### Cookie vs KV for Preference Storage

A cookie is the simplest and most performant option — the Worker reads it from the request headers without a KV round-trip. Use KV in addition when you need cross-device preference sync (authenticated users with a session ID). Both can coexist: check cookie first, fall back to KV.

### SEO Considerations

- Never redirect Googlebot on first crawl — Googlebot follows redirects but each 302 costs a crawl budget.
- The `hreflang` injection approach avoids the need for a separate sitemap per locale.
- Use `<link rel="canonical">` in origin HTML to point to the locale-prefixed URL, preventing duplicate content penalties.
- `x-default` hreflang should point to the URL a user gets when no locale matches — typically your English root.

### Accept-Language Parsing Edge Cases

- `*` wildcard means "any language" and should be ignored during negotiation.
- Quality values of `0` mean "not acceptable" — exclude those locales.
- Some browsers send `Accept-Language: en-US,en;q=0.5` without a space after the comma — the parser above handles this with `.trim()`.

---

## Anti-patterns

- **Never redirect on every request.** Cache the locale decision in a cookie after the first redirect so subsequent requests from the same browser are direct without running the Worker's detection logic.
- **Do not redirect API calls or static assets.** Check `content-type` or path prefix before applying the redirect logic — redirecting `fetch('/api/products')` to `/ar/api/products` will break your SPA.
- **Do not use 301 for locale redirects.** 301s are cached by browsers indefinitely. A user who clears their language preference cannot escape the cached redirect.
- **Avoid trusting `cf.country` alone.** Geo data misses VPN users, corporate proxies, and travellers. Always check Accept-Language and stored preferences first.

---

## Gotchas

- `request.cf` is typed as `IncomingRequestCfProperties | undefined` in `@cloudflare/workers-types`. Cast or null-check before use.
- Chinese has two common variants (`zh-CN`, `zh-TW`, `zh-HK`) that are mutually intelligible for the most part but have significant character set differences (Simplified vs Traditional). Treat them as separate locales in `COUNTRY_TO_LOCALE`.
- `set-cookie` cannot be set on a Response that also has a streaming body rewritten by HTMLRewriter — you must set the cookie on the redirectResponse first, then handle hreflang on the next (non-redirect) request.
- The `hreflang` injector appends to `<head>` using `el.append()`. If the page's `<head>` already has hreflang tags (added by origin CMS), you will get duplicates. Add a check or a handler to remove existing hreflang links first.
- `wrangler dev` with `--remote` flag uses real KV; without it, KV is emulated locally. Test geo logic with `--remote` or by mocking `request.cf`.

---

## Verification

```bash
# Start dev server
npx wrangler dev --local

# Simulate a German user (no preference cookie)
curl -sI 'http://localhost:8787/' \
  -H 'Accept-Language: de-DE,de;q=0.9,en;q=0.8'
# Expected: HTTP/1.1 302, Location: http://localhost:8787/de, Set-Cookie: locale_pref=de

# Simulate Arabic user
curl -sI 'http://localhost:8787/' \
  -H 'Accept-Language: ar,en;q=0.8'
# Expected: HTTP/1.1 302, Location: http://localhost:8787/ar

# Verify no redirect on second request (cookie set)
curl -sI 'http://localhost:8787/' \
  -H 'Accept-Language: de-DE' \
  -H 'Cookie: locale_pref=de'
# Expected: HTTP/1.1 200 (no redirect), x-i18n-source: preference

# Verify hreflang injection
curl -s 'http://localhost:8787/de/' \
  -H 'Cookie: locale_pref=de' \
  | grep 'hreflang'
# Expected: <link rel="alternate" hreflang="en" href="https://example.com/" />
#           <link rel="alternate" hreflang="de" href="https://example.com/de" />
#           <link rel="alternate" hreflang="x-default" href="https://example.com/" />

# Static asset — should not redirect
curl -sI 'http://localhost:8787/logo.png' -H 'Accept-Language: ar'
# Expected: 200, no Location header
```

---

## Related

- `workers-rtl-html-direction-edge.md` — inject RTL dir after locale resolution
- `workers-translation-fallback-chain-kv.md` — KV locale bundle loading
- `workers-currency-formatting-intl-edge.md` — currency from geo locale
- Google Search Central: Tell Google about localized versions of your page
- RFC 5646: Tags for Identifying Languages

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.google.com/search/docs/specialty/international/localized-versions
- https://www.rfc-editor.org/rfc/rfc7231#section-5.3.5 (Accept-Language)
- https://www.rfc-editor.org/rfc/rfc5646 (BCP 47)
- https://www.iso.org/obp/ui/#search (ISO 3166-1 country codes)
