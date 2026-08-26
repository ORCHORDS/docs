# D1 Inverted Index Manual Search in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need tag-based or keyword search where FTS5 is too heavy or you want precise control over tokenisation, ranking, and faceting. A hand-rolled inverted index in D1 — a `terms` table mapping tokens to document IDs — gives sub-millisecond lookup with full control over the token pipeline.

## Context

FTS5 is excellent for full prose search, but inverted indexes shine for structured tokens: product tags, skill keywords, permission names, category slugs. The index is two tables: `terms(term TEXT, doc_id INTEGER, weight REAL)` plus a covering index on `(term, weight DESC, doc_id)`. Queries become `SELECT doc_id FROM terms WHERE term = ?` followed by optional ranking.

---

## Schema

```sql
-- Run once via D1 migration
CREATE TABLE IF NOT EXISTS documents (
  id      INTEGER PRIMARY KEY,
  title   TEXT    NOT NULL,
  body    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS terms (
  term    TEXT    NOT NULL,
  doc_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  weight  REAL    NOT NULL DEFAULT 1.0,
  PRIMARY KEY (term, doc_id)
);

-- Covering index: term lookup → ranked doc list without touching the heap
CREATE INDEX IF NOT EXISTS idx_terms_term_weight ON terms (term, weight DESC, doc_id);
```

---

## Tokeniser

```typescript
// tokeniser.ts
export function tokenise(text: string): Map<string, number> {
  const freq = new Map<string, number>();
  const tokens = text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 2);

  for (const token of tokens) {
    freq.set(token, (freq.get(token) ?? 0) + 1);
  }
  return freq;
}

// TF weight: term frequency normalised by document length
export function tfWeight(termFreq: number, docLength: number): number {
  return termFreq / Math.log(1 + docLength);
}
```

---

## Indexing a Document

```typescript
// index.ts
import { tokenise, tfWeight } from './tokeniser';

export async function indexDocument(
  db: D1Database,
  id: number,
  title: string,
  body: string
): Promise<void> {
  const text = `${title} ${title} ${body}`; // title gets 2× weight implicitly
  const freq = tokenise(text);
  const docLen = freq.size;

  const stmts = [
    db.prepare('DELETE FROM terms WHERE doc_id = ?').bind(id),
    ...Array.from(freq.entries()).map(([term, count]) =>
      db
        .prepare('INSERT OR REPLACE INTO terms (term, doc_id, weight) VALUES (?, ?, ?)')
        .bind(term, id, tfWeight(count, docLen))
    ),
  ];

  await db.batch(stmts);
}
```

---

## Single-term and Multi-term Query

```typescript
// search.ts
export interface SearchResult {
  doc_id: number;
  score: number;
}

// Single-term lookup — uses the covering index
export async function searchSingle(db: D1Database, term: string): Promise<SearchResult[]> {
  const rows = await db
    .prepare('SELECT doc_id, weight AS score FROM terms WHERE term = ? ORDER BY weight DESC LIMIT 20')
    .bind(term.toLowerCase())
    .all<SearchResult>();
  return rows.results;
}

// Multi-term AND search: intersect doc_id sets, sum weights for ranking
export async function searchMulti(db: D1Database, query: string): Promise<SearchResult[]> {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];

  // Build: SELECT doc_id, SUM(weight) AS score FROM terms
  //        WHERE term IN (?,?,?) GROUP BY doc_id
  //        HAVING COUNT(DISTINCT term) = N   -- AND semantics
  //        ORDER BY score DESC LIMIT 20
  const placeholders = terms.map(() => '?').join(', ');
  const rows = await db
    .prepare(
      `SELECT doc_id, SUM(weight) AS score
         FROM terms
        WHERE term IN (${placeholders})
        GROUP BY doc_id
       HAVING COUNT(DISTINCT term) = ?
        ORDER BY score DESC
        LIMIT 20`
    )
    .bind(...terms, terms.length)
    .all<SearchResult>();

  return rows.results;
}
```

---

## Fetch Documents for Results

