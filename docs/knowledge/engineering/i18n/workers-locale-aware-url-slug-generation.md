# Locale-Aware URL Slug Generation for Multilingual Titles in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Content editors submit article titles in Chinese, Cyrillic, Arabic, or mixed scripts. You need to produce ASCII URL slugs that are human-readable, SEO-friendly, collision-free, and reversible to the canonical content ID. A naïve `title.replace(/\s+/g, '-').toLowerCase()` produces empty strings or garbled `%XX` sequences for non-Latin input.

## Context

- Cloudflare Workers handling a POST /articles endpoint
- D1 storing articles with both the original `title` and the generated `slug`
- KV providing a `slug → article_id` lookup table for fast routing
- Transliteration handled by a pure-TypeScript map (no npm transliteration libraries to bundle)

---

## Section 1: Transliteration Maps for CJK, Cyrillic, and Arabic

```typescript
// src/lib/transliterate.ts

// Cyrillic → Latin (BGN/PCGN romanisation, simplified)
const CYRILLIC_MAP: Record<string, string> = {
  'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh',
  'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
  'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
  'ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu',
  'я':'ya',
};

// Arabic → Latin (simplified ALA-LC without diacritics)
const ARABIC_MAP: Record<string, string> = {
  'ا':'a','ب':'b','ت':'t','ث':'th','ج':'j','ح':'h','خ':'kh','د':'d',
  'ذ':'dh','ر':'r','ز':'z','س':'s','ش':'sh','ص':'s','ض':'d','ط':'t',
  'ظ':'z','ع':'a','غ':'gh','ف':'f','ق':'q','ك':'k','ل':'l','م':'m',
  'ن':'n','ه':'h','و':'w','ي':'y','ء':"'",'ة':'h',
};

// CJK: use Unicode code point as hex (true romanisation needs a full dictionary)
function cjkToHex(char: string): string {
  return 'u' + char.codePointAt(0)!.toString(16).padStart(4, '0');
}

const CJK_RANGE_RE = /[　-鿿가-힯豈-﫿]/u;

export function transliterate(text: string): string {
  let result = '';
  for (const char of text) {
    const lo = char.toLowerCase();
    if (CYRILLIC_MAP[lo] !== undefined) {
      result += char === char.toUpperCase() && char !== lo
        ? CYRILLIC_MAP[lo].toUpperCase()
        : CYRILLIC_MAP[lo];
    } else if (ARABIC_MAP[lo] !== undefined) {
      result += ARABIC_MAP[lo];
    } else if (CJK_RANGE_RE.test(char)) {
      result += cjkToHex(char);
    } else {
      result += char;
    }
  }
  return result;
}
```

---

## Section 2: Slug Generation with Deduplication in D1

```typescript
// src/lib/slugify.ts
import { transliterate } from './transliterate';

export function slugify(title: string): string {
  return transliterate(title)
    .normalize('NFD')                    // decompose accented letters
    .replace(/[̀-ͯ]/g, '')     // strip combining diacritics
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')        // non-alphanumeric → hyphen
    .replace(/^-+|-+$/g, '')            // trim leading/trailing hyphens
    .slice(0, 80);                       // max 80 chars
}

// src/lib/slug-dedup.ts
import type { D1Database } from '@cloudflare/workers-types';
import { slugify } from './slugify';

/**
 * Generate a slug from title and ensure it is unique in D1.
 * Appends -2, -3, … until a free slot is found.
 */
export async function uniqueSlug(
  db: D1Database,
  title: string,
  maxAttempts = 10,
): Promise<string> {
  const base = slugify(title);
  if (!base) throw new Error('Title produces empty slug after transliteration');

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const candidate = attempt === 0 ? base : `${base}-${attempt + 1}`;
    const row = await db
      .prepare('SELECT id FROM articles WHERE slug = ?1 LIMIT 1')
      .bind(candidate)
      .first<{ id: string }>();
    if (!row) return candidate;
  }
  // Fallback: append a random suffix
  const suffix = Math.random().toString(36).slice(2, 8);
  return `${base}-${suffix}`;
}
```

---

## Section 3: Storing in D1 and Writing a KV Slug→ID Lookup

