# error-handling-strategies

**Issue:** Error handling — types, propagation, boundaries
**Date:** 2026-08-09
**Status:** documented

## Symptom
A function throws an error. The error propagates up. The
client sees a 500. The error is generic. You don't know
what went wrong. The user is frustrated.

## Root cause
**Errors are untyped and unhandled.** Without a strategy,
errors leak implementation details or hide root causes.

**Source:** Node.js Best Practices — Error Handling:
https://github.com/goldbergyoni/nodebestpractices

## The "typed error" pattern

```ts
// Custom error types
class ValidationError extends Error {
  constructor(message: string, public fields: Record<string, string>) {
    super(message);
    this.name = 'ValidationError';
  }
}

class NotFoundError extends Error {
  constructor(resource: string, id: string) {
    super(`${resource} not found: ${id}`);
    this.name = 'NotFoundError';
  }
}

class UnauthorizedError extends Error {
  constructor(message = 'Unauthorized') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

class ForbiddenError extends Error {
  constructor(message = 'Forbidden') {
    super(message);
    this.name = 'ForbiddenError';
  }
}
```

The error type is specific; the handler can branch on it.

## The "error boundary" pattern

For each layer, catch errors at the boundary:
```ts
// Handler
export async function handleRequest(request: Request, env: Env): Promise<Response> {
  try {
    return await processRequest(request, env);
  } catch (err) {
    return errorResponse(err, request);
  }
}

function errorResponse(err: unknown, request: Request): Response {
  // Map error type to response
  if (err instanceof ValidationError) {
    return new Response(JSON.stringify({
      type: 'https://example.com/probs/validation-failed',
      title: 'Validation failed',
      status: 400,
      errors: err.fields,
    }), { status: 400, headers: { 'content-type': 'application/problem+json' } });
  }

  if (err instanceof NotFoundError) {
    return new Response(JSON.stringify({
      type: 'https://example.com/probs/not-found',
      title: 'Not found',
      status: 404,
    }), { status: 404, headers: { 'content-type': 'application/problem+json' } });
  }

  if (err instanceof UnauthorizedError) {
    return new Response(JSON.stringify({
      type: 'https://example.com/probs/unauthorized',
      title: 'Unauthorized',
      status: 401,
    }), { status: 401, headers: { 'content-type': 'application/problem+json' } });
  }

  // Unknown error: log + 500
  console.error({ msg: 'unhandled.error', err: String(err), stack: (err as Error).stack, path: new URL(request.url).pathname });
  return new Response(JSON.stringify({
    type: 'https://example.com/probs/internal-error',
    title: 'Internal server error',
    status: 500,
  }), { status: 500, headers: { 'content-type': 'application/problem+json' } });
}
```

The boundary catches all errors; the response is consistent.

## The "fail fast" pattern

For invalid input, fail fast:
```ts
function divide(a: number, b: number): number {
  if (b === 0) throw new Error('Division by zero');
  return a / b;
}
```

Don't return null or 0 for invalid input. Throw.

## The "error context" pattern

For debugging, add context to the error:
```ts
async function getUser(id: string, ctx: McContext): Promise<User | null> {
  try {
    return await ctx.env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
  } catch (err) {
    throw new Error(`Failed to get user ${id}: ${(err as Error).message}`, { cause: err });
  }
}
```

The error chain has the original error + the context.

## The "error logging" pattern

For every error, log with context:
```ts
function logError(err: Error, context: Record<string, unknown>): void {
  console.error({
    timestamp: new Date().toISOString(),
    level: 'error',
    message: 'error',
    error: err.message,
    stack: err.stack,
    ...context,
  });
}

// Usage
try {
  await doSomething();
} catch (err) {
  logError(err as Error, { userId: ctx.user.id, requestId: ctx.requestId });
  throw err;
}
```

The log is structured; you can query it.

## The "error monitoring" pattern

Use Sentry (or similar) for error tracking:
```ts
import * as Sentry from '@sentry/browser';

Sentry.init({
  dsn: env.SENTRY_DSN,
  environment: env.ENVIRONMENT,
  release: env.RELEASE_VERSION,
});

try {
  await doSomething();
} catch (err) {
  Sentry.captureException(err, {
    tags: { feature: 'new-dashboard' },
    user: { id: ctx.user.id, tenantId: ctx.tenant.id },
    extra: { requestId: ctx.requestId },
  });
  throw err;
}
```

Sentry groups similar errors + alerts on spikes.

## The "graceful error" pattern

For non-critical errors, don't throw; degrade:
```ts
async function getRecommendations(userId: string, env: Env): Promise<string[]> {
  try {
    return await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { ... });
  } catch (err) {
    logError(err as Error, { userId, fallback: 'popular' });
    return getPopularItems();  // Fallback
  }
}
```

