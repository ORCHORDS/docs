# Cloudflare Pages + D1: Full-Stack SPA/SSR Deployment Pattern

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You want to deploy a full-stack web application — a React SPA or Next.js/SvelteKit/Astro
SSR site with a real database backend — entirely on Cloudflare, with zero servers or
containers. The frontend is served from Pages, the API and SSR logic run as Pages
Functions, and D1 provides the SQLite database accessible from the edge. You want a
single `wrangler pages deploy` to ship the entire stack.

## Context

Cloudflare Pages supports **Pages Functions** — Workers-based code co-located with your
static assets in a `functions/` directory. When you bind a D1 database to your Pages
project, every Function and SSR route can query it directly via the `D1Database` API
without a separate API server.

The architecture:
- **Static assets** (HTML, CSS, JS bundles) — served from Pages' CDN edge
- **`functions/api/[[path]].ts`** — a catch-all API route (Workers runtime)
- **`functions/_middleware.ts`** — authentication, CORS, rate-limiting middleware
- **D1 binding** — `DB` environment variable available inside all Functions
- **KV binding** (optional) — session storage or feature flags
- **R2 binding** (optional) — file uploads

This pattern suits: SaaS dashboards, content management tools, internal admin panels,
and any app where you want Cloudflare to be both CDN and application runtime.

## Project Structure

```
my-app/
├── public/               # Static assets (Vite build output → dist/)
│   └── _redirects        # SPA fallback
├── functions/
│   ├── _middleware.ts    # Global middleware (auth, CORS)
│   └── api/
│       └── [[path]].ts   # REST API catch-all
├── src/                  # React/Svelte frontend source
├── schema.sql            # D1 schema
├── migrations/           # D1 migration files
│   └── 0001_init.sql
├── wrangler.toml
└── package.json
```

## wrangler.toml

```toml
name               = "my-app"
compatibility_date = "2025-09-01"
pages_build_output_dir = "dist"

[[d1_databases]]
binding      = "DB"
database_name = "my-app-prod"
database_id  = "<your-d1-database-id>"

[[kv_namespaces]]
binding = "SESSIONS"
id      = "<your-kv-namespace-id>"

[[r2_buckets]]
binding    = "UPLOADS"
bucket_name = "my-app-uploads"

[vars]
APP_ENV = "production"

# Secrets via: wrangler pages secret put JWT_SECRET
```

## Database Schema and Migrations

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS users (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  email      TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL DEFAULT '',
  published  INTEGER NOT NULL DEFAULT 0,  -- SQLite bool
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_user_id  ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published, created_at DESC);
```

```bash
# Apply migration to local dev DB
wrangler d1 migrations apply my-app-prod --local

# Apply to production
wrangler d1 migrations apply my-app-prod
```

## Global Middleware

```typescript
// functions/_middleware.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  SESSIONS: KVNamespace;
  JWT_SECRET: string;
}

async function verifySession(
  sessionToken: string,
  env: Env
): Promise<{ userId: string; email: string } | null> {
  if (!sessionToken) return null;
  const data = await env.SESSIONS.get(`session:${sessionToken}`, 'json') as
    { userId: string; email: string } | null;
  return data;
}

