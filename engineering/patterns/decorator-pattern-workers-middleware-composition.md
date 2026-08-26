# Decorator Pattern: Workers Middleware Composition

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cross-cutting concerns — authentication, rate limiting, request logging, CORS, response caching — accumulate in route handlers until each handler is a tangled mix of business logic and infrastructure code. Copying the same `if (!token) return 401` block into every handler creates drift: one handler forgets CORS headers, another skips logging on errors. Adding a new concern (e.g., request-ID propagation) requires touching every file.

## Context

Cloudflare Workers expose a single `fetch(req, env, ctx)` entry point. There is no built-in middleware framework. The Decorator pattern wraps a handler function with another function of the same signature, building a chain where each decorator adds one concern and delegates to the next. Decorators compose without modifying the underlying handler, keeping each concern in a single file and making the wrapping order explicit at the composition site.

## Core Type — Handler as a First-Class Type

Define the handler signature once. Every decorator input and output is `Handler`.

```typescript
// src/middleware/types.ts
import type { Env } from '../env';

export type Handler = (
  req: Request,
  env: Env,
  ctx: ExecutionContext
) => Promise<Response>;

// A decorator takes a Handler and returns a Handler
export type Decorator = (next: Handler) => Handler;
```

## Authentication Decorator

Reads the session token from KV and attaches the resolved `userId` to a per-request context object passed via a header (Workers have no AsyncLocalStorage equivalent in all runtimes, so a cloned request with an appended header is the idiomatic approach).

```typescript
// src/middleware/auth.ts
import type { Decorator } from './types';
import type { Env } from '../env';

export const withAuth: Decorator = (next) => async (req, env, ctx) => {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) {
    return new Response(JSON.stringify({ error: 'unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const userId = await env.SESSIONS.get(`session:${token}`);
  if (!userId) {
    return new Response(JSON.stringify({ error: 'session_expired' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Forward resolved identity downstream via a synthetic header
  const enriched = new Request(req, {
    headers: new Headers([
      ...req.headers,
      ['x-user-id', userId],
    ]),
  });
  return next(enriched, env, ctx);
};
```

## Rate-Limit Decorator

Reads the token bucket from a Durable Object. Short-circuits with 429 before the handler runs.

```typescript
// src/middleware/rate-limit.ts
import type { Decorator } from './types';

export function withRateLimit(
  maxPerMinute: number
): Decorator {
  return (next) => async (req, env, ctx) => {
    const userId = req.headers.get('x-user-id') ?? req.headers.get('cf-connecting-ip') ?? 'anon';
    const id = env.RATE_LIMITER.idFromName(userId);
    const stub = env.RATE_LIMITER.get(id);

    const result = await stub.fetch(
      new Request('https://do/check', {
        method: 'POST',
        body: JSON.stringify({ maxPerMinute }),
      })
    ).then(r => r.json<{ allowed: boolean; remaining: number; resetAt: number }>());

    if (!result.allowed) {
      return new Response(JSON.stringify({ error: 'rate_limit_exceeded' }), {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': String(result.resetAt),
          'Retry-After': String(Math.ceil((result.resetAt - Date.now()) / 1000)),
        },
      });
    }

    const response = await next(req, env, ctx);
    return new Response(response.body, {
      status: response.status,
      headers: new Headers([
        ...response.headers,
        ['X-RateLimit-Remaining', String(result.remaining)],
      ]),
    });
  };
}
```

## Logging Decorator

Emits a structured log line for every request with method, path, status, and duration. Uses `ctx.waitUntil` so logging never delays the response.

```typescript
// src/middleware/logging.ts
import type { Decorator } from './types';

export const withLogging: Decorator = (next) => async (req, env, ctx) => {
  const requestId = req.headers.get('x-request-id') ?? crypto.randomUUID();
  const start = Date.now();

  const enriched = new Request(req, {
    headers: new Headers([...req.headers, ['x-request-id', requestId]]),
  });

  let status = 500;
  try {
    const response = await next(enriched, env, ctx);
    status = response.status;

    ctx.waitUntil(
      Promise.resolve().then(() => {
        console.log(JSON.stringify({
          requestId,
          method: req.method,
          path: new URL(req.url).pathname,
          status,
          durationMs: Date.now() - start,
          userId: req.headers.get('x-user-id'),
        }));
      })
    );

    return new Response(response.body, {
      status: response.status,
      headers: new Headers([...response.headers, ['x-request-id', requestId]]),
    });
  } catch (err) {
    ctx.waitUntil(
      Promise.resolve().then(() => {
        console.error(JSON.stringify({
          requestId, status: 500,
          error: String(err),
          durationMs: Date.now() - start,
        }));
      })
    );
    throw err;
  }
};
```

