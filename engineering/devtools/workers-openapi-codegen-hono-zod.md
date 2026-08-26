# OpenAPI Code Generation for Hono + Zod in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Worker exposes a REST API consumed by a TypeScript frontend and a mobile app. The API contract is informal — developers read the Worker source to understand request/response shapes. When the API changes, consumers break at runtime because there is no schema validation, no generated documentation, and no type-safe client SDK. Writing and maintaining an OpenAPI spec by hand is error-prone and quickly goes stale.

## Context

Applies when:
- Hono v4.x used as the Worker router
- TypeScript strict mode
- API consumed by TypeScript clients (frontend, other Workers, mobile BFF)
- Desire for a single source of truth: Zod schemas drive validation, OpenAPI spec, and client types simultaneously

`@hono/zod-openapi` is an official Hono extension that wraps routes with Zod schemas. When a request arrives, Zod validates the path params, query params, headers, and body before your handler runs. The same schemas are also used to generate an OpenAPI 3.1 spec at a dedicated endpoint. `openapi-typescript` then reads that spec and emits TypeScript types for a type-safe `fetch` wrapper.

## Solution

### Install dependencies

```bash
pnpm add hono @hono/zod-openapi zod
pnpm add -D openapi-typescript
```

### Define Zod schemas

```typescript
// src/schemas/user.ts
import { z } from 'zod';

export const UserIdParam = z.object({
  id: z.string().uuid().openapi({ example: '550e8400-e29b-41d4-a716-446655440000' }),
});

export const CreateUserBody = z.object({
  email: z.string().email().openapi({ example: 'user@example.com' }),
  name: z.string().min(1).max(100).openapi({ example: 'Jane Doe' }),
  role: z.enum(['admin', 'member', 'viewer']).default('member'),
}).openapi('CreateUserBody');

export const UserResponse = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  name: z.string(),
  role: z.enum(['admin', 'member', 'viewer']),
  createdAt: z.string().datetime(),
}).openapi('UserResponse');

export const UserListResponse = z.object({
  users: z.array(UserResponse),
  total: z.number().int().nonnegative(),
  nextCursor: z.string().optional(),
}).openapi('UserListResponse');

export const ErrorResponse = z.object({
  error: z.string(),
  code: z.string(),
  details: z.record(z.string()).optional(),
}).openapi('ErrorResponse');

export const PaginationQuery = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20).openapi({ example: 20 }),
  cursor: z.string().optional().openapi({ example: 'eyJpZCI6IjEyMyJ9' }),
});
```

### Create the OpenAPI app