export const onRequest: PagesFunction<Env>[] = [
  // CORS middleware
  async (ctx) => {
    const origin = ctx.request.headers.get('Origin');
    const allowedOrigins = ['https://my-app.com', 'https://staging.my-app.com'];
    const corsHeaders: Record<string, string> = {
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    if (origin && allowedOrigins.includes(origin)) {
      corsHeaders['Access-Control-Allow-Origin'] = origin;
    }

    if (ctx.request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    const response = await ctx.next();
    const newResp = new Response(response.body, response);
    for (const [k, v] of Object.entries(corsHeaders)) {
      newResp.headers.set(k, v);
    }
    return newResp;
  },

  // Auth middleware (runs for /api/* routes only)
  async (ctx) => {
    const url = new URL(ctx.request.url);
    const publicRoutes = ['/api/auth/login', '/api/auth/register', '/api/health'];

    if (!url.pathname.startsWith('/api/') || publicRoutes.includes(url.pathname)) {
      return ctx.next();
    }

    const token = ctx.request.headers.get('Authorization')?.replace('Bearer ', '');
    const session = token ? await verifySession(token, ctx.env as unknown as Env) : null;

    if (!session) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Inject user context into request (via custom header for the handler)
    const authedRequest = new Request(ctx.request, {
      headers: new Headers({
        ...Object.fromEntries(ctx.request.headers.entries()),
        'x-user-id': session.userId,
        'x-user-email': session.email,
      }),
    });
    ctx.request = authedRequest;

    return ctx.next();
  },
];
```

## API Catch-all Handler

```typescript
// functions/api/[[path]].ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  SESSIONS: KVNamespace;
  UPLOADS: R2Bucket;
  JWT_SECRET: string;
}

type RouteHandler = (
  request: Request,
  env: Env,
  params: Record<string, string>
) => Promise<Response>;

// Simple router
function makeRouter() {
  const routes: Array<{ method: string; pattern: URLPattern; handler: RouteHandler }> = [];

  function add(method: string, path: string, handler: RouteHandler) {
    routes.push({ method, pattern: new URLPattern({ pathname: path }), handler });
  }

  function match(request: Request) {
    const url = new URL(request.url);
    for (const route of routes) {
      if (route.method !== request.method && route.method !== '*') continue;
      const result = route.pattern.exec({ pathname: url.pathname });
      if (result) {
        return { handler: route.handler, params: result.pathname.groups as Record<string, string> };
      }
    }
    return null;
  }

  return { add, match };
}

const router = makeRouter();

// GET /api/health
router.add('GET', '/api/health', async (_req, env) => {
  const result = await env.DB.prepare('SELECT 1 AS ok').first<{ ok: number }>();
  return Response.json({ status: 'ok', db: result?.ok === 1 });
});

// GET /api/posts
router.add('GET', '/api/posts', async (request, env) => {
  const userId = request.headers.get('x-user-id')!;
  const url = new URL(request.url);
  const page  = parseInt(url.searchParams.get('page')  ?? '1', 10);
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20', 10), 100);
  const offset = (page - 1) * limit;

  const [rows, total] = await Promise.all([
    env.DB.prepare(
      'SELECT id, title, published, created_at FROM posts WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?'
    ).bind(userId, limit, offset).all<{ id: string; title: string; published: number; created_at: string }>(),
    env.DB.prepare('SELECT COUNT(*) as n FROM posts WHERE user_id = ?')
      .bind(userId).first<{ n: number }>(),
  ]);

  return Response.json({
    posts: rows.results,
    pagination: { page, limit, total: total?.n ?? 0 },
  });
});

// POST /api/posts
router.add('POST', '/api/posts', async (request, env) => {
  const userId = request.headers.get('x-user-id')!;
  const body = await request.json<{ title: string; body?: string }>();

  if (!body.title?.trim()) {
    return Response.json({ error: 'title is required' }, { status: 422 });
  }

  const id = crypto.randomUUID();
  await env.DB.prepare(
    'INSERT INTO posts (id, user_id, title, body) VALUES (?, ?, ?, ?)'
  ).bind(id, userId, body.title.trim(), body.body ?? '').run();

  return Response.json({ id }, { status: 201 });
});

// DELETE /api/posts/:id
router.add('DELETE', '/api/posts/:id', async (request, env, params) => {
  const userId = request.headers.get('x-user-id')!;
  const result = await env.DB.prepare(
    'DELETE FROM posts WHERE id = ? AND user_id = ?'
  ).bind(params['id'], userId).run();

  if (!result.meta.changes) return Response.json({ error: 'Not found' }, { status: 404 });
  return Response.json({ deleted: true });
});

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const match = router.match(ctx.request);
  if (!match) return Response.json({ error: 'Not found' }, { status: 404 });

  try {
    return await match.handler(ctx.request, ctx.env as unknown as Env, match.params);
  } catch (err) {
    console.error('API error:', err);
    return Response.json({ error: 'Internal server error' }, { status: 500 });
  }
};
```

## SPA Fallback for Client-Side Routing

```
# public/_redirects
/api/*   /api/:splat   200
/*       /index.html   200
```

This tells Pages to serve `index.html` for any non-asset, non-API path, enabling
React Router or Vue Router to handle client-side navigation.

## Local Development

```bash
# Start local dev server with D1, KV, R2 bindings
wrangler pages dev dist/ --d1 DB=my-app-prod --kv SESSIONS --r2 UPLOADS

# Or run vite dev server alongside wrangler
npx vite &
wrangler pages dev --proxy 5173

# Run migrations against local SQLite
wrangler d1 migrations apply my-app-prod --local
```

## Anti-patterns

- **Putting business logic in `_middleware.ts` that runs on every static asset request** —
  Pages middleware runs for both static assets and Functions. Guard with
  `if (!url.pathname.startsWith('/api/')) return ctx.next()` to avoid unnecessary
  D1 queries for `.js` and `.css` files.
- **Using D1 without prepared statements** — Never interpolate user input into SQL
  strings. Always use `.prepare().bind()`.
- **Relying on Pages Functions for heavy CPU work** — Functions share the Workers CPU
  limit (10 ms CPU / 30 s wall-clock per request for paid tier, 10 ms for free tier).
  Offload image resizing or PDF generation to a separate Worker with CPU time purchased.
- **Storing JWTs in `localStorage`** — Use `HttpOnly` cookies for session tokens.
  Pages Functions can set `Set-Cookie` headers; the `SESSIONS` KV stores the server-side
  session data.

## Gotchas

- **`functions/` directory is scanned at build time** — Files must be valid TypeScript/
  JavaScript. A syntax error in any `functions/` file prevents the entire Pages
  deployment from succeeding.
- **D1 binding is not available during `vite build`** — It is only available at runtime
  inside the Workers environment. Avoid importing D1 types at module level outside of
  function bodies, or use `@cloudflare/workers-types` for type-only imports.
- **Pages Functions have a 1 MB script size limit** — If your API logic grows large,
  split into multiple files or use service bindings to delegate to a separate Worker.
- **`URLPattern` is available in Workers but not in Node.js** — If you use Node.js
  locally for unit tests, polyfill `URLPattern` or abstract the routing logic.
- **D1 `RETURNING` clause requires `compatibility_date >= 2023-03-14`** — Ensure your
  `wrangler.toml` has a current enough `compatibility_date`.

## Verification

```bash
# Deploy to production
npm run build    # vite build → dist/
wrangler pages deploy dist/ --project-name my-app

# Run smoke tests
curl https://my-app.pages.dev/api/health
# Expected: {"status":"ok","db":1}

# Test auth rejection
curl -X GET https://my-app.pages.dev/api/posts
# Expected: {"error":"Unauthorized"}  HTTP 401

# Test full flow (requires a real session token)
TOKEN=$(curl -s -X POST https://my-app.pages.dev/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"secret"}' | jq -r .token)

curl -H "Authorization: Bearer $TOKEN" https://my-app.pages.dev/api/posts
```

## Related

- `d1-best-practices.md` — D1 query patterns and indexing
- `d1-migration-best-practices.md` — schema evolution with D1
- `pages-functions-middleware.md` — middleware chaining patterns
- `pages-functions-routing.md` — routing conventions in Pages Functions
- `pages-best-practices.md` — caching, headers, and build configuration
- `kv-best-practices.md` — session storage in KV

## Sources

- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- D1 + Pages binding: https://developers.cloudflare.com/pages/functions/bindings/
- Pages Functions routing: https://developers.cloudflare.com/pages/functions/routing/
- D1 TypeScript guide: https://developers.cloudflare.com/d1/worker-api/
- Wrangler Pages CLI: https://developers.cloudflare.com/workers/wrangler/commands/#pages
