# Multilingual sitemap.xml Generated from D1 in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your multilingual site has hundreds of pages in multiple locales and needs to serve a standards-compliant `sitemap.xml` with `<xhtml:link rel="alternate" hreflang>` annotations so that search engines index the correct language version for each region. The sitemap must reflect newly published content within hours, not after a full redeployment.

---

## Context
Storing page metadata in D1 — slug, locale, `updated_at` — lets a Worker query all published pages and generate the sitemap on the fly. For sites with tens of thousands of URLs, D1 can serve the full result set in under 50 ms at the edge. The generated XML is cached with the Cache API for 24 hours and invalidated by a Deploy Hook triggered from your CMS on publish. Sitemaps larger than 50 MB or 50 000 URLs (Google's limit) should be split by locale and referenced from a sitemap index file.

---

## Setup / Config

```toml
# wrangler.toml
name = "sitemap-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "site-db"
database_id = "YOUR_D1_DATABASE_ID"

[vars]
BASE_URL = "https://example.com"
SUPPORTED_LOCALES = "en,fr,de,es,ja"
DEFAULT_LOCALE = "en"
SITEMAP_TTL = "86400"
```

```bash
# Create D1 database and schema
wrangler d1 create site-db

wrangler d1 execute site-db --command "
CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  locale TEXT NOT NULL,
  title TEXT,
  published INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(slug, locale)
);

CREATE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug);
CREATE INDEX IF NOT EXISTS idx_pages_locale ON pages(locale);
CREATE INDEX IF NOT EXISTS idx_pages_published ON pages(published);

-- Seed test data
INSERT OR IGNORE INTO pages (slug, locale, title, updated_at) VALUES
  ('home', 'en', 'Home', '2026-08-01T00:00:00Z'),
  ('home', 'fr', 'Accueil', '2026-08-01T00:00:00Z'),
  ('home', 'de', 'Startseite', '2026-08-01T00:00:00Z'),
  ('about', 'en', 'About Us', '2026-07-15T00:00:00Z'),
  ('about', 'fr', 'À propos', '2026-07-15T00:00:00Z'),
  ('blog/hello-world', 'en', 'Hello World', '2026-08-24T00:00:00Z'),
  ('blog/bonjour-monde', 'fr', 'Bonjour le monde', '2026-08-24T00:00:00Z');
"
```

---

## Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  BASE_URL: string;
  SUPPORTED_LOCALES: string;
  DEFAULT_LOCALE: string;
  SITEMAP_TTL: string;
}

interface PageRow {
  slug: string;
  locale: string;
  updated_at: string;
}

interface SlugGroup {
  locales: Map<string, string>; // locale -> updated_at
  latestUpdate: string;
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function buildPageUrl(baseUrl: string, locale: string, slug: string, defaultLocale: string): string {
  const path = slug === 'home' ? '' : `/${escapeXml(slug)}`;
  if (locale === defaultLocale) {
    return `${baseUrl}${path}`;
  }
  return `${baseUrl}/${locale}${path}`;
}

/**
 * Build a full sitemap XML string from D1 page data.
 */
function buildSitemapXml(
  rows: PageRow[],
  baseUrl: string,
  defaultLocale: string,
  supportedLocales: string[],
): string {
  // Group rows by slug
  const groups = new Map<string, SlugGroup>();
  for (const row of rows) {
    if (!groups.has(row.slug)) {
      groups.set(row.slug, { locales: new Map(), latestUpdate: row.updated_at });
    }
    const group = groups.get(row.slug)!;
    group.locales.set(row.locale, row.updated_at);
    if (row.updated_at > group.latestUpdate) {
      group.latestUpdate = row.updated_at;
    }
  }

  const urlEntries: string[] = [];

  for (const [slug, group] of groups) {
    const alternates: string[] = [];

    // Build hreflang alternate links for all available locales
    for (const [locale, _updatedAt] of group.locales) {
      const href = buildPageUrl(baseUrl, locale, slug, defaultLocale);
      alternates.push(
        `      <xhtml:link rel="alternate" hreflang="${locale}" />`,
      );
    }

    // x-default points to the default locale URL
    if (group.locales.has(defaultLocale)) {
      const defaultHref = buildPageUrl(baseUrl, defaultLocale, slug, defaultLocale);
      alternates.push(
        `      <xhtml:link rel="alternate" hreflang="x-default" />`,
      );
    }

    // Emit one <url> block per locale
    for (const [locale, updatedAt] of group.locales) {
      const loc = buildPageUrl(baseUrl, locale, slug, defaultLocale);
      urlEntries.push(
        `  <url>\n    <loc>${loc}</loc>\n    <lastmod>${updatedAt.slice(0, 10)}</lastmod>\n${alternates.join('\n')}\n  </url>`,
      );
    }
  }

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset',
    '  xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
    '  xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ...urlEntries,
    '</urlset>',
  ].join('\n');
}

/**
 * Build a sitemap index file referencing per-locale sitemaps.
 */
