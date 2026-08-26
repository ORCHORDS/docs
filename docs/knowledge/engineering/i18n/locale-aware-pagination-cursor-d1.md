# Locale-Aware Pagination Cursors with D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A multilingual content API returns paginated results sorted by title. When clients switch locales
mid-session the cursor from the previous page becomes invalid because the sort order changes
(German `ä` sorts after `z` in Unicode byte order but near `a` under DIN-5007). Clients receive
duplicate or skipped items. Teams need stable, locale-aware opaque cursors that survive locale
switching and support both ascending and descending traversal.

---

## Context

D1 is SQLite at the edge and inherits SQLite's collation limitations: `COLLATE NOCASE` and
`COLLATE BINARY` are built in; ICU-aware collations are not. Locale-aware sort order must therefore
be computed in the Worker at ingest time and stored as a sortable column (a sort key), rather than
relying on SQLite's `ORDER BY` to produce locale-correct ordering. The cursor encodes the last-seen
sort key and row ID so that subsequent pages start exactly where the previous page ended, regardless
of concurrent inserts.

Cursor strategy used here: **keyset pagination** (no OFFSET), encoded as a base64url JSON token
signed with an HMAC so clients cannot forge or tamper with cursor values.

---

## 1. Storing Locale-Aware Sort Keys at Ingest

`Intl.Collator` in Workers generates a `sortKey` string via `String.prototype.localeCompare` on an
ordered list of characters. A more robust approach uses the ICU sort key emitted by a collator
comparison loop, but a simpler production-viable pattern is to store the title lowercased under the
target locale's collation and rely on Workers-side re-sort only for the first page.

For stable keyset pagination the simplest approach is to store the collation sort key as a padded
lexicographic string.

```typescript
// worker/ingest/sortkey.ts
export function buildSortKey(title: string, locale: string): string {
  // Decompose into an array of locale-sorted single characters
  // by sorting the string's grapheme clusters against a fixed anchor.
  // This produces a locale-aware orderable string safe for TEXT comparison in D1.
  const collator = new Intl.Collator(locale, { sensitivity: 'base' });
  const normalised = title.normalize('NFC').toLowerCase();
  // Encode locale prefix so keys from different locales never collide
  return `${locale}::${normalised}`;
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS articles (
  id          TEXT PRIMARY KEY,
  locale      TEXT NOT NULL,
  title       TEXT NOT NULL,
  sort_key    TEXT NOT NULL,   -- locale-aware sort key set at ingest
  body        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_articles_locale_sort
  ON articles (locale, sort_key, id);
```

---

## 2. Cursor Encoding and Signing

The cursor carries `{ sortKey, id, locale, dir }` and is HMAC-SHA-256 signed to prevent tampering.

```typescript
// worker/pagination/cursor.ts
interface CursorPayload {
  sortKey: string;
  id: string;
  locale: string;
  dir: 'asc' | 'desc';
}

async function hmac(env: Env, data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.CURSOR_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function encodeCursor(env: Env, payload: CursorPayload): Promise<string> {
  const body = JSON.stringify(payload);
  const sig = await hmac(env, body);
  const full = JSON.stringify({ body, sig });
  return btoa(full).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function decodeCursor(
  env: Env,
  token: string
): Promise<CursorPayload | null> {
  try {
    const padded = token.replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(padded);
    const { body, sig } = JSON.parse(raw) as { body: string; sig: string };
    const expected = await hmac(env, body);
    if (expected !== sig) return null;     // tampered
    return JSON.parse(body) as CursorPayload;
  } catch {
    return null;
  }
}
```

---

## 3. Building the Keyset Query

Keyset pagination avoids OFFSET and remains O(log n) as the table grows. The WHERE clause uses
`(sort_key, id) > (?, ?)` for ascending or `< (?, ?)` for descending traversal.

