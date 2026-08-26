# Ambient Context Pattern for Workers Request Scope

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Every function in a Worker's call stack needs access to the same per-request
data — the authenticated user, the tenant ID, the correlation ID, the feature-flag
snapshot, the locale — but threading these values through every function signature
creates boilerplate, makes refactoring expensive, and breaks when you call into
third-party utility code that knows nothing about your request context.

## Context

The Ambient Context pattern provides a single, request-scoped "context object" that
any code in the call stack can read without receiving it as a parameter. On Workers the
correct primitive for this is `AsyncLocalStorage` from the `node:async_hooks`
compatibility module (enabled with `nodejs_compat` in `wrangler.toml`). `AsyncLocalStorage`
stores a value in an "async context" that automatically propagates across `await`
boundaries, parallel `Promise.all` branches, and callbacks — matching the lifetime of
a single request.

Key properties:
- No global mutable state: each request gets its own isolated store.
- Works across `await` and Promise chains without manual passing.
- Readable from any function in the async call tree.
- Type-safe when wrapped in a typed accessor.

This pattern is often used together with Correlation ID Propagation
(`correlation-id-propagation-workers.md`) — the correlation ID is *one field* inside
the ambient context.

## Setting Up the Context Store

```typescript
// context/store.ts
import { AsyncLocalStorage } from 'node:async_hooks';

export interface RequestContext {
  requestId: string;
  tenantId: string | null;
  userId: string | null;
  roles: string[];
  locale: string;
  featureFlags: Record<string, boolean>;
  startedAt: number; // performance.now()
}

const storage = new AsyncLocalStorage<RequestContext>();

/** Run `fn` with the given context as the ambient context for the current async tree. */
export function withContext<T>(ctx: RequestContext, fn: () => T): T {
  return storage.run(ctx, fn);
}

/** Read the ambient context. Throws if called outside a withContext() scope. */
export function useContext(): RequestContext {
  const ctx = storage.getStore();
  if (!ctx) {
    throw new Error(
      'useContext() called outside a request context. ' +
      'Ensure withContext() wraps the fetch handler.',
    );
  }
  return ctx;
}

/** Safely read context without throwing (useful in utilities that may run outside requests). */
export function tryUseContext(): RequestContext | null {
  return storage.getStore() ?? null;
}
```

## Wrapping the Fetch Handler

```typescript
// worker.ts
import { withContext, RequestContext } from './context/store';
import { resolveRequestContext } from './context/resolver';
import { router } from './router';

export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  FLAGS_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const requestCtx = await resolveRequestContext(request, env);

    // Everything inside withContext() sees the same ambient context
    return withContext(requestCtx, async () => {
      try {
        return await router.handle(request, env, ctx);
      } catch (err) {
        const { requestId } = requestCtx;
        console.error({ requestId, error: String(err) });
        return new Response('Internal Server Error', { status: 500 });
      }
    });
  },
};
```

## Resolving the Context from Incoming Headers

```typescript
// context/resolver.ts
import { RequestContext } from './store';

export async function resolveRequestContext(
  request: Request,
  env: { KV: KVNamespace; FLAGS_KV: KVNamespace },
): Promise<RequestContext> {
  const requestId =
    request.headers.get('X-Request-Id') ?? crypto.randomUUID();

  // Tenant derived from JWT or header — simplified here
  const tenantId = request.headers.get('X-Tenant-Id') ?? null;
  const userId = request.headers.get('X-User-Id') ?? null;
  const roles = (request.headers.get('X-User-Roles') ?? '').split(',').filter(Boolean);
  const locale = request.headers.get('Accept-Language')?.split(',')[0] ?? 'en';

  // Feature flags fetched once per request and cached in the context
  const flagsRaw = tenantId
    ? await env.FLAGS_KV.get(`flags:${tenantId}`, 'json')
    : null;
  const featureFlags = (flagsRaw as Record<string, boolean>) ?? {};

  return {
    requestId,
    tenantId,
    userId,
    roles,
    locale,
    featureFlags,
    startedAt: performance.now(),
  };
}
```

## Consuming the Context in Domain Code

```typescript
// services/billing.ts — no context parameter needed
import { useContext } from '../context/store';

export async function getInvoices(db: D1Database): Promise<unknown[]> {
  const { tenantId, userId, roles } = useContext();

  if (!tenantId) throw new Error('Tenant required for invoice lookup');

  // Admins see all invoices, regular users see only their own
  const query = roles.includes('admin')
    ? db.prepare('SELECT * FROM invoices WHERE tenant_id = ?').bind(tenantId)
    : db
        .prepare('SELECT * FROM invoices WHERE tenant_id = ? AND user_id = ?')
        .bind(tenantId, userId);

  const { results } = await query.all();
  return results;
}

// Logging utility — no parameter threading needed
import { tryUseContext } from '../context/store';

export function log(level: string, message: string, extra?: object): void {
  const ctx = tryUseContext();
  console.log(JSON.stringify({
    level,
    message,
    requestId: ctx?.requestId,
    tenantId: ctx?.tenantId,
    ...extra,
  }));
}
```

