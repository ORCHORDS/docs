# TypeScript Template Literal Types for Workers Route Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers router uses string-based URL patterns like `"/api/v1/users/:id"`.
Handlers receive the matched params as `Record<string, string>`, giving you no compile-time
assurance that `params.id` exists. A typo (`params.userId`) returns `undefined` silently,
and only blows up at runtime.

You want TypeScript to:

1. Infer the parameter names from a route pattern string at the type level.
2. Type the `params` object as `{ id: string }` — not `Record<string, string>`.
3. Catch handler mismatches (wrong param names, missing params) at compile time.
4. Keep zero runtime overhead — no parsing or validation code ships to Workers.

---

## Context

TypeScript 4.1 introduced template literal types and recursive conditional types. Together
they make it possible to parse a route pattern string at the type level and extract
parameter names (`:param` segments) as a union of string literals. This union can then
become the keys of a `Record` type, producing a typed params object.

The approach works with any Workers routing layer (itty-router, Hono, or a hand-rolled
`URLPattern`-based router) because it operates entirely in the type system.

Runtime version requirement: none — these are purely compile-time constructs.
TypeScript version requirement: **≥ 4.1** for template literal types and infer inside
template literals.

---

## Step 1 — Extract Param Names from a Route Pattern String

```typescript
// src/types/route.ts

/**
 * ExtractParams<"/api/path/to/orders/:orderId">
 * => "userId" | "orderId"
 */
type ExtractParams<Path extends string> =
  Path extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ExtractParams<`/${Rest}`>
    : Path extends `${string}:${infer Param}`
    ? Param
    : never;

/**
 * RouteParams<"/api/path/to/orders/:orderId">
 * => { userId: string; orderId: string }
 */
type RouteParams<Path extends string> = {

};
```

Test the inference interactively in your IDE:

```typescript
type P = RouteParams<"/api/path/to/orders/:orderId">;
// Hover result: { userId: string; orderId: string }

type Q = RouteParams<"/healthz">;
// Hover result: {} (no params)

type R = ExtractParams<"/api/:version/items/:itemId">;
// Hover result: "version" | "itemId"
```

---

## Step 2 — Typed Handler Signature

```typescript
// src/types/route.ts (continued)

export type HandlerFn<Path extends string> = (
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  params: RouteParams<Path>
) => Response | Promise<Response>;

export type RouteDefinition<Path extends string> = {
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH" | "OPTIONS";
  path: Path;
  handler: HandlerFn<Path>;
};
```

---

## Step 3 — Router Implementation

```typescript
// src/router.ts
import type { RouteDefinition, RouteParams } from "./types/route";

// A minimal route registration helper that preserves the Path type
class Router {
  private routes: RouteDefinition<string>[] = [];

  add<Path extends string>(route: RouteDefinition<Path>): this {
    this.routes.push(route as RouteDefinition<string>);
    return this;
  }

  async handle(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    for (const route of this.routes) {
      if (route.method !== request.method) continue;

      const pattern = new URLPattern({ pathname: route.path });
      const match = pattern.exec({ pathname: url.pathname });

      if (match) {
        const params = match.pathname.groups as Record<string, string>;
        return route.handler(request, env, ctx, params as RouteParams<string>);
      }
    }

    return new Response("Not Found", { status: 404 });
  }
}

export const router = new Router();
```

---

## Step 4 — Registering Typed Routes

```typescript
// src/routes/users.ts
import { router } from "../router";
import type { RouteParams } from "../types/route";

router.add({
  method: "GET",
  path: "/api/v1/users/:userId",
  handler: async (request, env, ctx, params) => {
    // params is typed as { userId: string } — no cast needed
    const user = await env.DB.prepare("SELECT * FROM users WHERE id = ?")
      .bind(params.userId)  // autocomplete works here
      .first();

    if (!user) return new Response("Not Found", { status: 404 });
    return Response.json(user);
  },
});

router.add({
  method: "GET",
  path: "/api/v1/path/to/orders/:orderId",
  handler: async (request, env, ctx, params) => {
    // params: { userId: string; orderId: string }
    const order = await env.DB.prepare(
      "SELECT * FROM orders WHERE id = ? AND user_id = ?"
    )
      .bind(params.orderId, params.userId)  // both keys autocomplete
      .first();

    return Response.json(order ?? null);
  },
});

// TypeScript error: handler receives params.wrongKey which does not exist
router.add({
  method: "GET",
  path: "/api/v1/items/:itemId",
  handler: async (request, env, ctx, params) => {
    // @ts-expect-error: Property 'wrongKey' does not exist on type '{ itemId: string }'
    const _ = params.wrongKey;
    return new Response("ok");
  },
});
```

---

## Step 5 — Typed Route Map (Alternative Pattern)

For simpler use cases without a full router class, a plain record with `satisfies` gives
the same param inference:

```typescript
// src/route-map.ts
import type { HandlerFn } from "./types/route";

const routeMap = {
  "GET /api/v1/users/:userId": (async (req, env, ctx, params) => {
    // params: { userId: string }
    const row = await env.DB.prepare("SELECT * FROM users WHERE id = ?")
      .bind(params.userId)
      .first();
    return Response.json(row);
  }) satisfies HandlerFn<"/api/v1/users/:userId">,

  "POST /api/v1/users": (async (req, env, ctx, _params) => {
    // params: {} — no route params on this path
    const body = await req.json<{ email: string }>();
    await env.DB.prepare("INSERT INTO users (email) VALUES (?)")
      .bind(body.email)
      .run();
    return new Response(null, { status: 201 });
  }) satisfies HandlerFn<"/api/v1/users">,
} as const;
```

