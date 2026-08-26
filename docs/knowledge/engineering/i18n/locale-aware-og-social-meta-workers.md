# Locale-aware Open Graph and Social Meta Tag Generation in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A multilingual product page at `/fr/produits/chaussures` shares to Twitter/X with an English
title and `og:locale` set to `en_US` because the Worker injects static meta tags. LinkedIn
renders the wrong language preview. The hreflang declared in `<head>` differs from the
`og:locale:alternate` set, confusing crawlers. The platform must generate locale-aware
`<meta>` tags server-side in Workers based on the request locale, the page's available
translations, and the canonical URL structure.

## Context

Open Graph protocol uses `og:locale` with the format `language_TERRITORY` (underscore,
not hyphen), e.g. `fr_FR`, not `fr-FR`. This is distinct from BCP 47 (`fr-FR`) and from
IANA language tags. Workers must convert BCP 47 locale strings (from routing or Accept-Language)
into OG locale format, generate `og:locale:alternate` for all other supported locales, and
inject `hreflang` link elements consistently. HTMLRewriter is the recommended injection
mechanism — it avoids full HTML parsing and streams changes at the edge with minimal latency.

---

## 1. BCP 47 → OG locale conversion

```typescript
// src/lib/og-locale.ts

/**
 * Converts a BCP 47 language tag to Open Graph locale format (language_TERRITORY).
 * Examples:
 *   'fr-FR'  => 'fr_FR'
 *   'zh-Hant-TW' => 'zh_TW'   (script subtag dropped per OG convention)
 *   'en'     => 'en_US'        (fallback territory when region absent)
 *   'pt-BR'  => 'pt_BR'
 */
const DEFAULT_TERRITORY: Record<string, string> = {
  en: 'US', fr: 'FR', de: 'DE', es: 'ES', pt: 'BR', zh: 'CN',
  ja: 'JP', ko: 'KR', ar: 'SA', ru: 'RU', it: 'IT', nl: 'NL',
  sv: 'SE', pl: 'PL', tr: 'TR', vi: 'VN', th: 'TH', uk: 'UA',
};

export function toOgLocale(bcp47: string): string {
  try {
    const loc = new Intl.Locale(bcp47);
    const language = loc.language;
    const region   = loc.region ?? DEFAULT_TERRITORY[language] ?? language.toUpperCase();
    return `${language}_${region}`;
  } catch {
    // Malformed tag: return as-is with hyphen replaced
    return bcp47.replace('-', '_');
  }
}

// toOgLocale('fr-FR')      => 'fr_FR'
// toOgLocale('zh-Hant-TW') => 'zh_TW'
// toOgLocale('en')         => 'en_US'
```

---

## 2. Fetching localised page metadata from KV

```typescript
// src/lib/page-meta.ts
export interface PageMeta {
  title:       string;
  description: string;
  imageUrl:    string;
  canonicalUrl: string;
}

export interface Env {
  I18N_CACHE: KVNamespace;
  DB: D1Database;
}

export async function getPageMeta(
  pageId: string,
  locale: string,
  env: Env
): Promise<PageMeta | null> {
  const cacheKey = `meta:${pageId}:${locale}`;
  const cached = await env.I18N_CACHE.get<PageMeta>(cacheKey, { type: 'json' });
  if (cached) return cached;

  const row = await env.DB.prepare(
    `SELECT title, description, image_url, canonical_url
     FROM page_meta
     WHERE page_id = ? AND locale = ?`
  ).bind(pageId, locale).first<PageMeta>();

  if (!row) return null;

  // Cache for 10 minutes
  await env.I18N_CACHE.put(cacheKey, JSON.stringify(row), { expirationTtl: 600 });
  return row;
}
```

---

## 3. HTMLRewriter injection of OG and hreflang tags

