# D1 json_each() and json_tree() — Table-Valued Functions in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You store JSON arrays or objects in a D1 `TEXT` column and need to query individual elements as
rows — filtering orders by tag, unnesting product variants, aggregating per-item scores — without
pulling the entire JSON payload into JavaScript and processing it in memory. SQLite's built-in
`json_each()` and `json_tree()` table-valued functions (TVFs) let you iterate over JSON inline in
SQL, running entirely server-side on the D1 engine.

## Context

`json_each(json)` and `json_tree(json)` are SQLite virtual-table functions introduced in SQLite
3.9 (2015); Cloudflare D1 ships SQLite 3.46+ and fully supports both. They emit one row per JSON
element and can be joined, filtered, and aggregated like any table.

Column schema of `json_each` / `json_tree`:

| Column | Meaning |
|--------|---------|
| `key`  | Object key (TEXT) or array index (INTEGER) |
| `value`| The element value (any type) |
| `type` | `'null'`, `'true'`, `'false'`, `'integer'`, `'real'`, `'text'`, `'array'`, `'object'` |
| `atom` | Scalar value (`null` for arrays/objects) |
| `id`   | Unique integer id within the current JSON tree |
| `parent` | `id` of the parent node (`null` at root) |
| `fullkey` | JSONPath expression to this node |
| `path` | JSONPath of the parent container |

`json_each` walks only the **immediate children** of the root (or a supplied path). `json_tree`
walks the **entire subtree** recursively.

Optional second argument: `json_each(json, '$.path')` restricts iteration to a sub-path.

## Unnesting a JSON Array Column

```sql
-- Table: products(id TEXT, name TEXT, tags TEXT)
-- tags column stores: '["electronics","sale","new"]'

SELECT p.id, p.name, t.value AS tag
FROM products p, json_each(p.tags) AS t
WHERE t.value = 'sale';
```

```typescript
// src/repositories/product.repository.ts
import type { D1Database } from "@cloudflare/workers-types";

interface ProductRow {
  id: string;
  name: string;
  tag: string;
}

export async function getProductsByTag(
  db: D1Database,
  tag: string
): Promise<ProductRow[]> {
  const { results } = await db
    .prepare(
      `SELECT p.id, p.name, t.value AS tag
       FROM products p, json_each(p.tags) AS t
       WHERE t.value = ?`
    )
    .bind(tag)
    .all<ProductRow>();
  return results;
}
```

## Counting Tag Frequency Across All Products

```typescript
// src/analytics/tag-frequency.ts
import type { D1Database } from "@cloudflare/workers-types";

interface TagCount {
  tag: string;
  count: number;
}

export async function getTagFrequency(db: D1Database): Promise<TagCount[]> {
  const { results } = await db
    .prepare(
      `SELECT t.value AS tag, COUNT(*) AS count
       FROM products p, json_each(p.tags) AS t
       GROUP BY t.value
       ORDER BY count DESC`
    )
    .all<TagCount>();
  return results;
}
```

## Filtering Products That Have ALL of Several Tags (Tag Intersection)

```typescript
// src/repositories/product.repository.ts
export async function getProductsWithAllTags(
  db: D1Database,
  tags: string[]
): Promise<{ id: string; name: string }[]> {
  if (tags.length === 0) return [];

  // Build a single JSON array literal to pass as a bind parameter
  const tagsJson = JSON.stringify(tags);

  const { results } = await db
    .prepare(
      `SELECT p.id, p.name
       FROM products p
       WHERE (
         SELECT COUNT(DISTINCT required.value)
         FROM json_each(?) AS required
         WHERE EXISTS (
           SELECT 1 FROM json_each(p.tags) AS pt WHERE pt.value = required.value
         )
       ) = json_array_length(?)`
    )
    .bind(tagsJson, tagsJson)
    .all<{ id: string; name: string }>();

  return results;
}
```

## Walking a Nested JSON Object with json_tree

```sql
-- orders(id TEXT, line_items TEXT)
-- line_items: [{"sku":"A","qty":2,"price":9.99},{"sku":"B","qty":1,"price":4.99}]

-- Find all SKUs with qty > 1 anywhere in the line_items tree
SELECT o.id AS order_id, sku_node.value AS sku
FROM orders o
JOIN json_tree(o.line_items) AS price_node
  ON price_node.key = 'qty' AND CAST(price_node.value AS INTEGER) > 1
JOIN json_tree(o.line_items) AS sku_node
  ON sku_node.key = 'sku' AND sku_node.parent = price_node.parent;
```

```typescript
// src/repositories/order.repository.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function getHighQtySkusInOrders(
  db: D1Database,
  minQty: number
): Promise<{ order_id: string; sku: string }[]> {
  const { results } = await db
    .prepare(
      `SELECT o.id AS order_id, sku_node.value AS sku
       FROM orders o
       JOIN json_tree(o.line_items) AS qty_node
         ON qty_node.key = 'qty' AND CAST(qty_node.value AS INTEGER) >= ?
       JOIN json_tree(o.line_items) AS sku_node
         ON sku_node.key = 'sku' AND sku_node.parent = qty_node.parent`
    )
    .bind(minQty)
    .all<{ order_id: string; sku: string }>();
  return results;
}
```

## Inserting via json_each for Bulk Tag Writes

