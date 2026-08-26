# Locale-Aware XML Sitemap Generation in Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your multilingual site has 50,000 pages in 8 locales — 400,000 URL combinations total. The XML sitemap lives on the origin server and is rebuilt nightly by a cron job that takes 20 minutes. When pages are added or translated, Googlebot may not see the updated sitemap for up to 24 hours. You also struggle to keep `<xhtml:link rel="alternate" hreflang="...">` entries in sync with the actual route structure.

You need a sitemap that is:
- generated at the edge, bypassing the slow origin rebuild,
- always current (or cached with a short TTL keyed to a content hash),
- locale-aware, embedding correct `hreflang` annotations per URL,
- split into per-locale sitemaps and a sitemap index for scale.

---

## Context

A Cloudflare Worker can respond to `GET /sitemap.xml` (and `/sitemaps/sitemap-{locale}.xml`) directly, pulling page lists from KV or D1 and rendering XML on the fly. For large sites the Worker generates and caches a compressed XML blob in KV on first request (or via a Cron Trigger), then serves the cached version on subsequent requests.

The `robots.txt` worker points crawlers at the sitemap index. The overall request flow is:

```
Googlebot  →  Worker (sitemap.xml)
                ├── KV cache hit?  →  serve immediately
                └── cache miss  →  query D1 for pages → render XML → store in KV → serve
```

For very large sites, break work across a Cron Trigger that pre-builds sitemaps nightly into R2 or KV, and serve them as static blobs.

---

## 1. Data Model in D1

```sql
-- migrations/0001_pages.sql
CREATE TABLE pages (
  id          TEXT PRIMARY KEY,       -- e.g. "product:abc123"
  slug        TEXT NOT NULL,          -- locale-independent canonical slug
  locale      TEXT NOT NULL,          -- BCP 47 tag, e.g. "fr" or "pt-BR"
  path        TEXT NOT NULL,          -- full URL path, e.g. "/fr/produits/abc123"
  last_mod    TEXT NOT NULL,          -- ISO 8601 date
  priority    REAL NOT NULL DEFAULT 0.5,
  change_freq TEXT NOT NULL DEFAULT 'weekly',
  UNIQUE (slug, locale)
);

CREATE INDEX idx_pages_locale ON pages (locale);
CREATE INDEX idx_pages_last_mod ON pages (last_mod);
```

Each page row stores its locale-specific path so the sitemap builder does not need to re-derive URLs from routing rules.

---

## 2. XML Rendering Helpers

```typescript
// src/sitemap/render.ts

export interface SitemapPage {
  loc: string;        // absolute URL
  lastmod: string;    // YYYY-MM-DD
  priority: number;
  changefreq: string;
  alternates: Array<{ hreflang: string; href: string }>; // all locale variants
}

/**
 * Render one locale's sitemap XML (plain, not compressed).
 * Each <url> includes <xhtml:link> alternates for every locale,
 * plus an "x-default" pointing at the default locale.
 */
export function renderSitemapXml(
  pages: SitemapPage[],
  baseUrl: string
): string {
  const urlset = pages
    .map((p) => {
      const alternates = p.alternates
        .map(
          (a) =>
            `  <xhtml:link rel="alternate" hreflang="${esc(a.hreflang)}" />`
        )
        .join("\n");

      return `
<url>
  <loc>${esc(p.loc)}</loc>
  <lastmod>${esc(p.lastmod)}</lastmod>
  <changefreq>${esc(p.changefreq)}</changefreq>
  <priority>${p.priority.toFixed(1)}</priority>
${alternates}
</url>`.trimStart();
    })
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
${urlset}
</urlset>`;
}

/**
 * Render a sitemap index pointing at per-locale sitemaps.
 */