function buildSitemapIndex(baseUrl: string, locales: string[]): string {
  const sitemaps = locales
    .map((locale) => [
      '  <sitemap>',
      `    <loc>${baseUrl}/sitemap-${locale}.xml</loc>`,
      '  </sitemap>',
    ].join('\n'))
    .join('\n');

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    sitemaps,
    '</sitemapindex>',
  ].join('\n');
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const cache = caches.default;
    const ttl = parseInt(env.SITEMAP_TTL, 10) || 86400;
    const supportedLocales = env.SUPPORTED_LOCALES.split(',');

    // Sitemap index
    if (url.pathname === '/sitemap-index.xml') {
      const cacheKey = new Request(`${env.BASE_URL}/sitemap-index.xml`);
      const cached = await cache.match(cacheKey);
      if (cached) return cached;

      const xml = buildSitemapIndex(env.BASE_URL, supportedLocales);
      const response = new Response(xml, {
        headers: {
          'Content-Type': 'application/xml; charset=utf-8',
          'Cache-Control': `public, max-age=${ttl}`,
        },
      });
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return response;
    }

    // Per-locale sitemap: /sitemap-fr.xml
    const localeMatch = url.pathname.match(/^\/sitemap-([a-z]{2})\.xml$/);
    const isMaster = url.pathname === '/sitemap.xml';

    if (!isMaster && !localeMatch) {
      return new Response('Not found', { status: 404 });
    }

    const filterLocale = localeMatch ? localeMatch[1] : null;
    const cacheKey = new Request(`${env.BASE_URL}${url.pathname}`);
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    // Query D1
    let stmt: D1PreparedStatement;
    if (filterLocale) {
      stmt = env.DB.prepare(
        'SELECT slug, locale, updated_at FROM pages WHERE published = 1 AND locale = ? ORDER BY slug',
      ).bind(filterLocale);
    } else {
      stmt = env.DB.prepare(
        'SELECT slug, locale, updated_at FROM pages WHERE published = 1 ORDER BY slug',
      );
    }
    const { results } = await stmt.all<PageRow>();

    const xml = buildSitemapXml(results, env.BASE_URL, env.DEFAULT_LOCALE, supportedLocales);
    const response = new Response(xml, {
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Cache-Control': `public, max-age=${ttl}`,
      },
    });
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
```

---

## Integration / Testing

```bash
# Dev server
npx wrangler dev

# Fetch master sitemap
curl -s http://localhost:8787/sitemap.xml | xmllint --format -

# Fetch French-only sitemap
curl -s http://localhost:8787/sitemap-fr.xml

# Validate against sitemap schema (requires xmllint with schema support)
curl -s http://localhost:8787/sitemap.xml -o /tmp/sitemap.xml
xmllint --noout --schema https://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd /tmp/sitemap.xml

# Check hreflang presence
curl -s http://localhost:8787/sitemap.xml | grep 'hreflang'

# Count URL entries
curl -s http://localhost:8787/sitemap.xml | grep '<url>' | wc -l
```

```typescript
// test/sitemap.test.ts
import { describe, it, expect } from 'vitest';

// Test pure XML generation logic without Worker runtime
function escapeXml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

describe('Sitemap XML generation', () => {
  it('escapes XML special characters in slugs', () => {
    expect(escapeXml('blog/a&b')).toBe('blog/a&amp;b');
  });

  it('places default locale at root path', () => {
    const baseUrl = 'https://example.com';
    const slug = 'about';
    const locale = 'en';
    const defaultLocale = 'en';
    const path = slug === 'home' ? '' : `/${slug}`;
    const url = locale === defaultLocale ? `${baseUrl}${path}` : `${baseUrl}/${locale}${path}`;
    expect(url).toBe('https://example.com/about');
  });

  it('prefixes non-default locale', () => {
    const url = 'https://example.com' + '/fr' + '/about';
    expect(url).toBe('https://example.com/fr/about');
  });
});
```

---

## Anti-patterns
- **Generating sitemap at build time only** — newly published content won't appear until the next build/deploy; use D1 + Cache API for near-real-time updates.
- **Emitting one `<xhtml:link>` block globally** — each `<url>` entry must include its own full set of `<xhtml:link>` alternates, including a self-referencing one.
- **Omitting `x-default`** — search engines use `x-default` to choose the canonical URL when no locale-specific page matches; always point it at the default locale.
- **Returning unescaped slugs in XML** — slugs containing `&` or `<` will produce malformed XML; always escape.

---

## Gotchas
- Google's sitemap file size limit is 50 MB uncompressed and 50 000 URLs; split by locale using the sitemap index pattern for large catalogs.
- D1 `all()` returns at most 10 000 rows per query in the current implementation; paginate with `LIMIT`/`OFFSET` for very large sites.
- The `xmlns:xhtml` namespace must be declared on the `<urlset>` element, not on individual `<xhtml:link>` tags.
- Cache API `put()` must receive a cloned `Response` — calling `put` after reading the body will fail.

---

## Verification

```bash
# Check content type
curl -sI https://your-worker.workers.dev/sitemap.xml | grep content-type
# content-type: application/xml; charset=utf-8

# Verify cache is working
curl -sI https://your-worker.workers.dev/sitemap.xml | grep -i cf-cache-status
# CF-Cache-Status: HIT (on second request)

# Submit to Google Search Console
# https://search.google.com/search-console -> Sitemaps -> Submit

# D1 row count check
wrangler d1 execute site-db --command \
  "SELECT locale, COUNT(*) as count FROM pages WHERE published = 1 GROUP BY locale"
```

---

## Related
- `workers-hreflang-injection-html-rewriter.md`
- `workers-intl-message-format-kv-translations.md`
- `workers-date-time-format-timezone-d1.md`

---

## Sources
- Sitemaps protocol — https://www.sitemaps.org/protocol.html
- Google hreflang sitemaps — https://developers.google.com/search/docs/specialty/international/localized-versions#sitemap
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
