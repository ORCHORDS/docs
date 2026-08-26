# Cloudflare Pages Functions Middleware Chain Performance Optimization

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Every request to a Cloudflare Pages site runs through `_middleware.ts` files. Teams find that adding auth checks, rate limiting, and analytics logging in middleware sequentially adds 20–80 ms of latency to every edge response—even for static assets that don't need any of those checks. CPU time accumulates across the chain faster than expected.

## Context

Pages Functions uses a directory-based middleware model: a `functions/_middleware.ts` applies to all routes; a `functions/api/_middleware.ts` applies only under `/api/`. Each middleware calls `next()` to pass control down the chain. Because middleware files are co-located with route handlers they run on every matched request, including requests for static assets that are served from Cloudflare's cache and therefore never reach your Worker code—but middleware *above* the cache check does run before the cache lookup.

Key constraints:
- Middleware is CPU-billed in aggregate with the request handler.
- `next()` is async; sequential awaits are the primary latency source.
- Module-scope initialisation (JWT library setup, DB clients) runs once per isolate lifetime.

---

## Lazy Module-Scope Initialisation

Avoid importing heavy libraries at the top of every middleware file when only a fraction of requests use them:

```typescript
// functions/_middleware.ts
import type { EventContext } from "@cloudflare/workers-types";

interface Env {
  JWT_SECRET: string;
  AUTH_KV: KVNamespace;
}

// Deferred: only created on first request that needs auth
let jwtVerifier: ((token: string, secret: string) => Promise<{ sub: string }>) | null = null;

async function getVerifier() {
  if (!jwtVerifier) {
    // Dynamic import keeps cold-start cost out of module evaluation
    const { createVerifier } = await import("./lib/jwt");
    jwtVerifier = createVerifier();
  }
  return jwtVerifier;
}

export async function onRequest(ctx: EventContext<Env, string, unknown>) {
  const url = new URL(ctx.request.url);

  // Short-circuit: static assets need no auth
  if (url.pathname.startsWith("/assets/") || url.pathname === "/favicon.ico") {
    return ctx.next();
  }

  const token = ctx.request.headers.get("Authorization")?.slice(7);
  if (!token) {
    return new Response("Unauthorized", { status: 401 });
  }

  const verify = await getVerifier();
  const payload = await verify(token, ctx.env.JWT_SECRET);

  // Attach to locals for downstream handlers
  ctx.data.userId = payload.sub;
  return ctx.next();
}
```

---

## Parallelising Independent Middleware Checks

Sequential awaits compound latency. Run independent checks in parallel with `Promise.all`:

```typescript
// functions/api/_middleware.ts
import type { EventContext } from "@cloudflare/workers-types";

interface Env {
  RATE_LIMIT_KV: KVNamespace;
  FEATURE_FLAGS_KV: KVNamespace;
}

export async function onRequest(ctx: EventContext<Env, string, Record<string, unknown>>) {
  const clientIp = ctx.request.headers.get("CF-Connecting-IP") ?? "unknown";
  const userId = ctx.data.userId as string;

  // Run rate-limit check and feature-flag fetch in parallel
  const [rateLimitOk, flags] = await Promise.all([
    checkRateLimit(ctx.env.RATE_LIMIT_KV, clientIp),
    fetchFeatureFlags(ctx.env.FEATURE_FLAGS_KV, userId),
  ]);

  if (!rateLimitOk) {
    return new Response("Too Many Requests", {
      status: 429,
      headers: { "Retry-After": "60" },
    });
  }

  ctx.data.flags = flags;
  return ctx.next();
}

async function checkRateLimit(kv: KVNamespace, ip: string): Promise<boolean> {
  const key = `rl:${ip}:${Math.floor(Date.now() / 60_000)}`;
  const count = parseInt((await kv.get(key)) ?? "0", 10);
  if (count >= 100) return false;
  await kv.put(key, String(count + 1), { expirationTtl: 120 });
  return true;
}

async function fetchFeatureFlags(kv: KVNamespace, userId: string): Promise<Record<string, boolean>> {
  const raw = await kv.get(`flags:${userId}`, "json");
  return (raw as Record<string, boolean>) ?? {};
}
```

---

## Caching Middleware Results in the Request Locals

Avoid re-running the same KV or D1 query when multiple middleware layers need the same data:

```typescript
// functions/_middleware.ts — root middleware fetches user record once
import type { EventContext } from "@cloudflare/workers-types";

interface Env { USERS_KV: KVNamespace }
interface UserRecord { id: string; tier: "free" | "pro"; region: string }

export async function onRequest(ctx: EventContext<Env, string, { user?: UserRecord }>) {
  const userId = ctx.request.headers.get("X-User-Id");
  if (userId) {
    // Stored in ctx.data — available to all downstream middleware and route handlers
    ctx.data.user = await ctx.env.USERS_KV.get<UserRecord>(`user:${userId}`, "json") ?? undefined;
  }
  return ctx.next();
}

// functions/api/_middleware.ts — consumes without re-fetching
export async function onRequest(ctx: EventContext<Env, string, { user?: UserRecord }>) {
  if (ctx.data.user?.tier !== "pro") {
    return new Response("Upgrade required", { status: 402 });
  }
  return ctx.next();
}
```