```typescript
// src/app.ts
import { OpenAPIHono, createRoute } from '@hono/zod-openapi';
import {
  CreateUserBody,
  ErrorResponse,
  PaginationQuery,
  UserIdParam,
  UserListResponse,
  UserResponse,
} from './schemas/user';

const app = new OpenAPIHono<{ Bindings: Env }>();

// Route: GET /users
const listUsersRoute = createRoute({
  method: 'get',
  path: '/users',
  tags: ['Users'],
  summary: 'List all users',
  description: 'Returns a paginated list of users. Use `cursor` for subsequent pages.',
  request: {
    query: PaginationQuery,
  },
  responses: {
    200: {
      content: { 'application/json': { schema: UserListResponse } },
      description: 'Paginated list of users',
    },
    400: {
      content: { 'application/json': { schema: ErrorResponse } },
      description: 'Invalid query parameters',
    },
  },
});

app.openapi(listUsersRoute, async (c) => {
  // c.req.valid('query') is fully typed as { limit: number; cursor?: string }
  const { limit, cursor } = c.req.valid('query');
  const db = c.env.USERS_DB;

  const stmt = cursor
    ? db.prepare('SELECT * FROM users WHERE id > ? ORDER BY id LIMIT ?').bind(cursor, limit)
    : db.prepare('SELECT * FROM users ORDER BY id LIMIT ?').bind(limit);

  const { results } = await stmt.all<{
    id: string;
    email: string;
    name: string;
    role: 'admin' | 'member' | 'viewer';
    created_at: string;
  }>();

  const users = results.map((row) => ({
    id: row.id,
    email: row.email,
    name: row.name,
    role: row.role,
    createdAt: row.created_at,
  }));

  const nextCursor = results.length === limit ? results[results.length - 1]?.id : undefined;

  return c.json({ users, total: users.length, nextCursor }, 200);
});

// Route: GET /users/:id
const getUserRoute = createRoute({
  method: 'get',
  path: '/users/{id}',
  tags: ['Users'],
  summary: 'Get a user by ID',
  request: { params: UserIdParam },
  responses: {
    200: {
      content: { 'application/json': { schema: UserResponse } },
      description: 'User found',
    },
    404: {
      content: { 'application/json': { schema: ErrorResponse } },
      description: 'User not found',
    },
  },
});

app.openapi(getUserRoute, async (c) => {
  const { id } = c.req.valid('param');
  const row = await c.env.USERS_DB
    .prepare('SELECT * FROM users WHERE id = ?')
    .bind(id)
    .first<{ id: string; email: string; name: string; role: string; created_at: string }>();

  if (!row) {
    return c.json({ error: 'User not found', code: 'USER_NOT_FOUND' }, 404);
  }

  return c.json(
    {
      id: row.id,
      email: row.email,
      name: row.name,
      role: row.role as 'admin' | 'member' | 'viewer',
      createdAt: row.created_at,
    },
    200
  );
});

// Route: POST /users
const createUserRoute = createRoute({
  method: 'post',
  path: '/users',
  tags: ['Users'],
  summary: 'Create a new user',
  request: {
    body: {
      content: { 'application/json': { schema: CreateUserBody } },
      required: true,
    },
  },
  responses: {
    201: {
      content: { 'application/json': { schema: UserResponse } },
      description: 'User created successfully',
    },
    409: {
      content: { 'application/json': { schema: ErrorResponse } },
      description: 'Email already exists',
    },
    422: {
      content: { 'application/json': { schema: ErrorResponse } },
      description: 'Validation error',
    },
  },
});

app.openapi(createUserRoute, async (c) => {
  const { email, name, role } = c.req.valid('json');
  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  try {
    await c.env.USERS_DB
      .prepare('INSERT INTO users (id, email, name, role, created_at) VALUES (?, ?, ?, ?, ?)')
      .bind(id, email, name, role, createdAt)
      .run();
  } catch (err) {
    if (err instanceof Error && err.message.includes('UNIQUE constraint')) {
      return c.json({ error: 'Email already registered', code: 'EMAIL_EXISTS' }, 409);
    }
    throw err;
  }

  return c.json({ id, email, name, role, createdAt }, 201);
});

export default app;
```

### Expose the OpenAPI spec endpoint

```typescript
// src/index.ts
import app from './app';

// Register the OpenAPI JSON spec endpoint
app.doc('/openapi.json', {
  openapi: '3.1.0',
  info: {
    title: 'My API',
    version: '1.0.0',
    description: 'Cloudflare Workers API built with Hono + Zod',
  },
  servers: [
    { url: 'https://api.example.com', description: 'Production' },
    { url: 'http://localhost:8787', description: 'Local development' },
  ],
});

// Optional: Swagger UI at /docs (using @hono/swagger-ui if installed)
// app.get('/docs', swaggerUI({ url: '/openapi.json' }));

export default app satisfies ExportedHandler<Env>;
```

## Implementation Details

### Generating TypeScript client types from the live spec

```bash
# During development, run wrangler dev in one terminal:
wrangler dev &

# In another terminal, generate types from the local spec:
npx openapi-typescript http://localhost:8787/openapi.json -o src/client/api.d.ts
```

For CI, generate from the production spec:

```bash
npx openapi-typescript https://api.example.com/openapi.json -o packages/api-client/src/api.d.ts
```

Add to `package.json`:

