# Hyperdrive Connection Pool Testing in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Cloudflare Workers using Hyperdrive to connect to PostgreSQL face a unique testing problem: the actual Hyperdrive proxy service only exists in the production edge network and cannot be replicated locally. Integration tests must verify that queries issued through Hyperdrive's connection string execute correctly, that connection acquisition errors are handled gracefully, and that the Worker's SQL shapes match what callers expect — all without a live Hyperdrive binding in CI.

## Context

Hyperdrive provides a connection pooling proxy that exposes a PostgreSQL-compatible `connectionString` to the Worker. From the Worker's perspective, `env.HYPERDRIVE.connectionString` is a `postgres://` URL; the Worker connects with `postgres` or `pg` and issues queries normally. In Wrangler dev (`--local`) and Miniflare-based Vitest tests, the `HYPERDRIVE` binding accepts a `localConnectionString` in `wrangler.toml` that points to a locally accessible Postgres instance — typically a Docker container. The test strategy separates three concerns: query correctness (testable locally via Docker), error handling (mockable via a bad connection string), and pool size limits (verifiable only in staging with a real Hyperdrive binding and load test).

## Local Postgres Fixture Setup

```toml
# wrangler.toml
name = "products-api"
main = "src/index.ts"
compatibility_date = "2026-07-01"

[[hyperdrive]]
binding              = "HYPERDRIVE"
id                   = "local-dev-placeholder"
localConnectionString = "postgresql://test:test@localhost:5432/testdb"
```

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER:     test
      POSTGRES_PASSWORD: test
      POSTGRES_DB:       testdb
    ports:
      - "5432:5432"
    healthcheck:
      test:     ["CMD-SHELL", "pg_isready -U test -d testdb"]
      interval: 5s
      retries:  10
```

## Integration Tests — Query Correctness

```typescript
// test/hyperdrive.spec.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import postgres from "postgres";
import worker from "../src/index";

let sql: ReturnType<typeof postgres>;

beforeAll(async () => {
  sql = postgres(env.HYPERDRIVE.connectionString);
  await sql`
    CREATE TABLE IF NOT EXISTS products (
      id   SERIAL PRIMARY KEY,
      name TEXT   NOT NULL,
      sku  TEXT   UNIQUE NOT NULL
    )
  `;
  await sql`
    INSERT INTO products (name, sku)
    VALUES ('Widget', 'WIDG-001'), ('Gadget', 'GADG-002')
    ON CONFLICT DO NOTHING
  `;
});

afterAll(async () => {
  await sql`DROP TABLE IF EXISTS products`;
  await sql.end();
});

describe("GET /api/products", () => {
  it("returns all seeded products as JSON", async () => {
    const req = new Request("https://example.com/api/products");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");
    const body = await res.json<{ products: { sku: string }[] }>();
    expect(body.products.map((p) => p.sku)).toEqual(
      expect.arrayContaining(["WIDG-001", "GADG-002"])
    );
  });

  it("returns 404 for an unknown SKU", async () => {
    const req = new Request("https://example.com/api/products/UNKNOWN-999");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(404);
    const body = await res.json<{ error: string }>();
    expect(body.error).toMatch(/not found/i);
  });

  it("returns products in ascending SKU order", async () => {
    const req = new Request("https://example.com/api/products?sort=sku");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    const body = await res.json<{ products: { sku: string }[] }>();
    const skus = body.products.map((p) => p.sku);
    expect(skus).toEqual([...skus].sort());
  });
});
```

## Error Handling Tests with a Faulty Binding

```typescript
// test/hyperdrive-errors.spec.ts
import { describe, it, expect, vi } from "vitest";
import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "../src/index";

describe("Hyperdrive connection failure handling", () => {
  it("returns 503 when Postgres is unreachable", async () => {
    const faultyEnv = {
      HYPERDRIVE: {
        connectionString: "postgresql://bad:bad@127.0.0.1:9999/noexist",
      },
    } as unknown as Env;

    const req = new Request("https://example.com/api/products");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, faultyEnv, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(503);
    const body = await res.json<{ error: string }>();
    expect(body.error).toMatch(/database unavailable/i);
  });

  it("logs the error and returns 500 on an unexpected query exception", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    vi.mock("postgres", () => ({
      default: () =>
        new Proxy(() => {}, {
          apply() { throw new Error("syntax error at or near ..."); },
        }),
    }));

    const req = new Request("https://example.com/api/products");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, {} as Env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(500);
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringMatching(/syntax error/)
    );
    consoleSpy.mockRestore();
    vi.restoreAllMocks();
  });
});
```

## Worker Source Reference

```typescript
// src/index.ts (relevant excerpt)
import postgres from "postgres";

export interface Env {
  HYPERDRIVE: { connectionString: string };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sql = postgres(env.HYPERDRIVE.connectionString, { max: 5 });
    const url = new URL(request.url);

    try {
      if (url.pathname === "/api/products") {
        const rows = await sql<{ id: number; name: string; sku: string }[]>`
          SELECT id, name, sku FROM products ORDER BY sku ASC
        `;
        return Response.json({ products: rows });
      }

      const sku = url.pathname.split("/").pop();
      const [row] = await sql`SELECT * FROM products WHERE sku = ${sku}`;
      if (!row) return Response.json({ error: "not found" }, { status: 404 });
      return Response.json(row);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const status = msg.includes("connect") ? 503 : 500;
      console.error(msg);
      return Response.json(
        { error: status === 503 ? "database unavailable" : "internal error" },
        { status }
      );
    } finally {
      await sql.end({ timeout: 2 });
    }
  },
};
```

## Anti-patterns

- Connecting to the real Hyperdrive binding in local tests — the Hyperdrive proxy does not exist in `wrangler dev --local` mode and throws `binding not supported in local mode`
- Using `process.env.DATABASE_URL` directly in tests instead of `env.HYPERDRIVE.connectionString` — tests a different code path than production and misses binding resolution errors
- Calling `sql.end()` in `afterEach` instead of `afterAll` — creates connection race conditions when Vitest runs spec files in parallel worker threads

## Gotchas

- `localConnectionString` in `wrangler.toml` must include the full `postgresql://` scheme; omitting the scheme causes `postgres` to throw `invalid connection string` before any Worker code runs
- The `postgres` npm package caches connections at the module level by default; `sql.end()` in `afterAll` ensures the pool drains before Vitest exits, preventing `Cannot read properties of undefined` on subsequent runs
- Wrangler's local Hyperdrive simulation does not enforce pool limits or connection latency overhead; actual pool exhaustion and queuing behaviour must be validated in staging with a real Hyperdrive binding using a load test

## Verification

```bash
docker compose up -d postgres
docker compose ps   # wait until healthy

npx vitest run test/hyperdrive.spec.ts test/hyperdrive-errors.spec.ts --reporter=verbose
# Expected: query-correctness tests pass, 503 error path returns correct shape

# Confirm seed data is present after the test run
docker exec -it $(docker compose ps -q postgres) \
  psql -U test -d testdb -c "SELECT sku FROM products ORDER BY sku;"
```

## Related

- `testing/miniflare-d1-integration-testing.md`
- `testing/d1-testing-local.md`
- `testing/workers-service-bindings-vitest-testing.md`

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/workers/testing/vitest-integration/local-bindings/
- https://github.com/porsager/postgres
