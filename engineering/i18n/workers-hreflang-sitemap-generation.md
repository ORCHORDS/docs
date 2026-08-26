# Hreflang Sitemap Generation for Multilingual Sites via Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your multilingual site serves content in English, French, German, and Japanese, but search engines index only the English version because your sitemap has no hreflang annotations. Duplicate-content penalties arise from Google treating `example.com/en/pricing` and `example.com/fr/pricing` as near-duplicates without locale signals. You need a Workers endpoint that generates a valid sitemap XML with correct `<xhtml:link rel="alternate">` entries for every locale, keeps the sitemap fresh when locales change, and scales to tens of thousands of URLs across multiple locale paths.

---

## Context

Hreflang is a Google/Bing signal (not a ranking factor, but a disambiguation signal) that tells search engines which URL to serve to users in a given language+region combination. It is specified in the sitemap as `<xhtml:link rel="alternate" hreflang="..."/>` elements, or in the HTML `<head>`, or in HTTP `Link` headers. The sitemap approach is easiest to maintain centrally.

A Workers endpoint for sitemap generation:
- Reads the supported locale list from **KV** (config that changes without a deploy).
- Reads the URL slug list from **D1** (canonical list of content pages).
- Constructs the XML on the fly with per-locale `<loc>` and `<xhtml:link>` alternates.
- Includes an `x-default` entry pointing to the language-negotiation landing page.
- Uses a sitemap index when the URL count exceeds the 50,000-URL limit per sitemap file.
- Caches the sitemap response with a `Cache-Control` header and invalidates on locale config change.

---

## Solution

### 1. Locale configuration in KV

```typescript
// src/locale-config.ts

export interface LocaleConfig {
  locales: string[];           // BCP 47 tags: ["en", "fr", "de", "ja"]
  defaultLocale: string;       // Used for x-default
  urlPattern: string;          // e.g. "https://example.com/{locale}/{slug}"
  xDefault: string;            // e.g. "https://example.com/{slug}" (lang negotiation)
}

export interface Env {
  I18N_CONFIG_KV: KVNamespace;
  DB: D1Database;
}

export async function getLocaleConfig(env: Env): Promise<LocaleConfig> {
  const raw = await env.I18N_CONFIG_KV.get("locale_config", { type: "json" });
  if (!raw) {
    throw new Error("locale_config not found in KV — run setup script first");
  }
  return raw as LocaleConfig;
}

// KV value (set via Wrangler or API):
// key: "locale_config"
// value: {
//   "locales": ["en", "fr", "de", "ja", "ar", "pt-BR"],
//   "defaultLocale": "en",
//   "urlPattern": "https://example.com/{locale}/{slug}",
//   "xDefault": "https://example.com/{slug}"
// }
```

### 2. URL slug list from D1

```typescript
// src/slug-list.ts

interface PageSlug {
  slug: string;          // e.g. "pricing", "blog/hello-world"
  changefreq: string;    // "weekly", "monthly", "yearly"
  priority: string;      // "1.0", "0.8", "0.5"
  lastmod: string;       // ISO date "2026-08-24"
}

export async function getAllSlugs(env: Env): Promise<PageSlug[]> {
  const { results } = await env.DB
    .prepare(
      `SELECT slug, changefreq, priority,
       strftime('%Y-%m-%d', last_modified_at) AS lastmod
       FROM pages
       WHERE published = 1
       ORDER BY slug`
    )
    .all<PageSlug>();

  return results;
}

export async function getSlugBatch(
  env: Env,
  offset: number,
  limit: number
): Promise<PageSlug[]> {
  const { results } = await env.DB
    .prepare(
      `SELECT slug, changefreq, priority,
       strftime('%Y-%m-%d', last_modified_at) AS lastmod
       FROM pages
       WHERE published = 1
       ORDER BY slug
       LIMIT ? OFFSET ?`
    )
    .bind(limit, offset)
    .all<PageSlug>();

  return results;
}
```

### 3. Sitemap XML construction

