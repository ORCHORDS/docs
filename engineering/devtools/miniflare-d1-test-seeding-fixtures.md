# Miniflare D1 Test Data Seeding and Fixtures

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Workers tests hit a D1 database binding and fail intermittently because test state leaks between tests. You seed data in `beforeAll` but parallel test files share the same D1 instance. You need isolated, deterministic D1 state per test file (or per test) without a real D1 remote database.

## Context

`@cloudflare/vitest-pool-workers` runs each test file in its own Miniflare V8 isolate. By default all test files in the same Vitest run share the same set of Miniflare bindings, including D1 databases. This means data inserted by one test file can bleed into another when tests run in parallel.

Miniflare 4.x exposes a `D1Database` in-process binding backed by SQLite (via `better-sqlite3`). The binding is available through the `SELF` or `env` helper from `cloudflare:test`. Each isolate gets its own fresh SQLite in-memory store when `isolatedStorage: true` is set, which is the recommended setting for D1 fixture-based testing.

---

## Enabling Isolated Storage Per Test File

```typescript
// apps/worker/vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        isolatedStorage: true,   // each test file gets its own D1 state
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

With `isolatedStorage: true` Miniflare provisions a separate in-memory SQLite database for each test file. Data written in one file is invisible to others. The database is destroyed when the file's isolate is torn down.

---

## Applying Schema Migrations Before Tests

```typescript
// apps/worker/test/helpers/seed.ts
import { env } from "cloudflare:test";

export async function applyMigrations(): Promise<void> {
  const db = env.DB;   // D1Database binding from wrangler.toml

  // Run schema DDL — match what wrangler d1 migrations apply would run
  await db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id      TEXT PRIMARY KEY,
      email   TEXT NOT NULL UNIQUE,
      role    TEXT NOT NULL DEFAULT 'member',
      created INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      token      TEXT PRIMARY KEY,
      user_id    TEXT NOT NULL REFERENCES users(id),
      expires_at INTEGER NOT NULL
    );
  `);
}
```

`db.exec()` accepts a multi-statement SQL string separated by semicolons, matching the format of Wrangler migration files. This is the fastest way to apply a schema in tests without invoking the Wrangler CLI.

---

## Fixture Factories for Deterministic Test Data

```typescript
// apps/worker/test/helpers/factories.ts
import { env } from "cloudflare:test";

interface UserRow {
  id: string;
  email: string;
  role: string;
  created: number;
}

let userCounter = 0;

export async function createUser(
  overrides: Partial<UserRow> = {}
): Promise<UserRow> {
  userCounter += 1;
  const user: UserRow = {
    id: `user-${userCounter}`,
    email: `user${userCounter}@example.com`,
    role: "member",
    created: Date.now(),
    ...overrides,
  };

  await env.DB.prepare(
    "INSERT INTO users (id, email, role, created) VALUES (?, ?, ?, ?)"
  )
    .bind(user.id, user.email, user.role, user.created)
    .run();

  return user;
}

export async function createSession(userId: string): Promise<string> {
  const token = `tok-${Math.random().toString(36).slice(2)}`;
  const expiresAt = Date.now() + 3_600_000;

  await env.DB.prepare(
    "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)"
  )
    .bind(token, userId, expiresAt)
    .run();

  return token;
}
```

Counter-based IDs avoid UUID collision without requiring a random-number library. Factories return the inserted row so tests can assert on the exact data.

---

## Using Fixtures in Test Files

```typescript
// apps/worker/test/auth.test.ts
import { SELF } from "cloudflare:test";
import { applyMigrations, createUser, createSession } from "./helpers/factories";
import { describe, it, expect, beforeEach } from "vitest";

beforeEach(async () => {
  await applyMigrations();
});

describe("GET /api/me", () => {
  it("returns 401 when no session token is provided", async () => {
    const res = await SELF.fetch("https://worker.test/api/me");
    expect(res.status).toBe(401);
  });

  it("returns the user profile for a valid session", async () => {
    const user = await createUser({ role: "admin" });
    const token = await createSession(user.id);

    const res = await SELF.fetch("https://worker.test/api/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status).toBe(200);

    const body = await res.json<{ role: string }>();
    expect(body.role).toBe("admin");
  });
});
```

