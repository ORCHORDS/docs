# `instanceof Error` Returns False for Errors Caught from Subrequests / Service Bindings in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker catches an error thrown by a service binding call or a `fetch()` subrequest. The error object looks like a normal `Error`, yet `err instanceof Error` evaluates to `false`, causing downstream `if (err instanceof Error)` guards to silently fall through and produce confusing, hard-to-trace bugs in error-handling branches.

---

## Context

Cloudflare Workers runs each isolate in its own V8 context. When a service binding or a cross-isolate `fetch()` throws, the error object is created inside the *callee* isolate's context, where `Error` refers to a different prototype than the one in the *caller* isolate's context. JavaScript's `instanceof` walks the prototype chain and compares constructor references by identity, so an error created in realm A fails the `instanceof Error` check performed in realm B — even though the two `Error` constructors are functionally identical. This is the classic "cross-realm" or "cross-context" instanceof problem, well-known in browser iframes and Node.js `vm` modules, now surfacing in Workers with service bindings.

---

## What Went Wrong

```typescript
// worker-a.ts  (caller)
import type { Env } from './env';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const result = await env.SERVICE_B.fetch(request);
      return result;
    } catch (err) {
      // BUG: err comes from a different isolate realm.
      // instanceof check silently fails → falls to the else branch.
      if (err instanceof Error) {
        console.error('Caught error:', err.message); // never reached
        return new Response(err.message, { status: 500 });
      } else {
        // Generic fallback — message is lost
        return new Response('Unknown error', { status: 500 });
      }
    }
  },
};
```

## Root Cause

Each Workers isolate owns its own global scope, including its own `Error` constructor. An error thrown inside service binding Worker B is an instance of *B's* `Error.prototype`. When Worker A catches that error, `err instanceof Error` checks against *A's* `Error.prototype`. Because the two prototype objects are different references, `instanceof` returns `false` even though the error looks and behaves exactly like a normal `Error`.

This matches the ECMAScript spec: `instanceof` performs `OrdinaryHasInstance`, which compares `Object.getPrototypeOf(err)` against `Error.prototype` by strict object identity (`===`), not by structural shape.

## The Fix

Use duck-typing or `Object.prototype.toString` instead of `instanceof`:

```typescript
// utils/isError.ts

/**
 * Cross-realm safe error check.
 * Works across Workers isolate boundaries, iframes, and vm contexts.
 */
export function isError(value: unknown): value is Error {
  // Fast path: same-realm errors still pass instanceof
  if (value instanceof Error) return true;

  // Cross-realm path: check for the two canonical Error properties
  if (
    typeof value === 'object' &&
    value !== null &&
    'message' in value &&
    'stack' in value
  ) {
    return true;
  }

  // Belt-and-suspenders: Object.prototype.toString cross-realm tag
  return Object.prototype.toString.call(value) === '[object Error]';
}

/**
 * Extracts a string message from anything that might be an error.
 */
export function toErrorMessage(value: unknown): string {
  if (isError(value)) return value.message;
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
```

Refactored handler:

```typescript
// worker-a.ts  (caller) — fixed
import type { Env } from './env';
import { isError, toErrorMessage } from './utils/isError';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      return await env.SERVICE_B.fetch(request);
    } catch (err) {
      const message = toErrorMessage(err);
      const stack = isError(err) ? (err.stack ?? '') : '';

      console.error('Caught cross-realm error:', message, stack);
      return new Response(message, { status: 500 });
    }
  },
};
```

## Verification

```bash
# 1. Start both workers locally with wrangler
wrangler dev --config wrangler-service-b.toml &
wrangler dev --config wrangler-a.toml

# 2. Trigger a known-failing route in service B and observe Worker A's log
curl -i http://localhost:8787/trigger-error

# Expected: HTTP 500 with the real error message, not 'Unknown error'
# Confirm in wrangler dev output:
#   Caught cross-realm error: <real message> Error: ...

# 3. Unit test with vitest (Workers pool)
npx vitest run src/utils/isError.test.ts
```

Minimal test:

```typescript
// src/utils/isError.test.ts
import { describe, it, expect } from 'vitest';
import { isError } from './isError';

describe('isError', () => {
  it('accepts same-realm Error', () => {
    expect(isError(new Error('test'))).toBe(true);
  });

  it('accepts duck-typed error from another realm', () => {
    const crossRealmErr = { message: 'oops', stack: 'Error: oops\n  at ...', name: 'Error' };
    expect(isError(crossRealmErr)).toBe(true);
  });

  it('rejects plain objects without message+stack', () => {
    expect(isError({ code: 42 })).toBe(false);
  });

  it('rejects primitives', () => {
    expect(isError('string error')).toBe(false);
    expect(isError(null)).toBe(false);
  });
});
```

---

## Anti-patterns

- **`err instanceof Error` as the sole error guard** — Silently fails for cross-realm errors, eating the real message and stack trace.
- **`catch (err: any) { return err.message }`** — Accessing `.message` without any guard will throw if `err` is a string or primitive, which is valid in JavaScript `throw` statements.
- **Re-throwing the raw cross-realm object** — Callers further up the chain will have the same instanceof problem; wrap it in a new same-realm `Error` if re-throwing: `throw new Error(toErrorMessage(err))`.

---

## Gotchas

- `Object.prototype.toString.call(err) === '[object Error]'` is not universally reliable: user-land classes that extend `Error` may override `Symbol.toStringTag` and return a different string. The duck-typing check (`'message' in err && 'stack' in err`) is more pragmatic.
- Service binding errors sometimes arrive as plain `Response`-wrapped JSON, not thrown exceptions. Check `response.ok` before assuming a thrown error.
- In Miniflare / `wrangler dev`, service bindings run in the *same* process but separate isolates, so the cross-realm bug is reproducible locally.
- `cause` (ES2022 `Error` option) is also lost across realm boundaries unless explicitly serialised; never rely on `err.cause` from a cross-isolate catch without an `isError` guard.

---

## Related

- `workers-fetch-body-already-consumed.md`
- `d1-prepare-throws-on-missing-column.md`

---

## Sources

- MDN — instanceof and cross-realm objects — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/instanceof#instanceof_and_multiple_realms
- Cloudflare Workers Service Bindings docs — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- ECMAScript spec OrdinaryHasInstance — https://tc39.es/ecma262/#sec-ordinaryhasinstance
