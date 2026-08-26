# Locale-Aware RSS/Atom Feed Generation in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your blog or news site has content in multiple languages. Readers subscribe to your feed via RSS readers that send their own `Accept-Language` header. You want a single Workers endpoint (`/feed`) that serves a locale-specific RSS 2.0 or Atom 1.0 feed — translated titles, locale-formatted dates, and the correct `xml:lang` attribute — without a separate deployment per locale.

## Context

RSS 2.0 and Atom 1.0 both accept `xml:lang` on the root element to declare the feed's language. `<pubDate>` in RSS 2.0 uses RFC 2822 format; Atom's `<updated>` uses RFC 3339/ISO 8601. Workers can format RFC 2822 dates with `Intl.DateTimeFormat` using a fixed `en-US` locale (RFC 2822 weekday/month names are English-only by spec) while serving the feed content in the user's locale. D1 stores posts in multiple locales; the Worker queries the correct locale row and streams the XML response.

---

## D1 Schema for Multilingual Posts

```sql
-- migrations/0002_posts_i18n.sql
CREATE TABLE posts (
  id          TEXT NOT NULL,
  locale      TEXT NOT NULL,          -- BCP 47, e.g. 'de', 'ja', 'ar'
  slug        TEXT NOT NULL,
  title       TEXT NOT NULL,
  summary     TEXT NOT NULL,
  content     TEXT NOT NULL,
  published_at INTEGER NOT NULL,      -- Unix ms UTC
  updated_at   INTEGER NOT NULL,
  PRIMARY KEY (id, locale)
);
CREATE INDEX idx_posts_locale_published ON posts(locale, published_at DESC);
```

---

## Locale Negotiation for Feed Requests

```typescript
import { negotiateLocale } from "./locale-negotiation"; // reuse project helper

const FEED_LOCALES = ["en", "de", "fr", "ja", "ar", "pt", "es", "zh-Hans"];

export function feedLocale(request: Request): string {
  // Honour explicit ?lang= query param (allows direct subscription links)
  const url = new URL(request.url);
  const explicit = url.searchParams.get("lang");
  if (explicit && FEED_LOCALES.includes(explicit)) return explicit;

  // Fall back to Accept-Language negotiation
  const accept = request.headers.get("accept-language") ?? "en";
  return negotiateLocale(parseAcceptLanguage(accept), FEED_LOCALES);
}
```

---

## RFC 2822 Date Formatting (RSS pubDate)

```typescript
// RSS 2.0 pubDate MUST use English weekday/month names per RFC 2822
const RFC2822_FORMAT = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "UTC",
  hour12: false,
  timeZoneName: "short",
});

function toRfc2822(unixMs: number): string {
  // Intl formats to "Sun, 23 Aug 2026 14:00:00 UTC"
  // RSS readers expect "Sun, 23 Aug 2026 14:00:00 +0000"
  return RFC2822_FORMAT.format(new Date(unixMs)).replace("UTC", "+0000");
}

function toIso8601(unixMs: number): string {
  return new Date(unixMs).toISOString(); // "2026-08-23T14:00:00.000Z"
}
```

---

## RSS 2.0 Feed Builder

```typescript
interface PostRow {
  id: string;
  locale: string;
  slug: string;
  title: string;
  summary: string;
  published_at: number;
  updated_at: number;
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildRss(
  posts: PostRow[],
  locale: string,
  siteUrl: string,
  siteTitle: string
): string {
  const items = posts
    .map(
      (p) => `
    <item>
      <title>${escapeXml(p.title)}</title>
      <link>${siteUrl}/${p.locale}/${escapeXml(p.slug)}</link>
      <guid isPermaLink="true">${siteUrl}/${p.locale}/${escapeXml(p.slug)}</guid>
      <description>${escapeXml(p.summary)}</description>
      <pubDate>${toRfc2822(p.published_at)}</pubDate>
    </item>`
    )
    .join("");

  // Determine text direction for the feed's language
  const dir = isRtlLocale(locale) ? 'dir="rtl"' : "";

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xml:lang="${locale}" ${dir}>
  <channel>
    <title>${escapeXml(siteTitle)}</title>
    <link>${siteUrl}/${locale}/</link>
    <description>${escapeXml(siteTitle)}</description>
    <language>${locale}</language>
    <atom:link  rel="self" type="application/rss+xml"/>
    <lastBuildDate>${toRfc2822(Date.now())}</lastBuildDate>
    ${items}
  </channel>
</rss>`;
}