```typescript
// src/handlers/create-article.ts
import type { Env } from '../types';
import { uniqueSlug } from '../lib/slug-dedup';

export async function handleCreateArticle(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{ title: string; content: string; locale: string }>();

  if (!body.title?.trim()) {
    return Response.json({ error: 'title is required' }, { status: 400 });
  }

  const slug = await uniqueSlug(env.DB, body.title);
  const id   = crypto.randomUUID();

  // Write to D1
  await env.DB
    .prepare(
      `INSERT INTO articles (id, title, slug, content, locale, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
    )
    .bind(id, body.title, slug, body.content, body.locale, new Date().toISOString())
    .run();

  // Write KV lookup: slug → id (no TTL — slugs are permanent)
  await env.KV.put(`slug:${slug}`, id);

  return Response.json({ id, slug }, { status: 201 });
}

// src/handlers/get-article.ts — fast slug routing via KV
export async function handleGetArticle(
  request: Request,
  env: Env,
): Promise<Response> {
  const slug = new URL(request.url).pathname.split('/').pop() ?? '';

  // O(1) KV lookup
  const id = await env.KV.get(`slug:${slug}`);
  if (!id) return Response.json({ error: 'not found' }, { status: 404 });

  const article = await env.DB
    .prepare('SELECT id, title, slug, content, locale, created_at FROM articles WHERE id = ?1')
    .bind(id)
    .first<{ id: string; title: string; slug: string; content: string; locale: string; created_at: string }>();

  if (!article) return Response.json({ error: 'not found' }, { status: 404 });

  return Response.json(article);
}
```

D1 migration:

```sql
-- migrations/0002_articles.sql
CREATE TABLE IF NOT EXISTS articles (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  slug       TEXT NOT NULL UNIQUE,
  content    TEXT NOT NULL,
  locale     TEXT NOT NULL DEFAULT 'en',
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_articles_slug ON articles(slug);
```

---

## Anti-patterns

- **`encodeURIComponent(title)`** as a slug — produces `%E4%BD%A0%E5%A5%BD`, which is valid but opaque and fails naive `LIKE` queries.
- **Not deduplicating** — two articles with titles `Hello World` and `Hello-World` both slug to `hello-world`; the second insert crashes on the UNIQUE constraint.
- **Storing slug only in KV** without D1 — KV is eventually consistent; a race between two Workers could register the same slug for different IDs.
- **Unlimited slug length** — very long CJK hex slugs (`u4e2du6587u5185u5bb9...`) break URL length limits and readability.

## Gotchas

- CJK hex slugs are correct but not human-readable. For Chinese/Japanese production use-cases, consider [pinyin](https://www.npmjs.com/package/pinyin) or [kuroshiro](https://www.npmjs.com/package/kuroshiro) bundled into the Worker.
- Arabic right-to-left text may have Unicode bidirectional control characters (U+200F, U+061C) — strip them before slugifying: `.replace(/[​-‏‪-‮⁠-⁤]/g, '')`.
- `String.prototype.normalize('NFD')` does not transliterate — it only decomposes precomposed characters. You still need the Cyrillic/Arabic maps for non-Latin scripts.
- D1 `UNIQUE` index enforces deduplication at the DB layer as a safety net; the `uniqueSlug()` function reduces the chance of a failed insert but does not eliminate the race — wrap the insert in a retry on `SQLITE_CONSTRAINT_UNIQUE` (error code 2067).

---

## Verification

```bash
# Apply migration
npx wrangler d1 execute my-db --local --file=migrations/0002_articles.sql

# Start worker
npx wrangler dev

# Create an article with a Chinese title
curl -s -X POST http://localhost:8787/articles \
  -H 'Content-Type: application/json' \
  -d '{"title":"你好世界","content":"Hello World in Chinese","locale":"zh"}' | jq
# Expected: { "id": "...", "slug": "u4f60u597du4e16u754c" }

# Create a Cyrillic title
curl -s -X POST http://localhost:8787/articles \
  -H 'Content-Type: application/json' \
  -d '{"title":"Привет мир","content":"Hello World in Russian","locale":"ru"}' | jq
# Expected: { "id": "...", "slug": "privet-mir" }

# Retrieve by slug
curl -s http://localhost:8787/articles/privet-mir | jq '.title'
```

---

## Related

- `documentation/docs/policies/i18n/workers-script-detection-unicode-block.md`
- `documentation/docs/policies/i18n/workers-collator-locale-sort-d1-sqlite.md`
- `documentation/docs/policies/i18n/workers-intl-displaynames-locale-labels.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/normalize
- https://www.iana.org/assignments/language-subtag-registry/ (BCP-47 locale tags)
