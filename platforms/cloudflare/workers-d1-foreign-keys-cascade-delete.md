# Workers D1 Foreign Keys with Cascade Delete

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You model parent/child data in D1 (e.g., `users` and `orders`) and want deleting a user to automatically remove all their orders without writing multiple DELETE statements in application code. SQLite supports `ON DELETE CASCADE`, but D1 silently ignores foreign key constraints unless you enable them per connection with `PRAGMA foreign_keys = ON`.

---

## Context

SQLite's foreign key enforcement is disabled by default for backward compatibility. D1 wraps SQLite and inherits this behavior: you can define `REFERENCES parent(id) ON DELETE CASCADE` in your schema and D1 will accept the DDL, but without the pragma the cascade never fires. Every HTTP request to a Worker starts a fresh isolate execution context, so the pragma does not persist between requests — you must issue it before any statement that relies on FK enforcement. D1's batch API is the cleanest way to prepend the pragma to a group of related statements in a single round-trip. Testing with Vitest and the `@cloudflare/vitest-pool-workers` pool gives you a real SQLite environment where you can assert that cascade deletes actually removed child rows.

---

## Section 1 — Schema

```sql
-- migrations/0001_schema.sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  email      TEXT    NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS orders (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  total      REAL    NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS order_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  sku        TEXT    NOT NULL,
  qty        INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_orders_user ON orders (user_id);
CREATE INDEX idx_items_order ON order_items (order_id);
```

```toml
# wrangler.toml
name = "d1-fk-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "<your-d1-id>"
```

---

## Section 2 — Implementation

```typescript
// src/lib/db.ts
export interface Env {
  DB: D1Database;
}

/**
 * Run a group of statements with FK enforcement enabled.
 * Always the first statement in any batch that touches FK-constrained tables.
 */
export async function withForeignKeys(
  db: D1Database,
  statements: D1PreparedStatement[]
): Promise<D1Result[]> {
  return db.batch([
    db.prepare("PRAGMA foreign_keys = ON"),
    ...statements,
  ]);
}

// src/handlers/users.ts
import { withForeignKeys, Env } from "../lib/db";

export async function deleteUser(
  userId: number,
  env: Env
): Promise<{ deleted: boolean }> {
  // Single batch: enable FK, then delete the parent row.
  // The cascade removes orders and order_items automatically.
  const results = await withForeignKeys(env.DB, [
    env.DB.prepare("DELETE FROM users WHERE id = ?").bind(userId),
  ]);

  const deleteResult = results[1]; // index 0 = PRAGMA result
  return { deleted: (deleteResult.meta.changes ?? 0) > 0 };
}

export async function createOrderWithItems(
  userId: number,
  total: number,
  items: Array<{ sku: string; qty: number }>,
  env: Env
): Promise<number> {
  // Insert order first, then items — all in one batch with FK enabled.
  const insertOrder = env.DB.prepare(
    "INSERT INTO orders (user_id, total) VALUES (?, ?) RETURNING id"
  ).bind(userId, total);

  const [, orderResult] = await withForeignKeys(env.DB, [insertOrder]);
  const orderId = (orderResult.results[0] as { id: number }).id;

  if (items.length === 0) return orderId;

  const itemStatements = items.map((item) =>
    env.DB.prepare(
      "INSERT INTO order_items (order_id, sku, qty) VALUES (?, ?, ?)"
    ).bind(orderId, item.sku, item.qty)
  );

  await withForeignKeys(env.DB, itemStatements);
  return orderId;
}

// src/index.ts
import { Env } from "./lib/db";
import { deleteUser, createOrderWithItems } from "./handlers/users";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "DELETE" && url.pathname.startsWith("/users/")) {
      const userId = parseInt(url.pathname.split("/")[2], 10);
      const result = await deleteUser(userId, env);
      return Response.json(result);
    }

    if (request.method === "POST" && url.pathname === "/orders") {
      const body = await request.json<{
        userId: number;
        total: number;
        items: Array<{ sku: string; qty: number }>;
      }>();
      const orderId = await createOrderWithItems(
        body.userId,
        body.total,
        body.items,
        env
      );
      return Response.json({ orderId }, { status: 201 });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Section 3 — Vitest Testing

```typescript
// test/cascade.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { withForeignKeys } from "../src/lib/db";
import { deleteUser, createOrderWithItems } from "../src/handlers/users";

