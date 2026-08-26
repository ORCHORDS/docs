# Template Method Pattern: Abstract Handler Base Class for Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Every route handler in your Workers project repeats the same scaffolding: parse and validate the request body, check authentication, open a D1 connection, run the core logic, format the response, handle errors uniformly, and emit a structured log. The ceremony grows with each new endpoint, and when the error format or auth check changes, the fix must be applied to every handler individually.

Classic signs:
- `try/catch` blocks with identical `Response.json({ error: ... }, { status: 500 })` bodies duplicated across 20+ files
- Auth middleware applied inconsistently because each handler copies it differently
- A logging change requires a grep-and-replace across the entire handler directory
- Integration tests test scaffolding logic more than business logic

---

## Context

The Template Method pattern defines the skeleton of an algorithm in a base class, deferring specific steps to subclasses. Subclasses override hooks without changing the overall structure. In the Workers context, the base class owns the `fetch` entry-point and calls abstract or overrideable methods for auth, validation, execution, and response formatting. Each concrete handler only implements what is unique to it.

```
AbstractHandler.fetch(request, env, ctx)
  ├─ authenticate(request, env)   [default: no-op; override for auth]
  ├─ validate(request)            [abstract: parse + schema-check body]
  ├─ execute(ctx)                 [abstract: core business logic]
  └─ formatResponse(result)       [default: JSON 200; override as needed]
```

Any step that throws is caught by the base class, which maps known error types to HTTP status codes and formats a consistent error envelope.

---

## Base Handler Class

```typescript
// src/handlers/base-handler.ts
import type { Env } from "../types";

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export interface HandlerContext<TInput = unknown> {
  request: Request;
  env: Env;
  ctx: ExecutionContext;
  input: TInput;
  principal?: { userId: string; role: string };
}

export abstract class AbstractHandler<TInput = unknown, TOutput = unknown> {
  // ── Overrideable hooks ──────────────────────────────────────────────────

  /** Override to enforce authentication. Throw HttpError(401) on failure. */
  protected async authenticate(
    request: Request,
    env: Env
  ): Promise<{ userId: string; role: string } | undefined> {
    return undefined;
  }

  /** Parse and validate the incoming request. Return typed input or throw HttpError(400). */
  protected abstract validate(request: Request, env: Env): Promise<TInput>;

  /** Run the core business logic. Must return the result or throw. */
  protected abstract execute(context: HandlerContext<TInput>): Promise<TOutput>;

  /** Convert the result to a Response. Default: 200 JSON. */
  protected formatResponse(result: TOutput): Response {
    return Response.json(result);
  }

  // ── Template method ─────────────────────────────────────────────────────

  async handle(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let status = 200;

    try {
      const principal = await this.authenticate(request, env);
      const input = await this.validate(request, env);

      const handlerCtx: HandlerContext<TInput> = {
        request,
        env,
        ctx,
        input,
        principal,
      };

      const result = await this.execute(handlerCtx);
      const response = this.formatResponse(result);
      status = response.status;
      this.log(request, status, Date.now() - start);
      return response;
    } catch (err) {
      if (err instanceof HttpError) {
        status = err.status;
        this.log(request, status, Date.now() - start, err.message);
        return Response.json(
          { error: err.message, code: err.code ?? "ERROR" },
          { status: err.status }
        );
      }
      status = 500;
      const message = err instanceof Error ? err.message : "Internal server error";
      console.error("[handler]", request.method, new URL(request.url).pathname, message);
      this.log(request, status, Date.now() - start, message);
      return Response.json({ error: "Internal server error", code: "INTERNAL" }, { status: 500 });
    }
  }

  private log(request: Request, status: number, durationMs: number, errorMessage?: string) {
    const url = new URL(request.url);
    console.log(
      JSON.stringify({
        method: request.method,
        path: url.pathname,
        status,
        durationMs,
        ...(errorMessage ? { error: errorMessage } : {}),
      })
    );
  }
}
```

---

## Concrete Handler: Create Order

