# Injecting hreflang Tags into HTML Responses Using Workers HTMLRewriter

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your origin server returns HTML pages without `<link rel="alternate" hreflang>` tags, and retrofitting the origin is not feasible. You need to inject these tags transparently at the edge so that search engines can discover all language variants without modifying the origin application.

---

## Context
`HTMLRewriter` is a streaming HTML parser built into the Cloudflare Workers runtime that processes responses in a single pass without buffering the entire document. It can insert elements into `<head>` with zero allocation overhead compared to regex substitution on the full response body. The canonical URL and available locale map are stored in KV, keyed by the URL path, so the Worker can look up the correct set of alternates per page. The `x-default` hreflang is always set to the default locale URL. The result is verifiable with both `curl` and Google's Rich Results Test URL inspector.

---

## Setup / Config

```toml
# wrangler.toml
name = "hreflang-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "LOCALE_MAP"
id = "YOUR_KV_NAMESPACE_ID"
preview_id = "YOUR_KV_PREVIEW_ID"

[vars]
BASE_URL = "https://example.com"
DEFAULT_LOCALE = "en"
ORIGIN = "https://origin.example.com"
```

```bash
# Populate KV with per-path locale availability
# Key: URL path (e.g. "/about")
# Value: JSON array of available locale codes

wrangler kv:key put --binding=LOCALE_MAP "/" '["en","fr","de","es"]'
wrangler kv:key put --binding=LOCALE_MAP "/about" '["en","fr","de"]'
wrangler kv:key put --binding=LOCALE_MAP "/blog/hello-world" '["en","fr"]'
wrangler kv:key put --binding=LOCALE_MAP "/pricing" '["en","de","es"]'

# For locale-prefixed paths, map back to canonical slug
wrangler kv:key put --binding=LOCALE_MAP "/fr/about" '["en","fr","de"]'
wrangler kv:key put --binding=LOCALE_MAP "/de/about" '["en","fr","de"]'
```

---

## Implementation

```typescript
// src/index.ts
export interface Env {
  LOCALE_MAP: KVNamespace;
  BASE_URL: string;
  DEFAULT_LOCALE: string;
  ORIGIN: string;
}

/**
 * Determine the canonical slug for a given path.
 * /fr/about -> /about (strip locale prefix)
 * /about    -> /about
 */
function canonicalSlug(pathname: string, locales: string[]): string {
  for (const locale of locales) {
    if (pathname === `/${locale}` || pathname.startsWith(`/${locale}/`)) {
      return pathname.slice(locale.length + 1) || '/';
    }
  }
  return pathname;
}

/**
 * Build the URL for a given locale and slug.
 * Default locale: baseUrl + slug
 * Other locales:  baseUrl + /locale + slug
 */
function buildAlternateUrl(
  baseUrl: string,
  locale: string,
  slug: string,
  defaultLocale: string,
): string {
  const path = slug === '/' ? '' : slug;
  if (locale === defaultLocale) {
    return `${baseUrl}${path || '/'}`;
  }
  return `${baseUrl}/${locale}${path}`;
}

/**
 * Generate hreflang <link> tag HTML strings for injection.
 */
function buildHreflangTags(
  baseUrl: string,
  slug: string,
  locales: string[],
  defaultLocale: string,
): string[] {
  const tags: string[] = [];
  for (const locale of locales) {
    const href = buildAlternateUrl(baseUrl, locale, slug, defaultLocale);
    tags.push(`<link rel="alternate" hreflang="${locale}" >`);
  }
  // x-default always points to default locale URL
  if (locales.includes(defaultLocale)) {
    const defaultHref = buildAlternateUrl(baseUrl, defaultLocale, slug, defaultLocale);
    tags.push(`<link rel="alternate" hreflang="x-default" >`);
  }
  return tags;
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Proxy request to origin
    const originUrl = new URL(url.pathname + url.search, env.ORIGIN);
    const originRequest = new Request(originUrl.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.method !== 'GET' && request.method !== 'HEAD' ? request.body : null,
    });

    const originResponse = await fetch(originRequest);

    // Only transform HTML responses
    const contentType = originResponse.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) {
      return originResponse;
    }

    // Determine the canonical slug for this path
    // We need the list of all known locale prefixes to strip them
    // Pull the list from KV for this path first
    const knownLocales = ['en', 'fr', 'de', 'es', 'ja']; // fast static check
    const slug = canonicalSlug(url.pathname, knownLocales);

    // Look up available locales for this slug from KV
    const localesRaw = await env.LOCALE_MAP.get(slug);
    if (!localesRaw) {
      // No mapping for this path — return origin response unmodified
      return originResponse;
    }

    let locales: string[];
    try {
      locales = JSON.parse(localesRaw) as string[];
    } catch {
      return originResponse;
    }

    const hreflangTags = buildHreflangTags(
      env.BASE_URL,
      slug,
      locales,
      env.DEFAULT_LOCALE,
    );

    // Build modified response headers
    const responseHeaders = new Headers(originResponse.headers);
    // Vary on Accept-Language so CDN caches different versions correctly
    const existingVary = responseHeaders.get('Vary') ?? '';
    responseHeaders.set(
      'Vary',
      existingVary ? `${existingVary}, Accept-Language` : 'Accept-Language',
    );

    // Use HTMLRewriter to inject tags into <head>
    const rewriter = new HTMLRewriter().on('head', {
      element(element) {
        for (const tag of hreflangTags) {
          // Append each tag at the end of <head>
          element.append(tag, { html: true });
        }
      },
    });

    return rewriter.transform(
      new Response(originResponse.body, {
        status: originResponse.status,
        statusText: originResponse.statusText,
        headers: responseHeaders,
      }),
    );
  },
};
```

