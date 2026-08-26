# API Contract Testing with Zod Schemas and Vitest

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your backend emits JSON responses consumed by a frontend or third-party client. When a field is renamed, a type changes from `string` to `number`, or a nullable field becomes required, downstream consumers break silently at runtime. You need:

- Compile-time type safety that propagates from schema to TypeScript types.
- Runtime contract assertions that catch shape mismatches in test and production.
- Tests that fail loudly when the response schema drifts from the declared contract.
- Portable schemas usable for validation in the API handler, in tests, and in the client.

---

## Context

Zod is a TypeScript-first schema library that produces both a TypeScript type (`z.infer<typeof schema>`) and a runtime validator (`.parse()` / `.safeParse()`). Combined with Vitest's test runner, you can:

1. Define the canonical response schema once in a shared module.
2. Import that schema into both the API handler (validate outgoing responses) and the test suite (assert the shape of actual HTTP responses).
3. Use `safeParse` with structured error reporting to produce readable test failure messages.

This differs from Pact-style consumer-driven contracts in that it does not require a broker, provider verification step, or multi-service coordination — it is ideal for internal APIs where both producer and consumer are in the same monorepo.

Stack: **Cloudflare Workers (Hono), Zod 3, Vitest 2, `@cloudflare/vitest-pool-workers`**.

---

## 1. Shared Schema Module

```typescript
// src/schemas/api.ts
import { z } from "zod";

// ---- Primitives ----
export const PaginationSchema = z.object({
  page: z.number().int().positive(),
  perPage: z.number().int().min(1).max(100),
  total: z.number().int().nonnegative(),
  totalPages: z.number().int().nonnegative(),
});

// ---- Domain objects ----
export const ProductSchema = z.object({
  id: z.string().uuid(),
  slug: z.string().min(1).max(100),
  name: z.string().min(1).max(200),
  priceInCents: z.number().int().positive(),
  currency: z.enum(["usd", "eur", "gbp"]),
  stock: z.number().int().nonnegative(),
  tags: z.array(z.string()),
  createdAt: z.string().datetime(), // ISO-8601
  updatedAt: z.string().datetime(),
});

export const ProductListResponseSchema = z.object({
  data: z.array(ProductSchema),
  pagination: PaginationSchema,
});

export const ProductCreateRequestSchema = z.object({
  slug: z.string().min(1).max(100),
  name: z.string().min(1).max(200),
  priceInCents: z.number().int().positive(),
  currency: z.enum(["usd", "eur", "gbp"]),
  stock: z.number().int().nonnegative().default(0),
  tags: z.array(z.string()).default([]),
});

export const ErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    field: z.string().optional(),
  }),
});

// ---- Derived TypeScript types ----
export type Product = z.infer<typeof ProductSchema>;
export type ProductListResponse = z.infer<typeof ProductListResponseSchema>;
export type ProductCreateRequest = z.infer<typeof ProductCreateRequestSchema>;
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;
```

---

## 2. API Handler Using Zod for Output Validation

```typescript
// src/routes/products.ts
import { Hono } from "hono";
import type { Env } from "../types";
import {
  ProductListResponseSchema,
  ProductCreateRequestSchema,
  ProductSchema,
} from "../schemas/api";

const products = new Hono<{ Bindings: Env }>();

products.get("/", async (c) => {
  const page = Number(c.req.query("page") ?? 1);
  const perPage = Number(c.req.query("perPage") ?? 20);

  const { results, meta } = await c.env.DB.prepare(
    `SELECT * FROM products ORDER BY created_at DESC LIMIT ? OFFSET ?`
  )
    .bind(perPage, (page - 1) * perPage)
    .all();

  const countRow = await c.env.DB.prepare(
    `SELECT COUNT(*) as count FROM products`
  ).first<{ count: number }>();

  const total = countRow?.count ?? 0;

  const payload = {
    data: results,
    pagination: {
      page,
      perPage,
      total,
      totalPages: Math.ceil(total / perPage),
    },
  };

  // Validate outgoing response — catches bugs before they reach clients
  const parsed = ProductListResponseSchema.safeParse(payload);
  if (!parsed.success) {
    console.error("Response schema violation:", parsed.error.format());
    return c.json({ error: { code: "INTERNAL", message: "Schema violation" } }, 500);
  }

  return c.json(parsed.data);
});

products.post("/", async (c) => {
  const body = await c.req.json();
  const parsed = ProductCreateRequestSchema.safeParse(body);

  if (!parsed.success) {
    return c.json(
      { error: { code: "VALIDATION", message: "Invalid input", field: parsed.error.errors[0]?.path.join(".") } },
      400
    );
  }

  // Insert and return created product...
  return c.json({ data: { id: "new-uuid", ...parsed.data, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() } }, 201);
});

export default products;
```

