# D1 Seed Fixtures for Workers Integration Tests

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker reads and writes to a D1 database, and you want integration tests that exercise the full request-to-database path against a real (local) D1 instance rather than mocking SQL calls. You need a repeatable way to apply the schema, seed deterministic test rows before each test, call the Worker via `SELF.fetch()`, assert the database state afterwards, and tear down cleanly.

---

## Context
Wrangler's `--local` flag for `d1 execute` runs SQLite-backed D1 locally without touching Cloudflare's remote service, making it safe for CI. `@cloudflare/vitest-pool-workers` exposes the same local D1 instance to both the Worker under test and the test file, so you can use the `env.DB` binding directly in `beforeEach` to seed rows and in assertions to read state. Teardown via `DELETE FROM` is faster than `DROP TABLE` and avoids re-running the schema migration after every test.

---

## Setup / Config

```toml
# wrangler.toml
name = "my-d1-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "local-db-id"
```

```bash
# Apply schema to the local D1 instance used by Wrangler
npx wrangler d1 execute my-db --local --file=schema.sql
```

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS products (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
  id         TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(id),
  quantity   INTEGER NOT NULL,
  status     TEXT NOT NULL DEFAULT 'pending'
);
```

## Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /orders — create an order
    if (request.method === "POST" && url.pathname === "/orders") {
      const body = await request.json<{ productId: string; quantity: number }>();

      // Verify product exists
      const product = await env.DB
        .prepare("SELECT id, price_cents FROM products WHERE id = ?")
        .bind(body.productId)
        .first<{ id: string; price_cents: number }>();

      if (!product) {
        return Response.json({ error: "Product not found" }, { status: 404 });
      }

      const orderId = crypto.randomUUID();
      await env.DB
        .prepare(
          "INSERT INTO orders (id, product_id, quantity, status) VALUES (?, ?, ?, 'pending')"
        )
        .bind(orderId, body.productId, body.quantity)
        .run();

      return Response.json({ orderId, status: "pending" }, { status: 201 });
    }

    // GET /orders/:id — read an order
    const orderMatch = url.pathname.match(/^\/orders\/([\w-]+)$/);
    if (request.method === "GET" && orderMatch) {
      const order = await env.DB
        .prepare("SELECT * FROM orders WHERE id = ?")
        .bind(orderMatch[1])
        .first();

      if (!order) {
        return Response.json({ error: "Order not found" }, { status: 404 });
      }

      return Response.json(order);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Seed Script + Integration Tests

```typescript
// src/index.test.ts
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import type { Env } from "./index";

const db = (env as unknown as Env).DB;

// ---- Seed helpers -------------------------------------------------------

async function seedProducts() {
  await db
    .prepare(
      "INSERT INTO products (id, name, price_cents) VALUES (?, ?, ?)"
    )
    .bind("prod-001", "Widget Pro", 4999)
    .run();

  await db
    .prepare(
      "INSERT INTO products (id, name, price_cents) VALUES (?, ?, ?)"
    )
    .bind("prod-002", "Gadget Plus", 9999)
    .run();
}

async function teardown() {
  // Fastest teardown: DELETE all rows, keep schema intact
  await db.exec("DELETE FROM orders");
  await db.exec("DELETE FROM products");
}

// ---- Test suite ---------------------------------------------------------

describe("Order handler — D1 integration", () => {
  beforeEach(async () => {
    await teardown(); // ensure clean slate even if a previous test failed
    await seedProducts();
  });

  afterEach(async () => {
    await teardown();
  });

  it("creates an order and persists it to D1", async () => {
    const response = await SELF.fetch("https://example.com/orders", {
      method: "POST",
      body: JSON.stringify({ productId: "prod-001", quantity: 3 }),
      headers: { "Content-Type": "application/json" },
    });

    expect(response.status).toBe(201);
    const { orderId, status } = await response.json<{
      orderId: string;
      status: string;
    }>();
    expect(status).toBe("pending");

    // Assert DB state directly
    const row = await db
      .prepare("SELECT * FROM orders WHERE id = ?")
      .bind(orderId)
      .first<{ product_id: string; quantity: number; status: string }>();

    expect(row).not.toBeNull();
    expect(row!.product_id).toBe("prod-001");
    expect(row!.quantity).toBe(3);
    expect(row!.status).toBe("pending");
  });

  it("returns 404 for an unknown product", async () => {
    const response = await SELF.fetch("https://example.com/orders", {
      method: "POST",
      body: JSON.stringify({ productId: "does-not-exist", quantity: 1 }),
      headers: { "Content-Type": "application/json" },
    });

    expect(response.status).toBe(404);

    // Confirm no order was inserted
    const { results } = await db.prepare("SELECT id FROM orders").all();
    expect(results).toHaveLength(0);
  });

  it("reads an existing order by id", async () => {
    // Pre-insert an order bypassing the Worker
    const knownId = "order-known-123";
    await db
      .prepare(
        "INSERT INTO orders (id, product_id, quantity, status) VALUES (?, ?, ?, ?)"
      )
      .bind(knownId, "prod-002", 5, "pending")
      .run();

    const response = await SELF.fetch(
      `https://example.com/orders/${knownId}`
    );
    expect(response.status).toBe(200);

    const order = await response.json<{ id: string; quantity: number }>();
    expect(order.id).toBe(knownId);
    expect(order.quantity).toBe(5);
  });

  it("returns 404 for a non-existent order", async () => {
    const response = await SELF.fetch(
      "https://example.com/orders/ghost-order-999"
    );
    expect(response.status).toBe(404);
  });
});
```

---

## Anti-patterns
- **Running `DROP TABLE` in teardown** — you then need to re-apply the full schema in `beforeEach`, which is slower and brittle if the migration runner isn't idempotent.
- **Sharing test data IDs across tests** — hard-coded IDs that survive between tests due to a failed `afterEach` cause false positives; always clean up in `beforeEach` as well.
- **Using the remote D1 database in CI** — always pass `--local` to `wrangler d1 execute` and ensure `vitest-pool-workers` targets the local instance to keep tests fast and free.
- **Asserting only on the HTTP response, not the DB** — integration tests should verify side effects in the database, not just the returned JSON.

---

## Gotchas
- The local D1 SQLite file lives under `.wrangler/state/`; delete this directory to fully reset state between CI runs if tests are consistently dirty.
- `env.DB` inside the test file and `env.DB` inside the Worker are the **same** in-memory instance under `vitest-pool-workers` — writes from the Worker are immediately visible in your assertions.
- `D1Database.exec()` executes multiple semicolon-separated statements; use it for bulk `DELETE` teardowns to avoid multiple round-trips.
- Numeric values from D1 come back as JavaScript `number`, but TEXT primary keys come back as `string` — type your `.first<T>()` calls carefully.

---

## Verification

```bash
# Apply schema locally before first test run
npx wrangler d1 execute my-db --local --file=schema.sql

# Run integration tests
npx vitest run src/index.test.ts

# Inspect local DB state manually
npx wrangler d1 execute my-db --local --command="SELECT * FROM orders LIMIT 10"

# Reset local DB state
rm -rf .wrangler/state/v3/d1
```

---

## Related
- `workers-vitest-env-bindings-mock-service.md`
- `workers-test-durable-object-alarm-vitest.md`

---

## Sources
- Cloudflare D1 local development — https://developers.cloudflare.com/d1/best-practices/local-development/
- Vitest pool workers testing guide — https://developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/
