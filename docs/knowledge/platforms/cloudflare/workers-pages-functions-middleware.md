# Building Middleware Chains in Cloudflare Pages Functions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Pages project has grown beyond simple static files. You now need cross-cutting concerns — authentication checks, request logging, error boundaries, and CORS headers — applied consistently across multiple API routes under `functions/api/`. Duplicating this logic in every function file is error-prone. You want a middleware chain, similar to Express's `app.use()`, but implemented using Pages Functions' native `_middleware.ts` convention.

## Context

Cloudflare Pages Functions supports a special file naming convention: any file named `_middleware.ts` (or `_middleware.js`) in a `functions/` directory applies to all requests matched by that directory and its subdirectories. Middleware functions receive a `context` object and a `next()` function; calling `next()` passes control to the next middleware or the final route handler.

Directory layout:

```
functions/
  _middleware.ts          <- applies to ALL routes
  api/
    _middleware.ts        <- applies to /api/* routes only
    users/
      [id].ts             <- handles GET /api/users/:id
    orders.ts             <- handles GET/POST /api/orders
```

Middleware can short-circuit the chain by returning a `Response` directly without calling `next()`. It can also modify the request, enrich `context.data`, or wrap the response.

## Solution

```typescript
// functions/_middleware.ts
// Top-level middleware: CORS headers + global error boundary

import type { EventContext } from '@cloudflare/workers-types';

interface AppData {
  requestId: string;
  startTime: number;
  userId?: string;
}

export type AppContext = EventContext<Env, string, AppData>;

export interface Env {
  AUTH_SECRET: string;
  DB: D1Database;
  KV: KVNamespace;
}

export const onRequest: PagesFunction<Env, string, AppData>[] = [
  corsMiddleware,
  errorBoundaryMiddleware,
  requestIdMiddleware,
];

async function corsMiddleware(
  context: AppContext,
): Promise<Response> {
  // Handle preflight
  if (context.request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: corsHeaders(context.request),
    });
  }

  const response = await context.next();

  // Clone response and inject CORS headers.
  // Headers are immutable on a frozen Response, so we must clone.
  const newHeaders = new Headers(response.headers);
  for (const [key, value] of Object.entries(corsHeaders(context.request))) {
    newHeaders.set(key, value);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders,
  });
}

function corsHeaders(request: Request): Record<string, string> {
  const origin = request.headers.get('Origin') ?? '*';
  const allowedOrigins = ['https://example.com', 'https://staging.example.com'];
  const allowedOrigin = allowedOrigins.includes(origin) ? origin : allowedOrigins[0];

  return {
    'Access-Control-Allow-Origin': allowedOrigin,
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

async function errorBoundaryMiddleware(
  context: AppContext,
): Promise<Response> {
  try {
    return await context.next();
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Internal server error';
    const requestId = context.data.requestId ?? 'unknown';

    console.error(`[${requestId}] Unhandled error:`, err);

    return Response.json(
      { error: 'internal_error', message, requestId },
      { status: 500 },
    );
  }
}

async function requestIdMiddleware(
  context: AppContext,
): Promise<Response> {
  // Propagate an incoming request ID from a gateway, or generate one.
  const requestId =
    context.request.headers.get('X-Request-ID') ??
    crypto.randomUUID();

  context.data.requestId = requestId;
  context.data.startTime = Date.now();

  const response = await context.next();

  const newHeaders = new Headers(response.headers);
  newHeaders.set('X-Request-ID', requestId);
  newHeaders.set('X-Response-Time', `${Date.now() - context.data.startTime}ms`);

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders,
  });
}
```

```typescript
// functions/api/_middleware.ts
// API-scoped middleware: authentication + structured logging

import type { AppContext, Env } from '../_middleware';

export const onRequest: PagesFunction<Env, string>[] = [
  authMiddleware,
  loggingMiddleware,
];

async function authMiddleware(context: AppContext): Promise<Response> {
  const authHeader = context.request.headers.get('Authorization');

  if (!authHeader?.startsWith('Bearer ')) {
    return Response.json(
      { error: 'unauthorized', message: 'Bearer token required.' },
      { status: 401 },
    );
  }

  const token = authHeader.slice(7);

  // Validate token — replace with your real JWT verification logic.
  const userId = await validateToken(token, context.env.AUTH_SECRET);

  if (!userId) {
    return Response.json(
      { error: 'forbidden', message: 'Invalid or expired token.' },
      { status: 403 },
    );
  }

  // Pass userId downstream via context.data.
  context.data.userId = userId;

  return context.next();
}

async function validateToken(
  token: string,
  secret: string,
): Promise<string | null> {
  try {
    const [headerB64, payloadB64, signatureB64] = token.split('.');
    if (!headerB64 || !payloadB64 || !signatureB64) return null;

    const payload = JSON.parse(atob(payloadB64)) as {
      sub: string;
      exp: number;
    };

    if (payload.exp < Math.floor(Date.now() / 1000)) return null;

    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify'],
    );

    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const signature = Uint8Array.from(atob(signatureB64), (c) => c.charCodeAt(0));
    const valid = await crypto.subtle.verify('HMAC', key, signature, data);

    return valid ? payload.sub : null;
  } catch {
    return null;
  }
}

async function loggingMiddleware(context: AppContext): Promise<Response> {
  const { method } = context.request;
  const path = new URL(context.request.url).pathname;
  const userId = context.data.userId ?? 'anonymous';
  const requestId = context.data.requestId;

  console.log(
    JSON.stringify({
      type: 'request',
      requestId,
      userId,
      method,
      path,
      timestamp: new Date().toISOString(),
    }),
  );

  const response = await context.next();

  console.log(
    JSON.stringify({
      type: 'response',
      requestId,
      status: response.status,
      durationMs: Date.now() - context.data.startTime,
    }),
  );

  return response;
}
```

