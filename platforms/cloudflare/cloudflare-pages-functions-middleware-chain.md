# Pages Functions Middleware Chain

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to apply cross-cutting concerns — authentication, structured logging, and rate-limiting — consistently across every route in a Cloudflare Pages Functions project without duplicating code in each `+page.ts` or `[slug].ts` file. Pages Functions `_middleware.ts` files let you build an ordered middleware chain that runs before any route handler in the same directory.

## Context

- Platform: Cloudflare Pages Functions (file-based routing)
- Bindings: D1 (user sessions), KV (rate-limit counters)
- Middleware scope: per-directory — a `functions/_middleware.ts` covers all routes; a `functions/api/_middleware.ts` covers only `/api/*`
- Pattern: `context.next()` threads the request through the chain

---

## Section 1 — Directory Structure

```
functions/
├── _middleware.ts          ← global middleware (auth → log → rate-limit)
├── index.ts               ← GET /
├── api/
│   ├── _middleware.ts     ← API-only middleware (stricter rate limits)
│   ├── products.ts        ← GET /api/products
│   └── orders.ts          ← POST /api/orders
└── admin/
    ├── _middleware.ts     ← admin-only middleware (role check)
    └── dashboard.ts       ← GET /admin/dashboard
```

---

## Section 2 — Global Middleware (`functions/_middleware.ts`)

```typescript
// functions/_middleware.ts
import type { PagesFunction, EventContext } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  RATE_LIMIT_KV: KVNamespace;
  SESSION_SECRET: string;
}

// Chain: auth → logging → rate-limit → next()
export const onRequest: PagesFunction<Env>[] = [
  authMiddleware,
  loggingMiddleware,
  rateLimitMiddleware,
];

// ── Auth ────────────────────────────────────────────────────────────────────
async function authMiddleware(
  context: EventContext<Env, string, Record<string, unknown>>
): Promise<Response> {
  const { request, env, next, data } = context;
  const url = new URL(request.url);

  // Public paths skip auth
  const publicPaths = ['/', '/login', '/signup', '/health'];
  if (publicPaths.includes(url.pathname)) {
    return next();
  }

  const sessionToken = getCookie(request, 'session');
  if (!sessionToken) {
    return new Response('Unauthorized', {
      status: 401,
      headers: { 'WWW-Authenticate': 'Bearer realm="app"' },
    });
  }

  // Validate session against D1
  const session = await env.DB
    .prepare('SELECT user_id, role, expires_at FROM sessions WHERE token = ?')
    .bind(sessionToken)
    .first<{ user_id: number; role: string; expires_at: number }>();

  if (!session || session.expires_at < Date.now()) {
    return new Response('Session expired', { status: 401 });
  }

  // Attach user to context.data for downstream handlers
  data.user = { id: session.user_id, role: session.role };
  return next();
}

// ── Logging ──────────────────────────────────────────────────────────────────
async function loggingMiddleware(
  context: EventContext<Env, string, Record<string, unknown>>
): Promise<Response> {
  const { request, next, data } = context;
  const t0 = Date.now();
  const user = data.user as { id: number } | undefined;

  const response = await next();

  const duration = Date.now() - t0;
  console.log(
    JSON.stringify({
      ts: new Date().toISOString(),
      method: request.method,
      url: request.url,
      status: response.status,
      durationMs: duration,
      userId: user?.id ?? null,
    })
  );

  // Clone to add timing header without consuming the body
  const headers = new Headers(response.headers);
  headers.set('X-Response-Time', `${duration}ms`);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

// ── Rate Limit ───────────────────────────────────────────────────────────────
async function rateLimitMiddleware(
  context: EventContext<Env, string, Record<string, unknown>>
): Promise<Response> {
  const { request, env, next } = context;
  const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
  const key = `rl:${ip}:${Math.floor(Date.now() / 60_000)}`; // per-minute window

  const raw = await env.RATE_LIMIT_KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  const LIMIT = 120; // requests per minute per IP

  if (count >= LIMIT) {
    return new Response('Too Many Requests', {
      status: 429,
      headers: {
        'Retry-After': '60',
        'X-RateLimit-Limit': String(LIMIT),
        'X-RateLimit-Remaining': '0',
      },
    });
  }

  // Increment with TTL slightly longer than 1 minute
  await env.RATE_LIMIT_KV.put(key, String(count + 1), { expirationTtl: 90 });

  const response = await next();

  const headers = new Headers(response.headers);
  headers.set('X-RateLimit-Limit', String(LIMIT));
  headers.set('X-RateLimit-Remaining', String(Math.max(0, LIMIT - count - 1)));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function getCookie(request: Request, name: string): string | null {
  const cookie = request.headers.get('cookie') ?? '';
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`) );
  return match ? decodeURIComponent(match[1]) : null;
}
```

---

## Section 3 — API-Specific Middleware (`functions/api/_middleware.ts`)

```typescript
// functions/api/_middleware.ts
// Stricter rate limit for API routes; auth already handled by global middleware.
import type { PagesFunction, EventContext } from '@cloudflare/workers-types';
import type { Env } from '../_middleware';