The user gets something (popular items), not nothing.

## The "error in async" pattern

For async code, errors can be lost. Always await + catch:
```ts
// ❌ Bad: unhandled promise
ctx.waitUntil(sendEmail(input));  // Errors are unhandled

// ✅ Good: caught promise
ctx.waitUntil(sendEmail(input).catch(err => logError(err, { input })));
```

## The "global error handler" pattern

For unhandled errors at the boundary:
```ts
// In a Worker
addEventListener('unhandledrejection', (event) => {
  console.error({ msg: 'unhandledrejection', reason: String(event.reason) });
  event.preventDefault();
});

addEventListener('error', (event) => {
  console.error({ msg: 'unhandlederror', error: String(event.error) });
  event.preventDefault();
});
```

The global handler catches anything that escapes.

## The "retry vs fail" pattern

For transient errors, retry. For permanent errors, fail.
```ts
async function callApi<T>(fn: () => Promise<T>): Promise<T> {
  return withBackoff(fn, { isRetryable: (err) => isTransient(err) });
}

function isTransient(err: Error): boolean {
  // 5xx, network errors, timeouts: transient
  if (err.message.includes('5xx')) return true;
  if (err.message.includes('timeout')) return true;
  // 4xx, validation errors: permanent
  return false;
}
```

Transient errors retry; permanent errors fail fast.

## The "user-friendly error" pattern

For user-facing errors, use a friendly message:
```ts
function userMessage(err: Error): string {
  if (err instanceof ValidationError) return 'Please check the form and try again.';
  if (err instanceof NotFoundError) return 'The item you are looking for was not found.';
  if (err instanceof UnauthorizedError) return 'Please sign in to continue.';
  if (err instanceof ForbiddenError) return 'You do not have permission to do this.';
  return 'Something went wrong. Please try again later.';
}
```

The user gets a clear, actionable message. The internal
details (in the log) are separate.

## The "error documentation" pattern

For each error type, document:
- **What it means**
- **When it happens**
- **How to handle it**
- **User message**
- **HTTP status code**

```markdown
## Error types

### ValidationError (400)
- **Meaning:** The input is invalid
- **When:** The request body fails Zod validation
- **User message:** "Please check the form and try again."
- **Fields:** The invalid fields + their messages

### NotFoundError (404)
- **Meaning:** The resource doesn't exist
- **When:** The resource ID is not in the DB
- **User message:** "The item was not found."

### UnauthorizedError (401)
- **Meaning:** The user is not authenticated
- **When:** No valid session/JWT
- **User message:** "Please sign in to continue."

### ForbiddenError (403)
- **Meaning:** The user is authenticated but not authorized
- **When:** The user doesn't have the required role/scope
- **User message:** "You do not have permission to do this."

### InternalError (500)
- **Meaning:** An unexpected error
- **When:** Bug, unhandled case, infra issue
- **User message:** "Something went wrong. Please try again later."
- **Note:** Log the full error; don't leak to the user.
```

## The "error metrics" pattern

Track error metrics:
```ts
metrics.increment('errors.total', { type: 'validation', code: 'INVALID_EMAIL' });
metrics.increment('errors.total', { type: 'not_found', resource: 'user' });
metrics.increment('errors.total', { type: 'internal' });
```

The metrics show:
- Most common error types
- Error trends over time
- Spike detection

## The "error in tests" pattern

For tests, assert the error:
```ts
test('getUser throws NotFoundError for missing user', async () => {
  await expect(getUser('u_missing', ctx)).rejects.toThrow(NotFoundError);
});
```

The test verifies the error type.

## Verification
- **Test:** Every error path is tested
- **Live:** Errors are logged + monitored
- **Audit:** Quarterly error review

## Gotchas
- **The "swallow the error" anti-pattern.** `catch {}` hides
  bugs. Always log + handle.
- **The "leak the error" anti-pattern.** A 500 with the SQL
  query is a security bug. Strip internals.
- **The "throw a string" anti-pattern.** `throw 'error'`
  loses the stack. Always throw an `Error`.
- **The "no error boundary" anti-pattern.** Errors propagate
  to the client. Have a boundary at every layer.
- **The "error is a bug" anti-pattern.** Some errors are
  expected (validation, not found). Handle them
  differently.
- **The "unhandled promise rejection" anti-pattern.** A
  promise that rejects without a catch is a bug. Always
  handle.

## Related
- `error-codes-and-messages.md`
- `secure-defaults.md`
- `retry-with-exponential-backoff.md`
- `circuit-breaker-pattern.md`
- `graceful-degradation-detail.md`
- `observability-three-pillars-detail.md`
- Node.js best practices: https://github.com/goldbergyoni/nodebestpractices
- Error handling in TS: https://www.typescriptlang.org/docs/handbook/2/narrowing.html
