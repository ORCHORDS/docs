# D1 Check Constraint Domain Validation Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Application-layer validation in Cloudflare Workers catches most bad input, but gaps appear when data enters the database through migrations, admin scripts, or batch imports that bypass the Worker handler. Without database-level constraints, invalid values — negative prices, illegal enum strings, overlapping date ranges — silently persist and cause subtle downstream bugs.

## Context

D1 runs SQLite which fully supports CHECK constraints at both column and table scope. A CHECK expression can reference any deterministic SQL function — `length()`, `instr()`, `typeof()`, `json_valid()`, regular literals, and arithmetic. Constraints are enforced on every `INSERT` and `UPDATE`, regardless of the call path (Worker handler, `wrangler d1 execute`, migration script). Failed constraints raise `SQLITE_CONSTRAINT_CHECK` (D1 surfaces this as a `D1_ERROR`). CHECK constraints add zero query-time cost on reads; they run only during writes.

## Column-Level CHECK Constraints

Attach a CHECK expression directly to the column declaration for single-column rules:

```sql
-- migrations/0012_add_check_constraints.sql

CREATE TABLE products (
  id          TEXT    PRIMARY KEY,
  tenant_id   TEXT    NOT NULL,
  name        TEXT    NOT NULL CHECK(length(name) >= 1 AND length(name) <= 200),
  price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
  currency    TEXT    NOT NULL CHECK(currency IN ('USD','EUR','GBP','JPY','CAD')),
  status      TEXT    NOT NULL CHECK(status IN ('draft','active','archived')),
  tax_rate    REAL    NOT NULL CHECK(tax_rate >= 0.0 AND tax_rate <= 1.0),
  sku         TEXT             CHECK(sku IS NULL OR length(sku) BETWEEN 3 AND 64),
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
```

```typescript
// src/db/products.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface CreateProductInput {
  id: string;
  tenantId: string;
  name: string;
  priceCents: number;
  currency: string;
  status: 'draft' | 'active' | 'archived';
  taxRate: number;
  sku?: string;
}

export async function createProduct(
  db: D1Database,
  input: CreateProductInput
): Promise<void> {
  try {
    await db
      .prepare(
        `INSERT INTO products (id, tenant_id, name, price_cents, currency, status, tax_rate, sku)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .bind(
        input.id,
        input.tenantId,
        input.name,
        input.priceCents,
        input.currency,
        input.status,
        input.taxRate,
        input.sku ?? null
      )
      .run();
  } catch (err: unknown) {
    // D1 wraps SQLite constraint errors; message contains 'CHECK constraint failed'
    if (err instanceof Error && err.message.includes('CHECK constraint failed')) {
      throw new TypeError(`Invalid product data: ${err.message}`);
    }
    throw err;
  }
}
```

## Table-Level Multi-Column CHECK Constraints

Place cross-column rules as a table-level constraint after all column definitions:

```sql
CREATE TABLE subscriptions (
  id           TEXT    PRIMARY KEY,
  tenant_id    TEXT    NOT NULL,
  plan         TEXT    NOT NULL CHECK(plan IN ('free','pro','enterprise')),
  starts_at    INTEGER NOT NULL,
  ends_at      INTEGER,               -- NULL = open-ended
  trial_ends   INTEGER,
  seats        INTEGER NOT NULL CHECK(seats BETWEEN 1 AND 10000),
  -- Table-level: ends_at must be after starts_at when set
  CHECK(ends_at IS NULL OR ends_at > starts_at),
  -- Table-level: trial must end before subscription starts or within first 30 days
  CHECK(
    trial_ends IS NULL OR
    (trial_ends >= starts_at AND trial_ends <= starts_at + 2592000)
  ),
  -- Table-level: enterprise must have at least 10 seats
  CHECK(plan != 'enterprise' OR seats >= 10)
);
```

```typescript
// Validate plan-seat combination with a typed helper before insert
export type Plan = 'free' | 'pro' | 'enterprise';

