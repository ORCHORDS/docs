# D1 JSON Path Extraction in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You store semi-structured data in a TEXT column as JSON and need to query
specific nested fields — filter by a nested key, project a sub-object, or
aggregate over an array element — without fetching and parsing every row
in TypeScript.

## Context

SQLite ships a built-in `json_extract()` function and the shorthand `->` /
`->>` operators (available from SQLite 3.38, which D1 runs). These let you
reach into JSON columns at the SQL layer, which keeps payloads small and
lets D1 apply indexes defined on extracted values (via generated columns or
expression indexes).

D1 does **not** support PostgreSQL-style `jsonb` or `@>` containment; the
SQLite JSON functions are the only path.

---

## Core JSON Path Functions

### `json_extract(column, path)`

Returns the value at `path` with SQLite type inference (INTEGER, REAL, TEXT,
NULL). Returns NULL when the path does not exist.

```typescript
// Extract a nested scalar
const result = await env.DB.prepare(
  `SELECT json_extract(metadata, '$.user.country') AS country
   FROM orders
   WHERE json_extract(metadata, '$.user.country') = ?`
).bind("DE").all<{ country: string }>();
```

### `->` and `->>` shorthand operators

`col -> '$.key'` returns the raw JSON fragment (array or object stays JSON).
`col ->> '$.key'` extracts the scalar value (equivalent to `json_extract`).

```typescript
const result = await env.DB.prepare(
  `SELECT
     metadata ->> '$.plan'     AS plan,
     metadata -> '$.features'  AS features_json
   FROM subscriptions
   WHERE metadata ->> '$.status' = 'active'`
).all<{ plan: string; features_json: string }>();
```

---

## Indexing JSON Paths with Expression Indexes

D1 supports indexes on expressions, so you can index a frequently queried
JSON path without a schema redesign.

```sql
-- migration: add expression index on nested JSON field
CREATE INDEX IF NOT EXISTS idx_orders_country
  ON orders (json_extract(metadata, '$.user.country'));
```

```typescript
// Workers migration helper
async function addJsonIndex(db: D1Database): Promise<void> {
  await db.prepare(`
    CREATE INDEX IF NOT EXISTS idx_orders_country
    ON orders (json_extract(metadata, '$.user.country'))
  `).run();
}
```

After this index exists, the `WHERE json_extract(metadata, '$.user.country') = ?`
query in the first example hits the index instead of full-scanning the table.
Confirm with `EXPLAIN QUERY PLAN`.

---

## JSON Array Functions: `json_each` and `json_array_length`

`json_each(column, path)` is a table-valued function that unnests a JSON
array into rows.

```typescript
// Count orders that include product ID "prod_42" in a JSON array
const { results } = await env.DB.prepare(`
  SELECT o.id, o.total
  FROM orders o, json_each(o.metadata, '$.items') AS item
  WHERE item.value ->> '$.product_id' = ?
`).bind("prod_42").all<{ id: string; total: number }>();
```

`json_array_length(column, path)` returns the array length without unnesting:

```typescript
const { results } = await env.DB.prepare(`
  SELECT id, json_array_length(metadata, '$.items') AS item_count
  FROM orders
  WHERE json_array_length(metadata, '$.items') > 5
`).all<{ id: string; item_count: number }>();
```

---

## Constructing JSON in SELECT: `json_object` and `json_group_array`

Build JSON responses directly in the query to avoid N+1 round-trips:

```typescript
interface UserWithTags {
  id: number;
  name: string;
  tags: string; // JSON array string
}

const { results } = await env.DB.prepare(`
  SELECT
    u.id,
    u.name,
    json_group_array(t.label) AS tags
  FROM users u
  LEFT JOIN user_tags t ON t.user_id = u.id
  GROUP BY u.id
`).all<UserWithTags>();

// Deserialize in Workers
const users = results.map(r => ({
  ...r,
  tags: JSON.parse(r.tags) as string[],
}));
```

---

## Partial Update via `json_patch`

`json_patch(target, patch)` merges a patch object into existing JSON,
following RFC 7396 merge-patch semantics. NULL values in the patch delete
the corresponding key.

```typescript
async function patchMetadata(
  db: D1Database,
  orderId: string,
  patch: Record<string, unknown>
): Promise<void> {
  await db.prepare(`
    UPDATE orders
    SET metadata = json_patch(metadata, ?)
    WHERE id = ?
  `).bind(JSON.stringify(patch), orderId).run();
}

// Usage: update plan without touching other fields
await patchMetadata(env.DB, "ord_123", { plan: "enterprise" });
```

---

## Anti-patterns

- **`json_extract` in SELECT without WHERE index**: projecting a JSON path is
  fine, but filtering millions of rows with `WHERE json_extract(...)` on an
  unindexed path causes full-table scans. Add an expression index or a
  generated column.
- **Storing deeply nested structures and querying leaf nodes**: each extra
  nesting level adds overhead. Flatten common query targets into real columns
  or shallow JSON objects.
- **Using `->` expecting a scalar**: `->` returns raw JSON (a quoted string
  for text values). Use `->>` for scalar comparisons to avoid type mismatches
  in WHERE clauses.
- **`json_group_array` without ORDER BY**: the element order in the resulting
  array is undefined. Add `ORDER BY` inside the aggregate or sort afterward.
- **Parsing JSON in Workers to filter**: pulling all rows and filtering in TS
  is slow and wastes D1 request budget. Push predicates into SQL.

---

## Gotchas

- SQLite JSON functions return TEXT for object/array values; parse with
  `JSON.parse()` in Workers before spreading or indexing the result.
- `json_extract` returns NULL — not an error — for a missing path. Guard
  nullable fields in TypeScript with `?? defaultValue`.
- `json_patch` does a shallow merge; nested objects are replaced, not merged
  recursively. Use read-modify-write in a transaction for deep merges.
- Expression indexes must spell the path **identically** to the query
  (including case). A mismatch silently degrades to a full scan.
- D1 does not yet support the `JSON_TABLE` function available in MySQL/Postgres.

---

## Verification

```typescript
// Confirm expression index is used
const plan = await env.DB.prepare(`
  EXPLAIN QUERY PLAN
  SELECT id FROM orders
  WHERE json_extract(metadata, '$.user.country') = 'DE'
`).all();
// Look for "USING INDEX idx_orders_country" in the detail column

// Smoke-test json_patch round-trip
const before = JSON.stringify({ plan: "starter", seats: 5 });
const patch   = JSON.stringify({ seats: 10 });
const { results } = await env.DB.prepare(
  `SELECT json_patch(?, ?) AS merged`
).bind(before, patch).all<{ merged: string }>();
console.assert(JSON.parse(results[0].merged).seats === 10);
```

---

## Related

- `d1-json-each-table-valued-function-workers.md`
- `d1-json-columns-partial-indexes.md`
- `d1-json-patch-partial-update-workers.md`
- `d1-expression-index-function-based-workers.md`
- `d1-generated-columns-virtual-workers.md`

---

## Sources

- SQLite JSON functions reference: https://www.sqlite.org/json1.html
- SQLite expression indexes: https://www.sqlite.org/expridx.html
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- SQLite 3.38 `->` / `->>` operators: https://www.sqlite.org/json1.html#jptr
