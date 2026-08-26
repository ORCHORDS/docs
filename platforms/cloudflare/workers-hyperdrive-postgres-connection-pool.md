# Workers Hyperdrive — Postgres Connection Pooling

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers are stateless and spawn thousands of isolates globally; each isolate opening a fresh TLS connection to Postgres overwhelms the database's connection limit within seconds under moderate traffic. Hyperdrive maintains a regional connection pool close to each data center and hands Workers a pre-authenticated connection string that re-uses pooled connections, eliminating per-request connection overhead.

---

## Context

Hyperdrive wraps your Postgres database with a regional connection pooler (PgBouncer-compatible) and exposes a `connectionString` property on the binding that your Worker passes directly to the `postgres` (Postgres.js) npm package. Because multiple requests within the same Workers isolate share the same Node.js-compatible module scope, the `sql` client created from `env.HYPERDRIVE.connectionString` is reused across sequential requests in that isolate, reducing handshake costs further. For local development, Wrangler's `--persist` flag combined with the `HYPERDRIVE_LOCAL_CONNECTION_STRING` environment variable lets you point at a local Postgres instance without modifying application code. All queries must be parameterized — Hyperdrive does not alter query semantics, and SQL injection through string concatenation is just as dangerous as with direct Postgres.

---

## Section 1 — wrangler.toml

```toml
name = "hyperdrive-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[hyperdrive]]
binding = "HYPERDRIVE"
id = "<your-hyperdrive-config-id>"
# Created via: wrangler hyperdrive create my-hyperdrive \
#   --connection-string="postgres://user:pass@db.example.com:5432/mydb"

[dev]
# Local dev: override connection string without touching binding
# Set in .dev.vars (not committed):
# HYPERDRIVE_LOCAL_CONNECTION_STRING=postgres://localhost:5432/mydb_dev
```

```
# .dev.vars  (git-ignored)
HYPERDRIVE_LOCAL_CONNECTION_STRING=postgres://postgres:postgres@localhost:5432/mydb_dev
```

---

## Section 2 — Implementation

```typescript
// src/db.ts
import postgres from "postgres";

export interface Env {
  HYPERDRIVE: Hyperdrive;
  HYPERDRIVE_LOCAL_CONNECTION_STRING?: string;
}

/**
 * Module-level cache: the same sql client is reused across requests
 * within the same isolate instance. Workers garbage-collect the isolate
 * (and its connections) after idle timeout, so this is safe.
 */
let _sql: ReturnType<typeof postgres> | null = null;

export function getClient(env: Env): ReturnType<typeof postgres> {
  if (_sql) return _sql;

  // In local dev wrangler substitutes the HYPERDRIVE binding with a passthrough
  // that reads HYPERDRIVE_LOCAL_CONNECTION_STRING.
  const connectionString =
    env.HYPERDRIVE_LOCAL_CONNECTION_STRING ?? env.HYPERDRIVE.connectionString;

  _sql = postgres(connectionString, {
    // Hyperdrive manages the pool; keep the client lean
    max: 5,
    idle_timeout: 20,
    connect_timeout: 10,
    // Disable prepared statement caching — Hyperdrive's pooler may route
    // requests to different backend connections where named statements
    // are not available.
    prepare: false,
  });

  return _sql;
}

// src/handlers/products.ts
import { getClient, Env } from "../db";

export interface Product {
  id: number;
  name: string;
  price: number;
  stock: number;
}

export async function listProducts(
  env: Env,
  limit = 20,
  offset = 0
): Promise<Product[]> {
  const sql = getClient(env);
  // Always use tagged template literals — sql`` prevents SQL injection
  const rows = await sql<Product[]>`
    SELECT id, name, price, stock
    FROM products
    ORDER BY id
    LIMIT ${limit} OFFSET ${offset}
  `;
  return rows;
}

export async function getProduct(
  env: Env,
  id: number
): Promise<Product | null> {
  const sql = getClient(env);
  const [row] = await sql<Product[]>`
    SELECT id, name, price, stock
    FROM products
    WHERE id = ${id}
  `;
  return row ?? null;
}

export async function decrementStock(
  env: Env,
  productId: number,
  qty: number
): Promise<{ success: boolean; remaining: number }> {
  const sql = getClient(env);

  const [updated] = await sql<Array<{ stock: number }>>`
    UPDATE products
    SET stock = stock - ${qty}
    WHERE id = ${productId}
      AND stock >= ${qty}
    RETURNING stock
  `;

  if (!updated) {
    return { success: false, remaining: 0 };
  }

  return { success: true, remaining: updated.stock };
}

// src/index.ts
import { Env } from "./db";
import { listProducts, getProduct, decrementStock } from "./handlers/products";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/products" && request.method === "GET") {
      const limit = parseInt(url.searchParams.get("limit") ?? "20", 10);
      const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
      const products = await listProducts(env, limit, offset);
      return Response.json(products);
    }

    if (url.pathname.startsWith("/products/") && request.method === "GET") {
      const id = parseInt(url.pathname.split("/")[2], 10);
      const product = await getProduct(env, id);
      if (!product) return new Response("Not found", { status: 404 });
      return Response.json(product);
    }

    if (url.pathname.startsWith("/products/") && url.pathname.endsWith("/reserve") && request.method === "POST") {
      const id = parseInt(url.pathname.split("/")[2], 10);
      const { qty } = await request.json<{ qty: number }>();
      const result = await decrementStock(env, id, qty);
      if (!result.success) {
        return Response.json({ error: "Insufficient stock" }, { status: 409 });
      }
      return Response.json(result);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Section 3 — Local Dev and Integration Tests

```bash
# 1. Start a local Postgres instance
docker run -d \
  --name pg-local \
  -e POSTGRES_DB=mydb_dev \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16-alpine