---

## Integration / Testing

```bash
# Start local dev (Worker proxies to ORIGIN defined in wrangler.toml)
npx wrangler dev

# Inspect injected hreflang tags
curl -s http://localhost:8787/about | grep -A5 'hreflang'
# <link rel="alternate" hreflang="en" href="https://example.com/about">
# <link rel="alternate" hreflang="fr" href="https://example.com/fr/about">
# <link rel="alternate" hreflang="de" href="https://example.com/de/about">
# <link rel="alternate" hreflang="x-default" href="https://example.com/about">

# Confirm page without locale mapping is passed through unmodified
curl -s http://localhost:8787/unknown-path | grep 'hreflang'
# (no output — Worker returned origin response unchanged)

# Test that x-default is always present
curl -s http://localhost:8787/ | grep 'x-default'
# <link rel="alternate" hreflang="x-default" href="https://example.com/">

# Verify Vary header
curl -sI http://localhost:8787/about | grep -i vary
# Vary: Accept-Language

# Test with Google Rich Results URL Inspector (after deploy)
# 1. Deploy: npx wrangler deploy
# 2. Visit: https://search.google.com/test/rich-results
# 3. Enter your URL and check "Detected structured data" -> hreflang

# Batch-test all KV-mapped paths
for path in "/" "/about" "/blog/hello-world" "/pricing"; do
  echo "--- $path ---"
  curl -s "http://localhost:8787${path}" | grep 'hreflang' | wc -l
done
```

```typescript
// test/hreflang.test.ts
import { describe, it, expect } from 'vitest';

function canonicalSlug(pathname: string, locales: string[]): string {
  for (const locale of locales) {
    if (pathname === `/${locale}` || pathname.startsWith(`/${locale}/`)) {
      return pathname.slice(locale.length + 1) || '/';
    }
  }
  return pathname;
}

function buildAlternateUrl(
  baseUrl: string,
  locale: string,
  slug: string,
  defaultLocale: string,
): string {
  const path = slug === '/' ? '' : slug;
  return locale === defaultLocale
    ? `${baseUrl}${path || '/'}`
    : `${baseUrl}/${locale}${path}`;
}

describe('hreflang helpers', () => {
  it('strips locale prefix from pathname', () => {
    expect(canonicalSlug('/fr/about', ['en', 'fr', 'de'])).toBe('/about');
    expect(canonicalSlug('/about', ['en', 'fr', 'de'])).toBe('/about');
    expect(canonicalSlug('/fr', ['en', 'fr'])).toBe('/');
  });

  it('builds default locale URL at root path', () => {
    expect(buildAlternateUrl('https://example.com', 'en', '/about', 'en'))
      .toBe('https://example.com/about');
  });

  it('builds non-default locale URL with prefix', () => {
    expect(buildAlternateUrl('https://example.com', 'fr', '/about', 'en'))
      .toBe('https://example.com/fr/about');
  });

  it('handles root slug correctly', () => {
    expect(buildAlternateUrl('https://example.com', 'en', '/', 'en'))
      .toBe('https://example.com/');
    expect(buildAlternateUrl('https://example.com', 'fr', '/', 'en'))
      .toBe('https://example.com/fr');
  });
});
```

---

## Anti-patterns
- **Buffering the full HTML body with `Response.text()` and regex** — loses streaming, increases memory usage, and fails on very large pages.
- **Hardcoding locale lists in the Worker script** — use KV for the per-path locale map so new language variants can be added without redeployment.
- **Appending hreflang to `<body>` instead of `<head>`** — search engine crawlers expect hreflang in `<head>`; body injection is ignored.
- **Omitting `x-default`** — without it, Google will pick an arbitrary locale version as the canonical, which may not match your intent.
- **Not setting `Vary: Accept-Language`** — shared caches (CDN, ISP) may return the wrong language version to subsequent visitors.

---

## Gotchas
- `HTMLRewriter.on('head', handler)` fires once per `<head>` element; if the origin returns malformed HTML with no `<head>`, no tags are injected — add a fallback `on('html', ...)` handler to inject a `<head>` block.
- `element.append(tag, { html: true })` must receive a string — building the tag with template literals is fine but avoid unsanitised user input in `href` attributes.
- KV `get()` returns `null` for missing keys in under 1 ms; the overhead is negligible even on hot paths.
- The `HTMLRewriter` response is streaming — do not call `.text()` on it before returning, or you will buffer the entire transformed document.
- Workers do not follow redirects from the origin by default when using `fetch()`; set `redirect: 'follow'` if your origin issues 301/302s.

---

## Verification

```bash
# Deploy to production
npx wrangler deploy

# Full hreflang audit with curl
curl -s https://example.com/about \
  | grep -E 'hreflang|alternate' \
  | sort

# Confirm x-default is present on every mapped page
for path in "/" "/about" "/pricing"; do
  count=$(curl -s "https://example.com${path}" | grep -c 'x-default')
  echo "$path: x-default count = $count"
done

# Google Search Console hreflang report
# https://search.google.com/search-console -> International targeting -> Language
```

---

## Related
- `workers-multilingual-sitemap-xml-d1.md`
- `workers-intl-message-format-kv-translations.md`
- `workers-currency-number-format-cf-country.md`

---

## Sources
- Cloudflare HTMLRewriter docs — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Google hreflang documentation — https://developers.google.com/search/docs/specialty/international/localized-versions
- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- Google Rich Results Test — https://search.google.com/test/rich-results