export const onRequest: PagesFunction<Env>[] = [apiRateLimitMiddleware];

async function apiRateLimitMiddleware(
  context: EventContext<Env, string, Record<string, unknown>>
): Promise<Response> {
  const { request, env, next } = context;
  const user = context.data.user as { id: number } | undefined;

  // Authenticated API calls: per-user limit; unauthenticated: per-IP
  const subject = user ? `uid:${user.id}` : `ip:${request.headers.get('cf-connecting-ip')}`;
  const key = `api-rl:${subject}:${Math.floor(Date.now() / 60_000)}`;
  const API_LIMIT = 30;

  const raw = await env.RATE_LIMIT_KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= API_LIMIT) {
    return new Response(
      JSON.stringify({ error: 'rate_limit_exceeded' }),
      {
        status: 429,
        headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
      }
    );
  }

  await env.RATE_LIMIT_KV.put(key, String(count + 1), { expirationTtl: 90 });
  return next();
}
```

---

## Section 4 — Admin Role-Check Middleware (`functions/admin/_middleware.ts`)

```typescript
// functions/admin/_middleware.ts
import type { PagesFunction, EventContext } from '@cloudflare/workers-types';
import type { Env } from '../_middleware';

export const onRequest: PagesFunction<Env>[] = [
  async (context: EventContext<Env, string, Record<string, unknown>>) => {
    const user = context.data.user as { id: number; role: string } | undefined;

    if (!user) {
      // Global auth middleware should have caught this, but guard anyway
      return new Response('Unauthorized', { status: 401 });
    }

    if (user.role !== 'admin') {
      return new Response('Forbidden', { status: 403 });
    }

    return context.next();
  },
];
```

---

## Section 5 — Route Handler Using `context.data`

```typescript
// functions/api/products.ts
import type { PagesFunction, EventContext } from '@cloudflare/workers-types';
import type { Env } from '../_middleware';

export const onRequestGet: PagesFunction<Env> = async (
  context: EventContext<Env, string, Record<string, unknown>>
) => {
  const { env, data } = context;
  const user = data.user as { id: number; role: string };

  const { results } = await env.DB
    .prepare('SELECT id, name, price FROM products ORDER BY id DESC LIMIT 20')
    .all();

  return new Response(
    JSON.stringify({ products: results, requestedBy: user.id }),
    { headers: { 'Content-Type': 'application/json' } }
  );
};
```

---

## Section 6 — wrangler.toml / Pages Bindings

```toml
# wrangler.toml (or configure in Pages dashboard)
name = "my-pages-app"
pages_build_output_dir = "dist"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

---

## Anti-patterns

- Exporting a single function instead of an array from `_middleware.ts` — when chaining multiple middleware, export an array: `export const onRequest = [fn1, fn2, fn3]`.
- Calling `next()` more than once in a middleware — this sends duplicate requests downstream; call `next()` exactly once per execution path.
- Mutating `context.data` after `await next()` — downstream middleware has already read it; set data before calling `next()`.
- Using `_middleware.ts` for route-specific logic — middleware applies to ALL routes in the directory; use the route handler for route-specific behavior.
- Not cloning the response before adding headers — `response.headers` is immutable if you got it from `next()`; create a `new Response(response.body, ...)` copy.

## Gotchas

- Middleware arrays run in order; the first middleware to return a `Response` without calling `next()` short-circuits the chain.
- A `_middleware.ts` file at a parent directory level runs *before* a `_middleware.ts` in a child directory — execution is global first, then specific.
- `context.data` is typed as `Record<string, unknown>` by default; add a type assertion or augment the type for type-safe access.
- Pages Functions have a 50ms CPU time limit per invocation (Bundled plan); middleware that performs D1 queries adds to this budget.
- During `wrangler pages dev`, D1 and KV bindings require `--d1` and `--kv` flags or a `wrangler.toml` present in the project root.

## Verification

```bash
# Local development
wrangler pages dev dist --d1=DB=prod-db --kv=RATE_LIMIT_KV

# Test auth guard (no cookie → 401)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8788/api/products

# Test with a valid session cookie
curl -s -b "session=valid-token-here" http://localhost:8788/api/products | jq .

# Test rate limit (fire > 30 requests in a minute)
for i in $(seq 1 35); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -b "session=valid-token-here" http://localhost:8788/api/products
done

# Deploy to Pages
wrangler pages deploy dist

# Verify logging in tail
wrangler pages deployment tail
```

## Related

- `documentation/categories/cloudflare/workers-mutual-tls-client-certificate-auth.md`
- `documentation/categories/cloudflare/workers-smart-placement-auto-performance.md`
- `documentation/categories/cloudflare/cloudflare-zaraz-custom-event-workers-backend.md`
- `documentation/categories/cloudflare/workers-d1-alarms-scheduled-mutations.md`

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/functions/bindings/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