# 2. Create the schema
psql postgres://postgres:postgres@localhost:5432/mydb_dev -c "
  CREATE TABLE IF NOT EXISTS products (
    id    SERIAL PRIMARY KEY,
    name  TEXT   NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
  );
  INSERT INTO products (name, price, stock) VALUES
    ('Widget A', 9.99, 100),
    ('Widget B', 19.99, 50);
"

# 3. Run local Worker (reads .dev.vars for HYPERDRIVE_LOCAL_CONNECTION_STRING)
wrangler dev --persist

# 4. Test endpoints
curl http://localhost:8787/products
curl http://localhost:8787/products/1
curl -X POST http://localhost:8787/products/1/reserve \
  -H "Content-Type: application/json" \
  -d '{"qty": 5}'
```

```typescript
// test/products.test.ts
import { describe, it, expect, beforeAll } from "vitest";
import { env } from "cloudflare:test";

// For integration tests, set HYPERDRIVE_LOCAL_CONNECTION_STRING in vitest env
describe("products", () => {
  beforeAll(async () => {
    // Seed test data via direct SQL
    const { getClient } = await import("../src/db");
    const sql = getClient(env as never);
    await sql`
      INSERT INTO products (id, name, price, stock)
      VALUES (999, 'Test Widget', 1.00, 10)
      ON CONFLICT (id) DO UPDATE SET stock = 10
    `;
  });

  it("lists products", async () => {
    const { default: worker } = await import("../src/index");
    const req = new Request("http://localhost/products?limit=5");
    const resp = await worker.fetch(req, env as never);
    expect(resp.status).toBe(200);
    const data = await resp.json<unknown[]>();
    expect(Array.isArray(data)).toBe(true);
  });

  it("reserves stock and returns remaining", async () => {
    const { default: worker } = await import("../src/index");
    const req = new Request("http://localhost/products/999/reserve", {
      method: "POST",
      body: JSON.stringify({ qty: 3 }),
      headers: { "Content-Type": "application/json" },
    });
    const resp = await worker.fetch(req, env as never);
    const body = await resp.json<{ success: boolean; remaining: number }>();
    expect(body.success).toBe(true);
    expect(body.remaining).toBe(7);
  });

  it("returns 409 when stock is insufficient", async () => {
    const { default: worker } = await import("../src/index");
    const req = new Request("http://localhost/products/999/reserve", {
      method: "POST",
      body: JSON.stringify({ qty: 999 }),
      headers: { "Content-Type": "application/json" },
    });
    const resp = await worker.fetch(req, env as never);
    expect(resp.status).toBe(409);
  });
});
```

---

## Anti-patterns

- **Creating a new `postgres()` client per request** — Each instantiation opens new TCP connections to Hyperdrive's regional pooler, negating the pooling benefit and exhausting file descriptors quickly.
- **Enabling `prepare: true` with Hyperdrive** — Named prepared statements are scoped to a single backend connection; when Hyperdrive routes a subsequent request to a different connection, the statement is not found and the query fails.
- **Passing user input directly into tagged template strings with string interpolation** — `sql\`WHERE id = ${userId}\`` is safe (parameterized); manual string building inside the template is NOT.
- **Hardcoding the Hyperdrive connection string** — The string embeds your database password; always use the `env.HYPERDRIVE.connectionString` binding which Cloudflare manages and rotates.

---

## Gotchas

- `nodejs_compat` compatibility flag is required for the `postgres` (Postgres.js) npm package; without it, Node.js net/tls APIs are unavailable and the package throws at import.
- Hyperdrive does not support SSL mode `verify-full` from the Worker side; the TLS termination happens at Hyperdrive's regional edge. Your database still uses TLS between Hyperdrive and Postgres.
- The module-level `_sql` cache is per-isolate, not per-deployment; a new deploy creates new isolates with `_sql = null`, causing a brief burst of new connections.
- `wrangler hyperdrive create` validates the connection string by actually connecting; run it from a machine that has network access to your database.
- `max: 5` in the `postgres()` options caps connections per Worker isolate to Hyperdrive; Hyperdrive multiplexes these across its own pool to Postgres.

---

## Verification

```bash
# List Hyperdrive configs
wrangler hyperdrive list

# Inspect a specific config (shows caching and origin settings)
wrangler hyperdrive get <config-id>

# Tail Worker logs for connection errors
wrangler tail hyperdrive-worker --format pretty

# Check active Postgres connections (run on your DB server)
psql $DB_URL -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Deploy and smoke test
wrangler deploy
curl https://hyperdrive-worker.<subdomain>.workers.dev/products | jq length
```

---

## Related

- `workers-d1-foreign-keys-cascade-delete.md`
- `workers-ai-gateway-cache-budget.md`

---

## Sources

- Cloudflare Hyperdrive — https://developers.cloudflare.com/hyperdrive/
- Hyperdrive Get Started — https://developers.cloudflare.com/hyperdrive/get-started/
- Postgres.js (npm) — https://github.com/porsager/postgres
- Workers nodejs_compat — https://developers.cloudflare.com/workers/runtime-apis/nodejs/
