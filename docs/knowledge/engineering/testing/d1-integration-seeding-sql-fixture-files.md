# D1 SQL Fixture File Seeding Strategies for Integration Tests

2026-08-24 / example.com / production

---

## Symptom / Use-case

Your D1 integration tests need a known database state before each test run, but you currently seed data by calling your application's HTTP API endpoints in `beforeEach` hooks. This means your seeding code exercises the same code paths under test — a bug in the POST handler silently corrupts the fixture, causing cascading failures that look unrelated. You need to seed the database at the SQL layer, bypassing application logic, so that test failures point at the system under test rather than the fixture setup.

---

## Context

Cloudflare D1's `database.exec(sql)` method accepts multi-statement SQL strings, making it straightforward to load fixture files directly. In Miniflare / `@cloudflare/vitest-pool-workers`, the in-process D1 binding can execute these files synchronously within the test process. In Wrangler's `wrangler d1 execute` mode, the same files seed a local SQLite database or a remote D1 instance.

SQL fixture files are preferable to programmatic seeding via application code because:
- They are independent of the application layer — schema bugs become visible immediately.
- They are diffable in version control — a changed fixture is a first-class code review artifact.
- They load faster than HTTP-round-trip seeding for large datasets.
- They compose predictably: run schema migration SQL first, then fixture SQL.

This article covers four SQL seeding strategies and when to choose each. It complements `d1-test-fixtures-wrangler-seed.md` (which covers `wrangler d1 execute`) by focusing on fixture file organisation, reset strategies, and per-test isolation patterns.

---

## Strategy 1: Schema + Fixture SQL Pair

Maintain one schema file and one fixture file per test suite context. Apply them in `beforeAll` and reset with `DELETE FROM` in `beforeEach`.

```
test/
  fixtures/
    schema.sql        ← CREATE TABLE IF NOT EXISTS statements
    seed-catalog.sql  ← INSERT rows for catalog tests
    seed-orders.sql   ← INSERT rows for order tests
```

```sql
-- test/fixtures/schema.sql
CREATE TABLE IF NOT EXISTS products (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  stock       INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
  id          TEXT PRIMARY KEY,
  product_id  TEXT NOT NULL REFERENCES products(id),
  qty         INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

```sql
-- test/fixtures/seed-catalog.sql
INSERT INTO products (id, name, price_cents, stock) VALUES
  ('prod-001', 'Widget A', 999,  50),
  ('prod-002', 'Widget B', 1999, 10),
  ('prod-003', 'Widget C', 499,  0);
```

```ts
// test/integration/catalog.test.ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import worker from "../../src/index";

const SCHEMA = readFileSync(resolve(__dirname, "../fixtures/schema.sql"), "utf8");
const SEED = readFileSync(resolve(__dirname, "../fixtures/seed-catalog.sql"), "utf8");

beforeAll(async () => {
  await env.DB.exec(SCHEMA);
});

beforeEach(async () => {
  // Wipe rows, keep schema — order matters for FK constraints
  await env.DB.exec(`DELETE FROM orders; DELETE FROM products;`);
  await env.DB.exec(SEED);
});
```

---

## Strategy 2: Numbered Migration + Fixture Pipeline

Mirror the production migration pipeline in tests. Apply each migration once in `beforeAll` and re-seed in `beforeEach`. Guarantees tests run against the same schema version as production.

```
migrations/
  0001_create_products.sql
  0002_add_sku_column.sql
test/
  fixtures/
    baseline.sql
```

```ts
// test/setup/run-migrations.ts
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { D1Database } from "@cloudflare/workers-types";

export async function runMigrations(db: D1Database, migrationsDir: string) {
  const files = readdirSync(migrationsDir)
    .filter((f) => f.endsWith(".sql"))
    .sort(); // lexicographic order = migration order

  for (const file of files) {
    const sql = readFileSync(resolve(migrationsDir, file), "utf8");
    await db.exec(sql);
  }
}
```

```ts
// test/integration/products.test.ts
import { env } from "cloudflare:test";
import { beforeAll, beforeEach, describe, it, expect } from "vitest";
import { runMigrations } from "../setup/run-migrations";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const BASELINE = readFileSync(
  resolve(__dirname, "../fixtures/baseline.sql"),
  "utf8",
);

beforeAll(async () => {
  await runMigrations(env.DB, resolve(__dirname, "../../migrations"));
});

beforeEach(async () => {
  // Truncate in reverse FK dependency order
  await env.DB.exec(`
    DELETE FROM order_items;
    DELETE FROM orders;
    DELETE FROM products;
  `);
  await env.DB.exec(BASELINE);
});
```

---

## Strategy 3: Per-Test Savepoint (SQLite Savepoints)

When migrations are slow and many tests share the same base fixture, use SQLite savepoints to wrap each test in a pseudo-transaction that is rolled back. This avoids re-running `DELETE + INSERT` between tests.

```ts
// test/setup/savepoint-fixture.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function withSavepoint<T>(
  db: D1Database,
  name: string,
  fn: () => Promise<T>,
): Promise<T> {
  await db.exec(`SAVEPOINT ${name};`);
  try {
    const result = await fn();
    await db.exec(`ROLLBACK TO SAVEPOINT ${name};`);
    await db.exec(`RELEASE SAVEPOINT ${name};`);
    return result;
  } catch (err) {
    await db.exec(`ROLLBACK TO SAVEPOINT ${name};`);
    await db.exec(`RELEASE SAVEPOINT ${name};`);
    throw err;
  }
}
```

```ts
// test/integration/savepoint.test.ts
import { env } from "cloudflare:test";
import { it, expect } from "vitest";
import { withSavepoint } from "../setup/savepoint-fixture";

