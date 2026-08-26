# Vitest Global Setup D1 Migration Runner

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Vitest test suite for a Cloudflare Workers project that uses D1 fails intermittently
because the local D1 database is either empty, stale, or has a schema that doesn't match
the current migration state. Each developer manually runs `wrangler d1 migrations apply`
before running tests, causing CI failures when someone forgets, and wasting minutes on local
re-runs when the schema drifts.

You need a reliable way to run all pending D1 migrations exactly once before any test file
executes, using the same in-process Miniflare/`@cloudflare/vitest-pool-workers` instance
that the tests themselves use.

---

## Context

Vitest supports a `globalSetup` file (configured in `vitest.config.ts`) that runs **once**
before the entire test suite in the main Node process. A separate `setupFiles` entry runs
once per worker thread / test file. For D1 schema bootstrapping you want the global variant
so migrations execute only one time regardless of how many test files exist.

`@cloudflare/vitest-pool-workers` exposes a programmatic Miniflare API through
`runInDurableObject` and custom pool helpers, but for D1 DDL setup it is often simpler to
use the `better-sqlite3` database that Miniflare creates in `.wrangler/state/v3/d1/` and
apply migrations directly via the Node.js SQLite driver — no Worker runtime is required for
DDL.

For full integration fidelity (migrating through the same `D1Database` binding that Workers
code uses) you can also use `unstable_dev` from `wrangler` in global setup, query the D1
binding, and tear it down after.

Both approaches are covered below.

---

## Prerequisites

```bash
pnpm add -D better-sqlite3 @types/better-sqlite3
# or, if using the wrangler programmatic API:
pnpm add -D wrangler
```

---

## Approach A — Direct SQLite via `better-sqlite3`

This is the fastest approach. Miniflare persists D1 state as a SQLite file. Apply
migrations directly before Vitest starts any worker thread.

```typescript
// test/global-setup.ts
import path from "node:path";
import fs from "node:fs";
import Database from "better-sqlite3";

// Wrangler stores D1 files under .wrangler/state/v3/d1/<database-id>/
// The database id comes from wrangler.toml [[ d1_databases ]] binding.
const D1_DB_NAME = "my-app-db"; // matches `database_name` in wrangler.toml
const WRANGLER_STATE = path.resolve(process.cwd(), ".wrangler/state/v3/d1");
const MIGRATIONS_DIR = path.resolve(process.cwd(), "migrations");

function findD1Path(): string {
  // The directory name is the database uuid; Miniflare creates one automatically.
  // We match by inspecting the .wrangler/state/v3/d1 directory.
  const entries = fs.readdirSync(WRANGLER_STATE, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory()) {
      const candidate = path.join(WRANGLER_STATE, entry.name, "db.sqlite");
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  throw new Error(`D1 sqlite file not found under ${WRANGLER_STATE}`);
}

function getMigrationFiles(): string[] {
  return fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort(); // lexicographic order matches Wrangler convention
}

export async function setup(): Promise<void> {
  // Ensure .wrangler state directory exists (Miniflare creates it on first run,
  // but the first test that opens a D1 binding triggers that — chicken-and-egg).
  // We prime it by opening the path ourselves.
  fs.mkdirSync(WRANGLER_STATE, { recursive: true });

  // Miniflare may not have created the uuid subdirectory yet on a clean checkout.
  // Run a no-op Miniflare dev server tick first if needed (see Pattern B below
  // for the wrangler-based alternative that handles this automatically).
  let dbPath: string;
  try {
    dbPath = findD1Path();
  } catch {
    console.warn(
      "[global-setup] D1 sqlite not yet created; Miniflare will init it on first test run."
    );
    return;
  }

  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");

  // Track applied migrations in a dedicated table (same schema Wrangler uses)
  db.exec(`
    CREATE TABLE IF NOT EXISTS d1_migrations (
      id       INTEGER PRIMARY KEY AUTOINCREMENT,
      name     TEXT    NOT NULL UNIQUE,
      applied_at TEXT  NOT NULL DEFAULT (datetime('now'))
    )
  `);

  const applied = new Set(
    (db.prepare("SELECT name FROM d1_migrations").all() as { name: string }[]).map(
      (r) => r.name
    )
  );

  const applyMigration = db.transaction((name: string, sql: string) => {
    console.log(`[global-setup] Applying migration: ${name}`);
    db.exec(sql);
    db.prepare("INSERT INTO d1_migrations (name) VALUES (?)").run(name);
  });

  for (const file of getMigrationFiles()) {
    if (applied.has(file)) continue;
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, file), "utf8");
    applyMigration(file, sql);
  }

  db.close();
  console.log("[global-setup] D1 migrations complete.");
}

export async function teardown(): Promise<void> {
  // Nothing to tear down for the sqlite approach — Miniflare owns the file lifecycle.
}
```