```json
{
  "scripts": {
    "generate:types": "openapi-typescript http://localhost:8787/openapi.json -o src/client/api.d.ts",
    "generate:types:prod": "openapi-typescript https://api.example.com/openapi.json -o src/client/api.d.ts"
  }
}
```

### Type-safe API client with `openapi-fetch`

```bash
pnpm add openapi-fetch
```

```typescript
// src/client/index.ts  (in the frontend or consumer package)
import createClient from 'openapi-fetch';
import type { paths } from './api.d.ts'; // generated by openapi-typescript

const apiClient = createClient<paths>({
  baseUrl: process.env.API_BASE_URL ?? 'https://api.example.com',
  headers: {
    Authorization: `Bearer ${process.env.API_TOKEN}`,
  },
});

// Type-safe usage — all paths, methods, params, and responses are inferred
async function example() {
  // GET /users?limit=10
  const { data: list, error: listError } = await apiClient.GET('/users', {
    params: { query: { limit: 10 } },
  });
  if (listError) throw new Error(listError.error);
  // list.users is UserResponse[]
  // list.nextCursor is string | undefined

  // GET /users/{id}
  const { data: user, error: userError } = await apiClient.GET('/users/{id}', {
    params: { path: { id: '550e8400-e29b-41d4-a716-446655440000' } },
  });
  if (userError) throw new Error(userError.error);
  // user.email is string, user.role is 'admin' | 'member' | 'viewer'

  // POST /users
  const { data: created, error: createError } = await apiClient.POST('/users', {
    body: { email: 'new@example.com', name: 'New User', role: 'member' },
  });
  if (createError) throw new Error(createError.error);
  // created.id is string
}
```

### Validation error handling middleware

By default, `@hono/zod-openapi` returns a 400 when Zod validation fails. Customise the error format:

```typescript
// src/app.ts
const app = new OpenAPIHono<{ Bindings: Env }>({
  defaultHook: (result, c) => {
    if (!result.success) {
      const formatted = result.error.flatten();
      return c.json(
        {
          error: 'Validation failed',
          code: 'VALIDATION_ERROR',
          details: {
            ...formatted.fieldErrors,
            ...(formatted.formErrors.length > 0
              ? { _root: formatted.formErrors.join(', ') }
              : {}),
          },
        },
        422  // Unprocessable Entity
      );
    }
  },
});
```

### Adding authentication to the OpenAPI spec

```typescript
// src/app.ts — security scheme registration
app.openAPIRegistry.registerComponent('securitySchemes', 'BearerAuth', {
  type: 'http',
  scheme: 'bearer',
  bearerFormat: 'JWT',
});

// Apply security to all routes globally
const adminRoute = createRoute({
  method: 'delete',
  path: '/users/{id}',
  security: [{ BearerAuth: [] }],
  // ...
  responses: {
    204: { description: 'User deleted' },
    401: {
      content: { 'application/json': { schema: ErrorResponse } },
      description: 'Unauthorized',
    },
  },
});
```

### Testing routes with Hono's test utility

```typescript
// src/app.test.ts
import { describe, it, expect } from 'vitest';
import app from './app';

// Minimal Env mock
const mockEnv: Env = {
  USERS_DB: {
    prepare: (sql: string) => ({
      bind: (...args: unknown[]) => ({
        all: async () => ({ results: [], success: true, meta: {} }),
        first: async () => null,
        run: async () => ({ success: true, meta: {} }),
      }),
    }),
  } as unknown as D1Database,
};

describe('GET /users', () => {
  it('returns 200 with empty list', async () => {
    const res = await app.request('/users', {}, mockEnv);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ users: [], total: 0 });
  });

  it('returns 422 for invalid limit', async () => {
    const res = await app.request('/users?limit=999', {}, mockEnv);
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.code).toBe('VALIDATION_ERROR');
  });

  it('exposes openapi.json spec', async () => {
    const res = await app.request('/openapi.json', {}, mockEnv);
    expect(res.status).toBe(200);
    const spec = await res.json();
    expect(spec.openapi).toBe('3.1.0');
    expect(spec.paths).toHaveProperty('/users');
    expect(spec.paths).toHaveProperty('/users/{id}');
  });
});
```

