# Decorator Pattern: Workers Middleware Composition

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have a set of Worker fetch handlers (or service-binding stubs) that need non-functional behaviours layered on top — caching, tracing, retry logic, response normalisation — without modifying the handler code itself. Copy-pasting the behaviour into each handler violates DRY; subclassing is unavailable in a functional Workers codebase. You need a composable wrapping mechanism that adds capabilities transparently.

## Context

The Decorator pattern wraps an object (or function) with another that implements the same interface and adds behaviour before or after delegating to the original. In Cloudflare Workers every handler is essentially `(request, env, ctx) => Promise<Response>`, which is a first-class function — a perfect decoration target. Decorators are higher-order functions that accept a handler and return a new handler with identical signature. They compose left-to-right via `pipe` or simple nesting, building up a layered handler at module load time (cold-start cost paid once), so each inbound request flows through the full decoration stack with no extra allocation per request beyond the closure captures.

## Handler Type and Pipe Utility

```typescript
// lib/handler.ts
export type Handler = (request: Request, env: Env, ctx: ExecutionContext) => Promise<Response>;

export type Decorator = (handler: Handler) => Handler;

/** Apply decorators right-to-left so the first in the array is the outermost wrapper. */
export function pipe(...decorators: Decorator[]): Decorator {
  return (handler: Handler) =>
    decorators.reduceRight((h, d) => d(h), handler);
}
```

## Core Decorators

```typescript
// decorators/withCaching.ts
import { Decorator } from "../lib/handler";

export interface CacheOptions {
  ttlSeconds: number;
  cacheKeyFn?: (request: Request) => string;
  methods?: string[];
}

export function withCaching(options: CacheOptions): Decorator {
  const { ttlSeconds, cacheKeyFn, methods = ["GET", "HEAD"] } = options;

  return (handler) => async (request, env, ctx) => {
    if (!methods.includes(request.method)) {
      return handler(request, env, ctx);
    }

    const cacheKey = cacheKeyFn ? cacheKeyFn(request) : request.url;
    const cached = await caches.default.match(new Request(cacheKey));
    if (cached) return cached;

    const response = await handler(request, env, ctx);
    if (response.ok) {
      const toCache = new Response(response.clone().body, response);
      toCache.headers.set("Cache-Control", `public, max-age=${ttlSeconds}`);
      ctx.waitUntil(caches.default.put(new Request(cacheKey), toCache));
    }
    return response;
  };
}

// decorators/withTracing.ts
import { Decorator } from "../lib/handler";

export function withTracing(operationName: string): Decorator {
  return (handler) => async (request, env, ctx) => {
    const traceId = request.headers.get("x-trace-id") ?? crypto.randomUUID();
    const start = Date.now();
    let status = 0;

    try {
      const response = await handler(request, env, ctx);
      status = response.status;
      return response;
    } catch (err) {
      status = 500;
      throw err;
    } finally {
      ctx.waitUntil(
        env.ANALYTICS.writeDataPoint({
          blobs: [operationName, traceId, String(status)],
          doubles: [Date.now() - start],
          indexes: [operationName],
        })
      );
    }
  };
}

// decorators/withRetry.ts
import { Decorator } from "../lib/handler";

export interface RetryOptions {
  maxAttempts: number;
  retryOn?: (response: Response) => boolean;
  backoffMs?: number;
}

export function withRetry(options: RetryOptions): Decorator {
  const { maxAttempts, retryOn = (r) => r.status >= 500, backoffMs = 200 } = options;

  return (handler) => async (request, env, ctx) => {
    let lastResponse!: Response;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      // Clone the request so the body can be re-read on retry
      const cloned = request.clone();
      lastResponse = await handler(cloned, env, ctx);
      if (!retryOn(lastResponse)) return lastResponse;
      if (attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, backoffMs * 2 ** (attempt - 1)));
      }
    }
    return lastResponse;
  };
}

// decorators/withErrorNormalisation.ts
import { Decorator } from "../lib/handler";

export function withErrorNormalisation(): Decorator {
  return (handler) => async (request, env, ctx) => {
    try {
      return await handler(request, env, ctx);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Internal server error";
      console.error("Unhandled error", message);
      return Response.json({ error: message }, { status: 500 });
    }
  };
}
```

## Composition and Worker Entry Point

```typescript
// handlers/products.ts
import { Handler } from "../lib/handler";

export const productsHandler: Handler = async (request, env) => {
  const products = await env.DB.prepare("SELECT * FROM products LIMIT 50").all();
  return Response.json(products.results);
};

// worker.ts
import { pipe } from "./lib/handler";
import { withCaching } from "./decorators/withCaching";
import { withTracing } from "./decorators/withTracing";
import { withRetry } from "./decorators/withRetry";
import { withErrorNormalisation } from "./decorators/withErrorNormalisation";
import { productsHandler } from "./handlers/products";

// Decorators are applied at module load time — zero overhead per request
const decoratedProducts = pipe(
  withErrorNormalisation(),
  withTracing("products.list"),
  withCaching({ ttlSeconds: 60 }),
  withRetry({ maxAttempts: 2 })
)(productsHandler);

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/products")) {
      return decoratedProducts(request, env, ctx);
    }
    return new Response("Not Found", { status: 404 });
  },
};
```

## Service Binding Decorator

```typescript
// decorators/withServiceBindingFallback.ts — wraps a service-binding stub
import { Handler } from "../lib/handler";

export function withServiceBindingFallback(
  primary: Handler,
  fallback: Handler
): Handler {
  return async (request, env, ctx) => {
    try {
      const response = await primary(request, env, ctx);
      if (response.status < 500) return response;
      return fallback(request, env, ctx);
    } catch {
      return fallback(request, env, ctx);
    }
  };
}
```

## Anti-patterns

- Decorating at request time (constructing the decorator stack inside `fetch`) instead of at module load time — this allocates a new closure chain on every request.
- Mutating the original `request` object inside a decorator; always `request.clone()` before reading the body so downstream decorators can still read it.
- Layering retry logic outside caching — if the cache hit succeeds there is no need to retry; order decorators so caching wraps retry, not the other way around.

## Gotchas

- `Response` bodies in Cloudflare Workers are streams and can only be consumed once; if a decorator reads `response.json()` or `response.text()`, it must pass a new `Response` constructed from `response.clone()` to the next layer.
- `caches.default.put()` only accepts `GET` requests as the cache key; for non-GET responses, construct a synthetic cache key with a `GET` method `new Request(url, { method: "GET" })`.

## Verification

```bash
# Confirm caching header is set
curl -I https://api.example.com/products
# Expect: Cache-Control: public, max-age=60

# Verify trace data appears in Analytics Engine
wrangler analytics-engine query \
  --query "SELECT blob1 as operation, double1 as duration_ms FROM ANALYTICS LIMIT 10"

# Simulate 500 to test retry decorator
wrangler dev --local
# Force handler to return 500 and check logs for retry attempts
```

## Related

- `architecture/chain-of-responsibility-workers-middleware-pipeline.md`
- `architecture/circuit-breaker-design.md`
- `architecture/caching-layers-cloudflare-workers-kv-r2.md`
- `architecture/worker-to-worker-rpc-service-bindings.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://refactoring.guru/design-patterns/decorator
- https://developers.cloudflare.com/analytics/analytics-engine/
