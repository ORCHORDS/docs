# Hono.js on Cloudflare Workers: Type-Safe Frontend API Routes

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your frontend app needs a lightweight, type-safe API layer deployed to the edge without the overhead of a full Next.js or Remix setup. You want end-to-end type safety from the Worker handler down to the browser fetch call.

## Context
Hono is a fast, edge-native web framework with a zero-dependency core that runs natively on Cloudflare Workers. Its RPC client (`hc`) generates a fully-typed fetch wrapper from your route definitions, eliminating the need for a separate OpenAPI schema or code-generation step. Combined with Cloudflare bindings (D1, KV, R2), Hono covers the full backend surface for most frontend apps.

## Worker Entry Point and Route Definitions

```typescript
// src/worker.ts
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';

export type Env = {
  DB: D1Database;
  CACHE: KVNamespace;
  API_SECRET: string;
};

const app = new Hono<{ Bindings: Env }>();

app.use('*', cors({ origin: ['https://app.example.com'], credentials: true }));

const products = app.get('/products', async (c) => {
  const { results } = await c.env.DB.prepare(
    'SELECT id, name, price_cents FROM products WHERE active = 1 LIMIT 50'
  ).all<{ id: string; name: string; price_cents: number }>();
  return c.json({ products: results });
});

const createProduct = app.post(
  '/products',
  zValidator(
    'json',
    z.object({ name: z.string().min(1), price_cents: z.number().int().positive() })
  ),
  async (c) => {
    const { name, price_cents } = c.req.valid('json');
    const id = crypto.randomUUID();
    await c.env.DB.prepare(
      'INSERT INTO products (id, name, price_cents, active) VALUES (?, ?, ?, 1)'
    )
      .bind(id, name, price_cents)
      .run();
    return c.json({ id }, 201);
  }
);

// Export the app type for the RPC client
export type AppType = typeof products & typeof createProduct;

export default app;
```

## RPC Client in the Browser

```typescript
// src/lib/api.ts
import { hc } from 'hono/client';
import type { AppType } from '../worker';

// The client is fully typed — no runtime overhead, no codegen step
export const api = hc<AppType>(import.meta.env.VITE_API_URL);

// Usage in a React component:
// const res = await api.products.$get();
// const { products } = await res.json();
// TypeScript infers the response shape from the Worker route definition.
```

## Middleware: Auth and Rate Limiting

```typescript
// src/middleware/auth.ts
import { createMiddleware } from 'hono/factory';
import type { Env } from '../worker';

export const requireAuth = createMiddleware<{ Bindings: Env }>(async (c, next) => {
  const token = c.req.header('Authorization')?.replace('Bearer ', '');
  if (!token) return c.json({ error: 'Unauthorized' }, 401);

  const cached = await c.env.CACHE.get(`token:${token}`, { type: 'json' }) as
    | { userId: string }
    | null;

  if (cached) {
    c.set('userId' as never, cached.userId);
    return next();
  }

  // Validate JWT using the Web Crypto API (available in Workers)
  try {
    const [header, payload, sig] = token.split('.');
    const data = new TextEncoder().encode(`${header}.${payload}`);
    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(c.env.API_SECRET),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify']
    );
    const valid = await crypto.subtle.verify(
      'HMAC',
      keyMaterial,
      Uint8Array.from(atob(sig.replace(/-/g, '+').replace(/_/g, '/')), (ch) =>
        ch.charCodeAt(0)
      ),
      data
    );
    if (!valid) return c.json({ error: 'Invalid token' }, 401);
    const decoded = JSON.parse(atob(payload)) as { sub: string; exp: number };
    if (decoded.exp < Date.now() / 1000) return c.json({ error: 'Token expired' }, 401);
    await c.env.CACHE.put(`token:${token}`, JSON.stringify({ userId: decoded.sub }), {
      expirationTtl: 300,
    });
    c.set('userId' as never, decoded.sub);
    return next();
  } catch {
    return c.json({ error: 'Invalid token' }, 401);
  }
});
```

## Streaming Responses to the UI

```typescript
// src/routes/stream.ts
import { Hono } from 'hono';
import { streamText } from 'hono/streaming';
import type { Env } from '../worker';

const streamApp = new Hono<{ Bindings: Env }>();

streamApp.get('/events', (c) =>
  streamText(c, async (stream) => {
    const rows = await c.env.DB.prepare(
      'SELECT id, event_name, occurred_at FROM events ORDER BY occurred_at DESC LIMIT 100'
    ).all<{ id: string; event_name: string; occurred_at: string }>();

    for (const row of rows.results) {
      await stream.writeln(JSON.stringify(row));
      await stream.sleep(10); // back-pressure: avoid overwhelming the browser
    }
  })
);

export default streamApp;
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "my-api"
main = "src/worker.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
API_SECRET = "dev-secret-change-in-production"
```

## Anti-patterns
- Importing Node.js-only modules (`fs`, `path`) — Workers run V8 isolates, not Node.js; use `nodejs_compat` only for polyfillable APIs
- Returning `Response` objects directly instead of `c.json()` / `c.text()` — bypasses Hono's error handling and middleware chain
- Sharing the `AppType` export across packages without a monorepo workspace — the RPC client loses type safety if the import resolves to a stale build
- Putting secrets in `wrangler.toml` plaintext — use `wrangler secret put` for production values
- Forgetting to set `credentials: true` on both the CORS middleware and the browser `fetch` call — cookies won't be sent cross-origin

## Gotchas
- `zValidator` mutates `c.req.valid()` — calling `c.req.json()` after validation re-parses the body from a consumed stream; always use `c.req.valid('json')`
- D1 `.prepare().all()` returns `{ results, meta, success }` — destructure `results` before iterating
- Hono's `hc` client appends a trailing slash to the base URL if absent — ensure your Worker's route patterns match (use `app.basePath('/api')` consistently)
- `streamText` sets `Content-Type: text/plain` — for SSE, use `streamSSE` from `hono/streaming` instead
- Workers have a 128 MB memory limit per isolate — avoid buffering large D1 result sets in memory; stream with `cursor`-based pagination

## Verification
```bash
# Local development
npx wrangler dev --local --persist

# Type-check the RPC client
npx tsc --noEmit

# Smoke test
curl -s http://localhost:8787/products | jq '.products | length'

# Deploy and check binding
npx wrangler deploy && curl -s https://my-api.example.workers.dev/products
```

## Related
- [React Query + Cloudflare Workers API](react-query-optimistic-mutations-cloudflare-workers.md)
- [Remix Cloudflare Workers Adapter](remix-cloudflare-workers-adapter.md)
- [Form Validation with Zod + Workers Endpoint](form-validation-zod-workers-endpoint.md)
- [Feature Flags with Cloudflare Workers KV](feature-flags-cloudflare-workers-kv-edge-config.md)

## Sources
- https://hono.dev/docs/guides/rpc
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
- https://developers.cloudflare.com/d1/
- https://github.com/honojs/middleware/tree/main/packages/zod-validator
