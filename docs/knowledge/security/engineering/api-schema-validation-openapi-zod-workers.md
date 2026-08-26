# API Schema Validation with OpenAPI and Zod in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Requests reaching business logic contain unexpected fields, wrong types, or malformed payloads because the only validation is ad-hoc `if` checks. Automated fuzz testing or malformed client SDKs trigger 500 errors or—worse—silent data corruption in D1. You want a single, authoritative contract expressed as an OpenAPI 3.1 document and enforced at the Worker edge before any handler runs.

## Context

Cloudflare Workers run on the V8 isolate runtime; there is no Node.js `http` module and no Express middleware chain. Schema validation must be self-contained (no filesystem reads, no heavy npm packages that import Node builtins). Zod 3.x compiles to a single ESM bundle and works without polyfills. Combining Zod with a thin OpenAPI-description layer lets you publish a machine-readable spec and enforce it from the same source of truth.

## 1. Defining the Schema with Zod

```typescript
// src/schemas/create-order.ts
import { z } from "zod";

export const CreateOrderBody = z.object({
  customerId: z.string().uuid(),
  items: z
    .array(
      z.object({
        sku: z.string().min(1).max(64),
        quantity: z.number().int().positive().max(1000),
      })
    )
    .min(1)
    .max(100),
  couponCode: z.string().regex(/^[A-Z0-9-]{4,20}$/).optional(),
});

export type CreateOrderBody = z.infer<typeof CreateOrderBody>;
```

## 2. Validation Middleware in Workers

```typescript
// src/middleware/validate.ts
import { z, ZodError } from "zod";

export async function validateBody<T>(
  request: Request,
  schema: z.ZodType<T>
): Promise<{ data: T } | Response> {
  let raw: unknown;
  try {
    const contentType = request.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      return new Response(
        JSON.stringify({ error: "Content-Type must be application/json" }),
        { status: 415, headers: { "Content-Type": "application/json" } }
      );
    }
    raw = await request.json();
  } catch {
    return new Response(
      JSON.stringify({ error: "Malformed JSON body" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const result = schema.safeParse(raw);
  if (!result.success) {
    return new Response(
      JSON.stringify({ error: "Validation failed", details: result.error.issues }),
      { status: 422, headers: { "Content-Type": "application/json" } }
    );
  }
  return { data: result.data };
}
```

## 3. Query Parameter Validation

```typescript
// src/middleware/validate-query.ts
import { z } from "zod";

export const PaginationQuery = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  sort: z.enum(["asc", "desc"]).default("desc"),
});

export function validateQuery<T>(
  url: URL,
  schema: z.ZodType<T>
): { data: T } | Response {
  const raw = Object.fromEntries(url.searchParams.entries());
  const result = schema.safeParse(raw);
  if (!result.success) {
    return new Response(
      JSON.stringify({ error: "Invalid query parameters", details: result.error.issues }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
  return { data: result.data };
}
```

## 4. Wiring into the Worker Fetch Handler

```typescript
// src/index.ts
import { CreateOrderBody } from "./schemas/create-order";
import { validateBody } from "./middleware/validate";
import { PaginationQuery, validateQuery } from "./middleware/validate-query";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/orders") {
      const validated = await validateBody(request, CreateOrderBody);
      if (validated instanceof Response) return validated;
      return handleCreateOrder(validated.data, env);
    }

    if (request.method === "GET" && url.pathname === "/orders") {
      const validated = validateQuery(url, PaginationQuery);
      if (validated instanceof Response) return validated;
      return handleListOrders(validated.data, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## 5. Generating OpenAPI 3.1 from Zod

```typescript
// src/openapi.ts  (build-time script, not deployed to Workers)
import { generateSchema } from "@anatine/zod-openapi";
import { CreateOrderBody } from "./schemas/create-order";

const openApiComponent = generateSchema(CreateOrderBody);
// Embed in your openapi.json / openapi.yaml and serve it from a Worker route
// GET /openapi.json → return static JSON (bundled at build time)
```

```typescript
// Serve the spec from the Worker itself
const SPEC = JSON.stringify(require("./openapi.json"));

if (url.pathname === "/openapi.json") {
  return new Response(SPEC, {
    headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=3600" },
  });
}
```

## 6. Path Parameter Validation

```typescript
// src/middleware/validate-params.ts
import { z } from "zod";

export const OrderParams = z.object({
  orderId: z.string().uuid(),
});

export function extractPathParam(
  pathname: string,
  pattern: RegExp
): Record<string, string> | null {
  const match = pathname.match(pattern);
  if (!match?.groups) return null;
  return match.groups as Record<string, string>;
}

// Usage: /orders/:orderId
const raw = extractPathParam(url.pathname, /^\/orders\/(?<orderId>[^/]+)$/);
if (!raw) return new Response("Not Found", { status: 404 });
const paramsResult = OrderParams.safeParse(raw);
if (!paramsResult.success) return new Response("Bad Request", { status: 400 });
```

## Anti-patterns

- **Validating only on the frontend.** Client-side validation is UX, not security. Every request hitting the Worker must be treated as untrusted.
- **Using `z.any()` for nested blobs.** This silently passes malformed payloads; always fully type nested objects.
- **Swallowing `ZodError` details in production logs.** Log the structured `issues` array server-side even if you return a generic message to the client.
- **Parsing the body twice.** Calling `request.json()` a second time in the handler after validation returns an empty stream; pass the parsed data through.
- **Skipping content-type checks.** A `multipart/form-data` body silently fails `JSON.parse`; check the header first.

## Gotchas

- Zod's `.default()` transform only runs via `safeParse`/`parse`; raw TypeScript types will not reflect defaults—use `z.infer` to get the output type including defaults.
- `z.coerce.number()` accepts `"1.5"` for an integer field unless you chain `.int()`; always add `.int()` for quantity/page parameters.
- Workers bundle size: Zod 3.x adds ~12 KB gzipped. Use `wrangler deploy --minify` and confirm with `wrangler size`.
- `request.json()` can throw for bodies exceeding 100 MB (Workers limit); add a `Content-Length` pre-check or catch the throw.
- OpenAPI 3.1 uses JSON Schema draft 2020-12; `@anatine/zod-openapi` targets 3.0 by default—pass `{ target: "openApi3" }` and verify the output.

## Verification

```bash
# Valid payload – expect 200/201
curl -X POST https://api.example.com/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"550e8400-e29b-41d4-a716-446655440000","items":[{"sku":"WIDGET-A","quantity":3}]}'

# Missing required field – expect 422
curl -X POST https://api.example.com/orders \
  -H "Content-Type: application/json" \
  -d '{"items":[{"sku":"X","quantity":1}]}'

# Wrong content-type – expect 415
curl -X POST https://api.example.com/orders \
  -H "Content-Type: text/plain" -d 'hello'

# Fuzz with invalid UUID – expect 422
curl -X POST https://api.example.com/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"not-a-uuid","items":[{"sku":"A","quantity":1}]}'
```

## Related

- `sql-injection-prevention-d1-workers.md`
- `graphql-query-depth-limiting.md`
- `http-parameter-pollution-workers.md`
- `mass-assignment-prevention.md`
- `owasp-api-top-10-2023.md`

## Sources

- Zod documentation — https://zod.dev
- Cloudflare Workers runtime limits — https://developers.cloudflare.com/workers/platform/limits/
- OpenAPI 3.1 specification — https://spec.openapis.org/oas/v3.1.0
- OWASP API Security Top 10 2023 — https://owasp.org/API-Security/
- `@anatine/zod-openapi` — https://github.com/anatine/zod-plugins