---

## Early-Return Patterns to Minimise Response Time

Route-level middleware should exit as early as possible on the happy path:

```typescript
// functions/api/upload/_middleware.ts
import type { EventContext } from "@cloudflare/workers-types";

interface Env { MAX_UPLOAD_MB: string }

export async function onRequest(ctx: EventContext<Env, string, unknown>) {
  const method = ctx.request.method;

  // Only validate uploads—pass everything else immediately
  if (method !== "POST" && method !== "PUT") {
    return ctx.next();
  }

  const contentLength = Number(ctx.request.headers.get("Content-Length") ?? 0);
  const maxBytes = Number(ctx.env.MAX_UPLOAD_MB) * 1024 * 1024;

  if (contentLength > maxBytes) {
    return new Response(`Payload too large (max ${ctx.env.MAX_UPLOAD_MB} MB)`, {
      status: 413,
    });
  }

  return ctx.next();
}
```

---

## Measuring Middleware Latency with Server-Timing

Instrument individual middleware phases to find the slowest segment:

```typescript
// functions/_middleware.ts
export async function onRequest(
  ctx: EventContext<{ AI: Ai }, string, { timings: string[] }>
) {
  ctx.data.timings = [];
  const start = Date.now();

  const response = await ctx.next();

  // Append aggregate middleware wall time
  const total = Date.now() - start;
  const serverTiming = [
    ...ctx.data.timings,
    `middleware-total;dur=${total}`,
  ].join(", ");

  // Merge with any Server-Timing already set by the handler
  const existing = response.headers.get("Server-Timing");
  const merged = existing ? `${existing}, ${serverTiming}` : serverTiming;

  const mutable = new Response(response.body, response);
  mutable.headers.set("Server-Timing", merged);
  return mutable;
}
```

---

## Anti-patterns

- **Awaiting KV / D1 sequentially per middleware file**: each sequential await adds a network round-trip. Batch into `Promise.all` or move to a single root-middleware fetch.
- **Importing crypto/JWT libraries at module scope in every middleware file**: the library is shared across the isolate, but the import evaluation itself runs on each cold start for every middleware file in the chain.
- **Running auth checks on static asset paths**: `/assets/`, `/fonts/`, and Cloudflare Pages' built-in `/__cf_*` paths are served from cache before they reach middleware in some configurations; double-checking wastes CPU on paths that won't be affected.
- **Constructing a new `Response` to add headers on every request**: cloning `Response` is cheap but not free. If no mutation is needed, return the original.

## Gotchas

- Pages Functions middleware runs **before** Cloudflare's edge cache lookup for dynamic routes, but **static assets** served from Pages' asset store bypass Functions entirely—`_middleware.ts` does not run for them unless the request reaches an unmatched Functions route first.
- `ctx.data` is a plain object shared by reference across the middleware chain within a single request. Mutating it in parallel middleware (race on `ctx.data.x = …`) is safe only if you write to distinct keys.
- Middleware at a **parent directory** level runs for all child routes, including routes you did not intend to protect. Scope rate-limit logic in a child `_middleware.ts` rather than the root to avoid blocking static routes.
- Pages Functions have a **10 MB compressed bundle limit** per `_worker.js`. Middleware that imports large libraries contributes to this cap and can cause deploy failures.

## Verification

```bash
# Check Server-Timing headers after instrumenting middleware
curl -s -D - https://your-pages-site.pages.dev/api/hello \
  | grep -i "server-timing"
# Expected: Server-Timing: auth;dur=12, flags;dur=3, middleware-total;dur=18

# Measure cold vs warm median with hey
hey -n 200 -c 10 https://your-pages-site.pages.dev/api/hello \
  | grep -E "Average|P(50|95|99)"
```

Open the Workers & Pages dashboard → **Functions** → **CPU Time** histogram. The 99th-percentile CPU time should stay under 10 ms for middleware-only overhead. Trace spikes with `wrangler pages deployment tail`.

## Related

- `pages-functions-bundle-size-optimization.md`
- `pages-static-asset-chunking-code-split.md`
- `workers-middleware-chain-performance.md`
- `workers-service-binding-latency.md`
- `kv-read-performance.md`

## Sources

- Cloudflare Pages Functions Middleware: https://developers.cloudflare.com/pages/functions/middleware/
- Pages Functions Routing: https://developers.cloudflare.com/pages/functions/routing/
- Workers CPU time limits: https://developers.cloudflare.com/workers/platform/limits/#cpu-time