```typescript
// worker.ts
import { searchMulti } from './search';

export interface Env { DB: D1Database }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const q = new URL(request.url).searchParams.get('q') ?? '';
    const hits = await searchMulti(env.DB, q);
    if (hits.length === 0) return Response.json([]);

    const ids = hits.map(h => h.doc_id);
    const scoreMap = new Map(hits.map(h => [h.doc_id, h.score]));

    const placeholders = ids.map(() => '?').join(', ');
    const docs = await env.DB
      .prepare(`SELECT id, title FROM documents WHERE id IN (${placeholders})`)
      .bind(...ids)
      .all<{ id: number; title: string }>();

    const results = docs.results
      .map(d => ({ ...d, score: scoreMap.get(d.id) ?? 0 }))
      .sort((a, b) => b.score - a.score);

    return Response.json(results);
  },
};
```

---

## Incremental Index Maintenance via Cron

```typescript
// cron-reindex.ts — runs on a Cron Trigger
export async function reindexStale(db: D1Database): Promise<void> {
  // Track last-indexed timestamp in a meta table
  const meta = await db
    .prepare("SELECT value FROM _meta WHERE key = 'last_indexed_at'")
    .first<{ value: string }>();
  const since = meta?.value ?? '1970-01-01T00:00:00Z';

  const stale = await db
    .prepare('SELECT id, title, body FROM documents WHERE updated_at > ? LIMIT 500')
    .bind(since)
    .all<{ id: number; title: string; body: string }>();

  // Import indexDocument from index.ts
  const { indexDocument } = await import('./index');
  for (const doc of stale.results) {
    await indexDocument(db, doc.id, doc.title, doc.body);
  }

  await db
    .prepare("INSERT OR REPLACE INTO _meta (key, value) VALUES ('last_indexed_at', ?)")
    .bind(new Date().toISOString())
    .run();
}
```

---

## Anti-patterns

- **No covering index** — omitting `idx_terms_term_weight` forces D1 to scan all rows for a term; always include `weight DESC, doc_id` in the index to avoid the table heap lookup.
- **Indexing stop-words** — tokens like "the", "and", "is" produce massive posting lists with zero discriminative value; filter them in `tokenise`.
- **OR search via `IN` without `HAVING`** — returning all doc_ids that match *any* term without `HAVING COUNT(DISTINCT term) = N` gives OR semantics; make this explicit.
- **Re-indexing inside a single D1 batch larger than 100 statements** — D1 batch limit is 100 statements; chunk large documents.

## Gotchas

- D1's SQLite runs without the ICU extension, so lowercasing non-ASCII characters must be done in TypeScript, not in SQL `LOWER()`.
- The `PRIMARY KEY (term, doc_id)` on `terms` acts as a unique constraint and makes `INSERT OR REPLACE` safe for re-indexing; without it you'd accumulate duplicate rows.
- Large term vocabularies (>500 K unique terms) can make the `terms` table a hot spot; consider sharding term tables by first-letter prefix.
- `COUNT(DISTINCT term)` inside `HAVING` may be slow if the `IN` list is large; benchmark above 10 terms.

## Verification

```typescript
// Smoke test: index two docs, confirm ranked retrieval
async function smokeTest(db: D1Database): Promise<void> {
  const { indexDocument } = await import('./index');
  const { searchMulti } = await import('./search');

  await db.prepare('INSERT OR REPLACE INTO documents (id, title, body) VALUES (1, ?, ?)')
    .bind('TypeScript Guide', 'typescript types generics workers').run();
  await db.prepare('INSERT OR REPLACE INTO documents (id, title, body) VALUES (2, ?, ?)')
    .bind('Python Intro', 'python functions classes tutorial').run();

  await indexDocument(db, 1, 'TypeScript Guide', 'typescript types generics workers');
  await indexDocument(db, 2, 'Python Intro', 'python functions classes tutorial');

  const results = await searchMulti(db, 'typescript workers');
  console.assert(results[0].doc_id === 1, 'TypeScript doc should rank first');
}
```

## Related

- `d1-full-text-search-fts5.md`
- `d1-fts5-bm25-custom-ranking-workers.md`
- `d1-covering-index-composite-key-workers.md`
- `d1-json-aggregation-analytics.md`

## Sources

- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- SQLite index mechanics: https://www.sqlite.org/queryplanner.html
- Inverted index fundamentals: https://en.wikipedia.org/wiki/Inverted_index
