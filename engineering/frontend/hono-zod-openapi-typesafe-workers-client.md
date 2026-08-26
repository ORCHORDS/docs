# Hono + Zod OpenAPI for Type-Safe API Contracts Between Workers and the Frontend

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Frontend `fetch()` calls and Worker route handlers drift apart: the Worker adds a
required field, the React component still sends the old shape, and the error surfaces
only in production with a 400 response and an opaque JSON error body. The `@hono/zod-openapi`
package solves this by making the Zod schema the single source of truth: it validates
incoming requests on the Worker, generates an OpenAPI 3.1 spec, and — combined with
`hono/client` — provides a fully typed `hc<>()` fetch client for the frontend that
fails at `tsc` time when the call site diverges from the schema.

---

## Context

`@hono/zod-openapi` is an official Hono middleware that wraps routes with Zod
validation for request body, query params, path params, and response shapes.
`hono/client` (`hc<AppType>()`) reads the Hono `AppType` (the type of the Hono
application object) and returns a typed client whose method signatures mirror
every route's input and output schemas.

Both packages are pure TypeScript with no code-generation step: the type-level
client is derived at compile time by TypeScript's type inference, not by running
a codegen script. The Worker and frontend share types through a monorepo package
or a path alias — no runtime code from the Worker is imported by the browser.

---

## Worker: Defining Typed Routes with Zod OpenAPI

```typescript
// packages/api/src/routes/products.ts
import { createRoute, OpenAPIHono, z } from '@hono/zod-openapi';

// Shared schema — exported for frontend import (type-only is fine)
export const ProductSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1).max(120),
  price: z.number().positive(),
  currency: z.enum(['USD', 'EUR', 'GBP']),
  stock: z.number().int().min(0),
}).openapi('Product');

export const ProductListSchema = z.object({
  products: z.array(ProductSchema),
  total: z.number().int(),
  cursor: z.string().optional(),
}).openapi('ProductList');

const SearchQuerySchema = z.object({
  q: z.string().min(1).max(200).openapi({ example: 'blue sneakers' }),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
});

// Route definition — request and response shapes declared once
export const searchRoute = createRoute({
  method: 'get',
  path: '/products/search',
  request: {
    query: SearchQuerySchema,
  },
  responses: {
    200: {
      content: { 'application/json': { schema: ProductListSchema } },
      description: 'Search results',
    },
    400: {
      content: {
        'application/json': {
          schema: z.object({ error: z.string() }).openapi('ValidationError'),
        },
      },
      description: 'Validation error',
    },
  },
});
```

---

## Worker: Registering Routes and Generating the OpenAPI Spec

```typescript
// packages/api/src/index.ts
import { OpenAPIHono } from '@hono/zod-openapi';
import { cors } from 'hono/cors';
import { searchRoute, ProductListSchema } from './routes/products';

type Env = { DB: D1Database };

const app = new OpenAPIHono<{ Bindings: Env }>();

app.use('/api/*', cors());

app.openapi(searchRoute, async (c) => {
  // c.req.valid('query') is typed as { q: string; limit: number; cursor?: string }
  const { q, limit, cursor } = c.req.valid('query');

  const rows = await c.env.DB.prepare(
    'SELECT * FROM products WHERE name LIKE ?1 LIMIT ?2'
  )
    .bind(`%${q}%`, limit)
    .all();

  // Return shape is validated against ProductListSchema at runtime
  return c.json({ products: rows.results, total: rows.results.length });
});

// OpenAPI spec endpoint — useful for Swagger UI and client codegen
app.doc('/openapi.json', {
  openapi: '3.1.0',
  info: { title: 'Storefront API', version: '1.0.0' },
});

// Export the AppType — consumed by hc<> on the frontend
export type AppType = typeof app;
export default app;
```

---

## Frontend: The Typed `hc<>()` Client

```typescript
// apps/storefront/src/lib/api-client.ts
import { hc } from 'hono/client';
// Import ONLY the type — no Worker runtime code reaches the browser bundle
import type { AppType } from 'api/src/index';

// Point hc<> at the deployed Worker URL
// In Pages, the Worker is available at the same origin via a /api/* route
export const api = hc<AppType>('/');
```

Usage in a React component:

```typescript
// apps/storefront/src/features/search/SearchResults.tsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api-client';

export function SearchResults({ query }: { query: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['products', 'search', query],
    queryFn: async () => {
      // TypeScript infers the correct overload:
      // api.api.products.search.$get({ query: { q: string; limit?: number } })
      const res = await api.api.products.search.$get({
        query: { q: query, limit: 20 },
      });

      if (!res.ok) {
        const { error } = await res.json();   // typed as { error: string }
        throw new Error(error);
      }

      return res.json();   // typed as { products: Product[]; total: number; cursor?: string }
    },
    enabled: query.length > 0,
  });

  if (isLoading) return <p>Loading…</p>;

  return (
    <ul>
      {data?.products.map((p) => (
        <li key={p.id}>{p.name} — {p.currency} {p.price}</li>
      ))}
    </ul>
  );
}
```

