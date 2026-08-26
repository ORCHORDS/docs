# D1 FTS5 Multilingual Tokenizer Configuration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare D1-backed multilingual product catalogue needs full-text search across
English, German, Japanese, and Arabic content. SQLite's default FTS5 `unicode61`
tokenizer splits on whitespace and basic Unicode boundaries but produces poor results for
CJK languages (no word segmentation) and fails to fold Arabic diacritics (tashkeel).
You need to configure FTS5 tokenizers per locale and fall back gracefully in the Workers
edge runtime.

## Context

D1 runs SQLite at the edge. SQLite FTS5 ships with three built-in tokenizers: `ascii`,
`unicode61`, and `porter`. Custom tokenizers require a compiled extension, which D1 does
not support. The workaround is to perform locale-aware tokenization in the Worker before
inserting into FTS5, storing the result in a dedicated `tokens` column, and querying
that column. This gives full control over tokenization without any SQLite extension.

Applicable stack: Workers, D1 (FTS5 virtual tables), optional Workers AI (embedding
search fallback).

---

## 1. Schema: Separate Token Column per Language Group

```sql
-- migration 001_fts5_multilingual.sql

CREATE TABLE products (
  id          INTEGER PRIMARY KEY,
  locale      TEXT NOT NULL,
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  -- pre-tokenized, space-separated tokens for FTS
  title_tokens       TEXT NOT NULL DEFAULT '',
  description_tokens TEXT NOT NULL DEFAULT ''
);

-- One FTS5 virtual table per language group keeps tokenizer
-- options isolated and avoids cross-language noise.
CREATE VIRTUAL TABLE products_fts_latin USING fts5(
  id UNINDEXED,
  title_tokens,
  description_tokens,
  content='products',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 1'
);

CREATE VIRTUAL TABLE products_fts_cjk USING fts5(
  id UNINDEXED,
  title_tokens,
  description_tokens,
  content='products',
  content_rowid='id',
  tokenize='unicode61'  -- character n-gram done in Worker
);

CREATE VIRTUAL TABLE products_fts_arabic USING fts5(
  id UNINDEXED,
  title_tokens,
  description_tokens,
  content='products',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 1'
);
```

---

## 2. Worker-Side Tokenizer per Locale

```typescript
// src/lib/tokenizer.ts

/** Latin/Germanic: lowercase + NFD + strip combining marks */
function tokenizeLatin(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // strip combining diacritics
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** CJK: character-level bigrams to approximate word boundaries */
function tokenizeCJK(text: string): string {
  const tokens: string[] = [];
  // Emit individual characters and bigrams for recall
  const chars = [...text]; // spread handles surrogate pairs
  for (let i = 0; i < chars.length; i++) {
    tokens.push(chars[i]);
    if (i < chars.length - 1) tokens.push(chars[i] + chars[i + 1]);
  }
  return tokens.join(' ');
}

/** Arabic: strip tashkeel (diacritics) + normalize alef variants */
function tokenizeArabic(text: string): string {
  return text
    .replace(/[ً-ٟؐ-ؚۖ-ۜ]/g, '') // tashkeel
    .replace(/[آأإا]/g, 'ا') // normalize alef
    .replace(/ة/g, 'ه') // tah marbuta → hah
    .replace(/\s+/g, ' ')
    .trim();
}

const CJK_RANGE = /[　-鿿가-힯豈-﫿]/u;
const ARABIC_RANGE = /[؀-ۿ]/u;

export function tokenize(text: string, locale: string): string {
  if (ARABIC_RANGE.test(text) || locale.startsWith('ar')) {
    return tokenizeArabic(text);
  }
  if (CJK_RANGE.test(text) || /^(ja|zh|ko)/.test(locale)) {
    return tokenizeCJK(text);
  }
  return tokenizeLatin(text); // default: Latin/Germanic/Cyrillic
}

export function ftsTable(locale: string): string {
  if (/^(ja|zh|ko)/.test(locale)) return 'products_fts_cjk';
  if (/^ar/.test(locale)) return 'products_fts_arabic';
  return 'products_fts_latin';
}
```

---

## 3. Insert with Pre-tokenized Columns

```typescript
// src/lib/products-repo.ts
import type { D1Database } from '@cloudflare/workers-types';
import { tokenize } from './tokenizer';

interface ProductInsert {
  locale: string;
  title: string;
  description: string;
}

export async function insertProduct(
  db: D1Database,
  product: ProductInsert,
): Promise<number> {
  const titleTokens = tokenize(product.title, product.locale);
  const descTokens = tokenize(product.description, product.locale);

  const result = await db
    .prepare(
      `INSERT INTO products (locale, title, description, title_tokens, description_tokens)
       VALUES (?, ?, ?, ?, ?)
       RETURNING id`,
    )
    .bind(
      product.locale,
      product.title,
      product.description,
      titleTokens,
      descTokens,
    )
    .first<{ id: number }>();

  if (!result) throw new Error('Insert failed');
  return result.id;
}
```

---

## 4. Search Across Locale-Specific FTS Tables

```typescript
// src/lib/search.ts
import type { D1Database } from '@cloudflare/workers-types';
import { tokenize, ftsTable } from './tokenizer';

interface SearchResult {
  id: number;
  title: string;
  rank: number;
}

export async function search(
  db: D1Database,
  query: string,
  locale: string,
  limit = 20,
): Promise<SearchResult[]> {
  const tokenizedQuery = tokenize(query, locale);
  const table = ftsTable(locale);

  // FTS5 MATCH with phrase prefix for partial-word search
  const ftsQuery = tokenizedQuery
    .split(' ')
    .filter(Boolean)
    .map((t) => `"${t}"*`) // prefix match per token
    .join(' ');

  const rows = await db
    .prepare(
      `SELECT p.id, p.title, fts.rank
       FROM ${table} fts
       JOIN products p ON p.id = fts.id
       WHERE fts MATCH ?
         AND p.locale = ?
       ORDER BY fts.rank
       LIMIT ?`,
    )
    .bind(ftsQuery, locale, limit)
    .all<SearchResult>();

  return rows.results;
}
```