```typescript
// src/handlers/create-order-handler.ts
import { AbstractHandler, HttpError, type HandlerContext } from "./base-handler";
import type { Env } from "../types";

interface CreateOrderInput {
  items: Array<{ productId: string; quantity: number }>;
  currency: "USD" | "EUR";
}

interface CreateOrderOutput {
  orderId: string;
  status: "pending";
  createdAt: string;
}

export class CreateOrderHandler extends AbstractHandler<CreateOrderInput, CreateOrderOutput> {
  protected async authenticate(request: Request, env: Env) {
    const token = request.headers.get("Authorization")?.replace("Bearer ", "");
    if (!token) throw new HttpError(401, "Missing token", "UNAUTHORIZED");

    // Validate JWT / KV session — simplified here
    const session = await env.KV.get(`session:${token}`, "json") as { userId: string; role: string } | null;
    if (!session) throw new HttpError(401, "Invalid token", "UNAUTHORIZED");
    return session;
  }

  protected async validate(request: Request): Promise<CreateOrderInput> {
    if (request.method !== "POST") throw new HttpError(405, "Method not allowed", "METHOD_NOT_ALLOWED");

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      throw new HttpError(400, "Invalid JSON", "BAD_REQUEST");
    }

    const b = body as Record<string, unknown>;
    if (!Array.isArray(b.items) || b.items.length === 0) {
      throw new HttpError(400, "items must be a non-empty array", "VALIDATION_ERROR");
    }
    if (b.currency !== "USD" && b.currency !== "EUR") {
      throw new HttpError(400, "currency must be USD or EUR", "VALIDATION_ERROR");
    }

    return body as CreateOrderInput;
  }

  protected async execute(
    context: HandlerContext<CreateOrderInput>
  ): Promise<CreateOrderOutput> {
    const { input, env, principal } = context;
    const orderId = crypto.randomUUID();
    const createdAt = new Date().toISOString();

    await env.DB.prepare(
      `INSERT INTO orders (id, user_id, currency, status, created_at) VALUES (?, ?, ?, 'pending', ?)`
    )
      .bind(orderId, principal!.userId, input.currency, createdAt)
      .run();

    return { orderId, status: "pending", createdAt };
  }

  protected formatResponse(result: CreateOrderOutput): Response {
    return Response.json(result, { status: 201 });
  }
}
```

---

## Concrete Handler: Health Check (No Auth, No Body)

```typescript
// src/handlers/health-handler.ts
import { AbstractHandler, type HandlerContext } from "./base-handler";
import type { Env } from "../types";

interface HealthOutput { status: "ok"; timestamp: string }

export class HealthHandler extends AbstractHandler<null, HealthOutput> {
  protected async validate(): Promise<null> { return null; }

  protected async execute(_ctx: HandlerContext<null>): Promise<HealthOutput> {
    return { status: "ok", timestamp: new Date().toISOString() };
  }
}
```

---

## Router: Dispatching to Handlers

```typescript
// src/worker.ts
import type { Env } from "./types";
import { CreateOrderHandler } from "./handlers/create-order-handler";
import { HealthHandler } from "./handlers/health-handler";

const createOrder = new CreateOrderHandler();
const health = new HealthHandler();

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/health") return health.handle(request, env, ctx);
    if (url.pathname === "/orders" && request.method === "POST") return createOrder.handle(request, env, ctx);

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Testing a Handler in Isolation

```typescript
// src/handlers/__tests__/create-order-handler.test.ts
import { CreateOrderHandler } from "../create-order-handler";
import { describe, it, expect, vi } from "vitest";

const handler = new CreateOrderHandler();

function makeEnv(overrides: Partial<Env> = {}): Env {
  return {
    KV: {
      get: vi.fn().mockResolvedValue({ userId: "u1", role: "user" }),
    } as unknown as KVNamespace,
    DB: {
      prepare: vi.fn().mockReturnValue({
        bind: vi.fn().mockReturnValue({ run: vi.fn().mockResolvedValue({ success: true }) }),
      }),
    } as unknown as D1Database,
    ...overrides,
  } as Env;
}

const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