function isRtlLocale(locale: string): boolean {
  const rtlScripts = new Set(["Arab", "Hebr", "Thaa", "Syrc", "Tfng"]);
  try {
    const { script } = new Intl.Locale(locale).maximize();
    return script ? rtlScripts.has(script) : false;
  } catch {
    return false;
  }
}
```

---

## Workers Handler with D1 and Caching

```typescript
interface Env {
  DB: D1Database;
}

const SITE_URL = "https://example.com";
const SITE_TITLE = "My Multilingual Blog";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!new URL(request.url).pathname.startsWith("/feed")) {
      return new Response("Not found", { status: 404 });
    }

    const locale = feedLocale(request);

    const { results } = await env.DB.prepare(
      `SELECT id, locale, slug, title, summary, published_at, updated_at
         FROM posts
        WHERE locale = ?
        ORDER BY published_at DESC
        LIMIT 20`
    )
      .bind(locale)
      .all<PostRow>();

    // Fallback: if no posts in requested locale, serve English
    const effectivePosts =
      results.length > 0
        ? results
        : await env.DB.prepare(
            "SELECT id, locale, slug, title, summary, published_at, updated_at FROM posts WHERE locale = 'en' ORDER BY published_at DESC LIMIT 20"
          )
            .all<PostRow>()
            .then((r) => r.results);

    const xml = buildRss(effectivePosts, locale, SITE_URL, SITE_TITLE);

    return new Response(xml, {
      headers: {
        "Content-Type": "application/rss+xml; charset=utf-8",
        "Cache-Control": "public, max-age=900, s-maxage=900",
        "Content-Language": locale,
        Vary: "Accept-Language",
      },
    });
  },
};
```

---

## Anti-patterns

- **Embedding raw `<` `>` `&` in XML**: always XML-escape feed content; a single unescaped ampersand in a post title breaks every subscriber's reader.
- **Using `Date.toUTCString()` for `pubDate`**: it produces RFC 7231 format (`23 Aug 2026 14:00:00 GMT`) which is not valid RFC 2822. Use `Intl.DateTimeFormat` with explicit field options.
- **Serving a single global feed and localising it client-side**: RSS readers are headless; they never run JavaScript.
- **Forgetting `xml:lang`**: without it, screen readers and search engines cannot identify the feed's language; `<language>` (RSS) and `xml:lang` (Atom) are complementary, not redundant.

## Gotchas

- RSS 2.0 `<language>` uses IETF language tags but many readers accept only ISO 639-1 two-letter codes (`de`, not `de-DE`). Set `<language>` to the base subtag and `xml:lang` to the full BCP 47 tag.
- The `dir="rtl"` attribute is not part of the RSS or Atom spec but is respected by some readers (Feedly, NewsBlur). It does not harm readers that ignore it.
- Cloudflare's `Cache-Control: s-maxage` applies to the CDN; set a shorter `max-age` for subscriber clients so feed readers re-check at a reasonable interval.
- `Intl.Locale.maximize()` can throw on unusual or private-use subtags. Always wrap in try/catch.

## Verification

```bash
# Fetch German feed
curl "https://example.com/feed?lang=de" -H "Accept: application/rss+xml" | xmllint --format -

# Validate XML well-formedness
curl "https://example.com/feed?lang=ar" | xmllint --noout -

# Check xml:lang attribute
curl "https://example.com/feed?lang=ja" | grep 'xml:lang'

# Confirm Cache-Control and Content-Language headers
curl -I "https://example.com/feed?lang=fr"
```

## Related

- `content-negotiation-vary-header.md`
- `hreflang-seo-2026.md`
- `language-detection-workers-accept-language.md`
- `date-time-timezone-workers-edge-formatting.md`
- `locale-url-routing-workers-middleware.md`

## Sources

- RSS 2.0 specification: https://www.rssboard.org/rss-specification
- Atom RFC 4287: https://www.rfc-editor.org/rfc/rfc4287
- RFC 2822 date format: https://www.rfc-editor.org/rfc/rfc2822#section-3.3
- IETF language tags in RSS: https://www.rssboard.org/rss-language-codes
- `Intl.Locale.maximize()`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/maximize
