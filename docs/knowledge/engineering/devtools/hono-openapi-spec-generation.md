# Generating OpenAPI Specs from Workers Hono Routes

- Date: 2026-08-22
- Author: example.com
- Status: production

---

## Symptom / Use-case

You've built an API on Cloudflare Workers using Hono, and now you need an OpenAPI 3.1 specification — for auto-generating a client SDK, feeding a developer portal, powering request validation, or documenting the API for consumers. Writing the spec by hand and keeping it in sync with the code is error-prone. This article covers generating the OpenAPI spec directly from your Hono route definitions using `@hono/zod-openapi` and the `hono-openapi` ecosystem.

Typical scenarios:
- Generating a TypeScript client via `openapi-typescript` or `orval` from your Hono routes
- Publishing an interactive Swagger UI or Scalar docs page within the Worker itself
- Validating incoming requests against the schema at runtime using Zod
- Feeding an API gateway or API management platform (e.g., Apiary, Stoplight) with a machine-readable spec

---

## Context

Hono's core router has no built-in OpenAPI awareness — it maps URL patterns to handler functions. Two packages add spec generation:

| Package | Approach | Runtime validation |
|---------|----------|--------------------|
| `@hono/zod-openapi` | Extend `OpenAPIHono` with typed route builders | Yes — Zod validates every request |
| `hono-openapi` (middleware) | Annotate existing routes with OpenAPI metadata | Optional |
| `chanfana` (Cloudflare's own) | `OpenAPIRouter` wrapping `itty-router` | Yes — integrates with Workers Types |

This article focuses on `@hono/zod-openapi`, which is the most mature and integrates tightly with Hono. Cloudflare's `chanfana` is also covered for projects that prefer it.

---

## Setup: `@hono/zod-openapi`

```bash
pnpm add hono @hono/zod-openapi zod
pnpm add -D @cloudflare/workers-types wrangler
```

```toml
# wrangler.toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]
```

---

## Defining Routes with OpenAPI Metadata

Instead of `new Hono()`, use `new OpenAPIHono()`. Routes are defined with `.openapi()` instead of `.get()` / `.post()`:

```typescript
// src/index.ts
import { OpenAPIHono, createRoute, z } from '@hono/zod-openapi';

// Define reusable schemas
const UserSchema = z.object({
  id: z.string().uuid().openapi({ example: '550e8400-e29b-41d4-a716-446655440000' }),
  name: z.string().min(1).max(100).openapi({ example: 'Alice Johnson' }),
  email: z.string().email().openapi({ example: 'alice@example.com' }),
  createdAt: z.string().datetime().openapi({ example: '2026-01-15T10:30:00Z' }),
}).openapi('User');

const CreateUserSchema = z.object({
  name: z.string().min(1).max(100).openapi({ example: 'Bob Smith' }),
  email: z.string().email().openapi({ example: 'bob@example.com' }),
}).openapi('CreateUser');

const ErrorSchema = z.object({
  code: z.number().openapi({ example: 404 }),
  message: z.string().openapi({ example: 'User not found' }),
}).openapi('Error');

// Define route with OpenAPI metadata
const getUserRoute = createRoute({
  method: 'get',
  path: '/users/{id}',
  tags: ['Users'],
  summary: 'Get a user by ID',
  description: 'Retrieve a single user by their unique identifier.',
  request: {
    params: z.object({
      id: z.string().uuid().openapi({ description: 'User UUID' }),
    }),
  },
  responses: {
    200: {
      content: {
        'application/json': {
          schema: UserSchema,
        },
      },
      description: 'The requested user',
    },
    404: {
      content: {
        'application/json': {
          schema: ErrorSchema,
        },
      },
      description: 'User not found',
    },
  },
});

const createUserRoute = createRoute({
  method: 'post',
  path: '/users',
  tags: ['Users'],
  summary: 'Create a user',
  request: {
    body: {
      content: {
        'application/json': {
          schema: CreateUserSchema,
        },
      },
      required: true,
    },
  },
  responses: {
    201: {
      content: {
        'application/json': {
          schema: UserSchema,
        },
      },
      description: 'Created user',
    },
    422: {
      content: {
        'application/json': {
          schema: ErrorSchema,
        },
      },
      description: 'Validation error',
    },
  },
});
```

---

## Registering Routes and Handlers

```typescript
// src/index.ts (continued)
import type { Env } from './types/env';

const app = new OpenAPIHono<{ Bindings: Env }>();

// Handler gets fully typed, validated request data
app.openapi(getUserRoute, async (c) => {
  const { id } = c.req.valid('param'); // type: { id: string }

  const user = await c.env.DB.prepare(
    'SELECT id, name, email, created_at FROM users WHERE id = ?'
  ).bind(id).first<{ id: string; name: string; email: string; created_at: string }>();

  if (!user) {
    return c.json({ code: 404, message: 'User not found' }, 404);
  }

  return c.json({
    id: user.id,
    name: user.name,
    email: user.email,
    createdAt: user.created_at,
  }, 200);
});

app.openapi(createUserRoute, async (c) => {
  const body = c.req.valid('json'); // type: { name: string; email: string }

  const id = crypto.randomUUID();
  const now = new Date().toISOString();

  await c.env.DB.prepare(
    'INSERT INTO users (id, name, email, created_at) VALUES (?, ?, ?, ?)'
  ).bind(id, body.name, body.email, now).run();

  return c.json({
    id,
    name: body.name,
    email: body.email,
    createdAt: now,
  }, 201);
});

export default app;
```

---

## Serving the OpenAPI Spec and Swagger UI

Add spec and UI endpoints to the same app:

```typescript
// src/index.ts (continued)

// Serve OpenAPI JSON spec at /doc
app.doc('/doc', {
  openapi: '3.1.0',
  info: {
    version: '1.0.0',
    title: 'My API',
    description: 'API built on Cloudflare Workers with Hono',
    contact: {
      name: 'API Support',
      email: 'api@example.com',
    },
  },
  servers: [
    {
      url: 'https://api.example.com',
      description: 'Production',
    },
    {
      url: 'http://localhost:8787',
      description: 'Local development',
    },
  ],
  tags: [
    { name: 'Users', description: 'User management operations' },
  ],
});

// Serve Scalar API reference UI at /reference
// Scalar is a modern alternative to Swagger UI
app.get('/reference', (c) => {
  return c.html(`<!DOCTYPE html>
<html>
<head>
  <title>API Reference</title>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body>
  <script
    id="api-reference"
    data-url="/doc"
    type="application/json"
  ></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>`);
});
```

Navigate to `http://localhost:8787/doc` for the raw JSON spec and `http://localhost:8787/reference` for the interactive UI.

---

## Alternative: Cloudflare's `chanfana`

`chanfana` (formerly `itty-router-openapi`) is Cloudflare's official OpenAPI framework for Workers. It has a class-based approach that some teams prefer:

```bash
pnpm add chanfana hono zod
```

```typescript
// src/index.ts
import { fromHono, OpenAPIRoute, contentJson } from 'chanfana';
import { Hono } from 'hono';
import { z } from 'zod';

const hono = new Hono();
const app = fromHono(hono, {
  docs_url: '/docs',
  openapi_url: '/openapi.json',
  schema: {
    info: {
      title: 'My Workers API',
      version: '1.0.0',
    },
  },
});

class GetUser extends OpenAPIRoute {
  schema = {
    tags: ['Users'],
    summary: 'Get user by ID',
    request: {
      params: z.object({
        id: z.string().uuid(),
      }),
    },
    responses: {
      200: {
        description: 'User found',
        ...contentJson(z.object({
          id: z.string().uuid(),
          name: z.string(),
          email: z.string().email(),
        })),
      },
    },
  };

  async handle(c: any) {
    const { id } = c.req.valid('param');
    // ... fetch user from D1
    return { id, name: 'Alice', email: 'alice@example.com' };
  }
}

app.get('/users/:id', GetUser);
export default hono;
```

---

## Generating a TypeScript Client

Once the spec is available at `/doc`, use `openapi-typescript` to generate types and `openapi-fetch` to create a type-safe client:

```bash
pnpm add -D openapi-typescript
pnpm add openapi-fetch
```

```json
// package.json
{
  "scripts": {
    "generate:types": "openapi-typescript http://localhost:8787/doc -o src/client/api-types.ts"
  }
}
```

```bash
# Start the dev server first
wrangler dev &

# Generate TypeScript types from the live spec
pnpm generate:types
```

```typescript
// src/client/index.ts
import createClient from 'openapi-fetch';
import type { paths } from './api-types';

const client = createClient<paths>({ baseUrl: process.env.API_URL });

// Fully type-safe API calls
const { data, error } = await client.GET('/users/{id}', {
  params: {
    path: { id: '550e8400-e29b-41d4-a716-446655440000' },
  },
});

if (data) {
  console.log(data.name); // TypeScript knows this is a string
}
```

---

## Exporting the Spec at Build Time

For CI pipelines that need the spec file without running the Worker:

```typescript
// scripts/generate-spec.ts
import app from '../src/index';

// Access the spec via the doc endpoint
const response = await app.fetch(new Request('http://localhost/doc'));
const spec = await response.json();

// Write to file for CI artifacts or API gateway upload
const fs = await import('fs/promises');
await fs.writeFile('openapi.json', JSON.stringify(spec, null, 2));
console.log('OpenAPI spec written to openapi.json');
```

```bash
# Run with tsx (TypeScript executor)
pnpm add -D tsx
npx tsx scripts/generate-spec.ts
```

```yaml
# .github/workflows/generate-spec.yml
name: Generate OpenAPI Spec
on: [push]
jobs:
  spec:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install
      - run: npx tsx scripts/generate-spec.ts
      - uses: actions/upload-artifact@v4
        with:
          name: openapi-spec
          path: openapi.json
```

---

## Anti-Patterns

**Writing OpenAPI YAML by hand and keeping it separate from the code.** The spec diverges from the actual implementation within weeks. Code-first generation (from Zod schemas) is the source of truth.

**Using `.get()`/`.post()` instead of `.openapi()` on `OpenAPIHono`.** Routes defined with standard Hono methods are invisible to spec generation. Every route that should appear in the spec must use `.openapi()`.

**Exposing the `/doc` endpoint in production without authentication.** OpenAPI specs reveal your API surface area, error codes, and data shapes — valuable to attackers. Gate it behind an `Authorization` header check or deploy it only in non-production environments.

**Generating the client from the wrong URL.** Running `openapi-typescript` against a stale dev server that hasn't picked up your latest changes produces an outdated client. Always restart `wrangler dev` before regenerating.

**Using `z.any()` in response schemas.** This satisfies TypeScript but generates `{}` in the spec — useless for client generation. Define precise schemas for every response body.

---

## Gotchas

- **`@hono/zod-openapi` requires Zod 3.x.** Zod 4 (released 2025) has breaking changes. Check `@hono/zod-openapi`'s peer dependency range before upgrading Zod.

- **The spec is generated at request time, not build time.** The `/doc` endpoint dynamically assembles the spec from registered routes. If you have routes registered conditionally (e.g., only in development), they appear in the spec only when the Worker runs with those conditions.

- **Path parameters in Hono use `:id` syntax, but OpenAPI uses `{id}`.** `@hono/zod-openapi` handles this translation automatically in `createRoute`. Don't mix the two syntaxes in a single path string.

- **Scalar UI uses a CDN script.** In Workers deployed to production, if your Content Security Policy blocks `cdn.jsdelivr.net`, the Scalar UI page will be blank. Either host the Scalar bundle in R2/Workers Assets or adjust your CSP.

- **`c.req.valid('json')` throws a 400 if validation fails**, bypassing your custom error handler. Add the `onError` option to `new OpenAPIHono()` to customise validation error responses.

```typescript
const app = new OpenAPIHono({
  defaultHook: (result, c) => {
    if (!result.success) {
      return c.json({ code: 422, message: 'Validation failed', errors: result.error.issues }, 422);
    }
  },
});
```

---

## Verification

```bash
# 1. Start the dev server
wrangler dev

# 2. Fetch the OpenAPI spec
curl http://localhost:8787/doc | jq '.paths | keys'
# Expected: ["/users", "/users/{id}"]

# 3. Validate the spec is valid OpenAPI 3.1
pnpm add -D @redocly/cli
npx redocly lint http://localhost:8787/doc
# Expected: "No errors or warnings found."

# 4. Open the interactive UI
open http://localhost:8787/reference

# 5. Generate TypeScript types
pnpm generate:types
ls src/client/api-types.ts  # should exist with generated types

# 6. Confirm runtime validation rejects bad input
curl -X POST http://localhost:8787/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "not-an-email"}'
# Expected: 422 Unprocessable Entity
```

---

## Related

- `vitest-workers-miniflare-testing-setup.md` — Testing the routes you just documented
- `typescript-path-aliases-workers.md` — Keeping imports clean in larger Workers projects
- `typescript-cloudflare-workers-strict.md` — TypeScript config for Workers
- `wrangler-dev-remote-d1-r2-bindings.md` — Connecting to real data in dev
- `opentelemetry-workers-tracing-setup.md` — Adding tracing alongside the API

---

## Sources

- `@hono/zod-openapi` documentation: https://hono.dev/examples/zod-openapi
- Hono middleware docs: https://hono.dev/docs/middleware/builtin/swagger-ui
- chanfana (Cloudflare OpenAPI): https://chanfana.pages.dev/
- `openapi-typescript`: https://openapi-ts.dev/
- `openapi-fetch`: https://openapi-ts.dev/openapi-fetch/
- Redocly CLI linting: https://redocly.com/docs/cli/commands/lint/
- Scalar API reference: https://scalar.com/
