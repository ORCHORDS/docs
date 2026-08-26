# D1 Ephemeral Test Database Miniflare Teardown Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Integration tests that hit D1 leave data behind between test runs, causing false positives (old rows making counts wrong), false negatives (UNIQUE conflicts from previous seeds), and slow suites (each test fights over shared state). You need each test — or each test file — to start with a clean, schema-applied D1 database and tear it down completely when done.

---

## Context

Miniflare 3 (shipped with Wrangler 3+) provides a local D1 emulation layer backed by SQLite files on disk. Each `new Miniflare({...})` call creates isolated Workers environments. D1 databases are stored in temporary directories under the system's temp path by default, but Miniflare also supports in-memory mode and explicit teardown.

Key methods:

| API | Purpose |
|---|---|
| `new Miniflare({ d1Databases: [...] })` | Create an environment with one or more D1 bindings |
| `mf.getD1Database("BINDING_NAME")` | Get a `D1Database` handle to seed or query directly |
| `mf.dispose()` | Tear down the environment, releasing file handles and deleting temp files |
| `D1Database.batch([...])` | Apply schema migrations in one round trip |

Test isolation strategies:

- **Per-suite isolation**: One `Miniflare` instance per test file; `dispose()` in `afterAll`.
- **Per-test isolation**: New `Miniflare` per `it()` block; `dispose()` in `afterEach`. Slowest but fully clean.
- **Transaction rollback isolation**: Single instance; wrap each test in a transaction, rollback in `afterEach`. Fastest but only works if your handler code doesn't commit mid-test.

---

## Miniflare Setup and Teardown — Per-suite Pattern

```typescript
// test/helpers/miniflare-setup.ts
import { Miniflare, MiniflareOptions } from "miniflare";
import type { D1Database } from "@cloudflare/workers-types";

export interface TestContext {
  mf: Miniflare;
  db: D1Database;
}

/**
 * Creates an isolated Miniflare environment with a D1 binding.
 * Call this in beforeAll() and dispose() in afterAll().
 */
export async function createTestEnv(
  workerScript: string,
  migrationSql: string[]
): Promise<TestContext> {
  const options: MiniflareOptions = {
    modules: true,
    script: workerScript,
    d1Databases: ["DB"],
    // Explicit in-memory flag — no disk files to clean up
    d1Persist: false,
  };

  const mf = new Miniflare(options);
  const db = await mf.getD1Database("DB");

  // Apply migrations in order
  for (const sql of migrationSql) {
    await db.exec(sql);
  }

  return { mf, db };
}

export async function teardownTestEnv(ctx: TestContext): Promise<void> {
  await ctx.mf.dispose();
}
```

---

## Loading Migrations from Disk

```typescript
// test/helpers/load-migrations.ts
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

/**
 * Read all *.sql migration files from a directory, sorted lexicographically.
 * Mirrors how `wrangler d1 migrations apply` processes files.
 */
export async function loadMigrations(migrationsDir: string): Promise<string[]> {
  const entries = await readdir(migrationsDir, { withFileTypes: true });
  const sqlFiles = entries
    .filter((e) => e.isFile() && e.name.endsWith(".sql"))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((e) => join(migrationsDir, e.name));

  const contents = await Promise.all(
    sqlFiles.map((f) => readFile(f, "utf-8"))
  );

  return contents;
}
```

---

## Vitest Per-suite Isolation

```typescript
// test/article-repo.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { join } from "node:path";
import { createTestEnv, teardownTestEnv, type TestContext } from "./helpers/miniflare-setup";
import { loadMigrations } from "./helpers/load-migrations";
import { searchArticles } from "../src/repositories/article-search";

const WORKER_SCRIPT = `
  import { searchArticles } from "./src/repositories/article-search";
  export default {
    async fetch(req, env) {
      const url = new URL(req.url);
      const q = url.searchParams.get("q") || "";
      const results = await searchArticles(env.DB, q);
      return Response.json(results);
    }
  };
