# workers-rpc

**Issue:** Workers RPC — service bindings, type-safe
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have Worker A and Worker B. A calls B via fetch.
The URL is hard-coded. The response is `any`. You
deploy a breaking change in B. A breaks at runtime.

## Root cause
**HTTP calls are not type-safe.** Use Workers RPC.

**Source:** CF Workers RPC docs.

## The "service binding" pattern

For service bindings in `wrangler.toml`:
```toml
[[services]]
binding = "AUTH"
service = "auth-service"
```

The Worker can call `env.AUTH.method()` directly.

## The "RPC method" pattern

For RPC methods:
```ts
// auth-service (the callee)
export class AuthService {
  async verifyToken(token: string): Promise<User | null> {
    // ...
    return user;
  }
}

export default {
  async fetch(request: Request, env: Env) {
    return new Response('Not for direct invocation', { status: 404 });
  },
};
```

The class is exported.

## The "RPC call" pattern

For the call from the caller:
```ts
// api-service (the caller)
import { AuthService } from '../auth-service/src';

export default {
  async fetch(request: Request, env: Env) {
    const token = request.headers.get('authorization')?.replace('Bearer ', '');

    // Type-safe RPC call
    const user = await env.AUTH.verifyToken(token);
    if (!user) {
      return new Response('Unauthorized', { status: 401 });
    }

    return Response.json({ user });
  },
};
```

The call is type-safe.

## The "RPC types" pattern

For type safety, share the types:
```ts
// shared-types.ts
export interface User {
  id: string;
  email: string;
  displayName: string;
}
```

The types are shared.

## The "RPC error" pattern

For errors, use Error subclasses:
```ts
class UnauthorizedError extends Error {}

export class AuthService {
  async verifyToken(token: string): Promise<User | null> {
    if (!token) {
      throw new UnauthorizedError('Missing token');
    }
    // ...
  }
}
```

The error is typed.

## The "RPC streaming" pattern

For streaming, the response is a ReadableStream:
```ts
class DataService {
  async streamData(): Promise<ReadableStream> {
    return new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('chunk 1\n'));
        controller.enqueue(new TextEncoder().encode('chunk 2\n'));
        controller.close();
      },
    });
  }
}
```

The stream is typed.

## The "RPC vs HTTP" choice

| Use case | Use |
|---|---|
| **Internal services** | RPC |
| **External API** | HTTP |
| **Type safety** | RPC |
| **Public API** | HTTP |

For internal services, **RPC** is the right answer.

## The "RPC observability" pattern

For observability:
- **Call count:** How many calls?
- **Latency:** How long?
- **Errors:** % failed
- **Method:** Which method?

```ts
const start = Date.now();
try {
  const user = await env.AUTH.verifyToken(token);
  metrics.histogram('rpc.duration_ms', Date.now() - start, { method: 'verifyToken' });
  return user;
} catch (err) {
  metrics.increment('rpc.errors', { method: 'verifyToken' });
  throw err;
}
```

The RPC is monitored.

## The "RPC anti-pattern" anti-patterns

### 1. HTTP for internal
- **Issue:** Not type-safe
- **Fix:** RPC

### 2. No types shared
- **Issue:** `any` everywhere
- **Fix:** Share types

### 3. No error handling
- **Issue:** Errors are untyped
- **Fix:** Typed errors

### 4. RPC for external
- **Issue:** RPC is internal
- **Fix:** HTTP for external

## Verification
- **Test:** RPC works
- **Test:** Types are correct
- **Test:** Errors are typed
- **Live:** RPC is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "HTTP for internal" anti-pattern.** Use RPC.
- **The "no types shared" anti-pattern.** Share types.
- **The "no error handling" anti-pattern.** Type errors.

## Related
- `cloudflare/workers-resource-limits.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `feature-cookbook-feature-isolation.md`
- CF Workers RPC: https://developers.cloudflare.com/workers/runtime-apis/rpc/