---

## 3. Test Helper — Schema Assertion Utility

```typescript
// tests/helpers/assert-schema.ts
import { type ZodSchema, type ZodError } from "zod";
import { expect } from "vitest";

/**
 * Asserts that `data` matches `schema`, producing a readable Vitest failure
 * that includes all Zod path/message pairs if validation fails.
 */
export function assertMatchesSchema<T>(
  schema: ZodSchema<T>,
  data: unknown
): asserts data is T {
  const result = schema.safeParse(data);
  if (!result.success) {
    const formatted = formatZodError(result.error);
    // Throw with a structured message Vitest will display
    expect(result.success, `Schema validation failed:\n${formatted}`).toBe(true);
  }
}

function formatZodError(error: ZodError): string {
  return error.errors
    .map((e) => `  [${e.path.join(".") || "root"}] ${e.message}`)
    .join("\n");
}

/**
 * Returns a typed `{ success, data, error }` result — use when you want to
 * assert both the failure and its specific error fields.
 */
export function parseSchema<T>(schema: ZodSchema<T>, data: unknown) {
  return schema.safeParse(data);
}
```

---

## 4. Contract Tests for `GET /products`

```typescript
// tests/contracts/products-list.contract.test.ts
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeAll } from "vitest";
import { ProductListResponseSchema } from "../../src/schemas/api";
import { assertMatchesSchema, parseSchema } from "../helpers/assert-schema";

beforeAll(async () => {
  // Seed test data into Miniflare's D1
  await env.DB.prepare(`
    INSERT INTO products (id, slug, name, price_in_cents, currency, stock, tags, created_at, updated_at)
    VALUES
      ('uuid-1', 'widget-a', 'Widget A', 999, 'usd', 10, '[]', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
      ('uuid-2', 'widget-b', 'Widget B', 1999, 'eur', 5, '["sale"]', '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z')
  `).run();
});

describe("GET /products — response contract", () => {
  it("returns a response matching ProductListResponseSchema", async () => {
    const response = await SELF.fetch("http://worker/products");
    expect(response.status).toBe(200);

    const body = await response.json();
    // This assertion gives a full Zod error on mismatch — not just "expected true to be true"
    assertMatchesSchema(ProductListResponseSchema, body);
  });

  it("returns paginated data with correct pagination fields", async () => {
    const response = await SELF.fetch("http://worker/products?page=1&perPage=1");
    const body = await response.json();

    assertMatchesSchema(ProductListResponseSchema, body);

    // Type is inferred — no `as any` casts needed
    expect(body.pagination.page).toBe(1);
    expect(body.pagination.perPage).toBe(1);
    expect(body.pagination.total).toBe(2);
    expect(body.pagination.totalPages).toBe(2);
    expect(body.data).toHaveLength(1);
  });

  it("each product has all required fields with correct types", async () => {
    const response = await SELF.fetch("http://worker/products");
    const body = await response.json();

    assertMatchesSchema(ProductListResponseSchema, body);

    for (const product of body.data) {
      // priceInCents must be integer, not float
      expect(Number.isInteger(product.priceInCents)).toBe(true);
      // currency must be one of the enum values
      expect(["usd", "eur", "gbp"]).toContain(product.currency);
      // tags must be an array
      expect(Array.isArray(product.tags)).toBe(true);
      // dates must be ISO-8601
      expect(() => new Date(product.createdAt)).not.toThrow();
    }
  });
});
```

---

## 5. Contract Tests for `POST /products`

```typescript
// tests/contracts/products-create.contract.test.ts
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import {
  ProductSchema,
  ErrorResponseSchema,
} from "../../src/schemas/api";
import { assertMatchesSchema } from "../helpers/assert-schema";

const validPayload = {
  slug: "new-product",
  name: "New Product",
  priceInCents: 4999,
  currency: "usd",
  stock: 20,
  tags: ["new", "featured"],
};

describe("POST /products — contract tests", () => {
  it("returns a created product matching ProductSchema", async () => {
    const response = await SELF.fetch("http://worker/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(validPayload),
    });

    expect(response.status).toBe(201);
    const body = await response.json();

    // Unwrap the data envelope
    assertMatchesSchema(ProductSchema, body.data);
    expect(body.data.slug).toBe(validPayload.slug);
    expect(body.data.priceInCents).toBe(validPayload.priceInCents);
  });

  it("returns ErrorResponseSchema shape on invalid input", async () => {
    const response = await SELF.fetch("http://worker/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: "x", name: "" }), // missing required fields
    });

    expect(response.status).toBe(400);
    const body = await response.json();
    assertMatchesSchema(ErrorResponseSchema, body);
    expect(body.error.code).toBe("VALIDATION");
  });

  it("rejects negative priceInCents", async () => {
    const response = await SELF.fetch("http://worker/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...validPayload, priceInCents: -1 }),
    });

    expect(response.status).toBe(400);
    const body = await response.json();
    assertMatchesSchema(ErrorResponseSchema, body);
  });

  it("applies default values for optional fields", async () => {
    const minimalPayload = {
      slug: "minimal",
      name: "Minimal Product",
      priceInCents: 100,
      currency: "gbp",
    };

    const response = await SELF.fetch("http://worker/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(minimalPayload),
    });

    expect(response.status).toBe(201);
    const body = await response.json();
    // Defaults should be applied
    expect(body.data.stock).toBe(0);
    expect(body.data.tags).toEqual([]);
  });
});
```

---

## 6. Schema Regression Test — Detect Drift

```typescript
// tests/contracts/schema-drift.contract.test.ts
/**
 * These tests lock the schema shape. If a field is removed or renamed in
 * the source schema, these tests fail immediately — before any integration test
 * runs. Think of them as golden-master tests for the Zod schema itself.
 */
import { describe, it, expect } from "vitest";
import { ProductSchema, PaginationSchema } from "../../src/schemas/api";

describe("Schema shape — regression lock", () => {
  it("ProductSchema has the expected keys", () => {
    const shape = ProductSchema.shape;
    const keys = Object.keys(shape).sort();

    expect(keys).toEqual(
      ["createdAt", "currency", "id", "name", "priceInCents", "slug", "stock", "tags", "updatedAt"]
    );
  });

  it("PaginationSchema has the expected keys", () => {
    const keys = Object.keys(PaginationSchema.shape).sort();
    expect(keys).toEqual(["page", "perPage", "total", "totalPages"]);
  });

  it("currency enum includes exactly usd, eur, gbp", () => {
    const currencyField = ProductSchema.shape.currency;
    expect(currencyField.options).toEqual(["usd", "eur", "gbp"]);
  });

  it("priceInCents rejects zero", () => {
    const result = ProductSchema.shape.priceInCents.safeParse(0);
    expect(result.success).toBe(false);
  });

  it("priceInCents rejects floats", () => {
    const result = ProductSchema.shape.priceInCents.safeParse(9.99);
    expect(result.success).toBe(false);
  });
});
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| `response as Product` TypeScript cast without runtime check | Type cast bypasses actual validation; runtime shape may differ | Use `assertMatchesSchema(ProductSchema, response)` — gives you both types and runtime safety |
| Asserting only `response.status === 200` | Doesn't detect schema drift in the response body | Always parse the body with `assertMatchesSchema` after status checks |
| Duplicating schema in tests (`z.object({ id: z.string(), ... })`) | Schema drifts independently in tests and production code | Import the single canonical schema from `src/schemas/api.ts` |
| Using `.parse()` instead of `.safeParse()` | `.parse()` throws a `ZodError` with unformatted output; hard to read in CI | Use `.safeParse()` and format errors with a helper before calling `expect` |
| Testing schema validators in isolation without real HTTP | Does not catch serialization bugs (e.g., D1 returning `"true"` string vs `true` boolean) | Always test against a real or Miniflare-simulated HTTP response, not a manually constructed object |

---

## Gotchas

- **D1 returns strings for booleans** — SQLite stores booleans as `0`/`1`; if your Zod schema expects `z.boolean()` but D1 returns integers, `.parse()` will fail. Use `z.coerce.boolean()` or transform in the route handler.
- **`z.string().datetime()` is strict** — it rejects dates without the `Z` suffix or with milliseconds in some modes. Use `z.string().datetime({ offset: true })` to accept `+00:00` offsets.
- **`z.infer<T>` is a compile-time construct** — it does not produce a validator; you still need `.parse()` / `.safeParse()` at runtime.
- **`z.array(z.string())` and JSON round-trip** — D1 may return `tags` as a JSON string `"[\"sale\"]"` rather than an array. Parse it with `JSON.parse` before Zod validation, or use a `z.preprocess` transformer.
- **Schema versioning** — if consumers depend on your schema and you need to change it, introduce `ProductSchemaV2` alongside `ProductSchemaV1` rather than mutating the existing one, to avoid breaking tests that lock the V1 shape.
- **`assertMatchesSchema` does not narrow** — after calling `assertMatchesSchema(schema, data)`, TypeScript infers `data` is typed, but in a `forEach` callback you may need to re-cast. Use `const typed = ProductListResponseSchema.parse(data)` to get a properly typed value.

---

## Verification

```bash
# Run contract tests
npx vitest run tests/contracts/

# Run with verbose output for schema drift tests
npx vitest run tests/contracts/schema-drift.contract.test.ts --reporter=verbose

# Type-check schema usage across the project
npx tsc --noEmit

# Expected output:
# ✓ returns a response matching ProductListResponseSchema
# ✓ returns paginated data with correct pagination fields
# ✓ each product has all required fields with correct types
# ✓ returns a created product matching ProductSchema
# ✓ returns ErrorResponseSchema shape on invalid input
# ✓ ProductSchema has the expected keys
# ✓ currency enum includes exactly usd, eur, gbp
```

---

## Related

- [`api-contract-testing-schema-validation.md`](api-contract-testing-schema-validation.md) — broader schema validation approaches
- [`api-contract-testing-pact-workers.md`](api-contract-testing-pact-workers.md) — Pact consumer-driven contracts for Workers
- [`type-level-testing-typescript.md`](type-level-testing-typescript.md) — compile-time type assertion testing
- [`miniflare-d1-integration-testing.md`](miniflare-d1-integration-testing.md) — D1 integration with Miniflare
- [`vitest-cloudflare-pool-workers.md`](vitest-cloudflare-pool-workers.md) — Vitest Workers pool configuration

---

## Sources

- [Zod Documentation](https://zod.dev)
- [Zod — `.safeParse()` and error formatting](https://zod.dev/?id=safeparse)
- [Cloudflare Workers — D1 Binding](https://developers.cloudflare.com/d1/platform/client-api/)
- [Vitest — Test Utilities](https://vitest.dev/api/)
- [Hono — Input Validation with Zod](https://hono.dev/guides/validation)
