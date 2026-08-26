# D1 Alphanumeric Ordering Edge Cases

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Query results sorted by a text column containing numeric components (`"item-2"`, `"item-10"`) return `"item-10"` before `"item-2"` because SQLite uses lexicographic ordering by default. Pagination breaks when row IDs mix letters and digits. `ORDER BY name COLLATE NOCASE` fixes casing but not numeric suffix ordering.

## Context

D1 runs SQLite under the hood. SQLite's default collation for `TEXT` columns is binary — it compares bytes, so `'10' < '2'` because `'1' (0x31) < '2' (0x32)`. There is no built-in `NATURAL` collation in SQLite (unlike PostgreSQL's `pg_trgm` natural sort). The three safe escape hatches are: (1) zero-pad numeric segments at write time, (2) store a separate sortable integer column, or (3) post-process results in the Worker with an in-memory natural sort comparator.

---

## Schema-level Fix: Zero-Pad at Insert Time

If you control the schema, store a `sort_key` column with zero-padded segments. Sorting then becomes a plain `ORDER BY sort_key`.

```typescript
// Worker — build a zero-padded sort key before insert
function naturalSortKey(s: string, padWidth = 6): string {
  return s.replace(/\d+/g, (n) => n.padStart(padWidth, '0'));
}

// "chapter-2"  → "chapter-000002"
// "chapter-10" → "chapter-000010"

await env.DB.prepare(
  `INSERT INTO items (name, sort_key) VALUES (?, ?)`
).bind(name, naturalSortKey(name)).run();
```

Query simply becomes:

```sql
SELECT name FROM items ORDER BY sort_key ASC;
```

Downside: `sort_key` must be regenerated whenever naming conventions change.

---

## Runtime Fix: In-Worker Natural Sort

When the schema is fixed (legacy data, external source), fetch a bounded result set and sort in the Worker:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { results } = await env.DB.prepare(
      `SELECT id, name FROM items WHERE category = ? LIMIT 500`
    ).bind('chapters').all<{ id: number; name: string }>();

    const collator = new Intl.Collator(undefined, {
      numeric: true,       // "item-10" > "item-2" ✓
      sensitivity: 'base', // case-insensitive
    });

    results.sort((a, b) => collator.compare(a.name, b.name));

    return Response.json(results);
  },
};
```

`Intl.Collator` with `numeric: true` is available in the Workers runtime and produces correct natural order without regex hacks.

---

## COLLATE NOCASE Scope and Limitations

`COLLATE NOCASE` in SQLite only folds ASCII letters A–Z. Unicode characters outside that range are compared by their code point. For user-visible strings containing accented characters, do not rely solely on `COLLATE NOCASE`:

```sql
-- Works for ASCII names
SELECT * FROM users ORDER BY username COLLATE NOCASE;

-- "Ångström" will NOT sort adjacent to "angstrom" with COLLATE NOCASE
-- Fold in the application layer instead
```

```typescript
// Application-layer Unicode fold before query
const normalised = input.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const { results } = await env.DB.prepare(
  `SELECT * FROM users WHERE name_normalised LIKE ?`
).bind(`${normalised}%`).all();
```

Store `name_normalised` at write time alongside the display name.

---

## Cursor-Based Pagination with Mixed-Type Sort Keys

Natural sort + keyset pagination requires the cursor to encode the full sort key, not just an integer offset:

```typescript
interface Cursor { sortKey: string; id: number }

async function page(env: Env, after?: Cursor, limit = 50) {
  const base = `SELECT id, name, sort_key FROM items`;
  const query = after
    ? `${base} WHERE (sort_key, id) > (?, ?) ORDER BY sort_key, id LIMIT ?`
    : `${base} ORDER BY sort_key, id LIMIT ?`;

  const binds: (string | number)[] = after
    ? [after.sortKey, after.id, limit]
    : [limit];

  const { results } = await env.DB.prepare(query).bind(...binds).all<{
    id: number; name: string; sort_key: string;
  }>();

  const next = results.length === limit
    ? { sortKey: results.at(-1)!.sort_key, id: results.at(-1)!.id }
    : null;

  return { results, next };
}
```

Using `(sort_key, id) > (?, ?)` as the keyset predicate keeps pagination stable when `sort_key` values collide.

---

## Backfill Existing Data

When adding `sort_key` to a table with existing rows, run the backfill inside a D1 batch to stay within the 30-second CPU budget:

```typescript
async function backfill(env: Env, batchSize = 500) {
  let offset = 0;
  while (true) {
    const { results } = await env.DB.prepare(
      `SELECT id, name FROM items WHERE sort_key IS NULL LIMIT ?`
    ).bind(batchSize).all<{ id: number; name: string }>();

    if (results.length === 0) break;

    const stmts = results.map(({ id, name }) =>
      env.DB.prepare(`UPDATE items SET sort_key = ? WHERE id = ?`)
        .bind(naturalSortKey(name), id)
    );

    await env.DB.batch(stmts);
    offset += results.length;
    console.log(`Backfilled ${offset} rows`);
  }
}
```

Trigger via a one-off Cron or Wrangler tail invocation; do not run inline on a hot path.

---

## Anti-patterns

- **`ORDER BY CAST(name AS INTEGER)`** — silently returns 0 for strings that don't start with a digit; corrupts order without error.
- **`ORDER BY LENGTH(name), name`** — only works for purely numeric strings; breaks on `"item-2"` vs `"item-10"`.
- **Fetching all rows to sort in JS** — safe for <1 000 rows; dangerous at scale. Always push a `LIMIT` to D1 and sort a bounded set.
- **Assuming `COLLATE NOCASE` is Unicode-aware** — it is ASCII-only; combining it with `LIKE` on emoji or accented text produces surprising non-matches.

---

## Gotchas

- D1's SQLite version does not support custom collations via `CREATE COLLATION`; that API is unavailable in the runtime.
- `Intl.Collator` with `numeric: true` treats leading zeros as insignificant: `"001"` equals `"1"`. If your sort keys must distinguish zero-padded variants, use binary comparison on the stored key.
- Compound `(sort_key, id) >` keyset comparisons require the columns to be covered by an index: `CREATE INDEX idx_items_sort ON items(sort_key, id);` — otherwise each page triggers a full scan.
- D1 returns `results` as JavaScript objects; numeric TEXT columns come back as strings. `'10' > '9'` is `false` in JS string comparison — always pass strings through `Intl.Collator` or convert explicitly.

---

## Verification

```bash
# Insert test fixtures
wrangler d1 execute MY_DB --command "
  INSERT INTO items (name) VALUES ('item-1'),('item-10'),('item-2'),('item-20'),('item-3');
"

# Confirm broken default ordering
wrangler d1 execute MY_DB --command "SELECT name FROM items ORDER BY name;"
# Expected (wrong): item-1, item-10, item-2, item-20, item-3

# Confirm zero-pad fix
wrangler d1 execute MY_DB --command "SELECT name FROM items ORDER BY sort_key;"
# Expected (correct): item-1, item-2, item-3, item-10, item-20
```

---

## Related

- `d1-cursor-based-pagination-large-datasets.md`
- `d1-pragma-tuning.md`
- `d1-typescript-patterns.md`
- `d1-full-text-search.md`

---

## Sources

- SQLite documentation — Datatypes and Sort Order: https://www.sqlite.org/datatype3.html
- SQLite COLLATE documentation: https://www.sqlite.org/datatype3.html#collating_sequences
- MDN `Intl.Collator` — numeric option: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator/Collator
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