`;

describe("Article search repository", () => {
  let ctx: TestContext;

  beforeAll(async () => {
    const migrations = await loadMigrations(
      join(import.meta.dirname, "../migrations")
    );
    ctx = await createTestEnv(WORKER_SCRIPT, migrations);

    // Seed test data once for the suite
    await ctx.db.batch([
      ctx.db.prepare(
        `INSERT INTO articles (title, body) VALUES ('Running Shoes', 'Best shoes for runners')`
      ),
      ctx.db.prepare(
        `INSERT INTO articles (title, body) VALUES ('Walking Guide', 'A guide to daily walks')`
      ),
    ]);
  });

  afterAll(async () => {
    // dispose() deletes in-memory SQLite data and releases resources
    await teardownTestEnv(ctx);
  });

  it("finds stemmed variants", async () => {
    const results = await searchArticles(ctx.db, "run");
    expect(results).toHaveLength(1);
    expect(results[0].title).toBe("Running Shoes");
  });

  it("returns empty for no match", async () => {
    const results = await searchArticles(ctx.db, "cycling");
    expect(results).toHaveLength(0);
  });
});
```

---

## Per-test Isolation — Fresh Database Each Test

For tests that mutate schema or need truly clean state:

```typescript
// test/order-repo.test.ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { join } from "node:path";
import { Miniflare } from "miniflare";
import type { D1Database } from "@cloudflare/workers-types";
import { loadMigrations } from "./helpers/load-migrations";

describe("Order repository — per-test isolation", () => {
  let mf: Miniflare;
  let db: D1Database;

  beforeEach(async () => {
    const migrations = await loadMigrations(
      join(import.meta.dirname, "../migrations")
    );

    mf = new Miniflare({
      modules: true,
      script: `export default { fetch: () => new Response("ok") }`,
      d1Databases: ["DB"],
      d1Persist: false,
    });

    db = await mf.getD1Database("DB");

    // Apply all migrations fresh for each test
    for (const sql of migrations) {
      await db.exec(sql);
    }
  });

  afterEach(async () => {
    await mf.dispose(); // Completely destroys in-memory database
  });

  it("inserts an order", async () => {
    await db
      .prepare(`INSERT INTO orders (id, user_id, total_cents) VALUES (?1, ?2, ?3)`)
      .bind("ord-1", "usr-1", 5000)
      .run();

    const row = await db
      .prepare(`SELECT * FROM orders WHERE id = ?1`)
      .bind("ord-1")
      .first<{ id: string; total_cents: number }>();

    expect(row?.id).toBe("ord-1");
    expect(row?.total_cents).toBe(5000);
  });

  it("enforces UNIQUE constraint", async () => {
    await db
      .prepare(`INSERT INTO orders (id, user_id, total_cents) VALUES ('dup', 'u', 100)`)
      .run();

    await expect(
      db.prepare(`INSERT INTO orders (id, user_id, total_cents) VALUES ('dup', 'u', 200)`).run()
    ).rejects.toThrow(/UNIQUE/);
  });
});
```

---

## Transaction Rollback Isolation (Fastest)

When your code under test doesn't auto-commit mid-handler, you can skip re-creating the database between tests by rolling back:

```typescript
// test/helpers/rollback-isolation.ts
import type { D1Database } from "@cloudflare/workers-types";

/**
 * Wraps a test body in a BEGIN/ROLLBACK pair so the database state is
 * restored after each test. The database and schema only need to be
 * created once per suite.
 *
 * LIMITATION: Does not work if the code under test issues a COMMIT.
 */
export async function withRollback(
  db: D1Database,
  test: () => Promise<void>
): Promise<void> {
  await db.prepare("BEGIN").run();
  try {
    await test();
  } finally {
    await db.prepare("ROLLBACK").run();
  }
}
```

Usage:

```typescript
// test/user-repo.test.ts
import { describe, it, beforeAll, afterAll } from "vitest";
import { withRollback } from "./helpers/rollback-isolation";
// ...

describe("User repository — rollback isolation", () => {
  let ctx: TestContext;

  beforeAll(async () => {
    // Schema applied ONCE for the whole suite
    ctx = await createTestEnv(WORKER_SCRIPT, migrations);
  });

  afterAll(async () => {
    await teardownTestEnv(ctx);
  });

  it("creates a user", async () => {
    await withRollback(ctx.db, async () => {
      await ctx.db
        .prepare(`INSERT INTO users (id, email) VALUES ('u-1', 'a@b.com')`)
        .run();
      const row = await ctx.db
        .prepare(`SELECT email FROM users WHERE id = 'u-1'`)
        .first<{ email: string }>();
      expect(row?.email).toBe("a@b.com");
      // Rollback happens here — row is gone for the next test
    });
  });
});
```

