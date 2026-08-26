# D1 Batch and Transaction Testing with Vitest

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
D1's `batch()` API and statement chaining behave differently from single-query execution, and transaction rollback semantics are easy to mistest. This article covers how to verify batch operations and implicit transactions against a local D1 instance in Vitest.

## Context
Cloudflare D1 runs SQLite under the hood. The `db.batch([...stmts])` call executes multiple prepared statements in a single round-trip with implicit transactional semantics — if one fails, all roll back. Miniflare 3 emulates this behavior locally, making unit and integration tests reliable without a live Cloudflare account. Tests use `@cloudflare/vitest-pool-workers` with `wrangler.toml` declaring a `[[d1_databases]]` binding.

## Project Setup

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "local"
migrations_dir = "migrations"
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

Bootstrap a test schema in a `beforeAll` block so each suite starts with clean tables:

```typescript
// tests/helpers/db.ts
import { env } from "cloudflare:test";

export async function applySchema(): Promise<void> {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS accounts (
      id TEXT PRIMARY KEY,
      balance INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id TEXT NOT NULL,
      amount INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);
}

export async function clearTables(): Promise<void> {
  await env.DB.exec("DELETE FROM transactions; DELETE FROM accounts;");
}
```

## Testing Batch Inserts

```typescript
// tests/batch-insert.test.ts
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { applySchema, clearTables } from "./helpers/db";

beforeAll(applySchema);
beforeEach(clearTables);

describe("D1 batch inserts", () => {
  it("inserts multiple rows atomically", async () => {
    const result = await env.DB.batch([
      env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("acc-1", 1000),
      env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("acc-2", 500),
      env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("acc-3", 250),
    ]);

    expect(result).toHaveLength(3);
    result.forEach((r) => expect(r.success).toBe(true));

    const { results } = await env.DB.prepare("SELECT COUNT(*) as n FROM accounts").first<{ n: number }>();
    // first() returns the row directly
    const row = await env.DB.prepare("SELECT COUNT(*) as n FROM accounts").first<{ n: number }>();
    expect(row?.n).toBe(3);
  });

  it("rolls back entire batch when one statement fails", async () => {
    await env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("acc-1", 100).run();

    await expect(
      env.DB.batch([
        env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("acc-new", 50),
        // Violates PK constraint — causes rollback
        env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("acc-1", 999),
      ])
    ).rejects.toThrow();

    const row = await env.DB.prepare("SELECT COUNT(*) as n FROM accounts").first<{ n: number }>();
    expect(row?.n).toBe(1); // Only the pre-existing row remains
  });
});
```

## Testing Transfer Logic with Batch

Test a funds-transfer pattern that uses a batch to debit and credit atomically:

```typescript
// src/transfer.ts
export async function transfer(
  db: D1Database,
  fromId: string,
  toId: string,
  amount: number
): Promise<void> {
  await db.batch([
    db.prepare("UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?")
      .bind(amount, fromId, amount),
    db.prepare("UPDATE accounts SET balance = balance + ? WHERE id = ?")
      .bind(amount, toId),
    db.prepare("INSERT INTO transactions (account_id, amount) VALUES (?, ?)")
      .bind(fromId, -amount),
    db.prepare("INSERT INTO transactions (account_id, amount) VALUES (?, ?)")
      .bind(toId, amount),
  ]);
}
```

```typescript
// tests/transfer.test.ts
import { it, expect, beforeAll, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { transfer } from "../src/transfer";
import { applySchema, clearTables } from "./helpers/db";

beforeAll(applySchema);
beforeEach(async () => {
  await clearTables();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("alice", 500),
    env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)").bind("bob", 100),
  ]);
});

it("debits sender and credits receiver", async () => {
  await transfer(env.DB, "alice", "bob", 200);
  const alice = await env.DB.prepare("SELECT balance FROM accounts WHERE id = ?").bind("alice").first<{ balance: number }>();
  const bob = await env.DB.prepare("SELECT balance FROM accounts WHERE id = ?").bind("bob").first<{ balance: number }>();
  expect(alice?.balance).toBe(300);
  expect(bob?.balance).toBe(300);
});

it("records two transaction rows", async () => {
  await transfer(env.DB, "alice", "bob", 50);
  const { results } = await env.DB.prepare("SELECT * FROM transactions ORDER BY id").all();
  expect(results).toHaveLength(2);
  expect(results[0].amount).toBe(-50);
  expect(results[1].amount).toBe(50);
});
```

## Testing Prepared Statement Reuse

Prepared statements can be reused across `bind` calls; test that bindings do not bleed between calls:

```typescript
// tests/prepared-reuse.test.ts
import { it, expect, beforeAll, beforeEach } from "vitest";
import { env } from "cloudflare:test";
import { applySchema, clearTables } from "./helpers/db";

beforeAll(applySchema);
beforeEach(clearTables);

it("prepared statement bindings are independent across calls", async () => {
  const stmt = env.DB.prepare("INSERT INTO accounts (id, balance) VALUES (?, ?)");
  await stmt.bind("x", 10).run();
  await stmt.bind("y", 20).run();

  const x = await env.DB.prepare("SELECT balance FROM accounts WHERE id = ?").bind("x").first<{ balance: number }>();
  const y = await env.DB.prepare("SELECT balance FROM accounts WHERE id = ?").bind("y").first<{ balance: number }>();
  expect(x?.balance).toBe(10);
  expect(y?.balance).toBe(20);
});
```

## Anti-patterns
- Do not call `db.exec()` for parametric data — it does not support bound parameters and is vulnerable to injection.
- Avoid sharing a `D1Database` mock with `vi.fn()` stubs; the real Miniflare D1 instance catches constraint and type errors that mocks silently swallow.
- Do not assert `results.length` from a `batch()` call to verify row counts — inspect the DB directly with a `SELECT COUNT(*)`.

## Gotchas
- D1's `batch()` uses implicit savepoints, not `BEGIN TRANSACTION` — nested batches are not supported.
- `first()` returns `null` (not `undefined`) when no row matches; always guard with `?.` or a null check.
- Local Miniflare D1 does not enforce WAL-mode concurrency limits that production D1 enforces; parallel test suites may pass locally but contend in CI against a live database.
- `db.exec()` runs all statements but does not return per-statement metadata; use `batch()` when you need `success`/`meta` per statement.

## Verification
`npx vitest run tests/batch-insert.test.ts tests/transfer.test.ts` — all tests should pass. Run `npx wrangler d1 execute app-db --local --command "SELECT * FROM accounts"` to inspect state after a failing test.

## Related
- [d1-testing-local.md](d1-testing-local.md)
- [d1-test-fixtures-wrangler-seed.md](d1-test-fixtures-wrangler-seed.md)
- [miniflare-d1-integration-testing.md](miniflare-d1-integration-testing.md)
- [test-data-management-d1-factories.md](test-data-management-d1-factories.md)

## Sources
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/reference/local-development/
