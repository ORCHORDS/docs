# Multilingual Slug Routing with Cloudflare Workers and KV

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A content site publishes articles under locale-specific translated slugs:
- `/en/blog/how-to-bake-bread`
- `/de/blog/brot-backen-anleitung`
- `/fr/blog/comment-faire-du-pain`

A single canonical content ID (`article-42`) underlies all three. The routing Worker must resolve
any slug in any locale to the canonical ID, serve the correct locale content from D1, redirect
outdated slugs to the current canonical slug, and generate hreflang alternate links in the HTML
head — all without a round-trip to an origin server.

---

## Context

Workers KV is an ideal store for slug-to-ID lookup tables: reads are O(1) at the edge (eventually
consistent, ~60 s propagation), writes happen at publish time only, and the key space supports the
`<locale>:<slug>` composite key pattern. D1 holds the canonical content and alternate-slug history.
The combination enables a fully edge-native multilingual routing layer with sub-millisecond slug
resolution.

Architecture overview:

```
Request: GET /de/blog/brot-backen-anleitung
     ↓
Worker: resolve locale → "de", slug → "brot-backen-anleitung"
     ↓
KV lookup: key = "de:brot-backen-anleitung"
     ↓ (hit)
Value: "article-42"   (canonical ID)
     ↓
D1 query: SELECT content, current_slug FROM articles WHERE id = 'article-42' AND locale = 'de'
     ↓
Serve HTML with hreflang <link> tags for all available locales
```

---

## 1. KV Key Schema and Ingest

At publish time, every slug variant is written to KV. Old slugs are retained with a redirect
marker so links never break.

