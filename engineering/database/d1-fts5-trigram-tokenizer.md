# D1 FTS5 Trigram Tokenizer for Substring and Fuzzy Search

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need substring search (e.g. `LIKE '%query%'`) or typo-tolerant fuzzy matching on a D1 table but the default FTS5 `unicode61` tokenizer only matches whole-word prefixes. Users typing partial product SKUs, email fragments, or misspelled names get zero results even though matching rows exist.

## Context

SQLite's FTS5 extension ships a `trigram` tokenizer since SQLite 3.41 (Cloudflare D1 bundles a recent SQLite build that includes it). The trigram tokenizer breaks every string into overlapping three-character windows (`"hello"` → `"hel"`, `"ell"`, `"llo"`), indexing each window. This lets `MATCH 'ell'` find `"hello"` — true substring search without a sequential scan. The trade-off is a larger FTS index (roughly 3× the raw text size) and slightly slower inserts; for tables under a few hundred thousand rows in D1 this is acceptable.

## Creating the Trigram FTS5 Virtual Table

```typescript
// migrations/0010_trigram_search.sql (run via wrangler d1 migrations apply)
const MIGRATION = `
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
  product_id UNINDEXED,
  name,
  sku,
  description,
  tokenize = 'trigram'          -- key: trigram instead of unicode61
);

-- Populate from the real table after creation
INSERT INTO products_fts (product_id, name, sku, description)
SELECT id, name, sku, description FROM products;

-- Keep in sync with triggers
CREATE TRIGGER products_fts_insert AFTER INSERT ON products BEGIN
  INSERT INTO products_fts (product_id, name, sku, description)
  VALUES (new.id, new.name, new.sku, new.description);
END;

CREATE TRIGGER products_fts_update AFTER UPDATE ON products BEGIN
  DELETE FROM products_fts WHERE product_id = old.id;
  INSERT INTO products_fts (product_id, name, sku, description)
  VALUES (new.id, new.name, new.sku, new.description);
END;

CREATE TRIGGER products_fts_delete AFTER DELETE ON products BEGIN
  DELETE FROM products_fts WHERE product_id = old.id;
END;
`;
```

## Querying from a Cloudflare Worker

```typescript
// src/search.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

interface ProductRow {
  id: number;
  name: string;
  sku: string;
  price_cents: number;
  rank: number;
}

export async function searchProducts(
  env: Env,
  query: string,
  limit = 20,
  offset = 0
): Promise<ProductRow[]> {
  // Trigram tokenizer does NOT require the * prefix operator for substring.
  // Wrap the raw query in double quotes to treat it as a literal phrase.
  const ftsQuery = `"${query.replace(/"/g, '""')}"`;

  const { results } = await env.DB.prepare(
    `SELECT
       p.id,
       p.name,
       p.sku,
       p.price_cents,
       bm25(products_fts) AS rank
     FROM products_fts
     JOIN products p ON p.id = products_fts.product_id
     WHERE products_fts MATCH ?
     ORDER BY rank          -- lower bm25 = better match
     LIMIT ? OFFSET ?`
  )
    .bind(ftsQuery, limit, offset)
    .all<ProductRow>();

  return results;
}

// Handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const q = url.searchParams.get('q')?.trim();

    if (!q || q.length < 3) {
      return Response.json({ error: 'Query must be at least 3 characters' }, { status: 400 });
    }

    const rows = await searchProducts(env, q);
    return Response.json({ results: rows });
  },
};
```

## Case-Insensitive and Diacritic-Folded Search

```typescript
// src/normalise.ts
// The trigram tokenizer lowercases by default; for diacritic folding
// normalise on write so stored text and queries match.

export function normaliseSearchText(text: string): string {
  return text
    .normalize('NFD')                    // decompose diacritics
    .replace(/[̀-ͯ]/g, '')    // strip combining marks
    .toLowerCase();
}

// When inserting / updating:
async function upsertProduct(env: Env, product: {
  id: number; name: string; sku: string; description: string;
}) {
  // Normalise the real columns so FTS index and source stay aligned
  const normName = normaliseSearchText(product.name);
  const normDesc = normaliseSearchText(product.description);

  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO products (id, name, sku, description)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         name = excluded.name,
         sku   = excluded.sku,
         description = excluded.description`
    ).bind(product.id, normName, product.sku, normDesc),
    // Trigger handles FTS sync automatically
  ]);
}
```

## Highlighting Matched Snippets

```typescript
// Use FTS5 built-in highlight() and snippet() functions
export async function searchWithSnippets(env: Env, query: string) {
  const ftsQuery = `"${query.replace(/"/g, '""')}"`;

  const { results } = await env.DB.prepare(
    `SELECT
       p.id,
       highlight(products_fts, 1, '<mark>', '</mark>') AS name_highlighted,
       snippet(products_fts, 3, '<mark>', '</mark>', '…', 32) AS description_snippet,
       bm25(products_fts) AS rank
     FROM products_fts
     JOIN products p ON p.id = products_fts.product_id
     WHERE products_fts MATCH ?
     ORDER BY rank
     LIMIT 10`
  )
    .bind(ftsQuery)
    .all<{ id: number; name_highlighted: string; description_snippet: string; rank: number }>();

  return results;
}
```

## Anti-patterns

- Using `LIKE '%query%'` on large tables instead of trigram FTS — causes full table scan with no index support.
- Applying the `*` prefix operator (`query*`) with the trigram tokenizer — the trigram tokenizer ignores it; it is only meaningful with `unicode61`.
- Indexing very large text blobs (multi-KB descriptions) with trigram — the index grows 3× the content size; store a separate searchable summary column instead.

## Gotchas

- The trigram tokenizer requires query strings of at least 3 characters; shorter queries return zero results silently. Always validate `q.length >= 3` before hitting D1.
- `bm25()` returns negative values in SQLite FTS5 — `ORDER BY rank` (ascending) gives best-match-first, not `ORDER BY rank DESC`.
- Triggers created in migrations run inside the same D1 transaction; if your migration rolls back, trigger creation rolls back too — safe but verify with `sqlite_master` after applying.

## Verification

```bash
# Apply migration
wrangler d1 migrations apply MY_DB --remote

# Confirm tokenizer is registered
wrangler d1 execute MY_DB --remote \
  --command "SELECT * FROM sqlite_master WHERE name = 'products_fts';"

# Smoke-test substring match
wrangler d1 execute MY_DB --remote \
  --command "SELECT product_id FROM products_fts WHERE products_fts MATCH '\"SKU-00\"' LIMIT 5;"

# Check index size
wrangler d1 execute MY_DB --remote \
  --command "SELECT name, pgsize FROM dbstat WHERE name LIKE 'products_fts%' ORDER BY pgsize DESC;"
```

## Related

- `database/d1-full-text-search-fts5.md`
- `database/full-text-search-sqlite-fts5.md`
- `database/d1-json-columns-partial-indexes.md`
- `database/sqlite-virtual-table-d1-workers.md`

## Sources

- https://www.sqlite.org/fts5.html#the_trigram_tokenizer
- https://developers.cloudflare.com/d1/sql-api/
- https://developers.cloudflare.com/d1/tutorials/
