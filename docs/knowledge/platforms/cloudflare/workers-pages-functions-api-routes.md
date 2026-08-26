# Building API Routes with Cloudflare Pages Functions

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have a Cloudflare Pages project and need to add server-side API endpoints without deploying a separate Worker. Users hitting `/api/users` or `/api/products/:id` get 404s or must rely on external backends.

## Context

Cloudflare Pages Functions let you colocate server-side logic with your frontend inside the same Pages project. Files placed in the `/functions` directory are compiled into Workers at deploy time. Routes map directly from the filesystem path to the HTTP path, following a convention similar to Next.js file-based routing. Functions execute in the Cloudflare edge network and have access to the same bindings (KV, D1, R2, AI, Queues) as standalone Workers.

Pages Functions support:
- Static routes (`/functions/api/users.ts` → `GET /api/users`)
- Dynamic segments (`/functions/api/users/[id].ts` → `GET /api/users/:id`)
- Catch-all routes (`/functions/api/[...path].ts`)
- Middleware via `_middleware.ts` at any directory level
- Named exports for specific HTTP methods or a generic `onRequest` fallback

## Solution

### Directory Structure

```
my-pages-project/
├── public/               # Static assets
├── functions/
│   ├── _middleware.ts    # Global middleware
│   ├── api/
│   │   ├── _middleware.ts  # /api/* middleware
│   │   ├── users.ts        # GET/POST /api/users
│   │   └── users/
│   │       └── [id].ts     # /api/users/:id
│   └── health.ts           # GET /health
└── package.json
```

### Typed Environment Bindings

```typescript
// functions/env.d.ts
export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  ASSETS: Fetcher;
  API_SECRET: string;
}
```

### onRequest vs Named Method Exports

```typescript
// functions/api/users.ts
import type { Env } from '../env';

// Handle all HTTP methods
export const onRequest: PagesFunction<Env> = async (ctx) => {
  return new Response('Method not allowed', { status: 405 });
};

// Handle GET only — takes priority over onRequest for GET
export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const { env, request } = ctx;
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page') ?? '1');
  const limit = Math.min(Number(url.searchParams.get('limit') ?? '20'), 100);
  const offset = (page - 1) * limit;

  const { results } = await env.DB.prepare(
    'SELECT id, name, email, created_at FROM users ORDER BY created_at DESC LIMIT ?1 OFFSET ?2'
  )
    .bind(limit, offset)
    .all();

  return Response.json({ data: results, page, limit });
};

// Handle POST only
export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  const { env, request } = ctx;

  let body: { name: string; email: string };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!body.name || !body.email) {
    return Response.json({ error: 'name and email are required' }, { status: 422 });
  }

  const result = await env.DB.prepare(
    'INSERT INTO users (name, email) VALUES (?1, ?2) RETURNING id, name, email, created_at'
  )
    .bind(body.name, body.email)
    .first();

  return Response.json({ data: result }, { status: 201 });
};
```

### Dynamic Route Segments

```typescript
// functions/api/users/[id].ts
import type { Env } from '../../env';

export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const { env, params } = ctx;
  // params.id comes from the [id] segment
  const id = params.id as string;

  if (!/^\d+$/.test(id)) {
    return Response.json({ error: 'Invalid ID' }, { status: 400 });
  }

  const user = await env.DB.prepare(
    'SELECT id, name, email, created_at FROM users WHERE id = ?1'
  )
    .bind(Number(id))
    .first();

  if (!user) {
    return Response.json({ error: 'Not found' }, { status: 404 });
  }

  return Response.json({ data: user });
};

export const onRequestDelete: PagesFunction<Env> = async (ctx) => {
  const { env, params } = ctx;
  const id = Number(params.id as string);

  const { success } = await env.DB.prepare('DELETE FROM users WHERE id = ?1')
    .bind(id)
    .run();

  if (!success) {
    return Response.json({ error: 'Delete failed' }, { status: 500 });
  }

  return new Response(null, { status: 204 });
};
```

