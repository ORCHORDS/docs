# Locale-Based Content Variants in D1: Selection via `Accept-Language` with Quality Weighting

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your D1 database stores the same article, product description, or CMS block in
multiple locales (`en`, `fr`, `de`, `ar`). Your Worker must:

1. Parse `Accept-Language` with quality (q-value) weighting.
2. Select the best available locale from D1, falling back through the quality
   list until a match is found.
3. Set `Vary: Accept-Language` so Cloudflare's cache and downstream proxies
   store separate variants per language.
4. Return `Content-Language` and a canonical `Link` rel=alternate header for
   each available translation.

## Context

- Runtime: Cloudflare Workers
- Database: Cloudflare D1 (SQLite at the edge)
- Content type: multilingual CMS articles / product descriptions
- Cache strategy: Cloudflare Cache API keyed on `{url}:{resolved-locale}`

---

## 1. D1 Schema

```sql
-- migrations/001_content.sql
CREATE TABLE content (
  slug        TEXT    NOT NULL,
  locale      TEXT    NOT NULL,   -- BCP-47 primary subtag, e.g. "en", "fr"
  title       TEXT    NOT NULL,
  body        TEXT    NOT NULL,
  updated_at  INTEGER NOT NULL,   -- Unix epoch seconds
  PRIMARY KEY (slug, locale)
);

CREATE INDEX idx_content_slug ON content (slug);

-- Seed example
INSERT INTO content VALUES
  ('hello-world', 'en', 'Hello World', 'English body text.', unixepoch()),
  ('hello-world', 'fr', 'Bonjour le Monde', 'Texte en français.', unixepoch()),
  ('hello-world', 'de', 'Hallo Welt', 'Deutscher Text.', unixepoch()),
  ('hello-world', 'ar', 'مرحباً بالعالم', 'نص عربي.', unixepoch());
```

Apply with:

```bash
wrangler d1 execute <DB_NAME> --file migrations/001_content.sql
```

---

## 2. Accept-Language Parser with Quality Weighting

```typescript
// src/accept-language.ts

export interface WeightedLocale {
  tag:  string;   // full BCP-47 tag as sent by browser, e.g. "fr-CA"
  lang: string;   // primary subtag, e.g. "fr"
  q:    number;   // quality weight 0.0–1.0
}

/**
 * Parse Accept-Language header into a q-value sorted list.
 * Strips wildcard (*) entries; handles both "fr" and "fr-CA" forms.
 */
export function parseAcceptLanguage(header: string | null): WeightedLocale[] {
  if (!header) return [{ tag: 'en', lang: 'en', q: 1.0 }];

  return header
    .split(',')
    .map(entry => {
      const [rawTag, rawQ] = entry.trim().split(';q=');
      const tag  = rawTag.trim();
      const q    = rawQ ? parseFloat(rawQ) : 1.0;
      const lang = tag.split('-')[0].toLowerCase();
      return { tag, lang, q };
    })
    .filter(e => e.tag !== '*' && e.tag !== '' && !isNaN(e.q))
    .sort((a, b) => b.q - a.q);
}

/**
 * Given a priority-ordered list of weighted locales and the set of
 * locales available in the database, return the best match.
 * Prefers exact tag match over primary-subtag match.
 */
export function bestMatch(
  preferred: WeightedLocale[],
  available: Set<string>
): string {
  for (const { tag, lang } of preferred) {
    if (available.has(tag))  return tag;
    if (available.has(lang)) return lang;
  }
  // Last resort: return the first available locale
  return available.values().next().value ?? 'en';
}
```

---

## 3. D1 Content Repository

```typescript
// src/content-repo.ts

export interface ContentRow {
  slug:       string;
  locale:     string;
  title:      string;
  body:       string;
  updated_at: number;
}

export interface Env {
  DB: D1Database;
}

/**
 * Return all available locales for a slug (cheap index scan).
 */
export async function getAvailableLocales(
  slug: string,
  env: Env
): Promise<Set<string>> {
  const { results } = await env.DB
    .prepare('SELECT locale FROM content WHERE slug = ?')
    .bind(slug)
    .all<{ locale: string }>();

  return new Set(results.map(r => r.locale));
}

/**
 * Fetch a single content row by slug + locale.
 * Returns null when no row exists for the resolved locale.
 */
export async function getContent(
  slug:   string,
  locale: string,
  env:    Env
): Promise<ContentRow | null> {
  const row = await env.DB
    .prepare('SELECT * FROM content WHERE slug = ? AND locale = ?')
    .bind(slug, locale)
    .first<ContentRow>();

  return row ?? null;
}

/**
 * List all (slug, locale) pairs — useful for building `Link: rel=alternate`
 * headers listing all available translations.
 */
export async function getAllLocales(
  slug: string,
  env:  Env
): Promise<string[]> {
  const { results } = await env.DB
    .prepare('SELECT locale FROM content WHERE slug = ? ORDER BY locale')
    .bind(slug)
    .all<{ locale: string }>();

  return results.map(r => r.locale);
}
```