---

## Step 6 — Integration with Hono

If you use Hono, its router already infers params — but you can compose your own type utils
on top for stricter checks or custom validation layers:

```typescript
// src/hono-typed-routes.ts
import { Hono } from "hono";
import type { Env } from "../worker-configuration";

const app = new Hono<{ Bindings: Env }>();

// Hono infers params.userId from the path string natively
app.get("/api/v1/users/:userId", async (c) => {
  const { userId } = c.req.param(); // typed as { userId: string }
  const user = await c.env.DB.prepare("SELECT * FROM users WHERE id = ?")
    .bind(userId)
    .first();
  return c.json(user);
});

// Use RouteParams directly when building middleware that wraps Hono handlers
import type { RouteParams } from "./types/route";

function withTypedParams<Path extends string>(
  path: Path,
  fn: (params: RouteParams<Path>) => Response | Promise<Response>
): (c: Parameters<Parameters<typeof app.get>[1]>[0]) => Response | Promise<Response> {
  return (c) => fn(c.req.param() as RouteParams<Path>);
}

app.get(
  "/api/v1/path/to/settings",
  withTypedParams("/api/v1/path/to/settings", (params) => {
    // params: { userId: string }
    return Response.json({ userId: params.userId });
  })
);
```

---

## Advanced — Query String Parameter Types

Extend the pattern to cover typed query string params:

```typescript
// src/types/route.ts (extended)
type ExtractQuery<Search extends string> =
  Search extends `${string}?${infer QS}`
    ? QS extends `${infer Key}=${string}&${infer Rest}`
      ? Key | ExtractQuery<`?${Rest}`>
      : QS extends `${infer Key}=${string}`
      ? Key
      : never
    : never;

// Example: "/api/users/:userId?page=1&limit=20" => "page" | "limit"
type TestQuery = ExtractQuery<"/api/users/:userId?page=1&limit=20">;
// => "page" | "limit"
```

Note: this is an advanced technique. In practice, validating query strings at runtime with
a schema library (zod, valibot) is safer than relying purely on compile-time inference,
since URL inputs are untrusted at runtime regardless.

---

## Anti-patterns

**Using `Record<string, string>` as the params type everywhere:**
```typescript
// BAD — any key access compiles without error
handler: (req, env, ctx, params: Record<string, string>) => {
  const id = params.missingKey; // undefined at runtime, compiles fine
}

// GOOD — use RouteParams<Path>
handler: (req, env, ctx, params: RouteParams<"/users/:id">) => {
  const id = params.id; // string, guaranteed present
}
```

**Casting params with `as` at the call site:**
```typescript
// BAD — bypasses all type checking
const id = (params as any).userId;

// GOOD — the type should already be correct; if it's not, fix the route definition
const { userId } = params; // typed correctly through RouteParams
```

**Over-engineering the parser for optional segments (`/:id?`):**
Optional param segments (`?`) require additional conditional branches in `ExtractParams`.
For optional params, explicitly override the `RouteParams` type rather than extending the
parser — optional URL segments are better handled at runtime with a guard.

---

## Gotchas

- TypeScript's template literal type inference has depth limits. Routes with more than ~8-10
  nested segments can trigger "type instantiation is excessively deep" errors. Split deeply
  nested routes into sub-routers.
- `URLPattern` groups use named capture group syntax (`/:param`) and return `undefined` for
  groups that didn't participate in the match. When casting to `RouteParams<Path>`, ensure
  all optional segments are explicitly `| undefined` in your type.
- Param names that conflict with JavaScript reserved words (`class`, `delete`, `void`) are
  legal in URL patterns but will generate confusing TypeScript errors. Avoid them in path
  design.
- The `ExtractParams` utility only handles `:named` params. Wildcard segments (`*`,
  `(.*)`) are not extracted as named params. Treat them separately if needed.
- `URLPattern` is available in the Workers runtime natively. Do not polyfill it with the
  `urlpattern-polyfill` npm package — it is unnecessary in Workers and adds bundle size.

---

## Verification

```bash
# Confirm types are inferred correctly (zero type errors expected)
pnpm tsc --noEmit

# Confirm a handler with a wrong param key produces a type error
# (intentionally fail to verify the guard works)
echo "Verify type error on wrong param key in handlers — expected TS error."
```

In your IDE, hover over `params` inside any handler registered with `router.add()` and
confirm the inferred type shows only the declared param names.

---

## Related

- `typescript-workers-env-interface-module-augmentation.md`
- `typescript-satisfies-operator-workers-type-narrowing.md`
- `hono-rpc-client-type-generation-workers.md`
- `hono-openapi-spec-generation.md`
- `typescript-strict-mode-guide.md`

---

## Sources

- TypeScript 4.1 template literal types: https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-1.html#template-literal-types
- TypeScript `infer` in template literals: https://www.typescriptlang.org/docs/handbook/2/conditional-types.html#inferring-within-conditional-types
- `URLPattern` MDN reference: https://developer.mozilla.org/en-US/docs/Web/API/URLPattern
- Cloudflare Workers `URLPattern` support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/#url
- Hono routing docs: https://hono.dev/docs/api/routing
