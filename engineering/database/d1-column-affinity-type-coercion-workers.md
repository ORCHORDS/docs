# D1 Column Affinity and Type Coercion Pitfalls in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Queries return rows that don't match a strict filter. A `WHERE status = 1` returns rows
where `status` was inserted as the string `"1"`. Numeric comparisons give wrong ordering.
A TypeScript value typed as `number` comes back from D1 as a `string`. JSON schema
validation on the Worker side rejects values that look like the right type but are stored
differently.

These are all symptoms of SQLite's *type affinity* system — a design that D1 inherits
unchanged. Understanding it is essential for writing correct, efficient D1 schemas.

## Context

SQLite (and therefore D1) uses *dynamic typing*: any column can store any type of value
regardless of the declared type. The declared column type is treated as an *affinity hint*
that influences — but does not enforce — how values are stored.

SQLite defines five storage classes:
- `NULL`
- `INTEGER` (1, 2, 3, 4, 6, or 8 bytes)
- `REAL` (8-byte IEEE float)
- `TEXT` (UTF-8 or UTF-16 string)
- `BLOB` (raw bytes)

And five affinities (derived from the column's declared type name):
- `TEXT` — declared types containing "CHAR", "CLOB", or "TEXT"
- `NUMERIC` — declared types containing "NUM", "DECIMAL", or none of the other keywords
- `INTEGER` — declared types containing "INT"
- `REAL` — declared types containing "REAL", "FLOA", or "DOUB"
- `BLOB` / `NONE` — declared types "BLOB" or empty string

The affinity rules control coercion on INSERT/UPDATE. **They do not prevent a TEXT value
from landing in an INTEGER column if you explicitly supply a TEXT.**

## Affinity Coercion Rules

```sql
-- D1 migration: illustrating affinity behaviour
CREATE TABLE affinity_demo (
  i INTEGER,
  r REAL,
  t TEXT,
  n NUMERIC,
  b BLOB
);
```

```typescript
// workers/affinity-demo.ts
export default {
  async fetch(_req: Request, env: Env): Promise<Response> {
    const session = env.DB.withSession();

    // Insert mixed types — D1 passes values to SQLite as-is from the JS binding
    await session.prepare(
      "INSERT INTO affinity_demo (i, r, t, n, b) VALUES (?, ?, ?, ?, ?)"
    )
    // JS types sent: number, string "3.14", number 42, string "99", ArrayBuffer
    .bind(1, "3.14", 42, "99", new Uint8Array([0xde, 0xad]).buffer)
    .run();

    const row = await session
      .prepare("SELECT typeof(i), typeof(r), typeof(t), typeof(n), typeof(b) FROM affinity_demo")
      .first<Record<string, string>>();

    // Result:
    // typeof(i) = "integer"   — JS number 1 → INTEGER affinity → stored as INTEGER
    // typeof(r) = "real"      — JS string "3.14" → REAL affinity → coerced to REAL
    // typeof(t) = "integer"   — JS number 42 → TEXT affinity does NOT coerce integer to TEXT!
    //                           The value 42 stored as INTEGER in a TEXT column
    // typeof(n) = "integer"   — "99" → NUMERIC affinity → coerces to INTEGER
    // typeof(b) = "blob"      — ArrayBuffer → BLOB affinity → stored as BLOB

    return Response.json(row);
  },
};
```

The counterintuitive result: inserting `42` into a `TEXT` affinity column stores it as
`INTEGER`, not `"42"`. SQLite's TEXT affinity only converts to TEXT when the input cannot
be represented as a number.

## Common Pitfalls in D1 Workers

### Pitfall 1 — Boolean Storage

SQLite has no `BOOLEAN` type. Two conventions exist and they are not interchangeable:

```sql
-- Convention A: INTEGER 0/1
CREATE TABLE items (id TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1);

-- Convention B: TEXT 'true'/'false'
CREATE TABLE items_b (id TEXT PRIMARY KEY, active TEXT NOT NULL DEFAULT 'true');
```

```typescript
// Workers binding passes JS booleans as integers (0/1) automatically.
// But if you pass the JS boolean directly to .bind(), Cloudflare's D1 client
// converts it to INTEGER 0 or 1. This works fine with Convention A.

async function setActive(db: D1Database, id: string, active: boolean): Promise<void> {
  await db.prepare("UPDATE items SET active = ? WHERE id = ?")
    .bind(active ? 1 : 0, id)  // explicit — never rely on implicit bool→int
    .run();
}

// Reading back: D1 returns 0 or 1 as JS number, not boolean.
// Always normalise at the boundary:
async function getItem(db: D1Database, id: string) {
  const row = await db.prepare("SELECT id, active FROM items WHERE id = ?")
    .bind(id)
    .first<{ id: string; active: number }>();
  if (!row) return null;
  return { ...row, active: row.active === 1 };  // cast to boolean explicitly
}
```

### Pitfall 2 — Numeric String Comparisons

When a column has TEXT affinity (e.g. `VARCHAR(255)`), numeric comparisons use
lexicographic ordering, not numeric ordering:

```sql
-- TEXT affinity column
CREATE TABLE orders (id TEXT PRIMARY KEY, amount TEXT);
INSERT INTO orders VALUES ('a', '9'), ('b', '10'), ('c', '100');

-- WRONG: lexicographic sort puts '100' < '10' < '9'
SELECT id, amount FROM orders ORDER BY amount DESC;
-- Returns: a(9), c(100), b(10)

-- CORRECT: cast explicitly in the query
SELECT id, amount FROM orders ORDER BY CAST(amount AS REAL) DESC;
-- Returns: c(100), b(10), a(9)
```

```typescript
// Workers: safe numeric sort helper
function buildNumericSort(column: string, direction: "ASC" | "DESC"): string {
  // Validate column name to prevent injection — never interpolate user input directly
  const ALLOWED_COLUMNS = new Set(["amount", "price", "quantity", "score"]);
  if (!ALLOWED_COLUMNS.has(column)) throw new Error(`Invalid column: ${column}`);
  return `CAST(${column} AS REAL) ${direction}`;
}

const rows = await env.DB
  .prepare(`SELECT id, amount FROM orders ORDER BY ${buildNumericSort("amount", "DESC")}`)
  .all<{ id: string; amount: string }>();
```

### Pitfall 3 — NUMERIC Affinity and Floating-Point Loss

`NUMERIC` affinity converts text that looks like an integer to `INTEGER` storage, but text
that looks like a float to `REAL`. This can silently truncate decimal places:

```sql
CREATE TABLE prices (sku TEXT, price NUMERIC);
INSERT INTO prices VALUES ('A', '9.99');   -- stored as REAL 9.99  (OK)
INSERT INTO prices VALUES ('B', '10.00');  -- stored as INTEGER 10  (precision lost!)
INSERT INTO prices VALUES ('C', '10.10');  -- stored as REAL 10.1  (OK)
```

```typescript
// Prefer INTEGER cents or a TEXT column for money — never NUMERIC/REAL for currency
// See also: money-decimal-storage.md

CREATE TABLE prices_safe (sku TEXT, price_cents INTEGER NOT NULL);
-- Store 9.99 as 999, 10.00 as 1000, etc.

async function formatPrice(cents: number): string {
  return (cents / 100).toFixed(2);
}
```

### Pitfall 4 — UUID Sorting and Comparison

UUIDs stored as TEXT sort lexicographically, which is fine for equality but causes subtle
issues with range queries if UUIDs are version-mixed or if you need chronological ordering:

```sql
-- TEXT affinity: UUIDs compare as strings — correct for v4, wrong for ordering by time
CREATE TABLE events (id TEXT PRIMARY KEY, payload TEXT);

-- For time-ordered UUIDs (UUIDv7), the string sort IS chronological — use it
-- For v4, add a separate created_at column for ordering
CREATE TABLE events_v2 (
  id         TEXT    PRIMARY KEY,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  payload    TEXT
);
CREATE INDEX idx_events_v2_created ON events_v2 (created_at);
```

## Schema Design with Explicit Affinity

Write schemas that make the intended affinity unambiguous:

```typescript
// migrations/0001_explicit_types.sql — run via wrangler d1 migrations apply
const MIGRATION = `
CREATE TABLE IF NOT EXISTS products (
  -- INTEGER affinity: use "INTEGER" or "INT" in the type name
  id           INTEGER PRIMARY KEY,            -- rowid alias, fastest PK
  quantity     INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch()),  -- Unix epoch, not TEXT date

  -- REAL affinity: explicit float storage
  weight_kg    REAL,

  -- TEXT affinity: strings, JSON, UUIDs
  sku          TEXT NOT NULL UNIQUE,
  metadata     TEXT,                           -- JSON stored as TEXT

  -- BLOB: binary data
  thumbnail    BLOB,

  -- NEVER use bare DECIMAL, NUMERIC, or VARCHAR for business logic values
  -- price_cents  INTEGER NOT NULL  -- preferred for money
);
`;
```

