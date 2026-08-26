# Vitest Workers D1 Schema Migration Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You maintain a D1 database with a series of numbered SQL migration files. You want
automated tests that verify each migration applies cleanly, that post-migration schema
matches a golden shape, and that rollbacks (where supported) leave the database
unchanged. Running migrations manually before every CI build is slow and leaves gaps
when a migration silently breaks a foreign-key constraint or index.

## Context

D1 exposes `db.exec()` for running arbitrary SQL and `db.prepare()` for parameterised
queries. In the `@cloudflare/vitest-pool-workers` environment, each test file runs
inside a real Workers runtime with an isolated D1 instance. Migration files are
typically stored as `migrations/0001_init.sql`, `migrations/0002_add_users.sql`, and
so on. The test strategy is: start from an empty database, apply migrations one at a
time, assert schema shape after each step, then assert that application queries still
resolve correctly.

---

## Setting Up the Vitest Pool Workers Project

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          d1Databases: ["DB"],
        },
      },
    },
  },
});
```

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "app"
database_id = "local-only"
migrations_dir = "migrations"
```

---

## Loading Migration Files at Test Time

```typescript
// test/helpers/migrations.ts
import fs from "node:fs/promises";
import path from "node:path";

export async function readMigrations(dir: string): Promise<Array<{ name: string; sql: string }>> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const sqlFiles = entries
    .filter((e) => e.isFile() && e.name.endsWith(".sql"))
    .sort((a, b) => a.name.localeCompare(b.name));

  return Promise.all(
    sqlFiles.map(async (e) => ({
      name: e.name,
      sql: await fs.readFile(path.join(dir, e.name), "utf8"),
    }))
  );
}

export async function applyMigration(db: D1Database, sql: string): Promise<void> {
  // D1 exec() runs multi-statement SQL; split on semicolon for safety.
  const statements = sql
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);

  for (const stmt of statements) {
    await db.exec(stmt);
  }
}
```

---

## Schema Introspection Helpers

```typescript
// test/helpers/schema.ts
export interface ColumnInfo {
  name: string;
  type: string;
  notnull: number;
  dflt_value: string | null;
  pk: number;
}

export interface IndexInfo {
  name: string;
  unique: number;
  origin: string;
}

export async function getColumns(db: D1Database, table: string): Promise<ColumnInfo[]> {
  const result = await db.prepare(`PRAGMA table_info(?1)`).bind(table).all<ColumnInfo>();
  return result.results;
}

export async function getIndexes(db: D1Database, table: string): Promise<IndexInfo[]> {
  const result = await db.prepare(`PRAGMA index_list(?1)`).bind(table).all<IndexInfo>();
  return result.results;
}

export async function tableExists(db: D1Database, table: string): Promise<boolean> {
  const row = await db
    .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name=?1`)
    .bind(table)
    .first<{ name: string }>();
  return row !== null;
}
```

---

## Writing the Migration Tests

```typescript
// test/migrations.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { readMigrations, applyMigration } from "./helpers/migrations";
import { getColumns, getIndexes, tableExists } from "./helpers/schema";
import path from "node:path";

const MIGRATIONS_DIR = path.resolve(__dirname, "../migrations");