```typescript
// functions/api/users/[id].ts
// Route handler — receives enriched context.data from middleware.

import type { AppContext, Env } from '../../_middleware';

export const onRequestGet: PagesFunction<Env, 'id'> = async (
  context,
) => {
  const appCtx = context as unknown as AppContext;
  const { userId } = appCtx.data; // Set by authMiddleware
  const targetId = context.params.id;

  // Only allow users to fetch their own data (or admins).
  if (userId !== targetId) {
    return Response.json({ error: 'forbidden' }, { status: 403 });
  }

  const user = await context.env.DB
    .prepare('SELECT id, name, email FROM users WHERE id = ?')
    .bind(targetId)
    .first();

  if (!user) {
    return Response.json({ error: 'not_found' }, { status: 404 });
  }

  return Response.json({ user });
};
```

## Implementation Details

**Execution order:**

Middleware executes from the outermost directory inward, then route handler, then back outward:

```
Request ->
  functions/_middleware.ts (corsMiddleware)
  functions/_middleware.ts (errorBoundaryMiddleware)
  functions/_middleware.ts (requestIdMiddleware)
  functions/api/_middleware.ts (authMiddleware)
  functions/api/_middleware.ts (loggingMiddleware)
  functions/api/users/[id].ts (handler)
<- Response
```

**Array vs single export:**

```typescript
// Single middleware function:
export const onRequest: PagesFunction = myMiddleware;

// Chained array (executed left-to-right):
export const onRequest: PagesFunction[] = [middlewareA, middlewareB];
```

**Passing state between layers via `context.data`:**

`context.data` is a plain object scoped to a single request lifecycle. Each middleware layer can read and write properties on it. TypeScript generic typing (`EventContext<Env, string, AppData>`) lets you define the shape.

## Anti-patterns

- **Calling `context.next()` after returning a Response.** Once you `return response`, the chain is unwound. Calling `next()` again after that causes double-invocation of downstream handlers.
- **Mutating `context.request` directly.** `Request` is immutable. To modify request headers or body, construct a new `Request` and pass it to `context.next(request)`.
- **Putting all middleware in a single file.** Separate concerns: CORS at the top level, auth at the API level, resource-specific logic in route-level middleware.
- **Forgetting the error boundary.** Without an outer try/catch middleware, an unhandled exception in a route handler returns a generic 500 with no request ID, making debugging very hard.

## Gotchas

- **`_middleware.ts` is not a route.** Accessing `/_middleware` directly returns 404 — it is never exposed as an HTTP endpoint.
- **`next()` is called once per middleware.** If you call `context.next()` multiple times, the second call returns the same cached response (it does not re-execute the handler).
- **TypeScript path aliases.** Pages Functions bundling runs through esbuild. If you use path aliases in `tsconfig.json`, you must configure them in a `_worker.js` build step or via a build tool. Direct `functions/` TypeScript is compiled by Cloudflare's built-in step with no alias support.
- **`context.data` is not serialisable.** You can store any JavaScript value, including class instances and Promises. However, it is not persisted across requests or available after the response is sent.
- **`waitUntil` in middleware.** Use `context.waitUntil(promise)` for fire-and-forget background tasks (logging to an external service). Do not await these inside the middleware function or they will block the response.

## Verification

```bash
# Start local dev server
npx wrangler pages dev ./public --compatibility-date=2025-08-01

# Test CORS preflight
curl -X OPTIONS http://localhost:8788/api/users/123 \
  -H 'Origin: https://example.com' \
  -H 'Access-Control-Request-Method: GET' -v
# Expect: 204 with Access-Control-Allow-Origin header

# Test auth rejection
curl http://localhost:8788/api/users/123
# Expect: 401 {"error": "unauthorized"}

# Test with valid token
curl http://localhost:8788/api/users/123 \
  -H 'Authorization: Bearer <valid-token>'
# Expect: 200 with user data and X-Request-ID / X-Response-Time headers

# Test error boundary
# Temporarily throw in your route handler, then:
curl http://localhost:8788/api/users/trigger-error
# Expect: 500 {"error": "internal_error", "requestId": "..."}
```

## Related

- `workers-pages-d1-integration.md` — using D1 inside Pages Functions
- `workers-jwt-authentication.md` — full JWT validation with `jose`
- `workers-turnstile-captcha-integration.md` — adding Turnstile verification as middleware

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/functions/api-reference/
