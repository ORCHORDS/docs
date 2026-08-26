# Querying JSON Columns in D1 (SQLite JSON Functions)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have semi-structured or variable-shape data — product attributes, user preferences, tag lists, feature flags — and you want to store it alongside relational columns in D1 without creating a separate table for every possible field. You also need to filter and sort on values inside those JSON blobs without loading the entire row into the application layer.

## Context

D1 is backed by SQLite, which ships with a full JSON1 extension. Functions like `json_extract`, `json_each`, and `json_type` are available in D1 queries. The trade-off versus normalised relational columns is real: JSON columns are flexible but unindexed by default. SQLite generated columns let you extract a stable path from a JSON blob into an indexable virtual column, narrowing the gap significantly for read-heavy workloads.

---

## Schema Design

```sql
-- Products table: relational columns for frequently filtered fields,
-- JSON column for variable attributes.
CREATE TABLE products (
  id          TEXT  PRIMARY KEY,
  name        TEXT  NOT NULL,
  price_cents INTEGER NOT NULL,
  -- Stores arbitrary key-value attributes and a tags array, e.g.:
  -- {"color":"red","weight_g":450,"tags":["sale","featured"]}
  meta        TEXT  NOT NULL DEFAULT '{}',

  -- Generated (virtual) column: extracts the first tag for lightweight filtering.
  -- VIRTUAL means it is computed on read, not stored on disk.
  first_tag   TEXT  GENERATED ALWAYS AS (json_extract(meta, '$.tags[0]')) VIRTUAL
);

-- Index the generated column so WHERE first_tag = 'sale' is O(log n)
CREATE INDEX idx_products_first_tag ON products (first_tag);

-- Index on a scalar JSON field used in range queries
CREATE INDEX idx_products_weight
  ON products (CAST(json_extract(meta, '$.weight_g') AS INTEGER));
```

## Reading and Writing JSON Columns in TypeScript

```typescript
// src/db/products.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface ProductMeta {
  color?: string;
  weight_g?: number;
  tags?: string[];

}

export interface Product {
  id: string;
  name: string;
  price_cents: number;
  meta: ProductMeta;
}

/** Insert a product — meta is serialised to JSON text. */
export async function createProduct(
  db: D1Database,
  product: Product,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO products (id, name, price_cents, meta)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(
      product.id,
      product.name,
      product.price_cents,
      JSON.stringify(product.meta),
    )
    .run();
}

/** Return products carrying a specific tag (exact match on any array element). */
export async function findByTag(
  db: D1Database,
  tag: string,
): Promise<Product[]> {
  // json_each(meta, '$.tags') expands the tags array into rows;
  // the outer WHERE filters to rows where any element equals the target tag.
  const { results } = await db
    .prepare(
      `SELECT p.id, p.name, p.price_cents, p.meta
       FROM products p, json_each(p.meta, '$.tags') AS t
       WHERE t.value = ?
       ORDER BY p.price_cents ASC`,
    )
    .bind(tag)
    .all<{ id: string; name: string; price_cents: number; meta: string }>();

  return results.map((r) => ({ ...r, meta: JSON.parse(r.meta) as ProductMeta }));
}

/** Filter by a scalar JSON field using json_extract in the WHERE clause. */
export async function findByColor(
  db: D1Database,
  color: string,
): Promise<Product[]> {
  const { results } = await db
    .prepare(
      `SELECT id, name, price_cents, meta
       FROM products
       WHERE json_extract(meta, '$.color') = ?`,
    )
    .bind(color)
    .all<{ id: string; name: string; price_cents: number; meta: string }>();

  return results.map((r) => ({ ...r, meta: JSON.parse(r.meta) as ProductMeta }));
}

/** Range query on a numeric JSON field, cast to INTEGER for comparison. */
export async function findByMaxWeight(
  db: D1Database,
  maxWeightG: number,
): Promise<Product[]> {
  const { results } = await db
    .prepare(
      `SELECT id, name, price_cents, meta
       FROM products
       WHERE CAST(json_extract(meta, '$.weight_g') AS INTEGER) <= ?`,
    )
    .bind(maxWeightG)
    .all<{ id: string; name: string; price_cents: number; meta: string }>();

  return results.map((r) => ({ ...r, meta: JSON.parse(r.meta) as ProductMeta }));
}

/** Partially update a JSON column by merging new fields. */
export async function patchMeta(
  db: D1Database,
  productId: string,
  patch: Partial<ProductMeta>,
): Promise<void> {
  // json_patch performs an RFC 7396 merge: existing keys not in patch survive.
  await db
    .prepare(
      `UPDATE products
       SET meta = json_patch(meta, ?)
       WHERE id = ?`,
    )
    .bind(JSON.stringify(patch), productId)
    .run();
}
```

## Performance: JSON vs Normalised Columns

| Query pattern | JSON column | Normalised column |
|---|---|---|
| Point lookup on indexed generated column | O(log n) via index | O(log n) via index |
| Scalar filter without index | O(n) full scan | O(log n) if indexed |
| Array membership (`json_each`) | O(n) always | O(log n) with junction table |
| Partial update of one field | O(1) with `json_patch` | O(1) with targeted UPDATE |
| Schema evolution (add field) | Zero migration | ALTER TABLE required |

Rule of thumb: promote a JSON field to a relational column (or generated column with index) once it appears in a `WHERE` clause and the table exceeds ~100 k rows.

## Anti-patterns

- **Storing entire application state in one JSON blob.** Blobs that grow unbounded become expensive to parse and impossible to query efficiently. Decompose stable, frequently queried fields into relational columns.
- **Using `json_extract` in a WHERE clause on a large table without an index.** This triggers a full table scan every time. Add a generated column and index it.
- **Relying on JSON key order for comparisons.** SQLite's JSON functions do not guarantee key order. Always compare by `json_extract`, not by raw text equality.
- **Storing numbers as JSON strings.** `json_extract` will return a text value; `CAST(... AS INTEGER)` will work but silently produce 0 for non-numeric strings.

## Gotchas

- D1 returns JSON columns as raw `TEXT`. You must `JSON.parse()` them in TypeScript — they are not automatically deserialised.
- `json_each` produces a virtual table. It must appear in the `FROM` clause, not in a subquery `WHERE` position.
- Generated `VIRTUAL` columns are not stored; they are recomputed on every read. Use `STORED` if the expression is expensive and reads dominate writes.
- `json_patch` follows RFC 7396: setting a key to `null` removes it. If you need to store `null` as a value, use a sentinel string instead.

## Verification

```sql
-- Confirm json_extract works on a sample row
SELECT json_extract(meta, '$.tags[0]'), json_extract(meta, '$.color')
FROM products LIMIT 5;

-- Check EXPLAIN QUERY PLAN to confirm index use
EXPLAIN QUERY PLAN
SELECT * FROM products WHERE first_tag = 'sale';
-- Should show: SEARCH products USING INDEX idx_products_first_tag

-- List all distinct tags across all products
SELECT DISTINCT t.value
FROM products, json_each(products.meta, '$.tags') AS t
ORDER BY t.value;
```

## Related

- `d1-audit-log-application-trigger-workers.md` — JSON snapshots stored in audit rows
- `d1-cursor-pagination-workers.md` — paginate results that filter on JSON fields
- SQLite JSON1 extension documentation

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/json1.html
- https://www.sqlite.org/gencol.html
