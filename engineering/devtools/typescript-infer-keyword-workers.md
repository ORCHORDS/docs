# TypeScript infer Keyword in Workers Type Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You have generic Workers utilities — route handlers, middleware chains, binding accessors — and need
to extract inner types automatically so callers get precise types without repeating themselves or
casting with `as`.

## Context
Cloudflare Workers codebases accumulate complex generic patterns: typed `Env` interfaces, Hono RPC
response shapes, D1 query result rows, and middleware context extensions. The `infer` keyword lets
conditional types "capture" a sub-type from within a compound type at the call site, eliminating
manual extraction and `ReturnType<typeof …>` boilerplate. It pairs naturally with `@cloudflare/workers-types`
generics and Hono's type system.

## Extracting Handler Return Types

```ts
// types/utils.ts

/** Pull the resolved value out of any async function type */
type Awaited<T> = T extends Promise<infer R> ? R : T;

/** Extract the return value of a Workers fetch handler */
type HandlerReturn<H extends (...args: any[]) => any> =
  Awaited<ReturnType<H>>;

// Usage
import type { ExportedHandlerFetchHandler } from "@cloudflare/workers-types";

type MyEnv = { DB: D1Database; KV: KVNamespace };
type FetchHandler = ExportedHandlerFetchHandler<MyEnv>;
type FetchResult = HandlerReturn<FetchHandler>;
// → Response
```

## Unwrapping D1 Query Row Types

```ts
// types/d1.ts

/** Extract the row type from a D1 prepared statement result */
type D1Row<S> =
  S extends D1PreparedStatement
    ? D1Result<infer R>["results"][number]
    : never;

// Concrete helper: infer the row from a typed query function
type QueryRow<F extends (...args: any[]) => Promise<D1Result<any>>> =
  Awaited<ReturnType<F>> extends D1Result<infer Row> ? Row : never;

// Usage
async function listUsers(db: D1Database) {
  return db.prepare("SELECT id, name FROM users").all<{ id: number; name: string }>();
}

type UserRow = QueryRow<typeof listUsers>;
// → { id: number; name: string }

async function getUser(db: D1Database, id: number): Promise<UserRow | null> {
  const result = await db
    .prepare("SELECT id, name FROM users WHERE id = ?")
    .bind(id)
    .first<UserRow>();
  return result ?? null;
}
```

## Extracting Hono RPC Response Shapes

```ts
// types/hono.ts
import type { Hono } from "hono";
import type { ClientRequestOptions } from "hono/client";

/** Drill into a Hono app's typed routes to get the response body for a path */
type HonoRouteBody<
  App extends Hono<any, any, any>,
  Path extends string,
  Method extends "get" | "post" | "put" | "delete" = "get",
> = App extends Hono<any, infer Routes, any>
  ? Routes extends Record<Path, Record<Method, { output: infer Body }>>
    ? Body
    : never
  : never;

// Example app
import { Hono } from "hono";

const app = new Hono().get("/items", (c) =>
  c.json({ items: [{ id: 1, name: "Widget" }] })
);

type ItemsBody = HonoRouteBody<typeof app, "/items">;
// → { items: { id: number; name: string }[] }
```

## Narrowing KV Metadata Types

```ts
// types/kv.ts

/** Extract KV metadata type from a typed get call */
type KVMeta<F extends (...args: any[]) => Promise<KVNamespaceGetWithMetadataResult<any, any>>> =
  Awaited<ReturnType<F>> extends KVNamespaceGetWithMetadataResult<any, infer M>
    ? M
    : never;

interface SessionMeta {
  createdAt: number;
  userId: string;
}

async function getSession(kv: KVNamespace, key: string) {
  return kv.getWithMetadata<string, SessionMeta>(key, "text");
}

type Meta = KVMeta<typeof getSession>;
// → SessionMeta

// Narrowing helper: assert metadata is present
function assertMeta<T>(result: KVNamespaceGetWithMetadataResult<string, T>): T {
  if (result.metadata === null) {
    throw new Error("KV entry missing metadata");
  }
  return result.metadata;
}
```

## Building a Middleware Context Extractor

```ts
// types/middleware.ts
import type { MiddlewareHandler, Context } from "hono";

/** Given a middleware that adds variables to context, extract those variables */
type MiddlewareVars<M> =
  M extends MiddlewareHandler<infer Env, string, { Variables: infer V }>
    ? V
    : never;

// Example middleware
const authMiddleware: MiddlewareHandler<
  { Bindings: { KV: KVNamespace } },
  string,
  { Variables: { userId: string; role: "admin" | "user" } }
> = async (c, next) => {
  const token = c.req.header("Authorization") ?? "";
  // ... verify token ...
  c.set("userId", "u_123");
  c.set("role", "admin");
  await next();
};

type AuthVars = MiddlewareVars<typeof authMiddleware>;
// → { userId: string; role: "admin" | "user" }

// Use the extracted type in a downstream handler
function makeHandler(c: Context<{ Variables: AuthVars }>) {
  const userId = c.get("userId"); // string ✓
  return c.json({ userId });
}
```

## Anti-patterns
- Do not nest more than 3–4 levels of `infer` in a single conditional — the compiler error messages
  become unreadable and inference can silently widen to `unknown`.
- Do not use `infer` to replace explicit interfaces when the shape is stable; explicit types are
  easier to read and refactor.
- Do not combine `infer` with `any` in the captured position — `infer R` where `R` is constrained
  to `any` defeats the purpose and returns `unknown` in strict mode.
- Do not use `infer` solely to avoid writing a type; use it when the type is genuinely derived from
  another type that will evolve independently.

## Gotchas
- `infer` only works inside the `true` branch of a conditional type; placing it in the `false`
  branch is a type error.
- Distributive conditionals apply when the checked type is a naked type parameter; wrap in a tuple
  `[T] extends [U]` to suppress distribution when testing union members.
- TypeScript 5.4+ narrows `infer` captures in template literal types, which can cause previously
  passing inference to fail when upgrading.
- `@cloudflare/workers-types` generics use `unknown` as defaults; you must supply the concrete type
  argument before `infer` can extract a useful sub-type.

## Verification

```bash
# Type-check without emitting JS
pnpm tsc --noEmit

# Inspect an inferred type interactively in VSCode
# Hover over the type alias — the tooltip shows the resolved type

# Use tsd to assert inferred types in CI
pnpm add -D tsd
# In *.test-d.ts:
# import { expectType } from "tsd";
# expectType<UserRow>({} as QueryRow<typeof listUsers>);
pnpm tsd
```

## Related
- `typescript-satisfies-operator-workers-type-narrowing.md` — using `satisfies` to narrow
- `typescript-branded-types-workers-safe-strings.md` — branded primitives
- `typescript-template-literal-types-workers-route-pattern.md` — template literal inference
- `hono-rpc-client-type-generation-workers.md` — Hono RPC type flow end-to-end

## Sources
- https://www.typescriptlang.org/docs/handbook/2/conditional-types.html
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
- https://hono.dev/docs/guides/rpc
- https://github.com/cloudflare/workers-types