If the Worker removes `price` from `ProductSchema`, the `p.price` reference above
causes a TypeScript compile error before any code ships.

---

## Monorepo Package Layout

```
packages/
  api/
    src/
      index.ts          ← OpenAPIHono app + AppType export
      routes/
        products.ts     ← route definitions + Zod schemas
    package.json        ← name: "api"
    tsconfig.json
apps/
  storefront/
    src/
      lib/api-client.ts ← hc<AppType> client
    tsconfig.json       ← paths: { "api/*": ["../../packages/api/src/*"] }
    wrangler.toml       ← [[services]] binding for the Worker
```

```json
// apps/storefront/tsconfig.json (relevant excerpt)
{
  "compilerOptions": {
    "paths": {
      "api/*": ["../../packages/api/src/*"]
    }
  }
}
```

Vite / Pages build uses the same `paths` mapping to resolve the import at
compile time. The `import type { AppType }` import is erased entirely from the
browser bundle — only the `hono/client` runtime ships.

---

## Generating a Static OpenAPI Spec for Swagger UI

Add a build script to export the spec as a static JSON file, hosted on Pages:

```typescript
// packages/api/scripts/gen-openapi.ts
import app from '../src/index';

const spec = app.getOpenAPI31Document({
  openapi: '3.1.0',
  info: { title: 'Storefront API', version: '1.0.0' },
});

await Deno.writeTextFile(
  '../../apps/storefront/public/openapi.json',
  JSON.stringify(spec, null, 2)
);
```

Or via Node:

```typescript
import { writeFileSync } from 'node:fs';
import app from '../src/index.js';

const spec = app.getOpenAPI31Document({ openapi: '3.1.0', info: { title: 'API', version: '1' } });
writeFileSync('../../apps/storefront/public/openapi.json', JSON.stringify(spec));
```

The generated `openapi.json` is then served statically from Pages and can be
imported into Postman, Insomnia, or Scalar for team-wide API exploration.

---

## Anti-patterns

- **Importing Worker runtime modules into the frontend bundle**: `hc<AppType>` requires
  only the `AppType` — always use `import type`. Any non-type import from a Worker
  file that uses `cloudflare:workers` or `node:*` globals will break the browser build.
- **Skipping `.openapi()` annotations on response schemas**: Without response schema
  registration, `res.json()` returns `unknown` on the client side, defeating the
  purpose of the typed client.
- **Using `z.any()` as a shortcut in request schemas**: This silences validation errors
  on the Worker and returns `any` to the frontend client, removing type safety entirely.
- **Sharing the `app` instance itself instead of `AppType`**: The `app` object includes
  Worker runtime state. Only the type should cross the package boundary.

---

## Gotchas

- `hc<AppType>` path construction mirrors the Hono route paths exactly. If the route
  is `/api/products/search`, the client call is `api.api.products.search.$get(...)`.
  Nested path segments become nested property accesses.
- `z.coerce.number()` in query schemas is required because URL query parameters are
  always strings. Without `coerce`, `limit=20` fails Zod's `z.number()` check.
- `c.req.valid('query')` returns the coerced, parsed value — not the raw string from
  the URL. Downstream code receives `{ limit: 20 }` (number), not `{ limit: '20' }`.
- The `OpenAPIHono` instance must call `app.doc()` for `getOpenAPI31Document()` to
  collect all registered schemas. Routes added after the doc registration are excluded.
- `@hono/zod-openapi` peer-requires `hono >= 4.0.0` and `zod >= 3.22.0`.

---

## Verification

1. Run `curl 'http://localhost:8787/openapi.json'` and verify the spec includes the
   `products/search` path with the correct query parameters and response schema.
2. Call the endpoint with a missing `q` param: `curl 'http://localhost:8787/api/products/search'`.
   Expect a 400 with `{ error: '...' }` matching the error schema.
3. In the frontend, intentionally pass an extra unknown field to `$get()` and confirm
   TypeScript emits an "Object literal may only specify known properties" error.
4. Run `tsc --noEmit` across the monorepo after changing a Zod schema field and
   confirm compile errors surface in all call sites.

---

## Related

- `hono-cloudflare-workers-frontend-api.md` — Hono routing fundamentals on Workers
- `form-validation-zod-workers-endpoint.md` — Zod validation for form submissions
- `react-query-patterns.md` — TanStack Query with typed API responses
- `workers-rpc-typed-client-frontend.md` — RPC alternative for internal calls

---

## Sources

- @hono/zod-openapi package: https://hono.dev/examples/zod-openapi
- hono/client typed client: https://hono.dev/docs/guides/rpc
- Zod documentation: https://zod.dev/
- OpenAPI 3.1 specification: https://spec.openapis.org/oas/v3.1.0
- Cloudflare Workers + Hono: https://hono.dev/docs/getting-started/cloudflare-workers