it("returns 201 with orderId on valid request", async () => {
  const req = new Request("https://example.com/orders", {
    method: "POST",
    headers: { Authorization: "Bearer tok" },
    body: JSON.stringify({ items: [{ productId: "p1", quantity: 1 }], currency: "USD" }),
  });
  const res = await handler.handle(req, makeEnv(), ctx);
  expect(res.status).toBe(201);
  const body = await res.json<{ orderId: string }>();
  expect(body.orderId).toMatch(/^[0-9a-f-]{36}$/);
});

it("returns 401 when token is absent", async () => {
  const req = new Request("https://example.com/orders", { method: "POST", body: JSON.stringify({}) });
  const env = makeEnv({ KV: { get: vi.fn().mockResolvedValue(null) } as unknown as KVNamespace });
  const res = await handler.handle(req, env, ctx);
  expect(res.status).toBe(401);
});

it("returns 400 when items is empty", async () => {
  const req = new Request("https://example.com/orders", {
    method: "POST",
    headers: { Authorization: "Bearer tok" },
    body: JSON.stringify({ items: [], currency: "USD" }),
  });
  const res = await handler.handle(req, makeEnv(), ctx);
  expect(res.status).toBe(400);
});
```

---

## Anti-patterns

- **Putting routing logic inside the base class**: The base class should be ignorant of URL paths. Route dispatch belongs in the top-level `fetch` export.
- **Sharing one handler instance with mutable state**: Handler instances are safe only if they carry no per-request state. Never store `request` or `env` on `this` between hook calls; pass them through `HandlerContext`.
- **Swallowing typed errors with a bare `catch (e) {}`**: Always re-throw unexpected errors after logging; the base class `catch` is the designated safety net, not each hook.
- **Duplicating the `handle` orchestration in subclasses**: Override only the named hook methods. If you find yourself overriding `handle`, the hierarchy needs a rethink.
- **Deep inheritance hierarchies**: Limit to one level of concrete subclasses. Shared behaviour among a subset of handlers is better expressed as composable helpers injected via the constructor.

---

## Gotchas

- Workers instantiate module-scope classes once per isolate activation. Handler instances are reused across requests; ensure no per-request data leaks onto `this`.
- The `AbstractHandler` `handle` method logs to `console.log`; in Cloudflare Workers, `console.log` is routed to Workers Logs / Logpush. Replace with a structured logger that accepts the `env` if you need trace IDs.
- `request.json()` consumes the body stream. If `validate` reads the body, `execute` cannot read it again. Pass parsed data through `HandlerContext.input`.
- TypeScript's abstract class cannot be instantiated but can be exported and imported normally. Use `implements` when you want to satisfy a non-class interface alongside the hierarchy.
- `formatResponse` returns a `Response` whose `status` is read back for logging. Avoid constructing the response twice; return the same object from `formatResponse`.

---

## Verification

1. Send a valid `POST /orders` request and confirm response is 201 with `orderId` and `createdAt`.
2. Send without `Authorization` header; confirm 401 `{"error":"Missing token","code":"UNAUTHORIZED"}`.
3. Send with invalid JSON body; confirm 400 `{"error":"Invalid JSON","code":"BAD_REQUEST"}`.
4. Add a `throw new Error("unexpected")` inside `execute` and confirm the response is 500 `{"error":"Internal server error"}` and the original message is in `console.error`.
5. Verify `GET /health` returns 200 `{"status":"ok"}` without requiring an `Authorization` header.

---

## Related

- `decorator-pattern-workers-middleware.md` — composing middleware instead of inheriting it
- `chain-of-responsibility-workers-middleware-pipeline.md` — alternative middleware topology
- `error-codes-and-responses.md` — standardising error envelopes across handlers
- `structured-logging.md` — enriching the base-class log line with trace IDs

---

## Sources

- Gamma et al. — Design Patterns: Elements of Reusable Object-Oriented Software (1994): Template Method
- Cloudflare Workers TypeScript types: https://github.com/cloudflare/workers-types
- Vitest Workers integration: https://developers.cloudflare.com/workers/testing/vitest-integration/