```typescript
// src/sitemap-builder.ts
import type { LocaleConfig } from "./locale-config";

interface PageSlug {
  slug: string;
  changefreq: string;
  priority: string;
  lastmod: string;
}

function expandUrl(pattern: string, locale: string, slug: string): string {
  return pattern.replace("{locale}", locale).replace("{slug}", slug);
}

function buildUrlEntry(
  slug: PageSlug,
  config: LocaleConfig
): string {
  const { slug: s, changefreq, priority, lastmod } = slug;

  // Build the alternates block
  const alternates = config.locales
    .map(locale => {
      const href = expandUrl(config.urlPattern, locale, s);
      return `    <xhtml:link rel="alternate" hreflang="${locale}" />`;
    })
    .join("\n");

  // x-default entry
  const xDefault = config.xDefault.replace("{slug}", s);
  const xDefaultEntry = `    <xhtml:link rel="alternate" hreflang="x-default" />`;

  // Canonical <loc> is the default locale URL
  const canonicalUrl = expandUrl(config.urlPattern, config.defaultLocale, s);

  return [
    "  <url>",
    `    <loc>${canonicalUrl}</loc>`,
    `    <lastmod>${lastmod}</lastmod>`,
    `    <changefreq>${changefreq}</changefreq>`,
    `    <priority>${priority}</priority>`,
    alternates,
    xDefaultEntry,
    "  </url>",
  ].join("\n");
}

export function buildSitemap(
  slugs: PageSlug[],
  config: LocaleConfig
): string {
  const urlEntries = slugs.map(s => buildUrlEntry(s, config)).join("\n");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset',
    '  xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
    '  xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    urlEntries,
    "</urlset>",
  ].join("\n");
}
```

### 4. Sitemap index for large sites

```typescript
// src/sitemap-index.ts
import type { LocaleConfig } from "./locale-config";

const URLS_PER_SITEMAP = 1000; // Conservative; max is 50,000

export function buildSitemapIndex(
  totalSlugs: number,
  baseUrl: string,
  lastmod: string
): string {
  const count = Math.ceil(totalSlugs / URLS_PER_SITEMAP);
  const entries = Array.from({ length: count }, (_, i) => [
    "  <sitemap>",
    `    <loc>${baseUrl}/sitemap-${i + 1}.xml</loc>`,
    `    <lastmod>${lastmod}</lastmod>`,
    "  </sitemap>",
  ].join("\n")).join("\n");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    entries,
    "</sitemapindex>",
  ].join("\n");
}

// Page-specific sitemap batch
export async function buildSitemapPage(
  env: Env,
  config: LocaleConfig,
  page: number
): Promise<string> {
  const { getSlugBatch } = await import("./slug-list");
  const { buildSitemap } = await import("./sitemap-builder");

  const offset = (page - 1) * URLS_PER_SITEMAP;
  const slugs = await getSlugBatch(env, offset, URLS_PER_SITEMAP);
  return buildSitemap(slugs, config);
}
```

### 5. Automatic sitemap invalidation on locale config change

```typescript
// src/sitemap-invalidation.ts
// When locale config changes (new locale added, URL pattern updated),
// purge the cached sitemap responses via the Cloudflare Cache API.

export async function invalidateSitemapCache(
  request: Request,
  baseUrl: string
): Promise<void> {
  const cache = caches.default;
  const urlsToInvalidate = [
    `${baseUrl}/sitemap.xml`,
    `${baseUrl}/sitemap-index.xml`,
    // Invalidate known page sitemaps up to a reasonable max
    ...Array.from({ length: 20 }, (_, i) => `${baseUrl}/sitemap-${i + 1}.xml`),
  ];

  await Promise.all(
    urlsToInvalidate.map(url =>
      cache.delete(new Request(url))
    )
  );
}

// PATCH /admin/locale-config — update locale list and invalidate
export async function handleLocaleConfigUpdate(
  request: Request,
  env: Env,
  baseUrl: string
): Promise<Response> {
  const body = await request.json<{ locales: string[] }>();
  const existing = await env.I18N_CONFIG_KV.get("locale_config", { type: "json" }) as any;
  const updated = { ...existing, locales: body.locales };

  await env.I18N_CONFIG_KV.put("locale_config", JSON.stringify(updated));
  await invalidateSitemapCache(request, baseUrl);

  return new Response(JSON.stringify({ ok: true, locales: body.locales }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
```