```typescript
// src/rewriters/meta-injector.ts
import { toOgLocale } from '../lib/og-locale';
import { PageMeta } from '../lib/page-meta';

interface AlternateLocale {
  locale: string;        // BCP 47
  href: string;          // absolute URL for that locale
}

export class MetaInjector {
  constructor(
    private currentLocale: string,
    private meta: PageMeta,
    private alternates: AlternateLocale[]
  ) {}

  buildHeadTags(): string {
    const ogLocale = toOgLocale(this.currentLocale);
    const alternateOg = this.alternates
      .filter(a => a.locale !== this.currentLocale)
      .map(a => `<meta property="og:locale:alternate" content="${toOgLocale(a.locale)}" />`)
      .join('\n    ');

    const hreflangLinks = [
      ...this.alternates.map(
        a => `<link rel="alternate" hreflang="${a.locale}"  />`
      ),
      `<link rel="alternate" hreflang="x-default" en')?.href ?? this.meta.canonicalUrl}" />`,
    ].join('\n    ');

    return `
    <!-- Locale meta injected by Workers edge -->
    <meta property="og:locale"      content="${ogLocale}" />
    ${alternateOg}
    <meta property="og:title"       content="${escapeAttr(this.meta.title)}" />
    <meta property="og:description" content="${escapeAttr(this.meta.description)}" />
    <meta property="og:image"       content="${this.meta.imageUrl}" />
    <meta property="og:url"         content="${this.meta.canonicalUrl}" />
    <meta name="twitter:card"       content="summary_large_image" />
    <meta name="twitter:title"      content="${escapeAttr(this.meta.title)}" />
    <meta name="twitter:description" content="${escapeAttr(this.meta.description)}" />
    <meta name="twitter:image"      content="${this.meta.imageUrl}" />
    ${hreflangLinks}`;
  }
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}
```

---

## 4. Workers fetch handler composing everything

```typescript
// src/index.ts
import { getPageMeta } from './lib/page-meta';
import { MetaInjector } from './rewriters/meta-injector';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url    = new URL(req.url);
    // Locale extracted from URL prefix: /fr/produits/chaussures → 'fr-FR'
    const localeMatch = url.pathname.match(/^\/([a-z]{2}(?:-[A-Z]{2})?)\//);
    const locale      = localeMatch?.[1] ?? 'en';

    // List of locales the page exists in (from your routing config or D1)
    const supportedLocales: string[] = ['en', 'fr-FR', 'de-DE', 'es-ES', 'pt-BR'];
    const pageSlug = url.pathname.replace(/^\/[^/]+\//, '');
    const pageId   = pageSlug.replace(/\//g, ':');

    const [meta, originResp] = await Promise.all([
      getPageMeta(pageId, locale, env),
      fetch(req),
    ]);

    if (!meta || !originResp.ok) return originResp;

    const alternates = supportedLocales.map(loc => ({
      locale: loc,
      href: `${url.origin}/${loc}/${pageSlug}`,
    }));

    const injector = new MetaInjector(locale, meta, alternates);
    const tagsHtml = injector.buildHeadTags();

    // Inject after <head> opening tag, replacing any existing og: meta
    return new HTMLRewriter()
      .on('head', {
        element(el) {
          el.append(tagsHtml, { html: true });
        },
      })
      .on('meta[property^="og:"], meta[name^="twitter:"], link[rel="alternate"]', {
        element(el) {
          // Remove statically baked meta/link tags to avoid duplicates
          el.remove();
        },
      })
      .transform(originResp);
  },
};
```

---

## 5. Structured data (JSON-LD) locale injection

```typescript
// Append locale-aware JSON-LD to <body> for richer crawlers
function buildJsonLd(meta: PageMeta, locale: string): string {
  const ld = {
    '@context': 'https://schema.org',
    '@type':    'WebPage',
    name:       meta.title,
    description: meta.description,
    inLanguage: locale,       // BCP 47 — correct for JSON-LD (not OG underscore format)
    url:        meta.canonicalUrl,
    image:      meta.imageUrl,
  };
  return `<script type="application/ld+json">${JSON.stringify(ld)}</script>`;
}

// In the HTMLRewriter chain:
// .on('body', { element(el) { el.append(buildJsonLd(meta, locale), { html: true }); } })
```

---

## Anti-patterns

- **Using BCP 47 format (`fr-FR`) in `og:locale`** — OG requires underscore (`fr_FR`); some
  crawlers silently reject hyphen-separated values.
- **Setting `og:locale` from `Accept-Language` only** — Accept-Language negotiation differs
  from URL-based routing; the OG locale should reflect the page's actual language, not the
  header.
- **Omitting `og:locale:alternate`** — without alternates, Facebook/LinkedIn cannot link to
  other language versions; the `og:locale:alternate` list must include all localised URLs.
- **Serving `x-default` pointing to a locale-specific URL** — `x-default` should point to
  the language selector or the default fallback, not to `/en/...`, to signal an
  undifferentiated entry point.

## Gotchas

- **OG locale vs. `html[lang]`** — `html[lang]` uses BCP 47 (hyphens); `og:locale` uses
  underscore format. They must agree on the same language-region but use different separators.
- **JSON-LD `inLanguage` uses BCP 47** — do not convert to underscore format for JSON-LD;
  it follows ISO 639 / BCP 47 convention, not OG.
- **HTMLRewriter ordering** — the `el.remove()` pass on existing meta tags runs before the
  `el.append()` pass; confirm ordering by registering the removal handler first in the chain.
- **`og:image` must be absolute** — relative URLs in `og:image` are rejected by most social
  crawlers; always prefix with `https://`.
- **Caching with locale** — ensure `Vary: Accept-Language` or cache key includes locale when
  caching the transformed response in the Cache API.

## Verification

```typescript
import { toOgLocale } from './src/lib/og-locale';
import { describe, it, expect } from 'vitest';

describe('toOgLocale', () => {
  it('converts fr-FR correctly', () => expect(toOgLocale('fr-FR')).toBe('fr_FR'));
  it('applies default territory for bare en', () => expect(toOgLocale('en')).toBe('en_US'));
  it('drops script subtag from zh-Hant-TW', () => expect(toOgLocale('zh-Hant-TW')).toBe('zh_TW'));
  it('handles pt-BR', () => expect(toOgLocale('pt-BR')).toBe('pt_BR'));
});
```

Integration: use Miniflare or `wrangler dev` to serve a test page and assert the injected
`<meta property="og:locale">` value with an HTML parser in the test.

## Related

- `hreflang-seo-2026.md`
- `hreflang-seo-tags.md`
- `locale-aware-seo-hreflang.md`
- `locale-url-routing-workers-middleware.md`
- `content-negotiation-vary-header.md`
- `locale-aware-sitemap-xml-workers.md`

## Sources

- Open Graph Protocol specification: https://ogp.me/
- Facebook OG locale format: https://developers.facebook.com/docs/opengraph/using-objects/
- Google hreflang documentation: https://developers.google.com/search/docs/specialty/international/localized-versions
- Schema.org inLanguage: https://schema.org/inLanguage
- Cloudflare Workers HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