## Mutating Context Mid-Request (Immutable Update)

```typescript
// context/update.ts — replace the running context with an updated snapshot
import { AsyncLocalStorage } from 'node:async_hooks';
import { RequestContext, withContext, useContext } from './store';

/**
 * Run `fn` with an amended context. Only code inside `fn` sees the amendment;
 * callers above see the original. Safe for parallel branches.
 */
export function withAmendedContext<T>(
  amendment: Partial<RequestContext>,
  fn: () => T,
): T {
  const current = useContext();
  return withContext({ ...current, ...amendment }, fn);
}

// Usage: elevate roles for a sudo-mode route segment
export async function handleAdminAction(action: () => Promise<Response>): Promise<Response> {
  return withAmendedContext({ roles: ['admin'] }, action);
}
```

## Testing Context-Dependent Code

```typescript
// __tests__/billing.test.ts
import { withContext } from '../context/store';
import { getInvoices } from '../services/billing';

const baseCtx = {
  requestId: 'test-001',
  tenantId: 'tenant-A',
  userId: 'user-1',
  roles: ['user'],
  locale: 'en',
  featureFlags: {},
  startedAt: 0,
};

test('non-admin sees only own invoices', async () => {
  const result = await withContext(baseCtx, () => getInvoices(dbMock));
  expect(result.every((r: any) => r.user_id === 'user-1')).toBe(true);
});

test('admin sees all tenant invoices', async () => {
  const result = await withContext(
    { ...baseCtx, roles: ['admin'] },
    () => getInvoices(dbMock),
  );
  expect(result.length).toBeGreaterThan(1);
});

// No need to mock function parameters — just set the context
declare const dbMock: D1Database;
```

## Anti-patterns

- **Using a module-level global object as "request context"** — Workers may handle
  concurrent requests in the same isolate if module-level state is shared; each request
  overwrites the global and the next request reads stale or wrong data. Use
  `AsyncLocalStorage`, not a plain object.
- **Calling `useContext()` at module initialisation time** — code runs during module
  evaluation before any request arrives; `getStore()` returns `undefined`. Only call
  `useContext()` inside a function that runs within the `withContext()` scope.
- **Storing mutable objects in context** — the context should be treated as immutable
  after creation. Mutations bleed across concurrent async branches that share the same
  context reference. Use `withAmendedContext()` to fork.
- **Nesting `withContext()` without intending to shadow** — each `withContext()` call
  creates a new scope for all children. Code that should inherit the parent's context
  must not accidentally call `withContext()` with an empty object.

## Gotchas

- `AsyncLocalStorage` requires `nodejs_compat` (or `nodejs_compat_v2`) in `wrangler.toml`.
  Without it, importing `node:async_hooks` throws at runtime.
- `AsyncLocalStorage.run()` is synchronous and returns the return value of `fn()`.
  When `fn` is `async`, it returns a `Promise<T>` — always `await` it at the call site.
- `Promise.all([a(), b()])` — both branches inherit the *same* context from the parent
  scope. If you need each branch to have a different context, wrap each with its own
  `withContext()`.
- `ctx.waitUntil()` (the `ExecutionContext`) runs *after* the response is sent.
  Code inside `waitUntil` still inherits the async context from when `waitUntil` was
  called, so `useContext()` works — but `performance.now()` relative to `startedAt`
  may report inflated latencies.

## Verification

```typescript
// Smoke test: concurrent requests do not bleed context
test('parallel requests have isolated context', async () => {
  const results = await Promise.all(
    ['tenant-A', 'tenant-B'].map((tenantId) =>
      withContext({ ...baseCtx, tenantId }, async () => {
        await new Promise((r) => setTimeout(r, 10));
        return useContext().tenantId;
      }),
    ),
  );
  expect(results).toEqual(['tenant-A', 'tenant-B']);
});
```

## Related

- `correlation-id-propagation-workers.md`
- `decorator-pattern-workers-middleware-composition.md`
- `per-tenant-durable-object.md`
- `structured-logging.md`
- `feature-flags.md`

## Sources

- Node.js AsyncLocalStorage — https://nodejs.org/api/async_context.html
- Cloudflare Workers Node.js compatibility — https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- TC39 AsyncContext proposal (forthcoming) — https://github.com/tc39/proposal-async-context