### 6. Complete Worker entry point

```typescript
// src/index.ts
import { getLocaleConfig, type Env } from "./locale-config";
import { getAllSlugs } from "./slug-list";
import { buildSitemap } from "./sitemap-builder";
import { buildSitemapIndex, buildSitemapPage } from "./sitemap-index";
import { handleLocaleConfigUpdate } from "./sitemap-invalidation";

const CACHE_TTL = 3600; // 1 hour
const BASE_URL = "https://example.com";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const cache = caches.default;

    // Admin endpoint — no caching
    if (url.pathname === "/admin/locale-config" && request.method === "PATCH") {
      return handleLocaleConfigUpdate(request, env, BASE_URL);
    }

    // Try cache first
    const cachedResponse = await cache.match(request);
    if (cachedResponse) return cachedResponse;

    const config = await getLocaleConfig(env);
    let xml: string;
    let status = 200;

    if (url.pathname === "/sitemap-index.xml") {
      const slugs = await getAllSlugs(env);
      xml = buildSitemapIndex(slugs.length, BASE_URL, new Date().toISOString().slice(0, 10));

    } else if (url.pathname === "/sitemap.xml") {
      const slugs = await getAllSlugs(env);
      if (slugs.length > 1000) {
        // Redirect to index for large sites
        return Response.redirect(`${BASE_URL}/sitemap-index.xml`, 301);
      }
      xml = buildSitemap(slugs, config);

    } else {
      const pageMatch = url.pathname.match(/^\/sitemap-(\d+)\.xml$/);
      if (!pageMatch) return new Response("Not Found", { status: 404 });
      const page = parseInt(pageMatch[1], 10);
      xml = await buildSitemapPage(env, config, page);
    }

    const response = new Response(xml, {
      status,
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": `public, max-age=${CACHE_TTL}`,
        "X-Robots-Tag": "noindex",
      },
    });

    ctx.waitUntil(cache.put(request, response.clone()));
    return response;
  },
};
```

---

## Implementation Details

- **Hreflang values**: Must be BCP 47 language tags. Use `en` for all English, `en-US` for US English specifically. `x-default` is a special value meaning "no locale match" — point it at your language detection/redirect page.
- **All locales must be symmetric**: If `en` lists `fr` as an alternate, `fr` must list `en` as an alternate. Missing reciprocal annotations cause the signal to be ignored by Google.
- **Sitemap size limits**: Google supports up to 50,000 URLs and 50 MB per sitemap file. Use the index approach above 1,000 URLs in practice to keep response times low.
- **`xmlns:xhtml` namespace**: The `xhtml:link` element requires the namespace declaration on the root `<urlset>`. Without it, Google will report a parsing error in Search Console.
- **Lastmod format**: ISO 8601 (`2026-08-24` or `2026-08-24T12:00:00Z`). Mixed formats in one sitemap are valid but inconsistent.

---

## Anti-patterns

- **Hard-coding the locale list in Worker code.** Locales should live in KV so they can be updated without a deploy (and without restarting isolates).
- **Generating the full sitemap on every request without caching.** D1 queries and XML serialisation for 10,000 URLs takes hundreds of milliseconds. Cache aggressively.
- **Using `<link rel="alternate" hreflang>` only in HTML `<head>` without a sitemap entry.** For large sites, Googlebot may not crawl every page to discover the HTML hints. The sitemap is more reliable.
- **Including `http://` and `https://` variants as separate locales.** All URLs in the sitemap must use the canonical scheme/host. Use a single canonical base URL.
- **Not including `x-default`.** Without `x-default`, Google has no fallback URL for users in locales not explicitly listed.