---

## Approach B — Wrangler `unstable_dev` Programmatic API

Use the official Wrangler API to apply migrations through the `D1Database` binding, matching
the exact environment Workers code runs in.

```typescript
// test/global-setup-wrangler.ts
import { unstable_dev, type UnstableDevWorker } from "wrangler";
import path from "node:path";
import fs from "node:fs";

const MIGRATIONS_DIR = path.resolve(process.cwd(), "migrations");

let worker: UnstableDevWorker | undefined;

export async function setup(): Promise<void> {
  // Start a local dev worker solely to access the D1 binding programmatically.
  // The worker script only needs to expose a migration endpoint.
  worker = await unstable_dev(
    path.resolve(process.cwd(), "src/index.ts"),
    {
      experimental: { disableExperimentalWarning: true },
      local: true,
      persist: true,
      logLevel: "error",
    }
  );

  const migrationFiles = fs
    .readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  for (const file of migrationFiles) {
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, file), "utf8");
    // POST each migration SQL to a dedicated endpoint on the worker.
    // The worker's /admin/migrate endpoint must be enabled only in test mode.
    const resp = await worker.fetch("http://localhost/admin/migrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file, sql }),
    });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Migration ${file} failed: ${body}`);
    }
  }

  console.log("[global-setup] D1 migrations applied via wrangler dev.");
}

export async function teardown(): Promise<void> {
  await worker?.stop();
}
```

The corresponding Worker migration endpoint (guarded by an env flag):

```typescript
// src/index.ts (migration endpoint, guarded by env flag)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (
      request.method === "POST" &&
      new URL(request.url).pathname === "/admin/migrate" &&
      env.ENABLE_TEST_MIGRATION_ENDPOINT === "true"
    ) {
      const { name, sql } = (await request.json()) as { name: string; sql: string };
      await env.DB.exec(sql);
      return Response.json({ ok: true, name });
    }
    // ... normal routing
    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Vitest Config Wiring

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    // globalSetup runs ONCE in the main Node process before any test worker starts
    globalSetup: ["./test/global-setup.ts"],

    // setupFiles runs per worker thread (for per-test fixtures, not DDL)
    setupFiles: ["./test/setup.ts"],

    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          d1Databases: ["DB"],
          // Persist state so the migrations applied in globalSetup survive
          // into the test worker processes
          persistTo: "./.wrangler/state",
        },
      },
    },
  },
});
```

---

## Per-Test Fixture: Seed and Clean Between Tests

Migrations set up the schema once. Individual tests need isolated data. Use a setup file to
wrap each test in a transaction that rolls back on completion.

```typescript
// test/setup.ts
import { env } from "cloudflare:test";

// Reset tables (not schema) between tests using D1 delete-all
beforeEach(async () => {
  // Order matters for foreign keys; reverse dependency order
  await env.DB.exec("DELETE FROM order_items");
  await env.DB.exec("DELETE FROM orders");
  await env.DB.exec("DELETE FROM users");
});
```

For more complex seeding needs, create a helper:

```typescript
// test/fixtures/seed.ts
import { env } from "cloudflare:test";