## TypeScript Type Safety at the D1 Boundary

Use a thin mapper to enforce types coming out of D1:

```typescript
// lib/d1-types.ts
export interface ProductRow {
  id: number;
  quantity: number;
  created_at: number;      // Unix timestamp as number
  weight_kg: number | null;
  sku: string;
  metadata: string | null; // raw JSON string — parse separately
  thumbnail: ArrayBuffer | null;
}

// Validate and convert at the boundary — don't trust the raw row type
export function parseProductRow(raw: Record<string, unknown>): ProductRow {
  return {
    id: Number(raw.id),
    quantity: Number(raw.quantity),
    created_at: Number(raw.created_at),
    weight_kg: raw.weight_kg != null ? Number(raw.weight_kg) : null,
    sku: String(raw.sku),
    metadata: raw.metadata != null ? String(raw.metadata) : null,
    thumbnail: raw.thumbnail instanceof ArrayBuffer ? raw.thumbnail : null,
  };
}

// Usage
const raw = await env.DB.prepare("SELECT * FROM products WHERE id = ?").bind(id).first();
if (!raw) return null;
const product = parseProductRow(raw as Record<string, unknown>);
```

## Anti-patterns

**Using `VARCHAR(n)` expecting length enforcement.** SQLite ignores the length parameter
in `VARCHAR(n)`. The affinity is TEXT (because "CHAR" is in the name), but no truncation
occurs at `n` characters. Enforce length in application code or a CHECK constraint.

