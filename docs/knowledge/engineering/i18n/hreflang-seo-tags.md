# hreflang-seo-tags

**Issue:** Implementing hreflang link tags correctly for multilingual SEO
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without `hreflang`, Google may index the wrong locale variant or show English pages to non-English speakers. Common mistakes: missing `x-default`, no self-reference, mismatched codes.

## Pattern / Solution
HTML `<head>`:
```html
<link rel="alternate" hreflang="en"    href="https://example.com/en/about" />
<link rel="alternate" hreflang="fr"    href="https://example.com/fr/about" />
<link rel="alternate" hreflang="fr-CA" href="https://example.com/fr-ca/about" />
<link rel="alternate" hreflang="x-default" href="https://example.com/en/about" />
```
Rules:
1. Every page must include itself (self-reference)
2. `x-default` points to the fallback URL
3. All alternates must link back (reciprocal)
4. Use BCP 47 codes: `en`, `fr`, `zh-Hans`, `zh-Hant`, `pt-BR`

XML sitemap:
```xml
<url>
  <loc>https://example.com/en/about</loc>
  <xhtml:link rel="alternate" hreflang="fr" href="https://example.com/fr/about"/>
  <xhtml:link rel="alternate" hreflang="x-default" href="https://example.com/en/about"/>
</url>
```

## Gotchas
- Google ignores hreflang if the alternate URL returns non-200 status
- hreflang is a hint, not a directive -- Google may still serve alternates
- Verify via Google Search Console -> International Targeting report

## Related
- `hreflang-seo-2026.md`
- `content-negotiation-vary-header.md`
- `next-js-i18n-routing.md`
