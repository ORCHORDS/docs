# Decorator Pattern for Workers Middleware Chains

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Every Workers handler needs auth verification, structured logging, and rate limiting. Copy-pasting those concerns into each handler creates drift and makes global changes (e.g., switching to a new JWT library) require touching every file. The Decorator pattern wraps a core `ExportedHandler` with additional behaviour without modifying the handler's own code.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Language: TypeScript 5.x
- No third-party framework required — pure Workers runtime types
- Decorators compose left-to-right; outermost decorator runs first on `fetch`
- Rate limiting uses Cloudflare Rate Limiting API (Workers Paid plan) or a KV-backed counter

---

## 1. Core Handler Type

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  JWT_SECRET: string;
  RATE_LIMIT: RateLimit;  // Cloudflare Rate Limiting binding
}

/**
 * A thin alias — all decorators and the core handler satisfy this shape.
 */
export type WorkerHandler<E extends Env = Env> = ExportedHandler<E>;
```

---

## 2. Decorator Helper

```typescript
// src/middleware/types.ts
import { Env } from "../types";

export type FetchHandler<E extends Env = Env> = (
  req: Request,
  env: E,
  ctx: ExecutionContext
) => Promise<Response>;

/**
 * Wraps a `fetch` function so decorators only need to override `fetch`;
 * other lifecycle methods (scheduled, queue, etc.) pass through unchanged.
 */
export function withFetch<E extends Env>(
  inner: ExportedHandler<E>,
  wrapper: (
    req: Request,
    env: E,
    ctx: ExecutionContext,
    next: FetchHandler<E>
  ) => Promise<Response>
): ExportedHandler<E> {
  return {
    ...inner,
    async fetch(req, env, ctx) {
      return wrapper(req, env, ctx, inner.fetch!.bind(inner) as FetchHandler<E>);
    },
  };
}
```

---

## 3. Auth Decorator

```typescript
// src/middleware/auth.ts
import { Env, FetchHandler } from "./types";
import { withFetch } from "./types";

async function verifyJwt(
  token: string,
  secret: string
): Promise<{ sub: string; roles: string[] } | null> {
  try {
    // Workers supports SubtleCrypto — no external JWT library needed
    const [headerB64, payloadB64, sigB64] = token.split(".");
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );
    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), (c) =>
      c.charCodeAt(0)
    );
    const valid = await crypto.subtle.verify("HMAC", key, sig, data);
    if (!valid) return null;
    const payload = JSON.parse(atob(payloadB64));
    if (payload.exp && payload.exp < Date.now() / 1000) return null;
    return { sub: payload.sub, roles: payload.roles ?? [] };
  } catch {
    return null;
  }
}

export function withAuth<E extends Env>(
  inner: ExportedHandler<E>
): ExportedHandler<E> {
  return withFetch(inner, async (req, env, ctx, next) => {
    const authHeader = req.headers.get("authorization") ?? "";
    const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;
    if (!token) {
      return Response.json({ error: "Missing token" }, { status: 401 });
    }
    const claims = await verifyJwt(token, env.JWT_SECRET);
    if (!claims) {
      return Response.json({ error: "Invalid or expired token" }, { status: 401 });
    }
    // Inject verified identity into a request header for downstream use
    const authedReq = new Request(req, {
      headers: {
        ...Object.fromEntries(req.headers),
        "x-user-id": claims.sub,
        "x-user-roles": claims.roles.join(","),
      },
    });
    return next(authedReq, env, ctx);
  });
}
```

---

## 4. Structured Logging Decorator

```typescript
// src/middleware/logger.ts
import { Env } from "../types";
import { withFetch } from "./types";