```typescript
// Normalise a product's tags into a separate tag_index table for fast equality lookups
// without a full json_each scan on every query.

export async function indexProductTags(
  db: D1Database,
  productId: string,
  tags: string[]
): Promise<void> {
  const tagsJson = JSON.stringify(tags);
  await db
    .prepare(
      `INSERT OR IGNORE INTO tag_index (product_id, tag)
       SELECT ?, t.value
       FROM json_each(?)`
    )
    .bind(productId, tagsJson)
    .run();
}
```

## Extracting a Specific Sub-path

```typescript
// products.metadata = '{"dimensions":{"w":10,"h":20},"weight":1.5}'
// Extract all dimension keys without reading the full metadata object

export async function getDimensionKeys(
  db: D1Database,
  productId: string
): Promise<string[]> {
  const { results } = await db
    .prepare(
      `SELECT key
       FROM json_each(
         (SELECT metadata FROM products WHERE id = ?),
         '$.dimensions'
       )`
    )
    .bind(productId)
    .all<{ key: string }>();
  return results.map((r) => r.key);
}
```

## Anti-patterns

- **Using `json_tree` when `json_each` suffices** — `json_tree` walks the entire nested subtree
  and emits far more rows; use it only when you need recursion. `json_each` is O(n) in the number
  of immediate children; `json_tree` is O(total nodes).
- **Joining `json_each` on unindexed columns** — there is no index on JSON array elements; a
  `json_each` join requires a full scan of the outer table. For frequent tag-filter queries,
  materialise a `tag_index` table and keep it in sync.
- **`CAST(value AS INTEGER)` without type check** — `json_each.value` is `TEXT` in D1's driver
  result set; always `CAST` numeric values before arithmetic comparisons.
- **Storing deeply nested JSON and querying leaf nodes with `json_tree`** — deep trees produce
  many rows and slow D1 queries; flatten your schema when query patterns require per-leaf access.
- **Using `json_each` in a subquery correlated to millions of rows** — each outer row invokes the
  TVF separately; this is effectively an O(n) full-scan with TVF overhead per row.

## Gotchas

- `json_each` and `json_tree` emit **no rows** when the JSON is `NULL` or invalid — they do not
  raise an error. Use `json_valid(col)` in a `WHERE` clause or a `CHECK` constraint to guard
  invalid data.
- **D1's JavaScript driver returns all `json_each.value` columns as `TEXT`** even for numeric
  JSON values; cast explicitly with `CAST(t.value AS REAL)` in SQL or `Number(row.value)` in TS.
- **`json_each.key` is a string for objects, an integer for arrays** — but D1 returns both as
  `TEXT` in the JavaScript layer. Compare with `'0'`, `'1'`, not `0`, `1`.
- **The second argument (path) must be a quoted JSONPath string** starting with `$`; passing
  a bind parameter as the path literal is supported: `json_each(col, ?)`.
- **`json_group_array` and `json_each` interact** — `json_group_array(json_each.value)` re-wraps
  the unnested values back into a JSON array; useful for set-intersection and difference queries.

## Verification

```bash
# Confirm json_each is available in your D1 database
wrangler d1 execute myapp --command \
  "SELECT key, value, type FROM json_each('[1,\"hello\",{\"a\":1}]');"

# Walk a nested object tree
wrangler d1 execute myapp --command \
  "SELECT fullkey, atom, type FROM json_tree('{\"a\":{\"b\":42}}') WHERE atom IS NOT NULL;"
```

```typescript
// test/json-each.test.ts
import { expect, it, beforeAll } from "vitest";
import { env } from "cloudflare:test";

beforeAll(async () => {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS products (
      id TEXT PRIMARY KEY, name TEXT, tags TEXT NOT NULL DEFAULT '[]'
    );
    INSERT OR IGNORE INTO products VALUES
      ('p1', 'Widget', '["sale","electronics"]'),
      ('p2', 'Gadget', '["electronics","new"]'),
      ('p3', 'Donut',  '["sale","food"]');
  `);
});

it("finds products tagged sale via json_each", async () => {
  const { results } = await env.DB.prepare(
    `SELECT p.id FROM products p, json_each(p.tags) t WHERE t.value = 'sale'`
  ).all<{ id: string }>();
  expect(results.map((r) => r.id).sort()).toEqual(["p1", "p3"]);
});

it("counts tags correctly", async () => {
  const rows = await env.DB.prepare(
    `SELECT t.value AS tag, COUNT(*) AS cnt
     FROM products p, json_each(p.tags) t
     GROUP BY t.value ORDER BY cnt DESC LIMIT 1`
  ).first<{ tag: string; cnt: number }>();
  expect(rows?.tag).toBe("electronics");
  expect(rows?.cnt).toBe(2);
});
```

## Related

- `d1-json-column-patterns.md`
- `d1-json-patch-partial-update-workers.md`
- `d1-json-aggregation-analytics.md`
- `d1-json-columns-partial-indexes.md`
- `d1-fts5-bm25-custom-ranking-workers.md`

## Sources

- SQLite json_each / json_tree reference: https://www.sqlite.org/json1.html#jx
- SQLite table-valued functions: https://www.sqlite.org/vtab.html#tabfunc2
- Cloudflare D1 SQL API: https://developers.cloudflare.com/d1/reference/sql-api/
- json_valid() function: https://www.sqlite.org/json1.html#jvalid