describe("cascade delete", () => {
  beforeEach(async () => {
    // Seed: create a user with one order and two items
    await withForeignKeys(env.DB, [
      env.DB.prepare(
        "INSERT INTO users (id, email) VALUES (1, 'alice@example.com')"
      ),
    ]);
    await createOrderWithItems(1, 99.99, [
      { sku: "SKU-A", qty: 2 },
      { sku: "SKU-B", qty: 1 },
    ], env);
  });

  it("removes orders and items when user is deleted", async () => {
    const { deleted } = await deleteUser(1, env);
    expect(deleted).toBe(true);

    const [ordersResult, itemsResult] = await env.DB.batch([
      env.DB.prepare("SELECT COUNT(*) AS n FROM orders WHERE user_id = 1"),
      env.DB.prepare("SELECT COUNT(*) AS n FROM order_items"),
    ]);

    expect((ordersResult.results[0] as { n: number }).n).toBe(0);
    expect((itemsResult.results[0] as { n: number }).n).toBe(0);
  });

  it("rejects an order that references a non-existent user", async () => {
    await expect(
      createOrderWithItems(9999, 10.0, [{ sku: "X", qty: 1 }], env)
    ).rejects.toThrow();
  });
});
```

```bash
# Run tests
npx vitest run

# Apply migration to remote D1
wrangler d1 execute app-db --file=migrations/0001_schema.sql --remote

# Verify cascade manually
wrangler d1 execute app-db --command "INSERT INTO users (email) VALUES ('bob@example.com');" --remote
wrangler d1 execute app-db --command "INSERT INTO orders (user_id, total) VALUES (last_insert_rowid(), 50.00);" --remote
wrangler d1 execute app-db --command "PRAGMA foreign_keys = ON; DELETE FROM users WHERE email = 'bob@example.com';" --remote
wrangler d1 execute app-db --command "SELECT * FROM orders;" --remote
# Expected: empty result set
```

---

## Anti-patterns

- **Omitting `PRAGMA foreign_keys = ON` before each batch** — FK constraints silently do nothing; child rows are orphaned instead of deleted.
- **Running the pragma as a standalone `.run()` and then issuing separate statements** — The pragma applies to a connection-level session; D1 may route separate requests to different underlying connections, so the pragma from a previous call may not cover the next one.
- **Using `db.exec()` for multi-statement scripts with FK dependencies** — `exec()` does not return per-statement results and makes error attribution difficult; prefer `db.batch()`.
- **Not indexing the FK column** — Without an index on `orders.user_id`, a cascade delete performs a full table scan on `orders` for every parent row deleted.

---

## Gotchas

- The `PRAGMA foreign_keys = ON` result itself occupies index 0 in the `batch()` result array; your first real statement result is at index 1.
- D1 does not support `PRAGMA foreign_keys = ON` as a persistent database setting; it must be set in every batch or prepared statement group.
- `ON DELETE SET NULL` is also supported but requires the FK column to be nullable; cascade is simpler when child rows have no meaning without the parent.
- `wrangler d1 execute` with `--command` does not automatically enable FK pragmas, so manual cascade tests must include the pragma in the same `--command` string.
- Vitest with `@cloudflare/vitest-pool-workers` runs a real SQLite instance locally; FK behavior in tests matches D1 production exactly.

---

## Verification

```bash
# Check FK pragma status for the current connection
wrangler d1 execute app-db --command "PRAGMA foreign_keys;" --remote
# Returns: 0 (off) — expected since pragma is per-connection

# Confirm index exists
wrangler d1 execute app-db \
  --command "SELECT name FROM sqlite_master WHERE type='index';" --remote

# Count orphaned orders (should be 0 if cascade works)
wrangler d1 execute app-db \
  --command "SELECT COUNT(*) FROM orders o LEFT JOIN users u ON u.id = o.user_id WHERE u.id IS NULL;" \
  --remote
```

---

## Related

- `workers-r2-signed-url-time-limited-access.md`
- `cloudflare-queues-dlq-handler.md`

---

## Sources

- D1 Batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite Foreign Keys — https://www.sqlite.org/foreignkeys.html
- Vitest Pool Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