---

## Vitest Configuration for Miniflare

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    // Run test files in separate worker threads to avoid Miniflare port conflicts
    pool: "threads",
    poolOptions: {
      threads: {
        singleThread: false,
        maxThreads: 4,
      },
    },
    // Increase timeout — Miniflare initialisation can take 1-2 s
    testTimeout: 30_000,
    hookTimeout: 30_000,
    globals: false,
  },
});
```

---

## Anti-patterns

- **Sharing a single Miniflare instance across test files in parallel mode.** Vitest runs test files in parallel by default. A shared Miniflare instance will race, causing intermittent failures. Use per-file instances or `singleThread: true`.
- **Not calling `mf.dispose()` in `afterAll`/`afterEach`.** Miniflare holds open SQLite file handles. Leaked handles cause "database is locked" errors in subsequent test runs in the same process.
- **Using `d1Persist: true` without a test-specific directory.** Persisting to disk requires explicit cleanup (`fs.rm(dir, { recursive: true })`); otherwise test data accumulates across runs.
- **Applying migrations inside `it()` blocks.** Migration DDL should run in `beforeAll` or `beforeEach`, not inside test bodies. DDL inside tests makes the test fail for the wrong reason if schema creation fails.
- **Using rollback isolation for handlers that call `ctx.waitUntil`.** `waitUntil` may fire after the test's rollback, writing to the database in a "clean" state. Use per-test `Miniflare` instances for async background operations.

---

## Gotchas

- **`db.exec()` vs `db.prepare().run()`**: `db.exec()` runs a multi-statement SQL string in one call (good for migration files). `db.prepare().run()` is for single parameterised statements. Mix them correctly.
- **Miniflare `d1Persist: false` stores data in memory only**: This is the fastest option but data is lost on `dispose()`. Perfect for tests. Do NOT set `d1Persist: false` in a production-like dev environment.
- **`mf.getD1Database()` is async**: Unlike Wrangler env bindings, Miniflare's API is async. Always `await` it before using the handle.
- **Miniflare version pinning**: Miniflare versions track Workerd and Workers runtime versions. Pin `"miniflare": "^3.x.y"` in `devDependencies` and update alongside Wrangler to avoid behaviour divergence from production D1.
- **FTS5 virtual tables and rollback**: FTS5 writes to shadow tables internally. Rolling back a transaction that inserted FTS rows rolls back the FTS index as well — this is correct behaviour but can surprise if you inspect the FTS table directly after rollback.

---

## Verification

```bash
# Run the test suite with coverage
npx vitest run --coverage

# Verify no Miniflare processes leaked
ps aux | grep miniflare

# Confirm no test SQLite files remain (when d1Persist defaults to temp dir)
ls /tmp | grep miniflare-d1
```

Expected: zero stale processes, zero leftover SQLite files.

---

## Related

- `d1-seeding-ci-cd-pipelines.md` — Seeding D1 in CI before integration tests
- `d1-migrations-wrangler-ci-cd.md` — Wrangler migration runner for test pipelines
- `d1-schema-drift-detection-validation.md` — Schema comparison to catch migration drift
- `database-test-fixtures-isolation.md` — General test fixture isolation patterns
- `d1-foreign-keys-referential-integrity.md` — Enabling FK enforcement in test SQLite

---

## Sources

- Miniflare 3 documentation: https://miniflare.dev/
- Vitest configuration: https://vitest.dev/config/
- Cloudflare D1 local development: https://developers.cloudflare.com/d1/build-with-d1/local-development/
- SQLite in-memory databases: https://www.sqlite.org/inmemorydb.html
- Wrangler D1 test environments: https://developers.cloudflare.com/workers/testing/vitest-integration/