### Middleware Chaining

```typescript
// functions/api/_middleware.ts
// Runs before every handler under /api/*
import type { Env } from '../env';

const authMiddleware: PagesFunction<Env> = async (ctx) => {
  const { request, env, next } = ctx;
  const auth = request.headers.get('Authorization');

  if (!auth?.startsWith('Bearer ')) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const token = auth.slice(7);
  if (token !== env.API_SECRET) {
    return Response.json({ error: 'Forbidden' }, { status: 403 });
  }

  // Attach user context via request headers before forwarding
  const response = await next();
  return response;
};

const corsMiddleware: PagesFunction<Env> = async (ctx) => {
  const { request, next } = ctx;

  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '86400',
      },
    });
  }

  const response = await next();
  const newResponse = new Response(response.body, response);
  newResponse.headers.set('Access-Control-Allow-Origin', '*');
  return newResponse;
};

// Export array — executed left to right
export const onRequest = [corsMiddleware, authMiddleware];
```

### Catch-All Route

```typescript
// functions/api/[...path].ts
import type { Env } from '../env';

export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const segments = ctx.params.path as string[];
  return Response.json(
    { error: `Route /api/${segments.join('/')} not found` },
    { status: 404 }
  );
};
```

### wrangler.toml Bindings for Pages

```toml
# wrangler.toml (Pages project)
name = "my-pages-project"
pages_build_output_dir = "dist"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
API_SECRET = "change-me-in-dashboard"
```

## Implementation Details

**Execution order:** When a request arrives, Pages evaluates `_middleware.ts` files from the root downward before reaching the route handler. The `next()` call passes control to the next middleware or the final handler.

**Method priority:** Named exports (`onRequestGet`, `onRequestPost`, etc.) take precedence over the generic `onRequest` export for their respective HTTP method.

**Type safety:** The `PagesFunction<Env>` generic types `ctx.env` to your `Env` interface, giving full IntelliSense on bindings.

**Build output:** During `wrangler pages deploy` (or CI), Pages compiles all function files into a single `_worker.js` bundle via esbuild. You do not ship the raw TypeScript.

**Size limit:** The compiled Functions bundle must stay under 3 MB (uncompressed). Large dependencies shared across many routes should be extracted to a separate Worker.

## Anti-patterns

- Do not `import` from `node:*` builtins directly — use the Workers-compatible equivalents or polyfills.
- Avoid sharing mutable state at module level between requests; the isolate may handle multiple requests but state is not guaranteed.
- Do not put secrets in `wrangler.toml` committed to version control — use the Pages dashboard "Environment Variables" section for production values.
- Avoid deeply nested `_middleware.ts` chains that obscure the auth flow — keep middleware at the `/functions/api/` level and document what each layer does.

## Gotchas

- The `params` object values are always `string | string[]`. Destructure with a type assertion and validate before use.
- Pages Functions do **not** support `scheduled` triggers (cron) — use a standalone Worker for that.
- Local dev via `wrangler pages dev` emulates bindings but D1 uses a local SQLite file; schema must be migrated locally with `wrangler d1 migrations apply --local`.
- When returning binary responses (images, PDFs), set the correct `Content-Type` and do not run the body through `JSON.stringify`.

## Verification

```bash
# Run Pages Functions locally
npx wrangler pages dev ./dist --d1=DB --kv=CACHE

# Test a route
curl -H 'Authorization: Bearer change-me-in-dashboard' \
  http://localhost:8788/api/users

# Deploy to Pages
npx wrangler pages deploy ./dist --project-name my-pages-project

# Tail live logs
npx wrangler pages deployment tail --project-name my-pages-project
```

## Related

- `workers-hyperdrive-postgres-connection.md` — connecting to PostgreSQL from a function
- `workers-queues-fan-out-pattern.md` — publishing events from an API route
- Cloudflare Pages Functions docs: https://developers.cloudflare.com/pages/functions/

## Sources

- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/bindings/