**Relying on `BOOLEAN` as a type name.** `BOOLEAN` has NUMERIC affinity in SQLite. It does
not restrict values to 0/1. Add a CHECK constraint if you need enforcement:
`active INTEGER NOT NULL CHECK (active IN (0, 1))`.

**Storing dates as TEXT.** ISO-8601 strings sort correctly lexicographically but REAL (Julian
day) or INTEGER (Unix epoch) are faster to compare, range-query, and index. Use
`unixepoch()` for epoch storage and `datetime(col, 'unixepoch')` for display.

**Mixing storage conventions in the same column.** Because D1/SQLite permits it, you can end
up with a column that contains both `1` (INTEGER) and `"1"` (TEXT). `WHERE col = 1` will
not match the TEXT row. Establish a single convention and enforce it with CHECK constraints
or application-layer validation.

## Gotchas

- **D1's JavaScript binding does not send booleans as booleans.** Cloudflare's D1 client
  converts JS `true`/`false` to `1`/`0` integers. Do not assume TEXT `"true"`/`"false"`.

- **`null` in JS `.bind()` maps to SQL NULL**, not the string `"null"`. JSON serialisation
  must not be used as a substitute for NULL in bindings.

- **`typeof()` is your debugging friend.** When a comparison behaves unexpectedly, run
  `SELECT typeof(col) FROM table LIMIT 5` to inspect what is actually stored.

- **STRICT tables eliminate these pitfalls.** D1 supports `CREATE TABLE ... STRICT`, which
  enforces declared types rigorously. For new schemas, prefer STRICT tables to avoid
  affinity surprises. See `sqlite-strict-tables-any-type-contract.md`.

- **Index efficiency depends on stored type.** An index on a TEXT column used in a numeric
  comparison may not be used, or may scan more rows than expected. Match the query predicate
  type to the stored type.

## Verification

```typescript
// Smoke test: verify actual stored types match expectations
async function verifyColumnTypes(db: D1Database): Promise<void> {
  // Insert a known-good row
  const id = 1;
  await db.prepare("INSERT OR REPLACE INTO products (id, quantity, sku) VALUES (?, ?, ?)")
    .bind(id, 10, "TEST-SKU")
    .run();

  const types = await db.prepare(`
    SELECT
      typeof(id)       AS id_type,
      typeof(quantity) AS quantity_type,
      typeof(sku)      AS sku_type
    FROM products WHERE id = ?
  `).bind(id).first<Record<string, string>>();

  console.assert(types?.id_type === "integer",  `id must be integer, got ${types?.id_type}`);
  console.assert(types?.quantity_type === "integer", `quantity must be integer, got ${types?.quantity_type}`);
  console.assert(types?.sku_type === "text", `sku must be text, got ${types?.sku_type}`);

  console.log("column type verification: OK", types);
}
```

## Related

- `sqlite-strict-tables-any-type-contract.md` — enforce types at the schema level
- `d1-check-constraint-domain-validation-workers.md` — CHECK constraints for value enforcement
- `d1-typescript-type-generation.md` — generating TypeScript types from D1 schema
- `money-decimal-storage.md` — safe decimal/currency storage patterns
- `d1-json-column-patterns.md` — JSON stored as TEXT in D1

## Sources

- SQLite Type Affinity documentation: https://sqlite.org/datatype3.html
- SQLite STRICT tables: https://sqlite.org/stricttables.html
- Cloudflare D1 type binding behaviour: https://developers.cloudflare.com/d1/worker-api/d1-database/