## Anti-patterns

**Do not** define Zod schemas inline inside `createRoute()`. Inline schemas cannot be shared between routes (for reusable response types) and cannot be referenced by `openapi-typescript` as named components. Always export schemas from dedicated schema files.

**Do not** call `.openapi()` on every single intermediate Zod schema. Only call `.openapi('ComponentName')` on schemas that should appear as named components in the spec's `#/components/schemas` section — typically request bodies and response objects. Calling it on internal sub-schemas bloats the spec.

**Do not** manually write the OpenAPI spec JSON. The entire point of this setup is that the spec is derived from the Zod schemas. A manually written spec immediately diverges from the actual validation logic.

**Do not** skip the `defaultHook` for validation errors in production. Without it, Hono/Zod returns a generic 400 with a raw Zod error object that exposes internal field names and validation rule details — information useful for developers but inappropriate for end users.

## Gotchas

**`c.req.valid()` only works after `app.openapi()` registration**, not with plain `app.get()`. If you mix `app.openapi()` routes with regular Hono `app.get()` routes, the `valid()` helper throws at runtime for the non-OpenAPI routes. Use `app.openapi()` for all routes that need validation.

**`z.coerce` is required for query parameters**. URL query parameters are always strings. Without `z.coerce.number()`, a `limit=20` query param fails the `z.number()` check because `'20'` is a string, not a number. Use `z.coerce.number()` (or `z.string().transform(Number)`) for all numeric query params.

**`openapi-typescript` generates `paths` with literal path strings**. The generated type key for `GET /users/{id}` is `'/users/{id}'` (curly brace syntax), not `/users/:id` (Hono/Express colon syntax). The `openapi-fetch` client uses the curly-brace form matching the OpenAPI spec — do not confuse them.

**Generated `api.d.ts` must be regenerated after every schema change**. The generated file goes stale silently — the TypeScript compiler uses the old types while the runtime uses the new validation. Automate regeneration in CI: after deploying the Worker, run `openapi-typescript` against the live spec and commit the result (or fail CI if it has changed without a corresponding commit).

**Hono's `satisfies ExportedHandler<Env>`** requires the app to be cast: `export default app satisfies ExportedHandler<Env>`. The `OpenAPIHono` class returns a `Hono` instance which `satisfies` can verify is a valid handler.

## Verification

```bash
# Start local dev server
wrangler dev

# Verify the spec is served
curl http://localhost:8787/openapi.json | jq '.paths | keys'
# Expected: ["/users", "/users/{id}"]

# Test validation is enforced
curl -X POST http://localhost:8787/users \
  -H 'Content-Type: application/json' \
  -d '{"email": "not-an-email", "name": ""}'
# Expected: 422 with {"code": "VALIDATION_ERROR", "details": {"email": [...], "name": [...]}}

# Generate TypeScript types from the live spec
npx openapi-typescript http://localhost:8787/openapi.json -o /tmp/api.d.ts
cat /tmp/api.d.ts | grep 'UserResponse'
# Expected: interface definition with id, email, name, role, createdAt fields

# Run unit tests
pnpm vitest run src/app.test.ts
```

## Related

- `wrangler-config-typescript-types.md` — `Env` interface used in route handlers (`c.env.USERS_DB`)
- `workers-changesets-version-release-pipeline.md` — publishing the generated client SDK as an npm package
- `workers-lefthook-git-hooks-monorepo.md` — pre-commit hooks to validate schemas compile without error

## Sources

- https://hono.dev/examples/zod-openapi
- https://github.com/honojs/middleware/tree/main/packages/zod-openapi
- https://openapi-ts.dev/
- https://openapi-ts.dev/openapi-fetch/
- https://developers.cloudflare.com/workers/frameworks/framework-guides/hono/