describe("D1 schema migrations", () => {
  let db: D1Database;

  beforeEach(() => {
    // Each test gets a fresh, empty D1 via pool worker isolation.
    db = env.DB;
  });

  it("applies migration 0001 and creates the users table", async () => {
    const migrations = await readMigrations(MIGRATIONS_DIR);
    await applyMigration(db, migrations[0].sql); // 0001_init.sql

    expect(await tableExists(db, "users")).toBe(true);

    const cols = await getColumns(db, "users");
    const colNames = cols.map((c) => c.name);
    expect(colNames).toContain("id");
    expect(colNames).toContain("email");
    expect(colNames).toContain("created_at");

    const idCol = cols.find((c) => c.name === "id")!;
    expect(idCol.pk).toBe(1);
    expect(idCol.type.toUpperCase()).toBe("INTEGER");
  });

  it("applies migration 0002 and adds the posts table with FK", async () => {
    const migrations = await readMigrations(MIGRATIONS_DIR);
    await applyMigration(db, migrations[0].sql);
    await applyMigration(db, migrations[1].sql); // 0002_add_posts.sql

    expect(await tableExists(db, "posts")).toBe(true);

    const cols = await getColumns(db, "posts");
    expect(cols.map((c) => c.name)).toContain("user_id");

    // Verify FK is enforced at runtime.
    await db.exec("PRAGMA foreign_keys = ON");
    await expect(
      db.prepare("INSERT INTO posts (title, user_id) VALUES (?1, ?2)").bind("orphan", 9999).run()
    ).rejects.toThrow(/FOREIGN KEY/i);
  });

  it("applies all migrations end-to-end without error", async () => {
    const migrations = await readMigrations(MIGRATIONS_DIR);
    for (const m of migrations) {
      await expect(applyMigration(db, m.sql)).resolves.toBeUndefined();
    }
  });

  it("migration is idempotent when wrapped in IF NOT EXISTS", async () => {
    const migrations = await readMigrations(MIGRATIONS_DIR);
    await applyMigration(db, migrations[0].sql);
    // Re-applying must not throw if the migration used IF NOT EXISTS.
    await expect(applyMigration(db, migrations[0].sql)).resolves.toBeUndefined();
  });

  it("existing data survives a schema-only ALTER TABLE migration", async () => {
    const migrations = await readMigrations(MIGRATIONS_DIR);
    await applyMigration(db, migrations[0].sql);

    await db.prepare("INSERT INTO users (email) VALUES (?1)").bind("alice@example.com").run();

    // migration 0003 adds a nullable column — existing rows must survive.
    await applyMigration(db, migrations[2].sql);

    const row = await db
      .prepare("SELECT email FROM users WHERE email = ?1")
      .bind("alice@example.com")
      .first<{ email: string }>();
    expect(row?.email).toBe("alice@example.com");
  });
});
```

---

## Anti-patterns

- Running `db.exec()` with the entire multi-migration SQL blob in a single call.
  One bad statement silently aborts the rest in SQLite without a clear error boundary.
- Asserting only that `exec()` did not throw without verifying schema shape. Migrations
  can succeed but create wrong column types.
- Sharing a single D1 instance across all tests in a `describe` block without resetting
  between tests; migration state bleeds between cases.
- Checking column count instead of column names — future migrations add columns and
  break count-based assertions unnecessarily.

## Gotchas

- `PRAGMA foreign_keys = ON` must be set per-connection in SQLite/D1; it is OFF by
  default. Always enable it explicitly in tests that verify FK constraints.
- D1 `exec()` returns a `D1ExecResult` not a `D1Result`; it has no `.results` array.
  Use `prepare().all()` for introspection queries.
- `@cloudflare/vitest-pool-workers` re-creates the D1 binding for each test file worker
  but NOT between individual tests in the same file. Use `beforeEach` to drop and
  recreate tables if you need a truly blank slate inside a single file.
- SQLite `PRAGMA table_info()` does not accept a bound parameter on all D1 versions;
  if binding fails, interpolate the table name directly (safe since it comes from your
  own test code, not user input).

## Verification

```bash
# Run only migration tests
npx vitest run test/migrations.test.ts

# Run with verbose output to see each migration step
npx vitest run --reporter=verbose test/migrations.test.ts
```

Expected output: all five test cases pass with no D1 errors in the console.

## Related

- `miniflare-d1-migration-testing.md` — Miniflare-only approach using `MiniflareD1` directly
- `d1-test-fixtures-wrangler-seed.md` — seeding D1 with fixture data after migrations
- `vitest-workers-kv-namespace-isolation.md` — parallel isolation patterns applicable to D1

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://www.sqlite.org/pragma.html#pragma_table_info
- https://developers.cloudflare.com/d1/worker-api/d1-database/#exec
