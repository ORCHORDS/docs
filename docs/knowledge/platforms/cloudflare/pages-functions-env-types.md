# pages-functions-env-types

**Issue:** Incompatible Env interfaces across Pages Functions files — assignment errors when passing env
**Date:** 2026-08-11
**Status:** documented

## Symptom

```
error TS2345: Argument of type 'import("functions/_lib/types").Env' is not assignable
to parameter of type 'import("functions/_lib/auth").Env'.
  Types of property 'DB' are incompatible.
    Type '{ prepare: (q: string) => ... }' is not assignable to type 'D1Database | undefined'.
```

Happens when:
- A routing file (`[[path]].ts`) imports `PagesContext` from `_lib/types.ts`
- The handler it calls imports `Env` from `_lib/auth.ts`
- Both files define their own `Env` interface with different `DB` types

## Root cause

Large Pages Functions repos often start with a lightweight `types.ts` that defines a simple `Env`
with hand-written DB types. Over time, `auth.ts` grows a richer `Env` using `D1Database`, `KVNamespace`,
`DurableObjectNamespace`, `R2Bucket` (from `@cloudflare/workers-types`).

When a routing file does `const { env } = context` (where context is `PagesContext<types.Env>`),
and passes `env` to `handlerFn(request, env)` that expects `auth.Env`, TypeScript errors because
`types.Env.DB` is not structurally assignable to `auth.Env.DB` (`D1Database` has many more methods
than any hand-rolled interface).

## Fix

### Option A: Consolidate to one Env (preferred)

Delete `types.Env`, re-export from auth.ts:

```typescript
// _lib/types.ts
export type { Env } from './_lib/auth';  // or use relative path
export interface PagesContext<E = Env> {
  request: Request;
  env: E;
}
```

### Option B: Update types.Env to use strict globals

After adding `@cloudflare/workers-types` to tsconfig `types`, these are global:

```typescript
// _lib/types.ts
export interface Env {
  TURNSTILE_SECRET?: string;
  RESEND_API_KEY?: string;
  // Use strict global types — no import needed:
  DB?: D1Database;
  RATE_LIMIT?: KVNamespace;
  // Other fields as before
}
```

`D1Database` and `KVNamespace` are now structural supersets of the old hand-written types,
so `types.Env` becomes assignable to `auth.Env` for the relevant fields.

### Option C: Type cast in routing files (last resort)

```typescript
// [[path]].ts
export const onRequest = async (context: PagesContext): Promise<Response> => {
  return handler(context.request, context.env as import('../../../_lib/auth').Env);
};
```

## PagesContext design

```typescript
// _lib/types.ts
export interface PagesContext<E = Env> {
  request: Request;
  env: E;
  // Note: Cloudflare Pages Functions also pass params, waitUntil, next, data
  // Add if you need them; keep minimal to avoid locking to CF's internal types
}
```

## Typical routing file pattern

```typescript
// [[path]].ts
import type { PagesContext } from '../../../_lib/types';
import { handler1, handler2 } from './_handlers';
import { jsonError, authenticate, type Env } from '../../../_lib/auth';

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env } = context;
  // env is typed as Env from auth.ts — no incompatibility
  // ...
};
```

Using `PagesFunction<Env>` from `@cloudflare/workers-types` directly (instead of custom PagesContext)
is the most robust approach for routes that need the full Cloudflare context.

## Gotchas

- **`PagesContext.request_id`** doesn't exist. `PagesContext` only has `request` and `env`. If you write `context.request_id` in a Pages Function handler, you'll get "does not exist on type 'PagesContext'". Use `context.request.headers.get('cf-ray') ?? undefined` as a fallback.
- **Two Env definitions = two types**: TypeScript uses structural compatibility, not nominal. Even if the shapes are "compatible" at runtime, TS sees them as distinct types unless they actually match field-for-field.
- **`SEND_EMAIL` type**: Cloudflare's MailChannels binding has a specific type. Use `EmailMessage` from workers-types or leave it as `{ send: (m: unknown) => Promise<void> }`.

## Related

- `workers-types-migration.md`
- `pages-best-practices.md`
- `pages-functions-exact-match-routing.md`
- `mccontext-gate-pattern.md`