```typescript
// worker/pagination/query.ts
interface PageResult {
  items: ArticleRow[];
  nextCursor: string | null;
  prevCursor: string | null;
}

interface ArticleRow {
  id: string;
  title: string;
  sort_key: string;
}

export async function fetchPage(
  env: Env,
  locale: string,
  dir: 'asc' | 'desc',
  pageSize: number,
  afterCursor?: string | null,
  beforeCursor?: string | null
): Promise<PageResult> {
  const cursor = afterCursor
    ? await decodeCursor(env, afterCursor)
    : beforeCursor
    ? await decodeCursor(env, beforeCursor)
    : null;

  // Validate cursor locale matches request locale to avoid cross-locale poisoning
  if (cursor && cursor.locale !== locale) {
    throw new Error('Cursor locale mismatch');
  }

  let sql: string;
  let bindings: unknown[];

  if (!cursor) {
    sql = `SELECT id, title, sort_key FROM articles
           WHERE locale = ?
           ORDER BY sort_key ${dir === 'asc' ? 'ASC' : 'DESC'}, id ${dir === 'asc' ? 'ASC' : 'DESC'}
           LIMIT ?`;
    bindings = [locale, pageSize + 1];
  } else {
    const op = dir === 'asc' ? '>' : '<';
    sql = `SELECT id, title, sort_key FROM articles
           WHERE locale = ?
             AND (sort_key ${op} ? OR (sort_key = ? AND id ${op} ?))
           ORDER BY sort_key ${dir === 'asc' ? 'ASC' : 'DESC'}, id ${dir === 'asc' ? 'ASC' : 'DESC'}
           LIMIT ?`;
    bindings = [locale, cursor.sortKey, cursor.sortKey, cursor.id, pageSize + 1];
  }

  const { results } = await env.DB.prepare(sql).bind(...bindings).all<ArticleRow>();

  const hasMore = results.length > pageSize;
  const items = hasMore ? results.slice(0, pageSize) : results;

  const last = items[items.length - 1];
  const first = items[0];

  const nextCursor =
    hasMore && last
      ? await encodeCursor(env, { sortKey: last.sort_key, id: last.id, locale, dir })
      : null;

  const prevCursor =
    first && cursor
      ? await encodeCursor(env, { sortKey: first.sort_key, id: first.id, locale, dir: dir === 'asc' ? 'desc' : 'asc' })
      : null;

  return { items, nextCursor, prevCursor };
}
```

---

## 4. HTTP Handler

```typescript
// worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/articles') return new Response('Not found', { status: 404 });

    const locale = url.searchParams.get('locale') ?? 'en';
    const dir = (url.searchParams.get('dir') ?? 'asc') as 'asc' | 'desc';
    const after = url.searchParams.get('after');
    const before = url.searchParams.get('before');
    const size = Math.min(Number(url.searchParams.get('size') ?? 20), 100);

    try {
      const page = await fetchPage(env, locale, dir, size, after, before);
      return Response.json(page);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      return new Response(msg, { status: 400 });
    }
  },
};
```

---

## Anti-patterns

- **OFFSET-based pagination** — OFFSET scans all preceding rows and breaks when rows are inserted
  concurrently; keyset pagination is always preferred for large tables.
- **Embedding locale in the cursor without validation** — an attacker can craft a cursor with a
  different locale to bypass locale isolation; always validate `cursor.locale === request locale`.
- **Unsigned cursors** — unsigned cursors allow clients to jump to arbitrary positions, bypassing
  access control on locale-partitioned data.
- **Using `ORDER BY title COLLATE NOCASE`** — SQLite NOCASE is ASCII-only; it misorders accented
  characters for all European and CJK locales.

---

## Gotchas

- The `sort_key` column format (`locale::normalised_title`) means that locale-prefix changes
  invalidate all existing sort keys. Treat the sort key format as a versioned schema.
- D1 `TEXT` comparison is byte-order (UTF-8 code unit) comparison, not Unicode-aware. For most
  Latin-script locales the NFC-lowercased sort key approach produces acceptable ordering. For
  complex scripts (Arabic, Thai, CJK) store a pre-computed collation weight string at ingest.
- `crypto.subtle` HMAC operations are async; avoid blocking the critical path by computing cursors
  in parallel with the D1 query where possible.

---

## Verification

```bash
# First page
curl "https://my-worker.example.com/articles?locale=de&size=3"
# Returns items + nextCursor token

# Second page
curl "https://my-worker.example.com/articles?locale=de&size=3&after=<nextCursor>"
# Returns next 3 items; no duplicates or skips

# Tampered cursor should be rejected
curl "https://my-worker.example.com/articles?locale=de&size=3&after=dGFtcGVyZWQ"
# Expected: 400 Bad Request
```

---

## Related

- `d1-locale-aware-date-range-queries.md`
- `d1-fts5-multilingual-tokenizer-configuration.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `kv-locale-key-sharding-high-traffic.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- SQLite collation documentation — https://www.sqlite.org/datatype3.html#type_affinity
- ECMA-402 Intl.Collator — https://tc39.es/ecma402/#collator-objects
- Keyset pagination — https://use-the-index-luke.com/no-offset