Because `isolatedStorage: true` is set, the `beforeEach` schema application starts from a clean database each time. There is no `afterEach` teardown needed.

---

## Batch-seeding Large Fixture Sets

```typescript
// apps/worker/test/helpers/seed.ts
import { env } from "cloudflare:test";

export async function seedUsers(count: number): Promise<void> {
  // D1 batch() runs multiple statements in a single round-trip
  const statements = Array.from({ length: count }, (_, i) =>
    env.DB.prepare(
      "INSERT INTO users (id, email, role, created) VALUES (?, ?, ?, ?)"
    ).bind(
      `bulk-user-${i}`,
      `bulk${i}@example.com`,
      "member",
      Date.now() + i
    )
  );

  await env.DB.batch(statements);
}
```

`D1Database.batch()` executes all statements inside a single SQLite transaction, making bulk seeding significantly faster than individual `.run()` calls.

---

## Anti-patterns

- **Sharing a single `beforeAll` across parallel test files without `isolatedStorage`** — inserts from file A appear in file B's queries; tests pass or fail non-deterministically based on execution order.
- **Using `wrangler d1 execute --local` to seed test databases** — this writes to the persistent `.wrangler/state/v3/d1/` directory on disk, which survives between test runs and pollutes state.
- **Storing D1 instances in module-level variables** — the binding reference is only valid within the Miniflare isolate context; capturing it before `beforeEach` can yield stale or undefined references.
- **Running migrations with `db.exec()` in a `beforeAll` with `isolatedStorage: true`** — `beforeAll` runs once per file, which is correct; but if you rely on test-level isolation within the file, use `beforeEach` instead.

---

## Gotchas

- `isolatedStorage: true` creates a new SQLite database per file but not per individual test. To isolate individual tests within a file, wrap each test in a transaction that is rolled back in `afterEach`.
- D1's `exec()` method in Miniflare silently ignores `--` SQL comments but errors on `/**/` block comments with certain SQLite versions. Strip comments from migration files before passing to `exec()`.
- Miniflare's D1 does not enforce foreign key constraints by default. Add `PRAGMA foreign_keys = ON;` at the top of `applyMigrations()` if your schema relies on them.
- The in-memory SQLite in Miniflare does not persist to disk. Running `wrangler d1 migrations apply --local` before tests is unnecessary and may create `.wrangler/state/` directories that confuse the local dev setup.
- `D1Database.batch()` is atomic in D1 production but Miniflare's batch is a loop of individual statements. Tests relying on batch atomicity may behave differently in production.

---

## Verification

```bash
# Run a single test file to confirm isolation works
pnpm --filter ./apps/worker vitest run test/auth.test.ts --reporter=verbose

# Run two files in parallel and confirm no state bleed
pnpm --filter ./apps/worker vitest run test/auth.test.ts test/users.test.ts

# Confirm schema is applied fresh each run (no "table already exists" errors)
pnpm --filter ./apps/worker vitest run --reporter=verbose 2>&1 | grep -i "already exists"
# Expected: (no output)
```

---

## Related

- `miniflare-storage-backend-testing.md` — KV, R2, and Durable Objects storage backends
- `miniflare-v4-migration-guide.md` — upgrading from Miniflare 3.x API
- `vitest-workers-miniflare-testing-setup.md` — base isolate configuration
- `wrangler-dev-local-d1-r2-kv.md` — local D1 bindings for `wrangler dev`

---

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/isolation-and-concurrency/
- https://developers.cloudflare.com/d1/best-practices/local-development/
- https://miniflare.dev/storage/d1
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
