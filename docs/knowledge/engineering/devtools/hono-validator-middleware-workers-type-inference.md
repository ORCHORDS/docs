# Hono Validator Middleware Workers Type Inference

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a Cloudflare Workers API with Hono and want request validation (body, query params, headers, path params) that propagates type-safe parsed values into your route handlers — without manual type casting.

## Context

Hono's `@hono/zod-validator` attaches a `ValidatedData` type to the `Context` object via TypeScript generics. When the middleware runs, it parses the incoming data and either short-circuits with a 400 response or passes the typed, validated value downstream. The `c.req.valid(target)` call inside the handler is fully typed to the inferred Zod schema output.

---

## Installing the Validator Package

```bash
pnpm add hono zod @hono/zod-validator
```

---

## JSON Body Validation with Inferred Types

```typescript
// src/routes/users.ts
import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";

const CreateUserSchema = z.object({
  name: z.string().min(1).max(100),
  email: z.string().email(),
  role: z.enum(["admin", "member", "viewer"]).default("member"),
});

export const usersRouter = new Hono<{ Bindings: CloudflareBindings }>()
  .post(
    "/",
    zValidator("json", CreateUserSchema),
    async (c) => {
      const data = c.req.valid("json");
      //    ^? { name: string; email: string; role: "admin" | "member" | "viewer" }

      const user = await c.env.DB.prepare(
        "INSERT INTO users (name, email, role) VALUES (?, ?, ?) RETURNING *"
      ).bind(data.name, data.email, data.role).first<{ id: number }>();

      return c.json({ id: user!.id }, 201);
    }
  );
```

---

## Query Parameter Validation

```typescript
const ListQuerySchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  search: z.string().optional(),
});

app.get(
  "/items",
  zValidator("query", ListQuerySchema),
  async (c) => {
    const { page, limit, search } = c.req.valid("query");
    const offset = (page - 1) * limit;
    const rows = await c.env.DB.prepare(
      search ? "SELECT * FROM items WHERE name LIKE ? LIMIT ? OFFSET ?" : "SELECT * FROM items LIMIT ? OFFSET ?"
    ).bind(...(search ? [`%${search}%`, limit, offset] : [limit, offset])).all();
    return c.json({ items: rows.results, page, limit });
  }
);
```

---

## Header and Path Param Validation

```typescript
const AuthHeaderSchema = z.object({
  "x-api-key": z.string().min(32),
});

const ItemParamSchema = z.object({
  id: z.coerce.number().int().positive(),
});

app.delete(
  "/items/:id",
  zValidator("header", AuthHeaderSchema),
  zValidator("param", ItemParamSchema),
  async (c) => {
    const { "x-api-key": apiKey } = c.req.valid("header");
    const { id } = c.req.valid("param"); // ^? number

    if (!(await verifyApiKey(apiKey, c.env))) return c.json({ error: "Unauthorized" }, 401);
    await c.env.DB.prepare("DELETE FROM items WHERE id = ?").bind(id).run();
    return c.body(null, 204);
  }
);
```

---

## Custom Error Response Hook

```typescript
function typedValidator<T extends z.ZodTypeAny>(
  target: "json" | "query" | "param" | "header" | "form",
  schema: T
) {
  return zValidator(target, schema, (result, c) => {
    if (!result.success) {
      const issues = result.error.issues.map((i) => ({
        field: i.path.join("."),
        message: i.message,
      }));
      return c.json({ error: "Validation failed", issues }, 400);
    }
  });
}
```

---

## Anti-patterns

- Using `c.req.json()` directly after attaching `zValidator("json", ...)` — this re-parses, missing the pre-validated typed value.
- Wrapping Zod schemas in `z.any()` fallbacks — defeats type inference.
- Using `zValidator` with `z.string()` for `"json"` target — the JSON target expects an object.
- Forgetting `z.coerce.number()` for path params — path params arrive as strings.

---

## Gotchas

- `c.req.valid()` is only typed when called with the exact same target string used in `zValidator`.
- Multiple validators on the same route stack correctly, but each `c.req.valid(target)` call is independent.
- In Workers, `c.req.json()` can throw if the body is not valid JSON before Zod runs.

---

## Verification

```bash
pnpm tsc --noEmit
pnpm vitest run src/routes/users.test.ts

curl -s -X POST https://localhost:8787/users \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"not-an-email"}' | jq .
```

---

## Related

- `hono-rpc-client-type-generation-workers.md`
- `hono-openapi-spec-generation.md`
- `typescript-cloudflare-workers-strict.md`

---

## Sources

- `@hono/zod-validator` docs: https://hono.dev/docs/guides/validation
- Zod coerce docs: https://zod.dev/?id=coercion-for-primitives
