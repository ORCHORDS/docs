# pages-functions-middleware

**Issue:** Writing middleware in Pages Functions using `_middleware.ts` files
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pages Functions support middleware via `_middleware.ts` files placed in the `functions/` directory. Middleware intercepts all requests at its directory level and calls `ctx.next()` to pass to the next handler.

## Pattern / Solution

```typescript
// functions/_middleware.ts — applies to ALL routes
export async function onRequest(ctx: EventContext<Env, string, Record<string, unknown>>) {
  const start = Date.now();

  // Pre-processing — runs before the route handler
  const requestId = crypto.randomUUID();
  ctx.data.requestId = requestId;

  // Call next handler (route function or static file)
  const response = await ctx.next();

  // Post-processing — modify the response
  const duration = Date.now() - start;
  const modified = new Response(response.body, response);
  modified.headers.set('X-Request-Id', requestId);
  modified.headers.set('X-Response-Time', `${duration}ms`);

  return modified;
}
```

```typescript
// functions/api/_middleware.ts — applies only to /api/* routes
import { verifyJWT } from '../_utils/auth';

export async function onRequest(ctx: EventContext<Env, string, Record<string, unknown>>) {
  const token = ctx.request.headers.get('Authorization')?.replace('Bearer ', '');

  if (!token) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    ctx.data.user = await verifyJWT(token, ctx.env.JWT_SECRET);
  } catch {
    return Response.json({ error: 'Invalid token' }, { status: 403 });
  }

  // Return early without ctx.next() to short-circuit — or call ctx.next() to continue
  return ctx.next();
}
```

```
functions/
├── _middleware.ts          ← runs for all routes
├── api/
│   ├── _middleware.ts      ← runs for /api/* only (after root middleware)
│   ├── users.ts            ← /api/users
│   └── [[route]].ts        ← catch-all /api/*
└── index.ts                ← /
```

**Chaining middleware (multiple `_middleware.ts` at different levels):**
Middleware runs from the outermost directory inward. Root `_middleware.ts` runs first, then `api/_middleware.ts`, then the route handler.

## Gotchas
- Calling `ctx.next()` is optional — return a `Response` directly to short-circuit the chain.
- `ctx.data` is a plain object; type it carefully to avoid runtime errors in downstream handlers.
- `_middleware.ts` applies to **all** HTTP methods at its level — add method checks manually.
- Middleware does **not** run for files served directly from the static asset directory.
- There can be only **one** `_middleware.ts` per directory level.
- Errors thrown in middleware propagate up; wrap in try/catch and return appropriate error responses.

## Related
- `pages-functions-routing.md`
- `pages-functions-env-types.md`
- `cors-pages-functions.md`
