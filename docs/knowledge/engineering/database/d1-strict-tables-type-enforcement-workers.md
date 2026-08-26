# D1 STRICT Tables — Type Enforcement in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your D1 queries silently insert the string `"42"` into an `INTEGER` column, or store `NULL` in a
column you assumed was `NOT NULL`, because SQLite's default type-affinity rules are permissive.
You want hard type enforcement at the database-engine level — not just inside your TypeScript layer
— so bad data never reaches the table even when ad-hoc SQL is run outside your application.

## Context

SQLite's classic "type affinity" system allows any value to be stored in any column regardless of
declared type. SQLite 3.37 (November 2021) introduced **STRICT tables**, and Cloudflare D1 ships
SQLite 3.46+ which fully supports them. A `STRICT` table rejects values that do not match the
column's declared type, raising `SQLITE_CONSTRAINT_DATATYPE` (error code 5). Only six type tokens
are permitted in STRICT columns: `INT`, `INTEGER`, `REAL`, `TEXT`, `BLOB`, and `ANY`. `ANY`
explicitly opts a single column back into flexible affinity while the rest of the table stays
strict.

Key D1 constraints that interact with STRICT:
- D1 rows are capped at 1 MB; BLOB columns in STRICT tables follow the same limit.
- D1's JavaScript driver returns all integers as `number` (safe up to 2^53 − 1); if you need
  full 64-bit integers use `REAL` or store as `TEXT`.
- STRICT mode enforcement happens inside the SQLite engine before any D1 network layer, so it is
  enforced equally in `env.DB.prepare()` calls and in Wrangler's `--local` mode.

## Creating a STRICT Table

```sql
-- migrations/0001_products_strict.sql
CREATE TABLE products (
  id        INTEGER PRIMARY KEY,
  sku       TEXT    NOT NULL,
  price     REAL    NOT NULL CHECK (price >= 0),
  stock     INT     NOT NULL DEFAULT 0,
  metadata  ANY,          -- flexible column, keeps classic affinity
  created_at TEXT   NOT NULL
) STRICT;
```

```typescript
// src/db/migrate.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function applyMigration(db: D1Database): Promise<void> {
  const ddl = await (await fetch("/migrations/0001_products_strict.sql")).text();
  await db.exec(ddl);
}
```

## Verifying STRICT Mode at Runtime

```typescript
// src/db/introspect.ts
import type { D1Database } from "@cloudflare/workers-types";

interface TableInfo {
  name: string;
  strict: number; // 1 = STRICT, 0 = classic
}

export async function isStrictTable(
  db: D1Database,
  tableName: string
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT strict FROM pragma_table_list WHERE name = ?`
    )
    .bind(tableName)
    .first<TableInfo>();
  return row?.strict === 1;
}
```

## Inserting with Type Safety

```typescript
// src/repositories/product.repository.ts
import type { D1Database } from "@cloudflare/workers-types";

interface NewProduct {
  sku: string;
  price: number;
  stock: number;
  metadata?: unknown;
}

interface Product extends NewProduct {
  id: number;
  created_at: string;
}

export async function createProduct(
  db: D1Database,
  product: NewProduct
): Promise<Product> {
  // STRICT table will reject: string price, NULL sku, integer-as-text stock
  const result = await db
    .prepare(
      `INSERT INTO products (sku, price, stock, metadata, created_at)
       VALUES (?, ?, ?, ?, ?)
       RETURNING *`
    )
    .bind(
      product.sku,
      product.price,
      product.stock,
      product.metadata !== undefined
        ? JSON.stringify(product.metadata)
        : null,
      new Date().toISOString()
    )
    .first<Product>();

  if (!result) throw new Error("Insert returned no row");
  return result;
}
```

## Handling STRICT Type Errors in Workers

```typescript
// src/handlers/product.handler.ts
import type { D1Database } from "@cloudflare/workers-types";
import { createProduct } from "../repositories/product.repository";

function isD1TypeError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  // D1 surfaces the SQLite error message directly
  return (
    err.message.includes("SQLITE_CONSTRAINT_DATATYPE") ||
    err.message.includes("cannot store") // SQLite 3.37 wording
  );
}