export async function seedUser(overrides: Partial<{ id: string; email: string }> = {}) {
  const user = {
    id: overrides.id ?? crypto.randomUUID(),
    email: overrides.email ?? `user-${Date.now()}@example.com`,
  };
  await env.DB.prepare("INSERT INTO users (id, email) VALUES (?, ?)")
    .bind(user.id, user.email)
    .run();
  return user;
}
```

---

## CI Integration

```yaml
# .github/workflows/test.yml
- name: Run tests (D1 migrations run automatically in globalSetup)
  run: pnpm vitest run
  env:
    ENABLE_TEST_MIGRATION_ENDPOINT: "true"
```

No separate `wrangler d1 migrations apply --local` step is needed in CI when using either
approach above, since `globalSetup` runs automatically before any test.

---

## Anti-patterns

**Running migrations in `setupFiles` instead of `globalSetup`:**
`setupFiles` runs once per test *file*, so migrations execute N times and can race if
Vitest parallelises file execution. Use `globalSetup` for DDL.

**Hard-coding the D1 sqlite path:**
The path includes an auto-generated UUID that changes on fresh environments. Use the
directory scan approach shown in Approach A, or rely on the wrangler-based Approach B.

**Not persisting Miniflare state between globalSetup and tests:**
Miniflare's `persistTo` must point to the same directory that `globalSetup` wrote into.
If they diverge (e.g. one uses `.wrangler/state` and the other `.wrangler/state/v3`),
tests see an empty DB.

**Applying migrations inside test bodies:**
Each test that calls `wrangler d1 migrations apply` starts an external process, adding
multiple seconds of latency per test. Always hoist this to `globalSetup`.

---

## Gotchas

- `unstable_dev` in Approach B starts a full Wrangler dev server and consumes a local port.
  If another process holds the port, `setup()` throws. Use a distinct port via the `port`
  option or the `WRANGLER_UNSTABLE_DEV_PORT` env var.
- Vitest's `--watch` mode re-runs `setupFiles` but NOT `globalSetup` between runs.
  This is intentional — migrations run once on startup. If you add a new migration file
  while watch mode is running, restart Vitest.
- The `better-sqlite3` package is a native addon. In CI environments that run inside Docker
  make sure the base image architecture matches the native addon build. Use `pnpm rebuild` if
  you get "invalid ELF header" errors.
- Migration files must be deterministically sorted. Rely on the numeric prefix convention
  Wrangler uses (e.g. `0001_create_users.sql`) and sort lexicographically.
- `db.exec()` in D1 (the Workers binding) does not support multiple semicolon-separated
  statements in all runtime versions. If a migration file contains multiple statements, split
  them and execute them in sequence.

---

## Verification

```bash
# Confirm migrations run exactly once before tests
pnpm vitest run --reporter=verbose 2>&1 | grep '\[global-setup\]'

# Confirm schema exists in tests
pnpm vitest run --testNamePattern="schema smoke"
```

Expected output in `--reporter=verbose`:
```
[global-setup] Applying migration: 0001_create_users.sql
[global-setup] Applying migration: 0002_create_orders.sql
[global-setup] D1 migrations complete.
```

On subsequent runs with no new migration files:
```
[global-setup] D1 migrations complete.
```
(no "Applying" lines — idempotent.)

---

## Related

- `miniflare-d1-test-seeding-fixtures.md`
- `wrangler-d1-migrations-local-dev-workflow.md`
- `wrangler-unstable-dev-programmatic-api-testing.md`
- `vitest-workers-miniflare-testing-setup.md`
- `vitest-pool-workers-cloudflare-test-api.md`

---

## Sources

- Vitest global setup docs: https://vitest.dev/config/#globalsetup
- `@cloudflare/vitest-pool-workers` readme: https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Wrangler `unstable_dev` API: https://developers.cloudflare.com/workers/wrangler/api/
- Cloudflare D1 migrations reference: https://developers.cloudflare.com/d1/reference/migrations/
- `better-sqlite3` docs: https://github.com/WiseLibs/better-sqlite3