---

## 5. Keeping FTS5 Indexes in Sync (Content Tables)

FTS5 `content=` tables require manual sync on updates and deletes:

```typescript
// src/lib/fts-sync.ts
import type { D1Database } from '@cloudflare/workers-types';
import { tokenize, ftsTable } from './tokenizer';

export async function syncFTS(
  db: D1Database,
  id: number,
  locale: string,
  titleTokens: string,
  descTokens: string,
): Promise<void> {
  const table = ftsTable(locale);
  // Delete old FTS row then re-insert (content table pattern)
  await db.batch([
    db
      .prepare(`DELETE FROM ${table} WHERE id = ?`)
      .bind(id),
    db
      .prepare(
        `INSERT INTO ${table} (id, title_tokens, description_tokens)
         VALUES (?, ?, ?)`,
      )
      .bind(id, titleTokens, descTokens),
  ]);
}

export async function deleteFTS(
  db: D1Database,
  id: number,
  locale: string,
): Promise<void> {
  const table = ftsTable(locale);
  await db.prepare(`DELETE FROM ${table} WHERE id = ?`).bind(id).run();
}
```

---

## 6. Fallback to Workers AI Embeddings for Low-Recall Queries

When FTS5 returns zero results, fall back to semantic vector search via Vectorize:

```typescript
// src/lib/semantic-fallback.ts
import type { Ai, VectorizeIndex } from '@cloudflare/workers-types';

export async function semanticFallback(
  ai: Ai,
  vectorize: VectorizeIndex,
  query: string,
  locale: string,
  topK = 10,
): Promise<{ id: string; score: number }[]> {
  const { data } = await ai.run('@cf/baai/bge-base-en-v1.5', {
    text: [query],
  });
  const embedding = data[0];

  const results = await vectorize.query(embedding, {
    topK,
    filter: { locale },
    returnValues: false,
    returnMetadata: false,
  });

  return results.matches.map((m) => ({ id: m.id, score: m.score }));
}
```

---

## Anti-patterns

- **Using a single FTS5 table for all locales** — Latin `remove_diacritics` mangling
  applied to Arabic or CJK text produces garbage tokens.
- **Relying on FTS5 `porter` stemmer for non-English** — porter is English-only and
  incorrectly stems German, French, and Spanish words.
- **Querying raw `title` / `description` columns with FTS5 MATCH** — you must query the
  pre-tokenized `*_tokens` columns; raw columns contain untokenized text and MATCH will
  not apply your Worker-side normalization.
- **Forgetting to sync FTS5 content tables on UPDATE/DELETE** — content tables are not
  automatically updated; the primary table and FTS index diverge silently.
- **CJK unigrams only (no bigrams)** — single characters produce massive index recall
  with very low precision. Bigram pairs significantly improve query quality.

## Gotchas

- FTS5 `MATCH` query strings with special characters (`"`, `-`, `*`) must be escaped or
  wrapped in quotes. Unescaped `-` is interpreted as NOT.
- D1 FTS5 `rank` column returns a negative float (BM25 score). Lower (more negative)
  rank = worse match. Sort `ORDER BY fts.rank` ascending for best-first.
- D1 does not support `fts5vocab` auxiliary tables — you cannot enumerate indexed tokens
  for autocomplete. Build a separate autocomplete table in D1 if needed.
- The `content=` parameter makes FTS5 read-through to the base table for snippet/highlight
  functions (`snippet()`, `highlight()`). These functions require a `content` table and
  will return empty strings without one.
- Workers AI `@cf/baai/bge-base-en-v1.5` embeds English text only. For multilingual
  semantic fallback use `@cf/baai/bge-m3` (multilingual model).

## Verification

```sql
-- Confirm FTS5 tables were created
SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name LIKE 'products_fts%';

-- Test a Latin query
INSERT INTO products (locale, title, description, title_tokens, description_tokens)
VALUES ('de', 'Käsekuchen', 'Leckerer Käsekuchen', 'kasekuchen', 'leckerer kasekuchen');
SELECT id FROM products_fts_latin WHERE products_fts_latin MATCH '"kasekuchen"';

-- Confirm Arabic tashkeel stripped
SELECT title_tokens FROM products WHERE locale = 'ar' LIMIT 1;
```

```typescript
// test/tokenizer.test.ts
import { tokenize } from '../src/lib/tokenizer';

describe('tokenize', () => {
  it('strips German umlaut diacritics', () => {
    expect(tokenize('Käsekuchen', 'de')).toBe('kasekuchen');
  });

  it('emits CJK bigrams', () => {
    const tokens = tokenize('東京', 'ja').split(' ');
    expect(tokens).toContain('東京');
    expect(tokens).toContain('東');
    expect(tokens).toContain('京');
  });

  it('strips Arabic tashkeel', () => {
    // كِتَاب → كتاب
    expect(tokenize('كِتَاب', 'ar')).toBe('كتاب');
  });
});
```

## Related

- `accent-insensitive-search-pipeline-2026.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `translation-memory-semantic-vectorize-workers.md`
- `d1-schema-locale-preferences-content-translations-2026.md`

## Sources

- SQLite FTS5 documentation: https://www.sqlite.org/fts5.html
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Unicode CJK Unified Ideographs block: https://www.unicode.org/charts/PDF/U4E00.pdf