it("deleting a product does not leak into the next test", async () => {
  await withSavepoint(env.DB, "sp1", async () => {
    await env.DB.exec(`DELETE FROM products WHERE id = 'prod-001';`);
    const { results } = await env.DB.prepare(
      `SELECT COUNT(*) AS c FROM products;`,
    ).all<{ c: number }>();
    expect(results[0].c).toBe(2);
  });

  // After savepoint rollback, prod-001 is back
  const { results } = await env.DB.prepare(
    `SELECT COUNT(*) AS c FROM products;`,
  ).all<{ c: number }>();
  expect(results[0].c).toBe(3);
});
```

---

## Strategy 4: Parameterised Fixture Builder

For tests that need variations on the baseline fixture, generate SQL strings from a builder rather than maintaining multiple files.

```ts
// test/fixtures/product-builder.ts
let _seq = 0;

export interface ProductFixture {
  id?: string;
  name?: string;
  priceCents?: number;
  stock?: number;
}

export function buildProductSQL(overrides: ProductFixture = {}): string {
  const id = overrides.id ?? `prod-${String(++_seq).padStart(4, "0")}`;
  const name = overrides.name ?? `Product ${id}`;
  const price = overrides.priceCents ?? 1000;
  const stock = overrides.stock ?? 10;
  return `INSERT INTO products (id, name, price_cents, stock) VALUES ('${id}', '${name}', ${price}, ${stock});`;
}

export function resetSeq() {
  _seq = 0;
}
```

```ts
// test/integration/out-of-stock.test.ts
import { env } from "cloudflare:test";
import { beforeEach, describe, it, expect } from "vitest";
import { buildProductSQL, resetSeq } from "../fixtures/product-builder";
import worker from "../../src/index";

beforeEach(async () => {
  resetSeq();
  await env.DB.exec(`DELETE FROM products;`);
  await env.DB.exec(buildProductSQL({ stock: 0, name: "Sold Out Item" }));
  await env.DB.exec(buildProductSQL({ stock: 5, name: "In Stock Item" }));
});

describe("GET /products?inStock=true", () => {
  it("returns only in-stock products", async () => {
    const res = await worker.fetch(
      new Request("https://worker.test/products?inStock=true"),
      env,
    );
    const body = await res.json<{ products: unknown[] }>();
    expect(body.products).toHaveLength(1);
  });
});
```

---

## Anti-patterns

- **Seeding via the application's own HTTP endpoints** — application bugs corrupt fixtures silently; seed at the SQL layer.
- **Sharing mutable fixture state between parallel test files** — Vitest runs files concurrently by default; each file must use an independent D1 instance or the Miniflare pool isolates them.
- **Committing fixture SQL with hardcoded datetimes** — `datetime('now')` defaults in the schema handle this; avoid `'2024-01-01T00:00:00Z'` literals that break time-sensitive queries.
- **Forgetting FK ordering on delete** — SQLite enforces FK constraints when `PRAGMA foreign_keys = ON`; delete child tables first.
- **Using `TRUNCATE` (MySQL syntax) in SQLite** — SQLite does not support `TRUNCATE`; use `DELETE FROM table` without a `WHERE` clause.

---

## Gotchas

- `db.exec()` accepts multiple statements separated by semicolons, but Miniflare's D1 implementation may have subtle differences from production D1 regarding multi-statement batches — always test migration compatibility against `wrangler d1 execute --local` as well.
- Savepoints in D1 are SQLite savepoints; they do not persist across `fetch()` boundaries in the real runtime (each DO alarm or Worker invocation is a separate connection). Savepoints are therefore only safe in Miniflare's single-process test environment.
- `readFileSync` from `node:fs` is not available inside a `@cloudflare/vitest-pool-workers` isolate — read fixture files in a Vitest `globalSetup` file or pass file contents through `cloudflare:test`'s `env` mechanism using a custom binding.
- Large fixture files (thousands of rows) can time out Miniflare's default test timeout; chunk large seeds into batches or use `db.batch()` with prepared statements.

---

## Verification

```bash
# Apply schema and baseline seed to local D1
npx wrangler d1 execute my-db --local --file=test/fixtures/schema.sql
npx wrangler d1 execute my-db --local --file=test/fixtures/baseline.sql

# Run integration tests against local D1
npx vitest run test/integration --reporter=verbose

# Confirm no row bleed between tests by checking counts post-suite
npx wrangler d1 execute my-db --local --command="SELECT COUNT(*) FROM products;"
```

Expected: row counts match baseline seed after the suite completes (confirming proper reset).

---

## Related

- `d1-test-fixtures-wrangler-seed.md` — `wrangler d1 execute` seeding workflow
- `test-data-management-d1-factories.md` — factory builder pattern for D1 test data
- `miniflare-d1-integration-testing.md` — Miniflare D1 binding setup
- `miniflare-d1-migration-testing.md` — migration application in Miniflare
- `database-seeding-tests.md` — general database seeding concepts
- `transactional-test-rollback.md` — rollback strategies for test isolation

---

## Sources

- D1 `database.exec()` API: https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/#databaseexec
- SQLite savepoints: https://www.sqlite.org/lang_savepoint.html
- Wrangler D1 execute: https://developers.cloudflare.com/d1/reference/wrangler-commands/#execute
- `@cloudflare/vitest-pool-workers` global setup: https://developers.cloudflare.com/workers/testing/vitest-integration/get-started/