---

## 4. Worker Entry Point with Cache API

```typescript
// src/index.ts
import { parseAcceptLanguage, bestMatch } from './accept-language';
import { getAvailableLocales, getContent, getAllLocales } from './content-repo';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url  = new URL(request.url);
    // Expect path like /content/<slug>
    const slug = url.pathname.replace(/^\/content\//, '').replace(/\/+$/, '');

    if (!slug) {
      return new Response('Not Found', { status: 404 });
    }

    // 1. Parse Accept-Language
    const preferred = parseAcceptLanguage(
      request.headers.get('Accept-Language')
    );

    // 2. Find available locales for this slug
    const available = await getAvailableLocales(slug, env);
    if (available.size === 0) {
      return new Response('Not Found', { status: 404 });
    }

    // 3. Pick best locale
    const resolved = bestMatch(preferred, available);

    // 4. Check Cache API (keyed on URL + resolved locale)
    const cache    = caches.default;
    const cacheKey = new Request(`${url.origin}${url.pathname}#${resolved}`);
    const cached   = await cache.match(cacheKey);
    if (cached) return cached;

    // 5. Fetch from D1
    const content = await getContent(slug, resolved, env);
    if (!content) {
      return new Response('Not Found', { status: 404 });
    }

    // 6. Build Link rel=alternate headers
    const allLocales  = await getAllLocales(slug, env);
    const alternates  = allLocales
      .map(l => `<${url.origin}/content/${slug}>;rel="alternate";hreflang="${l}"`)
      .join(', ');

    // 7. Assemble response
    const body = JSON.stringify({
      slug,
      locale:  resolved,
      title:   content.title,
      body:    content.body,
      updated: content.updated_at
    }, null, 2);

    const response = new Response(body, {
      status:  200,
      headers: {
        'Content-Type':     'application/json; charset=utf-8',
        'Content-Language': resolved,
        'Vary':             'Accept-Language',
        'Link':             alternates,
        'Cache-Control':    'public, max-age=300'
      }
    });

    // 8. Store in Cache API (non-blocking)
    ctx.waitUntil(cache.put(cacheKey, response.clone()));

    return response;
  }
};
```

---

## Anti-patterns

- **Selecting locale from a URL query param without `Vary`** — any proxy or
  Cloudflare cache may serve the wrong-language response to other users.
- **Fetching all locales then filtering in JS** — one indexed `WHERE slug = ?`
  plus `WHERE slug = ? AND locale = ?` is far cheaper than a full table scan.
- **Caching without the resolved locale in the key** — two users with different
  `Accept-Language` hitting the same URL get the same cached body.
- **Returning 404 when the exact locale tag is missing** — always fall back
  through the primary subtag (`fr-CA` → `fr`) before giving up.

## Gotchas

- D1 is SQLite; it is case-sensitive for `TEXT` columns by default. Store
  locale codes in a canonical form (all lowercase primary subtag) and
  normalise on insert.
- The Cache API `cacheKey` must be a `Request` object, not a plain string. The
  URL fragment (`#locale`) is stripped by some proxies but kept by Workers'
  Cache API for key discrimination.
- `ctx.waitUntil` keeps the isolate alive after `return response` so the cache
  write completes. Without it the write may be abandoned.
- `Vary: Accept-Language` tells Cloudflare's cache to store a separate variant
  per unique header value. This can balloon cache storage for sites with many
  locales. Use a coarse cache key (primary subtag only) if needed.

## Verification

```bash
npx wrangler dev src/index.ts

# English (default)
curl -s -H 'Accept-Language: en' http://localhost:8787/content/hello-world \
  | jq '{locale, title}'
# → { "locale": "en", "title": "Hello World" }

# French with region tag — should match primary subtag 'fr'
curl -s -H 'Accept-Language: fr-CA,fr;q=0.9,en;q=0.8' \
  http://localhost:8787/content/hello-world | jq '{locale, title}'
# → { "locale": "fr", "title": "Bonjour le Monde" }

# Arabic
curl -s -H 'Accept-Language: ar-SA,ar;q=0.9' \
  http://localhost:8787/content/hello-world | jq '{locale, title}'
# → { "locale": "ar", "title": "مرحباً بالعالم" }

# Verify Vary and Link headers
curl -sI -H 'Accept-Language: de' http://localhost:8787/content/hello-world \
  | grep -iE 'vary|content-language|link'
```

## Related

- `workers-translation-missing-key-alert-d1.md` — detecting missing locale rows in D1
- `workers-bidirectional-text-rtl-html-rewriter.md` — RTL transforms after locale detection
- `workers-number-system-arabic-indic.md` — numeral formatting per resolved locale

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://www.rfc-editor.org/rfc/rfc9110#name-accept-language
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Vary
