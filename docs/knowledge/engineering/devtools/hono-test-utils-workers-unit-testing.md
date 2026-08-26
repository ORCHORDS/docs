# Hono Test Utils for Cloudflare Workers Unit Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Hono ships a first-party `@hono/testing` package (and the built-in `app.request()` helper) that lets you unit-test route handlers, middleware chains, and response shapes entirely in-process without spinning up a real HTTP server or Miniflare instance. This makes individual route tests extremely fast and suitable for TDD workflows where feedback time matters.

## Context

The `app.request()` method accepts a URL string or `Request` object and returns a `Promise<Response>`, mirroring the Fetch API contract that Workers expose. Combined with Vitest running in Node.js mode (not the Miniflare pool), the test suite runs in milliseconds. Miniflare is reserved for integration tests that need real D1, KV, or R2 bindings. Keeping the two layers separate avoids the cold-start overhead of spawning a workerd process for every test file.

## App Under Test

```typescript
// src/app.ts
import { Hono } from "hono";
import { bearerAuth } from "hono/bearer-auth";
import { HTTPException } from "hono/http-exception";

export type Env = {
  DB: D1Database;
  API_TOKEN: string;
};

export const app = new Hono<{ Bindings: Env }>();

app.use("/api/*", async (c, next) => {
  const auth = bearerAuth({ token: c.env.API_TOKEN });
  return auth(c, next);
});

app.get("/api/users/:id", async (c) => {
  const { id } = c.req.param();
  const user = await c.env.DB.prepare(
    "SELECT id, name, email FROM users WHERE id = ?"
  )
    .bind(id)
    .first<{ id: string; name: string; email: string }>();

  if (!user) {
    throw new HTTPException(404, { message: "User not found" });
  }

  return c.json(user);
});

app.post("/api/users", async (c) => {
  const body = await c.req.json<{ name: string; email: string }>();
  const id = crypto.randomUUID();

  await c.env.DB.prepare(
    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)"
  )
    .bind(id, body.name, body.email)
    .run();

  return c.json({ id }, 201);
});
```

## Unit Tests with app.request() and Mocked Bindings

```typescript
// src/app.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { app } from "./app";

// Minimal D1 mock — returns only what each test needs
function makeDB(
  overrides: Partial<D1Database> = {}
): D1Database {
  const statement: D1PreparedStatement = {
    bind: vi.fn().mockReturnThis(),
    first: vi.fn().mockResolvedValue(null),
    run: vi.fn().mockResolvedValue({ success: true, meta: {} }),
    all: vi.fn().mockResolvedValue({ results: [], success: true, meta: {} }),
    raw: vi.fn().mockResolvedValue([]),
  };

  return {
    prepare: vi.fn(() => statement),
    batch: vi.fn(),
    exec: vi.fn(),
    dump: vi.fn(),
    ...overrides,
  } as unknown as D1Database;
}

const ENV = {
  API_TOKEN: "test-token-abc",
  DB: makeDB(),
};

// Helper: fire a request through the full Hono middleware stack
async function req(
  method: string,
  path: string,
  options: RequestInit & { env?: typeof ENV } = {}
) {
  const { env = ENV, ...init } = options;
  return app.request(path, { method, ...init }, env);
}

describe("GET /api/users/:id", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 401 when no token is provided", async () => {
    const res = await req("GET", "/api/users/123");
    expect(res.status).toBe(401);
  });

  it("returns 404 when user does not exist", async () => {
    const res = await req("GET", "/api/users/missing", {
      headers: { Authorization: "Bearer test-token-abc" },
    });
    expect(res.status).toBe(404);
    const body = await res.json<{ message: string }>();
    expect(body.message).toBe("User not found");
  });

  it("returns the user when found", async () => {
    const mockUser = { id: "123", name: "Alice", email: "alice@example.com" };
    const db = makeDB();
    (db.prepare("").bind().first as ReturnType<typeof vi.fn>).mockResolvedValue(mockUser);

    const env = { ...ENV, DB: db };
    const res = await req("GET", "/api/users/123", {
      headers: { Authorization: "Bearer test-token-abc" },
      env,
    });

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(mockUser);
  });
});

describe("POST /api/users", () => {
  it("creates a user and returns 201 with id", async () => {
    const res = await req("POST", "/api/users", {
      headers: {
        Authorization: "Bearer test-token-abc",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: "Bob", email: "bob@example.com" }),
    });

    expect(res.status).toBe(201);
    const body = await res.json<{ id: string }>();
    expect(typeof body.id).toBe("string");
  });
});
```

## vitest.config.ts for Split Unit / Integration Pools

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Unit tests run in the Node.js pool — fast, no workerd cold-start
    include: ["src/**/*.test.ts"],
    exclude: ["src/**/*.integration.test.ts"],
    environment: "node",
    globals: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.test.ts"],
    },
  },
});
```

## Anti-patterns

- Mocking `fetch` globally with `vi.stubGlobal` for subroute tests — use `app.request()` directly so middleware (auth, logging, error handling) is exercised in the same call.
- Sharing a single `makeDB` mock instance across `describe` blocks without resetting `vi.fn()` call counts between tests; use `beforeEach(() => vi.clearAllMocks())` consistently.
- Writing tests that assert on raw `Response` bodies using string matching — parse JSON with `res.json()` and do structural assertions so tests are not brittle to formatting changes.

## Gotchas

- `app.request()` in Hono v4+ accepts a third argument for the environment bindings (`Env`). In earlier versions the signature differs — check your Hono version and adjust accordingly.
- The `bearerAuth` middleware reads `c.env.API_TOKEN` at request time, so the token must be in the env object passed as the third argument to `app.request()`, not hardcoded in the Hono app constructor.
- `crypto.randomUUID()` is available in Node.js 19+ and in workerd, but older Node.js versions used in CI may lack it — pin Node.js >= 20 in `.node-version` or use `node:crypto` explicitly.

## Verification

```bash
# Run only unit tests (fast, no Miniflare)
pnpm vitest run --project unit

# Run with coverage
pnpm vitest run --coverage

# Watch mode during development
pnpm vitest --reporter=verbose src/app.test.ts
```

## Related

- `devtools/vitest-workers-miniflare-testing-setup.md`
- `devtools/miniflare-custom-plugins-bindings.md`
- `devtools/hono-openapi-spec-generation.md`

## Sources

- https://hono.dev/docs/guides/testing
- https://vitest.dev/config/#environment
- https://developers.cloudflare.com/workers/testing/unit-tests/