---

## Gotchas

- **`caches.default.put()` only works for GET requests.** If your sitemap URL requires authentication headers, caching via the Cache API fails. Serve sitemaps publicly.
- **KV eventual consistency**: After writing a new locale config, KV changes may take up to 60 seconds to propagate globally. The `invalidateSitemapCache` call handles cached Workers responses, but KV read replicas may briefly serve stale config.
- **Cloudflare Cache deduplication**: The Cache API key is the full URL including query string. If your sitemap URL ever includes a cache-buster query param, each variant is cached separately.
- **Sitemap index `lastmod`**: Googlebot uses `lastmod` to decide whether to re-fetch. If you always set it to `now`, Google will re-crawl every time. Set it to the actual last modification date of the slug list.
- **Per-locale URL patterns**: If your French URLs use `example.com/fr-fr/slug` but your hreflang is `fr-FR`, they must match. Inconsistency between path prefix and hreflang tag causes Search Console warnings.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Fetch and validate sitemap
curl -s https://your-worker.workers.dev/sitemap.xml | xmllint --format -

# Check hreflang annotations are present
curl -s https://your-worker.workers.dev/sitemap.xml | \
  grep -c 'hreflang'
# Should equal: (number of pages) * (number of locales + 1 for x-default)

# Validate with Google's rich results test or Search Console
# Submit sitemap: https://search.google.com/search-console/sitemaps

# Test cache invalidation
curl -X PATCH https://your-worker.workers.dev/admin/locale-config \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"locales":["en","fr","de","ja","ko"]}'
# => {"ok":true,"locales":["en","fr","de","ja","ko"]}

# Confirm new locale in sitemap
curl -s https://your-worker.workers.dev/sitemap.xml | grep 'hreflang="ko"'
```

```typescript
// tests/sitemap-builder.test.ts
import { describe, it, expect } from "vitest";
import { buildSitemap } from "../src/sitemap-builder";

const CONFIG = {
  locales: ["en", "fr", "de"],
  defaultLocale: "en",
  urlPattern: "https://example.com/{locale}/{slug}",
  xDefault: "https://example.com/{slug}",
};

const SLUGS = [
  { slug: "pricing", changefreq: "weekly", priority: "0.8", lastmod: "2026-08-24" },
];

describe("buildSitemap", () => {
  it("includes all locale alternates", () => {
    const xml = buildSitemap(SLUGS, CONFIG);
    expect(xml).toContain('hreflang="en"');
    expect(xml).toContain('hreflang="fr"');
    expect(xml).toContain('hreflang="de"');
    expect(xml).toContain('hreflang="x-default"');
  });

  it("uses canonical en URL as loc", () => {
    const xml = buildSitemap(SLUGS, CONFIG);
    expect(xml).toContain("<loc>https://example.com/en/pricing</loc>");
  });

  it("includes xhtml namespace", () => {
    const xml = buildSitemap(SLUGS, CONFIG);
    expect(xml).toContain('xmlns:xhtml="http://www.w3.org/1999/xhtml"');
  });
});
```

---

## Related

- `documentation/categories/i18n/workers-intl-edge-locale.md`
- `documentation/categories/i18n/accept-language-negotiation.md`
- `documentation/categories/i18n/workers-geo-redirect-locale-detection.md`
- `documentation/categories/i18n/d1-translation-store.md`

---

## Sources

- Google Developers: [Tell Google about localised versions of your page](https://developers.google.com/search/docs/specialty/international/localized-versions)
- Sitemaps.org: [Sitemap protocol](https://www.sitemaps.org/protocol.html)
- Cloudflare Docs: [Workers KV](https://developers.cloudflare.com/kv/)
- Cloudflare Docs: [Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- Cloudflare Docs: [D1 Database](https://developers.cloudflare.com/d1/)
- RFC 5646: [Tags for Identifying Languages (BCP 47)](https://www.rfc-editor.org/rfc/rfc5646)