export function withLogger<E extends Env>(
  inner: ExportedHandler<E>
): ExportedHandler<E> {
  return withFetch(inner, async (req, env, ctx, next) => {
    const start = Date.now();
    const { method, url } = req;
    let status = 500;
    try {
      const res = await next(req, env, ctx);
      status = res.status;
      return res;
    } finally {
      // console.log in Workers emits to wrangler tail / Logpush
      console.log(
        JSON.stringify({
          ts: new Date().toISOString(),
          method,
          url,
          status,
          ms: Date.now() - start,
          userId: req.headers.get("x-user-id") ?? null,
        })
      );
    }
  });
}
```

---

## 5. Rate Limiting Decorator

```typescript
// src/middleware/rateLimit.ts
import { Env } from "../types";
import { withFetch } from "./types";

/**
 * Uses the Cloudflare Rate Limiting API binding.
 * Declare in wrangler.toml:
 *
 *   [[unsafe.bindings]]
 *   name = "RATE_LIMIT"
 *   type = "ratelimit"
 *   namespace_id = "1001"
 *   simple = { limit = 100, period = 60 }
 */
export function withRateLimit<E extends Env>(
  inner: ExportedHandler<E>
): ExportedHandler<E> {
  return withFetch(inner, async (req, env, ctx, next) => {
    // Key by IP; fall back to 'global' if CF-Connecting-IP is absent (local dev)
    const key =
      req.headers.get("cf-connecting-ip") ??
      req.headers.get("x-forwarded-for") ??
      "global";
    const { success } = await env.RATE_LIMIT.limit({ key });
    if (!success) {
      return new Response("Too Many Requests", {
        status: 429,
        headers: { "retry-after": "60" },
      });
    }
    return next(req, env, ctx);
  });
}
```

---

## 6. Core Handler + Composition

```typescript
// src/handlers/core.ts
import { Env } from "../types";

const coreHandler: ExportedHandler<Env> = {
  async fetch(req, env, _ctx) {
    const userId = req.headers.get("x-user-id");
    return Response.json({ hello: userId, ts: Date.now() });
  },
};

export default coreHandler;
```

```typescript
// src/index.ts
import { Env } from "./types";
import coreHandler from "./handlers/core";
import { withAuth } from "./middleware/auth";
import { withLogger } from "./middleware/logger";
import { withRateLimit } from "./middleware/rateLimit";

// Stack: rate-limit → logger → auth → core
// Outermost (withRateLimit) is the first to intercept each request.
export default withRateLimit(
  withLogger(
    withAuth(coreHandler)
  )
) satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Modifying the core handler directly**: adding auth logic inside `coreHandler.fetch` violates single responsibility and cannot be toggled per-route.
- **Stateful decorator instances**: each Worker invocation may hit a fresh isolate; decorators must be pure functions of the request, not closures over mutable state.
- **Swallowing the `finally` block in logger**: always use `try/finally` so the log line emits even when `next()` throws.
- **Re-reading request body in multiple decorators**: `Request.body` is a one-shot stream; clone the request if more than one decorator needs the body.

## Gotchas

- `new Request(req, { headers: {...} })` merges headers from the options object over the original — it does not append. Re-spread `Object.fromEntries(req.headers)` first.
- Cloudflare Rate Limiting bindings are only available at runtime (not in `wrangler dev` without `--remote`) — stub the binding for local dev.
- `crypto.subtle` is globally available in Workers without any import.
- The `satisfies` operator on the export catches type mismatches at build time without widening the export type.

## Verification

```bash
# Tail logs during local testing
wrangler tail --format pretty

# Happy path
curl -s -H "Authorization: Bearer <valid-jwt>" http://localhost:8787/ | jq .

# Auth failure
curl -s http://localhost:8787/  # Expect 401

# Rate limit (send 101 requests)
for i in $(seq 1 101); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer <valid-jwt>" \
    http://localhost:8787/
done | sort | uniq -c
# Expect: 100× 200, 1× 429
```

## Related

- `documentation/docs/policies/architecture/workers-api-gateway-aggregator-service-bindings.md`
- `documentation/docs/policies/architecture/workers-observer-pattern-queues-fanout.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/workers/observability/logging/workers-logs/