export function renderSitemapIndex(
  locales: string[],
  baseUrl: string,
  lastmod: string
): string {
  const sitemaps = locales
    .map(
      (locale) => `
<sitemap>
  <loc>${esc(`${baseUrl}/sitemaps/sitemap-${locale}.xml`)}</loc>
  <lastmod>${esc(lastmod)}</lastmod>
</sitemap>`.trimStart()
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemaps}
</sitemapindex>`;
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
```

Never inject raw URL strings into XML without `esc()` — URLs with `&` in query parameters will produce malformed XML that Google Search Console rejects with a parse error.

---

## 3. Fetching Pages from D1 and Building Alternates

```typescript
// src/sitemap/fetch.ts
import type { D1Database } from "@cloudflare/workers-types";
import type { SitemapPage } from "./render";

interface PageRow {
  slug: string;
  locale: string;
  path: string;
  last_mod: string;
  priority: number;
  change_freq: string;
}

/**
 * Load all pages for a specific locale and attach hreflang alternates.
 * Uses a self-join by slug to find all locale variants of each page.
 */
export async function fetchPagesForLocale(
  db: D1Database,
  targetLocale: string,
  baseUrl: string,
  defaultLocale: string
): Promise<SitemapPage[]> {
  // First: get all pages in the target locale.
  const { results: rows } = await db
    .prepare(
      `SELECT slug, locale, path, last_mod, priority, change_freq
       FROM pages
       WHERE locale = ?
       ORDER BY last_mod DESC
       LIMIT 45000` // Google's 50,000 URL cap with headroom
    )
    .bind(targetLocale)
    .all<PageRow>();

  if (!rows || rows.length === 0) return [];

  // Second: for each slug, fetch all locale variants in one query.
  const slugs = rows.map((r) => r.slug);
  const placeholders = slugs.map(() => "?").join(",");
  const { results: allVariants } = await db
    .prepare(
      `SELECT slug, locale, path FROM pages WHERE slug IN (${placeholders})`
    )
    .bind(...slugs)
    .all<Pick<PageRow, "slug" | "locale" | "path">>();

  // Index variants by slug.
  const variantMap = new Map<string, Array<{ hreflang: string; href: string }>>();
  for (const v of allVariants ?? []) {
    if (!variantMap.has(v.slug)) variantMap.set(v.slug, []);
    variantMap.get(v.slug)!.push({
      hreflang: v.locale,
      href: `${baseUrl}${v.path}`,
    });
  }

  return rows.map((row) => {
    const alternates = variantMap.get(row.slug) ?? [];

    // Add x-default pointing at the default locale variant.
    const defaultVariant = alternates.find(
      (a) => a.hreflang === defaultLocale
    );
    if (defaultVariant) {
      alternates.push({ hreflang: "x-default", href: defaultVariant.href });
    }

    return {
      loc: `${baseUrl}${row.path}`,
      lastmod: row.last_mod,
      priority: row.priority,
      changefreq: row.change_freq,
      alternates,
    };
  });
}
```

---

## 4. Worker Handler with KV Caching

```typescript
// src/index.ts
import type { D1Database, KVNamespace } from "@cloudflare/workers-types";
import { fetchPagesForLocale } from "./sitemap/fetch";
import { renderSitemapIndex, renderSitemapXml } from "./sitemap/render";

interface Env {
  DB: D1Database;
  SITEMAP_CACHE: KVNamespace;
  BASE_URL: string;
  SUPPORTED_LOCALES: string;  // comma-separated, e.g. "en,fr,de,ja,ar"
  DEFAULT_LOCALE: string;
}

const CACHE_TTL_SECONDS = 3600; // 1 hour
const XML_HEADERS = {
  "content-type": "application/xml; charset=utf-8",
  "cache-control": `public, max-age=${CACHE_TTL_SECONDS}, stale-while-revalidate=86400`,
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const locales = env.SUPPORTED_LOCALES.split(",");

    // --- Sitemap index ---
    if (url.pathname === "/sitemap.xml") {
      const cacheKey = "sitemap-index";
      const cached = await env.SITEMAP_CACHE.get(cacheKey);
      if (cached) {
        return new Response(cached, { headers: XML_HEADERS });
      }

      const lastmod = new Date().toISOString().slice(0, 10);
      const xml = renderSitemapIndex(locales, env.BASE_URL, lastmod);

      await env.SITEMAP_CACHE.put(cacheKey, xml, {
        expirationTtl: CACHE_TTL_SECONDS,
      });
      return new Response(xml, { headers: XML_HEADERS });
    }

    // --- Per-locale sitemap ---
    const localeMatch = url.pathname.match(
      /^\/sitemaps\/sitemap-([a-zA-Z0-9-]+)\.xml$/
    );
    if (localeMatch) {
      const locale = localeMatch[1];
      if (!locales.includes(locale)) {
        return new Response("Unknown locale", { status: 404 });
      }

      const cacheKey = `sitemap-${locale}`;
      const cached = await env.SITEMAP_CACHE.get(cacheKey);
      if (cached) {
        return new Response(cached, { headers: XML_HEADERS });
      }

      const pages = await fetchPagesForLocale(
        env.DB,
        locale,
        env.BASE_URL,
        env.DEFAULT_LOCALE
      );
      const xml = renderSitemapXml(pages, env.BASE_URL);

      await env.SITEMAP_CACHE.put(cacheKey, xml, {
        expirationTtl: CACHE_TTL_SECONDS,
      });
      return new Response(xml, { headers: XML_HEADERS });
    }

    return new Response("Not found", { status: 404 });
  },

  // Cron Trigger: pre-build all sitemaps nightly to warm the KV cache.
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const locales = env.SUPPORTED_LOCALES.split(",");

    for (const locale of locales) {
      const pages = await fetchPagesForLocale(
        env.DB,
        locale,
        env.BASE_URL,
        env.DEFAULT_LOCALE
      );
      const xml = renderSitemapXml(pages, env.BASE_URL);
      await env.SITEMAP_CACHE.put(`sitemap-${locale}`, xml, {
        expirationTtl: CACHE_TTL_SECONDS * 24,
      });
    }

    const lastmod = new Date().toISOString().slice(0, 10);
    const indexXml = renderSitemapIndex(locales, env.BASE_URL, lastmod);
    await env.SITEMAP_CACHE.put("sitemap-index", indexXml, {
      expirationTtl: CACHE_TTL_SECONDS * 24,
    });

    console.log(`Sitemaps rebuilt for ${locales.length} locales`);
  },
} satisfies ExportedHandler<Env>;
```

Cron schedule in `wrangler.toml`:

```toml
[[triggers.crons]]
crons = ["0 3 * * *"]   # 03:00 UTC daily
```

---

## 5. robots.txt Integration

```typescript
// Inside the same Worker, add a robots.txt route:

if (url.pathname === "/robots.txt") {
  const body = [
    "User-agent: *",
    "Allow: /",
    "",
    `Sitemap: ${env.BASE_URL}/sitemap.xml`,
  ].join("\n");

  return new Response(body, {
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}
```

Always reference the sitemap index URL (not individual locale sitemaps) in `robots.txt`. Google follows the index and discovers all sub-sitemaps from there.

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Putting all locales in one `<urlset>` with 400,000 `<url>` entries | Google's 50,000 URL / 50 MB limit per sitemap file | Split into per-locale sitemaps under a sitemap index |
| Injecting raw URLs into XML without escaping | `&`, `<`, `>` in query parameters break XML parsing | Always pass URLs through an `esc()` function |
| Omitting `x-default` | Googlebot has no fallback for users whose language is not in the alternate list | Add `x-default` pointing at the default locale |
| Using relative URLs in `<loc>` | Sitemaps require absolute URLs per the sitemap protocol spec | Always prepend `BASE_URL` |
| Regenerating the sitemap on every request without caching | Hundreds of D1 queries per second for a high-traffic site | Cache in KV; use Cron Trigger for proactive rebuilds |
| Serving sitemap from a path Cloudflare's cache would bypass (with `Cache-Control: private`) | CDN cache miss on every crawl request | Set `Cache-Control: public, max-age=3600` |

---

## Gotchas

- **D1 row limit per query:** D1 returns at most 10,000 rows per `.all()` call by default. For sites with more than 10,000 pages per locale, paginate with `LIMIT`/`OFFSET` and concatenate results before rendering.
- **KV value size:** KV values are limited to 25 MiB. An uncompressed sitemap for 45,000 URLs with full alternates (~800 bytes each) can exceed this. Compress with `CompressionStream` and serve with `Content-Encoding: gzip`, or split into additional sub-sitemaps (e.g. by content type).
- **`lastmod` semantics:** Google treats `lastmod` as a signal, not a guarantee. Provide accurate dates (from `last_mod` in D1) rather than today's date for every URL.
- **Case sensitivity in locale tags:** `pt-BR` and `pt-br` are equivalent per BCP 47 but some crawlers are case-sensitive. Canonicalise to the CLDR recommended casing before storing in D1 and rendering in XML.
- **Sitemap index discovery:** Submit the index URL directly in Google Search Console — do not expect crawlers to discover it purely from `robots.txt` in the first crawl.

---

## Verification

```bash
# Fetch and lint the sitemap index
curl -s https://example.com/sitemap.xml | xmllint --noout -

# Fetch a locale sitemap and count <url> entries
curl -s https://example.com/sitemaps/sitemap-fr.xml \
  | grep -c '<url>'

# Verify hreflang annotations are present
curl -s https://example.com/sitemaps/sitemap-fr.xml \
  | grep 'hreflang' | head -5

# Check cache headers
curl -I https://example.com/sitemap.xml | grep -i cache-control

# Validate via Google Search Console
# → Coverage → Sitemaps → Submit URL
```

Google's Rich Results Test can also parse sitemap XML and surface issues with hreflang values that reference non-existent locales.

---

## Related Articles

- `locale-url-routing-workers-middleware.md`
- `hreflang-seo-2026.md`
- `locale-aware-seo-hreflang.md`
- `translation-kv-caching-ttl-strategy.md`
- `d1-schema-locale-preferences-content-translations-2026.md`
- `cloudflare-workers-geolocation-locale-routing.md`

---

## Sources

- Sitemaps protocol specification — https://www.sitemaps.org/protocol.html
- Google: Manage multilingual and multiregional sitemaps — https://developers.google.com/search/docs/specialty/international/localized-versions
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Google Search Console Sitemap report — https://support.google.com/webmasters/answer/7451001
