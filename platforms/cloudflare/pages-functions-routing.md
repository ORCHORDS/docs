# pages-functions-routing

**Issue:** Cloudflare Pages Functions file-based routing — path params, catch-all, method dispatch
**Date:** 2026-08-11
**Status:** documented

## File → URL mapping

Pages Functions maps files under `functions/` to URL paths:

| File path | Matches URL |
|-----------|-------------|
| `functions/api/users.ts` | `/api/users` |
| `functions/api/users/[id].ts` | `/api/users/:id` |
| `functions/api/users/[[path]].ts` | `/api/users/*` (catch-all) |
| `functions/api/v1/index.ts` | `/api/v1/` (note trailing slash) |

## Exported handler signatures

```typescript
// PagesContext type
import type { PagesContext } from '@cloudflare/workers-types';

// Named export per HTTP method (preferred — prevents accidental wrong-method access):
export const onRequestGet: PagesFunction<Env> = async (context) => { ... };
export const onRequestPost: PagesFunction<Env> = async (context) => { ... };
export const onRequestDelete: PagesFunction<Env> = async (context) => { ... };
export const onRequestPatch: PagesFunction<Env> = async (context) => { ... };

// Single catch-all export (manual dispatch):
export const onRequest: PagesFunction<Env> = async (context) => {
  const { request } = context;
  switch (request.method) {
    case 'GET': return handleGet(request, context.env);
    case 'POST': return handlePost(request, context.env);
    default: return new Response('Method Not Allowed', { status: 405 });
  }
};
```

## Reading path params

```typescript
// File: functions/api/users/[id].ts
export const onRequestGet: PagesFunction<Env> = async (context) => {
  const id = context.params.id as string;
  // context.params is typed as Record<string, string | string[]>
  // For [id].ts → string; for [[path]].ts → string[]
  ...
};

// File: functions/api/mc/engine/[[path]].ts — catch-all
export const onRequestGet: PagesFunction<Env> = async (context) => {
  const segments = context.params.path as string[];
  // /api/mc/engine/partners/abc → ['partners', 'abc']
  const [resource, id] = segments;
  ...
};
```

## Reading request info — NO request_id on context

`PagesContext` does NOT have a `request_id` field. For tracing, use `cf-ray` header:

```typescript
const requestId = context.request.headers.get('cf-ray') ?? crypto.randomUUID();
```

Do NOT use `context.request_id` — it doesn't exist. TypeScript may not catch this
if you haven't imported PagesFunction types strictly.

## env binding access

```typescript
// context.env is typed as Env (your interface):
const db = context.env.DB;  // D1Database | undefined
const kv = context.env.RATE_LIMIT;  // KVNamespace | undefined

// Pass to handlers that expect Env:
return handleGet(context.request, context.env);
```

## Middleware pattern (onRequest + next())

```typescript
// functions/api/_middleware.ts — applies to all /api/* routes
export const onRequest: PagesFunction<Env> = async (context) => {
  // Log every request
  const start = Date.now();
  const response = await context.next();
  const duration = Date.now() - start;
  console.log(`${context.request.method} ${new URL(context.request.url).pathname} ${response.status} ${duration}ms`);
  return response;
};
```

Place `_middleware.ts` files to apply to a subtree. They chain via `context.next()`.

## CORS headers

```typescript
// functions/api/_middleware.ts
export const onRequest: PagesFunction<Env> = async (context) => {
  if (context.request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'access-control-allow-origin': '*',
        'access-control-allow-methods': 'GET, POST, PATCH, DELETE, OPTIONS',
        'access-control-allow-headers': 'content-type, authorization',
        'access-control-max-age': '86400',
      },
    });
  }
  const response = await context.next();
  response.headers.set('access-control-allow-origin', '*');
  return response;
};
```

## 404 for unknown subpaths (catch-all dispatch)

```typescript
// functions/api/mc/engine/[[path]].ts
export const onRequest: PagesFunction<Env> = async (context) => {
  const segments = (context.params.path as string[]) ?? [];
  const [resource, id, sub] = segments;

  if (resource === 'controls') return handleControls(context.request, context.env, id, sub);
  if (resource === 'vendors') return handleVendors(context.request, context.env, id, sub);

  return new Response(JSON.stringify({ error: 'not_found' }), {
    status: 404,
    headers: { 'content-type': 'application/json' },
  });
};
```

## Gotchas

- **`context.request_id` does NOT exist**: Use `cf-ray` header or generate a UUID. This catches many "TS thinks it's fine" bugs because the type is `any` in loose tsconfig.
- **Index files and trailing slashes**: `functions/api/v1/index.ts` serves `/api/v1/` (trailing slash). Without trailing slash, it 404s unless you add a redirect.
- **Catch-all vs named param priority**: A named param `[id].ts` takes priority over a catch-all `[[path]].ts` at the same level. Named params are more specific.
- **Method exports vs `onRequest`**: Named method exports (`onRequestGet`) auto-return 405 for other methods. `onRequest` does NOT — you must handle 405 manually.
- **No `context.next()` in leaf handlers**: `context.next()` is only meaningful in middleware (`_middleware.ts`). Calling it in a leaf handler with no deeper route returns a 404 from Pages.
- **`env` is typed as `Env` only if you declare it**: `PagesFunction<Env>` generic parameter sets the type. Without it, `context.env` is `unknown`.

## Related

- `pages-functions-env-types.md`
- `typescript-route-handler.md`
- `workers-types-migration.md`
- `mccontext-gate-pattern.md`