```typescript
// worker/publish/slugs.ts
interface SlugEntry {
  canonicalId: string;
  isCanonical: boolean;        // false → this slug is outdated, redirect to current
  canonicalSlug?: string;      // set when isCanonical === false
}

export async function registerSlug(
  env: Env,
  locale: string,
  slug: string,
  canonicalId: string,
  options: { isCanonical: boolean; canonicalSlug?: string } = { isCanonical: true }
): Promise<void> {
  const key = `${locale}:${slug}`;
  const value: SlugEntry = {
    canonicalId,
    isCanonical: options.isCanonical,
    canonicalSlug: options.canonicalSlug,
  };
  // KV TTL not set — slugs are permanent until explicitly deleted
  await env.SLUGS_KV.put(key, JSON.stringify(value));
}

export async function resolveSlug(
  env: Env,
  locale: string,
  slug: string
): Promise<SlugEntry | null> {
  const raw = await env.SLUGS_KV.get(`${locale}:${slug}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SlugEntry;
  } catch {
    return null;
  }
}
```

---

## 2. D1 Schema for Canonical Content and Alternates

```sql
CREATE TABLE IF NOT EXISTS articles (
  id           TEXT NOT NULL,
  locale       TEXT NOT NULL,
  slug         TEXT NOT NULL,   -- current canonical slug for this locale
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (id, locale)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_locale_slug
  ON articles (locale, slug);

-- All locale variants of an article
CREATE TABLE IF NOT EXISTS article_locales (
  article_id TEXT NOT NULL,
  locale     TEXT NOT NULL,
  slug       TEXT NOT NULL,
  PRIMARY KEY (article_id, locale)
);
```

---

## 3. Slug Resolution and Redirect Logic

```typescript
// worker/routing/resolve.ts
import { resolveSlug } from '../publish/slugs';

interface ResolveResult {
  kind: 'found' | 'redirect' | 'not_found';
  canonicalId?: string;
  redirectUrl?: string;
}

export async function resolveRequest(
  env: Env,
  locale: string,
  slug: string,
  basePath: string   // e.g. "/de/blog/"
): Promise<ResolveResult> {
  const entry = await resolveSlug(env, locale, slug);

  if (!entry) return { kind: 'not_found' };

  if (!entry.isCanonical && entry.canonicalSlug) {
    return {
      kind: 'redirect',
      redirectUrl: `${basePath}${entry.canonicalSlug}`,
    };
  }

  return { kind: 'found', canonicalId: entry.canonicalId };
}
```

---

## 4. Fetching Content and Alternate Slugs from D1

```typescript
// worker/routing/content.ts
interface ArticleRow {
  title: string;
  body: string;
  slug: string;
}

interface AlternateRow {
  locale: string;
  slug: string;
}

export async function fetchArticle(
  env: Env,
  canonicalId: string,
  locale: string
): Promise<ArticleRow | null> {
  return env.DB.prepare(
    `SELECT title, body, slug FROM articles WHERE id = ? AND locale = ? LIMIT 1`
  )
    .bind(canonicalId, locale)
    .first<ArticleRow>();
}

export async function fetchAlternates(
  env: Env,
  canonicalId: string
): Promise<AlternateRow[]> {
  const { results } = await env.DB.prepare(
    `SELECT locale, slug FROM article_locales WHERE article_id = ?`
  )
    .bind(canonicalId)
    .all<AlternateRow>();
  return results;
}
```

---

## 5. Building hreflang Link Tags

```typescript
// worker/routing/hreflang.ts
export function buildHreflangTags(
  alternates: Array<{ locale: string; slug: string }>,
  baseUrl: string,        // e.g. "https://example.com"
  basePath: string        // e.g. "/blog/"
): string {
  const tags = alternates.map(({ locale, slug }) => {
    const href = `${baseUrl}/${locale}${basePath}${slug}`;
    return `<link rel="alternate" hreflang="${locale}" >`;
  });

  // x-default points to the English version
  const defaultLocale = alternates.find((a) => a.locale === 'en');
  if (defaultLocale) {
    const href = `${baseUrl}/en${basePath}${defaultLocale.slug}`;
    tags.push(`<link rel="alternate" hreflang="x-default" >`);
  }

  return tags.join('\n    ');
}
```

---

## 6. Main Router Handler

```typescript
// worker/index.ts
const LOCALE_PATH_RE = /^\/([a-z]{2}(?:-[A-Z]{2})?)\/blog\/([^/?#]+)/;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = LOCALE_PATH_RE.exec(url.pathname);

    if (!match) return new Response('Not found', { status: 404 });

    const [, locale, slug] = match;
    const basePath = `/${locale}/blog/`;

    const resolved = await resolveRequest(env, locale, slug, basePath);

    if (resolved.kind === 'not_found') {
      return new Response('Not found', { status: 404 });
    }

    if (resolved.kind === 'redirect' && resolved.redirectUrl) {
      return Response.redirect(`${url.origin}${resolved.redirectUrl}`, 301);
    }

    const [article, alternates] = await Promise.all([
      fetchArticle(env, resolved.canonicalId!, locale),
      fetchAlternates(env, resolved.canonicalId!),
    ]);

    if (!article) return new Response('Not found', { status: 404 });

    const hreflang = buildHreflangTags(alternates, url.origin, '/blog/');

    const html = `<!DOCTYPE html>
<html lang="${locale}" dir="${isRtl(locale) ? 'rtl' : 'ltr'}">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtml(article.title)}</title>
  ${hreflang}
</head>
<body>
  <h1>${escapeHtml(article.title)}</h1>
  <article>${article.body}</article>
</body>
</html>`;

    return new Response(html, {
      headers: { 'Content-Type': 'text/html; charset=UTF-8' },
    });
  },
};

function isRtl(locale: string): boolean {
  return ['ar', 'he', 'fa', 'ur', 'yi', 'dv'].includes(locale.split('-')[0]);
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
```

---

## Anti-patterns

- **Using KV as the primary content store** — KV has eventual consistency (up to 60 s); reading
  stale article content is unacceptable. KV is correct for slug→ID mapping only; content lives
  in D1.
- **Treating the slug as the canonical ID** — slugs change when titles are edited; always maintain
  a stable `canonicalId` and map all historical slugs to it.
- **URL-encoding the locale in the KV key** — use plain BCP-47 tags (`de`, `fr`, `sw-KE`); URL
  encoding introduces key collisions when the KV key contains `%2F` vs `/`.
- **Generating hreflang tags from KV only** — KV may be stale; always query D1 for the authoritative
  list of available locales before emitting hreflang links.

---

## Gotchas

- KV `list()` operations (scanning all slugs by locale prefix) are slow for large key spaces;
  maintain a D1 `article_locales` table as the source of truth for alternate discovery.
- `Response.redirect()` with a 301 status caches aggressively in browsers; use 302 during
  testing and switch to 301 only when the canonical slug is stable.
- The regex `^\/([a-z]{2}(?:-[A-Z]{2})?)\/blog\/` does not match extended subtags like `zh-Hant-TW`;
  expand the pattern if your locale set includes script subtags.
- Workers KV has a maximum value size of 25 MB and a maximum key size of 512 bytes. Slug keys are
  well within limits but compound keys for very long slugs should be hashed.

---

## Verification

```bash
# Publish a slug
curl -X POST https://my-worker.example.com/admin/slugs \
  -H "Content-Type: application/json" \
  -d '{"locale":"de","slug":"brot-backen-anleitung","canonicalId":"article-42","isCanonical":true}'

# Fetch by slug
curl https://my-worker.example.com/de/blog/brot-backen-anleitung
# Expected: 200 HTML with hreflang tags

# Old slug triggers redirect
curl -I https://my-worker.example.com/de/blog/alter-slug
# Expected: HTTP 301 → current canonical slug

# Confirm hreflang in response
curl -s https://my-worker.example.com/en/blog/how-to-bake-bread | grep hreflang
```

---

## Related

- `locale-aware-url-slug-normalization.md`
- `internationalized-routing-url-localization.md`
- `hreflang-seo-2026.md`
- `locale-url-routing-workers-middleware.md`
- `translation-kv-caching-ttl-strategy.md`

---

## Sources

- Cloudflare Workers KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Google Search hreflang documentation — https://developers.google.com/search/docs/specialty/international/localized-versions
- RFC 5646 — Tags for Identifying Languages — https://www.rfc-editor.org/rfc/rfc5646
- Unicode CLDR language subtag registry — https://www.iana.org/assignments/language-subtag-registry