export function validateSubscription(plan: Plan, seats: number): void {
  if (plan === 'enterprise' && seats < 10) {
    throw new RangeError('Enterprise plan requires at least 10 seats');
  }
  if (seats < 1 || seats > 10000) {
    throw new RangeError(`seats must be 1–10000, got ${seats}`);
  }
}
// Belt-and-suspenders: TypeScript check + DB constraint both enforce the rule.
```

## JSON Column Validity Constraints

Ensure a TEXT column stores only valid JSON, or only a valid JSON object:

```sql
CREATE TABLE webhooks (
  id          TEXT    PRIMARY KEY,
  tenant_id   TEXT    NOT NULL,
  url         TEXT    NOT NULL CHECK(
                length(url) >= 8 AND
                (url LIKE 'https://%' OR url LIKE 'http://localhost%')
              ),
  headers     TEXT    NOT NULL DEFAULT '{}' CHECK(json_valid(headers)),
  retry_cfg   TEXT    NOT NULL DEFAULT '{}' CHECK(
                json_valid(retry_cfg) AND
                json_type(retry_cfg) = 'object'
              ),
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
```

```typescript
// src/db/webhooks.ts

export async function upsertWebhook(
  db: D1Database,
  id: string,
  tenantId: string,
  url: string,
  headers: Record<string, string>,
  retryConfig: { maxAttempts: number; backoffMs: number }
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO webhooks (id, tenant_id, url, headers, retry_cfg)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         url       = excluded.url,
         headers   = excluded.headers,
         retry_cfg = excluded.retry_cfg`
    )
    .bind(
      id,
      tenantId,
      url,
      JSON.stringify(headers),
      JSON.stringify(retryConfig)
    )
    .run();
}
```

## Adding Constraints to Existing Tables

SQLite's `ALTER TABLE ADD COLUMN` supports constraints on the new column only. To add a CHECK to an existing column, recreate the table:

```sql
-- migrations/0015_add_price_check.sql
-- Step 1: create new table with constraint
CREATE TABLE products_v2 (
  id          TEXT    PRIMARY KEY,
  tenant_id   TEXT    NOT NULL,
  name        TEXT    NOT NULL CHECK(length(name) >= 1 AND length(name) <= 200),
  price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
  currency    TEXT    NOT NULL,
  status      TEXT    NOT NULL CHECK(status IN ('draft','active','archived')),
  tax_rate    REAL    NOT NULL CHECK(tax_rate >= 0.0 AND tax_rate <= 1.0),
  sku         TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Step 2: copy data (rows violating the new constraint will fail here)
INSERT INTO products_v2 SELECT * FROM products;

-- Step 3: replace
DROP TABLE products;
ALTER TABLE products_v2 RENAME TO products;
```

```typescript
// Run migration inside a D1 transaction via exec
export async function runConstraintMigration(db: D1Database): Promise<void> {
  await db.exec(`
    BEGIN;
    CREATE TABLE products_v2 (
      id          TEXT    PRIMARY KEY,
      name        TEXT    NOT NULL CHECK(length(name) >= 1 AND length(name) <= 200),
      price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
      status      TEXT    NOT NULL CHECK(status IN ('draft','active','archived'))
    );
    INSERT INTO products_v2 SELECT id, name, price_cents, status FROM products;
    DROP TABLE products;
    ALTER TABLE products_v2 RENAME TO products;
    COMMIT;
  `);
}
```

## Anti-patterns

- Relying solely on Worker-layer validation without database constraints — batch imports, migration scripts, and admin tooling bypass the Worker; the database is the last line of defense.
- Using `CHECK(currency = 'USD' OR currency = 'EUR' OR …)` instead of `CHECK(currency IN ('USD','EUR',…))` — the `IN` form is more readable and easier to extend.
- Adding complex business logic to CHECK constraints (e.g., subqueries, joins) — SQLite CHECK cannot contain subqueries; only deterministic expressions on the current row's columns are allowed.
- Catching all D1 errors generically and masking constraint violations — check for `'CHECK constraint failed'` in the error message to return a meaningful 400 response rather than a 500.
- Migrating large tables with table-recreation (copy-rename) without first cleaning data that violates the new constraint — the `INSERT INTO … SELECT *` will fail if existing rows don't satisfy the CHECK.

## Gotchas

- SQLite evaluates CHECK constraints on `INSERT` and `UPDATE` but not on `DELETE`. You cannot use a CHECK to prevent deletion based on a column value; use a trigger for that.
- `CHECK(NOT NULL)` is redundant — use the `NOT NULL` column modifier instead; SQLite processes NOT NULL separately from CHECK and gives a clearer error message.
- SQLite does not enforce CHECK constraints in `WITHOUT ROWID` tables when the constraint references columns other than the primary key in certain edge cases — test thoroughly if combining the two features.
- D1 does not expose the constraint name in the error message (unlike PostgreSQL `pg_constraint`); the error reads `CHECK constraint failed: products`. Introspect constraint names via `PRAGMA table_info` or `sqlite_schema`.
- Adding CHECK constraints to a column via `ALTER TABLE ADD COLUMN` with a default value is valid, but the constraint is not retroactively verified against existing rows — only new inserts/updates are checked.

## Verification

```typescript
// tests/check-constraints.test.ts
import { env } from 'cloudflare:test';

describe('CHECK constraint enforcement', () => {
  beforeEach(async () => {
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS products (
        id          TEXT PRIMARY KEY,
        price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
        status      TEXT    NOT NULL CHECK(status IN ('draft','active','archived'))
      )
    `);
    await env.DB.exec(`DELETE FROM products`);
  });

  it('rejects negative price_cents', async () => {
    await expect(
      env.DB.prepare(
        `INSERT INTO products (id, price_cents, status) VALUES ('p1', -1, 'active')`
      ).run()
    ).rejects.toThrow(/CHECK constraint failed/);
  });

  it('rejects invalid status', async () => {
    await expect(
      env.DB.prepare(
        `INSERT INTO products (id, price_cents, status) VALUES ('p2', 100, 'deleted')`
      ).run()
    ).rejects.toThrow(/CHECK constraint failed/);
  });

  it('accepts valid row', async () => {
    const { success } = await env.DB.prepare(
      `INSERT INTO products (id, price_cents, status) VALUES ('p3', 0, 'draft')`
    ).run();
    expect(success).toBe(true);
  });
});
```

```bash
# Inspect constraints on an existing D1 table via sqlite_schema
wrangler d1 execute MY_DB --command \
  "SELECT sql FROM sqlite_schema WHERE type='table' AND name='products'"
```

## Related

- `database/d1-foreign-keys-referential-integrity.md` — referential integrity via FOREIGN KEY
- `database/d1-deferred-foreign-key-transaction-workers.md` — deferred constraint evaluation
- `database/d1-generated-columns-virtual-workers.md` — computed columns that CHECK can reference
- `database/d1-schema-drift-detection-validation.md` — detecting schema changes at runtime
- `database/d1-schema-introspection-sqlite-master-workers.md` — querying constraint definitions

## Sources

- https://www.sqlite.org/lang_createtable.html#check_constraints
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://www.sqlite.org/datatype3.html
