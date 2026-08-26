# workers-service-bindings-advanced

**Issue:** Advanced patterns for Worker-to-Worker communication via Service Bindings
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service Bindings allow one Worker to call another Worker directly without an HTTP round-trip. They support RPC (with Workers RPC), HTTP fetch, and streaming, enabling microservice architectures on the Workers platform.

## Pattern / Solution

```toml
# Caller wrangler.toml
[[services]]
binding = "AUTH_SERVICE"
service = "auth-worker"
entrypoint = "AuthHandler"  # optional: target a specific named export class

[[services]]
binding = "DATA_SERVICE"
service = "data-worker"
```

```typescript
// Caller Worker
export interface Env {
  AUTH_SERVICE: Fetcher;
  DATA_SERVICE: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. HTTP-style call — full Request/Response cycle
    const authRes = await env.AUTH_SERVICE.fetch(
      new Request('https://auth/validate', {
        method: 'POST',
        body: JSON.stringify({ token: request.headers.get('Authorization') }),
        headers: { 'Content-Type': 'application/json' },
      })
    );
    if (!authRes.ok) return new Response('Unauthorized', { status: 401 });

    // 2. RPC-style call (Workers RPC — requires named export class)
    // const user = await env.AUTH_SERVICE.getUser(userId);

    // 3. Stream data from another Worker
    const dataStream = await env.DATA_SERVICE.fetch(
      new Request('https://data/stream')
    );
    return new Response(dataStream.body, {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

```typescript
// auth-worker/src/index.ts
export class AuthHandler {
  async fetch(request: Request): Promise<Response> {
    const { token } = await request.json() as { token: string };
    const valid = token === 'secret'; // simplified
    return Response.json({ valid });
  }
}

export default {
  async fetch(request: Request): Promise<Response> {
    return new Response('Auth Worker');
  },
};
```

**Service Binding vs HTTP:**
| Feature | Service Binding | HTTP fetch |
|---|---|---|
| Latency | ~0 ms (in-memory) | ~50 ms+ |
| Billing | Shared CPU budget | Separate invocation |
| Auth | None needed | Token/header required |
| Streaming | Supported | Supported |

## Gotchas
- Service Binding calls share the **caller's CPU time budget** — a slow callee can exhaust the caller's limit.
- The URL in `env.SERVICE.fetch(new Request('https://anything/path'))` — the host is ignored; only the path matters.
- You cannot use Service Bindings to call a Worker in a different Cloudflare account.
- Both Workers must be deployed to the same account; dev-mode bindings point at the running local instance.
- Circular bindings (A → B → A) are allowed but can create infinite loops; guard with a header.
- Workers RPC (class-based) requires `wrangler.toml` to specify `entrypoint`.

## Related
- `workers-rpc.md`
- `workers-module-workers.md`
- `workers-best-practices.md`