export async function handleCreateProduct(
  request: Request,
  db: D1Database
): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  if (
    typeof (body as Record<string, unknown>).price !== "number" ||
    typeof (body as Record<string, unknown>).sku !== "string"
  ) {
    return new Response("price must be a number, sku must be a string", {
      status: 422,
    });
  }

  try {
    const product = await createProduct(db, body as Parameters<typeof createProduct>[1]);
    return Response.json(product, { status: 201 });
  } catch (err) {
    if (isD1TypeError(err)) {
      return new Response(`Type constraint violation: ${(err as Error).message}`, {
        status: 422,
      });
    }
    throw err;
  }
}
```

## Mixing STRICT and Non-STRICT Tables in JOINs

```typescript
// src/db/queries.ts — join a STRICT products table to a classic tags table
import type { D1Database } from "@cloudflare/workers-types";

interface ProductWithTags {
  id: number;
  sku: string;
  tags: string; // JSON array
}

export async function getProductsWithTags(
  db: D1Database
): Promise<ProductWithTags[]> {
  // STRICT only applies to the table's own DML; JOINs work normally
  const { results } = await db
    .prepare(
      `SELECT p.id, p.sku, json_group_array(t.name) AS tags
       FROM products p
       LEFT JOIN product_tags pt ON pt.product_id = p.id
       LEFT JOIN tags t          ON t.id = pt.tag_id
       GROUP BY p.id`
    )
    .all<ProductWithTags>();
  return results;
}
```

## Anti-patterns

- **Using `TEXT NOT NULL` and storing numbers as strings** in a STRICT table — works but loses
  numeric comparisons (`price > 10` on TEXT uses lexicographic order).
- **Casting in application code only** without a STRICT table — a raw `wrangler d1 execute` or
  external migration tool bypasses application logic and may silently coerce values.
- **Using STRICT with `BLOB` for JSON** — prefer `TEXT` for JSON; BLOB requires the driver to send
  a `Uint8Array`, not a JavaScript string.
- **Omitting `ANY` on truly polymorphic columns** — forcing every column to be strict when the
  column genuinely stores mixed types causes unnecessary errors and workarounds.

## Gotchas

- **`INTEGER PRIMARY KEY` aliasing still works** in STRICT tables — the rowid alias behaviour is
  unchanged; the column must be `INTEGER`, not `INT`, for the alias to apply.
- **Boolean values**: SQLite has no `BOOLEAN` type token; STRICT tables do not allow `BOOLEAN`.
  Use `INT` with `CHECK (col IN (0, 1))` instead.
- **`strftime()` return type**: functions like `strftime()`, `date()`, and `json()` return `TEXT`;
  assigning their result to an `INT` column in a STRICT table will fail at runtime.
- **Wrangler local mode** enforces STRICT identically to remote D1 — use it to catch violations
  in CI before deploying.
- **`pragma_table_list`** is the authoritative way to check `strict`; `pragma_table_info` does
  not expose it.

## Verification

```bash
# Check STRICT flag via Wrangler
wrangler d1 execute <DB_NAME> --command \
  "SELECT name, strict FROM pragma_table_list WHERE type='table';"

# Attempt a type violation locally to confirm enforcement
wrangler d1 execute <DB_NAME> --local --command \
  "INSERT INTO products (sku, price, stock, created_at) VALUES ('X', 'not-a-number', 0, '2026-08-23');"
# Expected: error: SQLITE_CONSTRAINT_DATATYPE
```

```typescript
// test/strict.test.ts (Vitest + @cloudflare/vitest-pool-workers)
import { expect, it } from "vitest";
import { env } from "cloudflare:test";

it("rejects non-numeric price in STRICT products table", async () => {
  await expect(
    env.DB.prepare(
      "INSERT INTO products (sku, price, stock, created_at) VALUES (?, ?, ?, ?)"
    )
      .bind("SKU-1", "twelve", 0, "2026-08-23")
      .run()
  ).rejects.toThrow(/SQLITE_CONSTRAINT_DATATYPE|cannot store/i);
});
```

## Related

- `d1-check-constraint-domain-validation-workers.md`
- `d1-column-affinity-type-coercion-workers.md`
- `sqlite-strict-tables-any-type-contract.md`
- `d1-schema-versioning-wrangler-migrations.md`

## Sources

- SQLite STRICT Tables spec: https://www.sqlite.org/stricttables.html
- Cloudflare D1 docs — SQLite compatibility: https://developers.cloudflare.com/d1/reference/compatibility-matrix/
- SQLite 3.37.0 release notes: https://www.sqlite.org/changes.html
- `pragma_table_list` reference: https://www.sqlite.org/pragma.html#pragma_table_list
