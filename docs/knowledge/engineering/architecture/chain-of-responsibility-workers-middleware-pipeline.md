# Chain of Responsibility: Workers Middleware Pipeline

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Every Cloudflare Worker route needs cross-cutting concerns applied in a consistent order — authentication, rate limiting, input validation, request logging, response compression — but writing nested `if` blocks or chaining `try/catch` wrappers in each handler leads to spaghetti that is hard to reorder or test individually. You need a linear pipeline where each step either passes the request forward or short-circuits with a response.

## Context

The Chain of Responsibility pattern passes a request along a chain of handlers; each handler decides whether to process the request itself, pass it to the next handler, or terminate the chain early. In a Cloudflare Worker this maps to a middleware array: each middleware is an async function that receives the request, a mutable context object, and a `next()` function. Calling `next()` delegates to the following middleware; not calling it short-circuits the chain. The router assembles a chain per route, composes it once at cold-start, and dispatches each request through the composed chain.

## Middleware Types and Composition

```typescript
// middleware/types.ts
export interface RequestContext {
  request: Request;
  env: Env;
  params: Record<string, string>;
  userId?: string;
  requestId: string;
  startedAt: number;

}

export type Next = () => Promise<Response>;
export type Middleware = (ctx: RequestContext, next: Next) => Promise<Response>;

export function compose(...middlewares: Middleware[]): Middleware {
  return async (ctx: RequestContext, finalHandler: Next): Promise<Response> => {
    let index = -1;

    const dispatch = async (i: number): Promise<Response> => {
      if (i <= index) throw new Error("next() called multiple times");
      index = i;
      const fn = i < middlewares.length ? middlewares[i] : finalHandler;
      return fn(ctx, () => dispatch(i + 1));
    };

    return dispatch(0);
  };
}
```

## Core Middleware Implementations

```typescript
// middleware/requestId.ts
import { Middleware } from "./types";

export const requestIdMiddleware: Middleware = async (ctx, next) => {
  ctx.requestId = crypto.randomUUID();
  const response = await next();
  return new Response(response.body, {
    status: response.status,
    headers: { ...Object.fromEntries(response.headers), "x-request-id": ctx.requestId },
  });
};

// middleware/logger.ts
import { Middleware } from "./types";

export const loggerMiddleware: Middleware = async (ctx, next) => {
  const response = await next();
  const duration = Date.now() - ctx.startedAt;
  console.log(JSON.stringify({
    requestId: ctx.requestId,
    method: ctx.request.method,
    url: ctx.request.url,
    status: response.status,
    durationMs: duration,
  }));
  return response;
};

// middleware/auth.ts
import { Middleware } from "./types";

export const authMiddleware: Middleware = async (ctx, next) => {
  const authHeader = ctx.request.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const token = authHeader.slice(7);
  const row = await ctx.env.DB.prepare(
    "SELECT user_id FROM api_tokens WHERE token = ? AND expires_at > ?"
  ).bind(token, new Date().toISOString()).first<{ user_id: string }>();

  if (!row) {
    return Response.json({ error: "Invalid or expired token" }, { status: 401 });
  }

  ctx.userId = row.user_id;
  return next();
};

// middleware/rateLimiter.ts
import { Middleware } from "./types";

export const rateLimiterMiddleware: Middleware = async (ctx, next) => {
  if (!ctx.userId) return next(); // rate-limit by authenticated user only

  const key = `rl:${ctx.userId}`;
  const current = Number((await ctx.env.KV.get(key)) ?? "0");

  if (current >= 100) {
    return Response.json({ error: "Rate limit exceeded" }, {
      status: 429,
      headers: { "Retry-After": "60" },
    });
  }

  // Increment counter; TTL resets the window
  await ctx.env.KV.put(key, String(current + 1), { expirationTtl: 60 });
  return next();
};

// middleware/validateBody.ts
import { Middleware } from "./types";

export function validateBody<T>(
  schema: (raw: unknown) => T | null
): Middleware {
  return async (ctx, next) => {
    if (ctx.request.method === "GET" || ctx.request.method === "HEAD") {
      return next();
    }
    let raw: unknown;
    try {
      raw = await ctx.request.json();
    } catch {
      return Response.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const parsed = schema(raw);
    if (parsed === null) {
      return Response.json({ error: "Body validation failed" }, { status: 422 });
    }
    ctx.body = parsed;
    return next();
  };
}
```

## Router Wiring

```typescript
// router.ts
import { compose, Middleware, RequestContext } from "./middleware/types";
import { requestIdMiddleware } from "./middleware/requestId";
import { loggerMiddleware } from "./middleware/logger";
import { authMiddleware } from "./middleware/auth";
import { rateLimiterMiddleware } from "./middleware/rateLimiter";
import { handleCreateOrder } from "./handlers/orders";

const globalChain = compose(requestIdMiddleware, loggerMiddleware);
const protectedChain = compose(authMiddleware, rateLimiterMiddleware);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ctx: RequestContext = {
      request,
      env,
      params: {},
      requestId: "",
      startedAt: Date.now(),
    };

    return globalChain(ctx, () =>
      protectedChain(ctx, async () => {
        const url = new URL(request.url);
        if (url.pathname === "/orders" && request.method === "POST") {
          return handleCreateOrder(ctx);
        }
        return new Response("Not Found", { status: 404 });
      })
    );
  },
};
```

## Anti-patterns

- Calling `next()` after mutating a cloned `Response` object — cloned responses stream the body, so mutating headers after the fact may be a no-op; build the final response once.
- Adding global authentication middleware to a chain that includes public health-check or webhook-verification routes; apply `authMiddleware` only on protected sub-chains.
- Sharing mutable state on `ctx` across concurrent requests — each request gets its own `ctx` object, but if you accidentally store shared module-level state it will bleed between requests.

## Gotchas

- Cloudflare Workers have a per-request CPU limit; each `await next()` hop adds a microtask boundary but minimal wall-clock overhead. However, a deep chain with many KV/D1 calls compounds latency — batch reads where possible.
- The `compose` function relies on `index` tracking to detect double-`next()` calls; if middleware spawns sub-tasks via `ctx.waitUntil` that also call `next()`, the index check will throw.

## Verification

```bash
# Run the chain locally with Miniflare
wrangler dev --local

# Happy path
curl -X POST http://localhost:8787/orders \
  -H "Authorization: Bearer valid-token" \
  -H "Content-Type: application/json" \
  -d '{"productId":"p1","qty":2}'

# Expect 401 without token
curl -X POST http://localhost:8787/orders -H "Content-Type: application/json" -d '{}'

# Expect 429 after 100 requests in a minute
for i in $(seq 1 101); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X GET http://localhost:8787/orders \
    -H "Authorization: Bearer valid-token"
done
```

## Related

- `architecture/rate-limiting-architecture-workers.md`
- `architecture/api-gateway-pattern-cloudflare-workers.md`
- `architecture/decorator-pattern-workers-middleware-composition.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch-event/
- https://refactoring.guru/design-patterns/chain-of-responsibility
- https://developers.cloudflare.com/workers/observability/logging/workers-logs/
