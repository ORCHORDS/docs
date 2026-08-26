# Locale-Aware SEO and hreflang

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Google serves English to French users even though a French
translation exists, or ignores all locale variants entirely.
Alternatively, Search Console reports "hreflang errors":
missing self-referential annotations, mismatched locale
codes, or reciprocal links that don't point back.

## Context

`hreflang` is a strong hint to search engines about which
locale variant to serve — not a directive. Correct
implementation requires every locale variant to reference
every other (including itself), valid BCP 47 codes, and
canonical URL consistency. Cloudflare Worker geo-redirects
interact with hreflang and need careful deployment to avoid
canonicalization conflicts.

## 1. Three implementation methods

Googlebot accepts hreflang signals via three channels. Pick
one and use it consistently — mixing methods on the same
site produces ambiguous signals.

**Method A — HTML `<head>` link elements (recommended for
most sites):**

```html
<head>
  <link rel="alternate" hreflang="en" href="https://example.com/page"/>
  <link rel="alternate" hreflang="fr" href="https://example.com/fr/page"/>
  <link rel="alternate" hreflang="fr-CA" href="https://example.com/fr-ca/page"/>
  <link rel="alternate" hreflang="x-default" href="https://example.com/page"/>
</head>
```

**Method B — HTTP `Link` response header** (for PDFs and
non-HTML documents): same key/value pairs as the `<link>`
elements, sent as a `Link:` response header.

**Method C — XML sitemap `<xhtml:link>` entries (each URL
repeated with cross-references to every other variant):**

```xml
<url>
  <loc>https://example.com/page</loc>
  <xhtml:link rel="alternate" hreflang="en"
              href="https://example.com/page"/>
  <xhtml:link rel="alternate" hreflang="fr"
              href="https://example.com/fr/page"/>
  <xhtml:link rel="alternate" hreflang="x-default"
              href="https://example.com/page"/>
</url>
```

The sitemap method scales for large sites — Googlebot
discovers all URLs in a single sitemap crawl.

## 2. `x-default` and locale-code requirements

`hreflang="x-default"` marks the fallback for users whose
locale matches no annotation — point it at the default
locale or a language-selector landing page.

```html
<link rel="alternate" hreflang="x-default"
      href="https://example.com/"/>
```

Locale codes must be valid BCP 47 tags:

| Code      | Valid? | Note                              |
|-----------|--------|-----------------------------------|
| `en`      | YES    | Language only                     |
| `en-US`   | YES    | Language + region                 |
| `zh-Hans` | YES    | Language + script                 |
| `en_US`   | NO     | Underscore instead of hyphen      |
| `cn`      | NO     | Not a valid ISO 639-1 code        |

Use ISO 639-1 language subtags with hyphen-separated ISO
3166-1 alpha-2 region subtags. Codes are case-insensitive
in the spec but Google normalises them — use lowercase.

## 3. Reciprocal self-referencing requirement

Every locale variant page must include hreflang annotations
for all other locale variants AND for itself. A missing
self-reference causes Googlebot to discard the entire
cluster.

```html
<!-- On https://example.com/fr/page (the French page): -->
<link rel="alternate" hreflang="en"
      href="https://example.com/page"/>         <!-- ← other -->
<link rel="alternate" hreflang="fr"
      href="https://example.com/fr/page"/>      <!-- ← self  -->
<link rel="alternate" hreflang="x-default"
      href="https://example.com/page"/>
```

Checklist: each locale page annotates all other variants,
annotates itself, includes `x-default`, uses absolute URLs,
and the self-reference matches `<link rel="canonical">`.

## 4. Canonical URL interaction

The canonical URL and the hreflang URL for the same locale
must match exactly. If `<link rel="canonical">` points to a
different URL than the hreflang `href` for that locale,
Googlebot ignores the hreflang annotation.

```html
<!-- Both must point to the same URL -->
<link rel="canonical" href="https://example.com/fr/page"/>
<link rel="alternate" hreflang="fr"
      href="https://example.com/fr/page"/>
```

Never set the English page as canonical on a French page
— it forces Google to ignore all locale variants.

## 5. Cloudflare Worker geo-redirect vs hreflang

Geo-redirects target human users; hreflang targets crawlers.
Googlebot crawls from US IPs — a Worker redirecting US
traffic to `/en/` will prevent Googlebot from crawling
`/fr/` unless French URLs appear in the sitemap.

```javascript
// Cloudflare Worker: exempt crawlers from geo-redirect
export default {
  async fetch(request) {
    const ua = request.headers.get('user-agent') || '';
    if (/Googlebot|Bingbot|Slurp/i.test(ua)) {
      return fetch(request); // crawlers see canonical URL
    }
    const locale = countryToLocale(request.cf?.country);
    if (locale !== 'en') {
      const path = new URL(request.url).pathname;
      // 302 — geo-redirects are user-specific, not permanent
      return Response.redirect(
        `https://example.com/${locale}${path}`, 302);
    }
    return fetch(request);
  }
};
```

Use 302, not 301 — a permanent redirect collapses all
locale equity into the single redirected URL.

## Anti-patterns

- Using underscore locale codes (`en_US`) — not accepted.
- Omitting the self-referential annotation on each page.
- Pointing all `hreflang` entries at the same URL.
- Using 301 permanent redirects for geo-based redirects.
- Mixing hreflang methods (HTML head, HTTP header, sitemap).
- Setting `x-default` to a locale-specific URL like `/en/`.

## Gotchas

- Bing and Yandex interpret hreflang differently from
  Google — test in each engine's webmaster tools.
- Large sites (>10k pages) with HTML `<head>` hreflang
  bloat every page; the sitemap method scales better.
- Search Console reports hreflang errors up to 48 hours
  after a fix — do not re-deploy prematurely.
- `hreflang` targets locale, not ranking. Content quality
  still determines ranking position.

## Verification

- Check Google Search Console > International Targeting
  for hreflang errors after deployment.
- Validate with hreflang.ahrefs.com before sitemap submission.
- Run `curl -A Googlebot` on locale URLs; confirm no
  redirect (bot exemption working).
- Diff the sitemap against the live locale URL list.

## Related

- `i18n/hreflang-seo-2026.md`
- `i18n/internationalized-routing-url-localization.md`
- `i18n/content-negotiation-vary-header.md`
- `i18n/locale-detection-browser.md`

## Source URLs (verified 2026-08-17)

- https://developers.google.com/search/docs/specialty/international/localized-versions
- https://www.w3.org/International/questions/qa-html-language-declarations
- https://developers.cloudflare.com/workers/examples/geolocation-hello-world/
- https://support.google.com/webmasters/answer/189077
- https://datatracker.ietf.org/doc/html/rfc5646