## Composition — Applying Decorators at the Entrypoint

`compose` applies decorators right-to-left so the first in the array is the outermost wrapper (runs first on the way in, last on the way out).

```typescript
// src/middleware/compose.ts
import type { Handler, Decorator } from './types';

export function compose(...decorators: Decorator[]): Decorator {
  return (handler: Handler): Handler =>
    decorators.reduceRight((acc, dec) => dec(acc), handler);
}
```

```typescript
// src/index.ts
import type { Env } from './env';
import type { Handler } from './middleware/types';
import { compose } from './middleware/compose';
import { withLogging } from './middleware/logging';
import { withAuth } from './middleware/auth';
import { withRateLimit } from './middleware/rate-limit';
import { router } from './router';

// Stack: logging → auth → rate-limit → router
const handler: Handler = compose(
  withLogging,
  withAuth,
  withRateLimit(60),
)(router);

export default {
  fetch: handler,
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Mutating the original `Request` object — always clone with `new Request(req, { ... })`
- Returning `Response` from a decorator without calling `next` when the intent is to short-circuit — short-circuiting is correct, but log/trace it so the omission is visible
- Nesting decorators via closure capture of mutable state — decorators must be stateless; share state only through the request headers or the Env binding
- Reversing the compose order and getting auth after rate-limiting — document the intended stack order with a comment at the composition site
- Creating a new decorator per route for per-route rate limits — parameterise the decorator with `withRateLimit(n)` instead

## Gotchas

- `new Request(req, { headers: new Headers([...req.headers, ...]) })` — spreading `Headers` requires `[...req.headers]` (iterable), not `Object.fromEntries` on typed headers objects in older runtimes
- `ctx.waitUntil` accepts a single Promise; wrap multiple tasks in `Promise.all`
- Decorators that read the body must `req.clone()` before consuming — consuming a body is destructive in Workers
- Response headers set in inner handlers are visible in outer decorators only after `await next(req, env, ctx)` resolves; do not read them before that
- In tests, pass a `new ExecutionContext()` (from `@cloudflare/workers-types`) or use `import { createExecutionContext } from 'cloudflare:test'`

## Verification

```typescript
// src/middleware/__tests__/compose.test.ts
import { describe, it, expect, vi } from 'vitest';
import { compose } from '../compose';
import type { Handler } from '../types';

describe('compose', () => {
  it('applies decorators in outer-to-inner order', async () => {
    const order: string[] = [];
    const makeDecorator = (name: string) =>
      (next: Handler): Handler =>
        async (req, env, ctx) => {
          order.push(`${name}:in`);
          const res = await next(req, env, ctx);
          order.push(`${name}:out`);
          return res;
        };

    const base: Handler = async () => new Response('ok');
    const decorated = compose(
      makeDecorator('A'),
      makeDecorator('B'),
    )(base);

    const env = {} as any;
    const ctx = { waitUntil: vi.fn(), passThroughOnException: vi.fn() };
    await decorated(new Request('https://x.com/'), env, ctx);
    expect(order).toEqual(['A:in', 'B:in', 'B:out', 'A:out']);
  });
});
```

## Related

- `documentation/categories/patterns/proxy-pattern-workers-service-binding-auth.md`
- `documentation/categories/patterns/template-method-pattern-workers-handler.md`
- `documentation/categories/patterns/correlation-id-propagation-workers.md`
- `documentation/categories/patterns/api-rate-limiting-detail.md`
- `documentation/categories/patterns/structured-logging.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch-event/
- https://developers.cloudflare.com/workers/runtime-apis/request/
- https://refactoring.guru/design-patterns/decorator
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
