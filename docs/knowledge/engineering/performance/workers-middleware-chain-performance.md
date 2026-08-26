# Workers Middleware Chain Performance

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Cloudflare Worker composed of multiple middleware layers (auth, rate-limit, cache, logging) accumulates 10–50 ms of overhead per layer due to redundant header parsing, repeated `request.clone()` calls, and sequential awaits that could be parallelised. Restructuring the middleware chain eliminates this overhead.

## Context
Middleware in Workers is typically implemented as a chain of async functions that each receive a `Request` and call a `next()` function to delegate to the next layer. Naively, each layer re-parses the URL, re-reads headers it doesn't own, and clones the request defensively. In Workers, `request.clone()` copies the body buffer and is expensive for large bodies. Sequential awaits in middleware prevent work that could run in parallel. Careful middleware design recovers most of this overhead with minimal structural change.

## Typed Middleware Contract

Define a lean middleware type to avoid ambiguity between layers:

```typescript
type Next = () => Promise<Response>;
type Middleware = (request: Request, env: Env, ctx: ExecutionContext, next: Next) => Promise<Response>;

function compose(...middlewares: Middleware[]): ExportedHandlerFetchHandler<Env> {
  return async (request: Request, env: Env, ctx: ExecutionContext): Promise<Response> => {
    let index = -1;
    async function dispatch(i: number): Promise<Response> {
      if (i <= index) throw new Error("next() called multiple times");
      index = i;
      const middleware = middlewares[i];
      if (!middleware) return new Response("Not Found", { status: 404 });
      return middleware(request, env, ctx, () => dispatch(i + 1));
    }
    return dispatch(0);
  };
}

export default { fetch: compose(authMiddleware, rateLimitMiddleware, cacheMiddleware, routerMiddleware) };
```

## Parsing Headers Once with a Context Object

Parse shared data once at the entry point and pass it via a `WeakMap`-keyed context to avoid re-parsing:

```typescript
interface RequestContext {
  url: URL;
  authToken: string | null;
  country: string;
}

const ctxMap = new WeakMap<Request, RequestContext>();

function getCtx(request: Request): RequestContext {
  if (!ctxMap.has(request)) {
    ctxMap.set(request, {
      url: new URL(request.url),
      authToken: <redacted-secret>"authorization"),
      country: (request as any).cf?.country ?? "XX",
    });
  }
  return ctxMap.get(request)!;
}

const authMiddleware: Middleware = async (request, env, ctx, next) => {
  const { authToken } = getCtx(request);
  if (!authToken) return new Response("Unauthorized", { status: 401 });
  // Verify token without re-reading headers
  return next();
};

const rateLimitMiddleware: Middleware = async (request, env, ctx, next) => {
  const { url, country } = getCtx(request); // No re-parse
  const key = `${country}:${url.pathname}`;
  const allowed = await checkRateLimit(env, key);
  if (!allowed) return new Response("Too Many Requests", { status: 429 });
  return next();
};
```

## Parallel Pre-flight Checks

Run independent middleware checks in parallel before any of them can short-circuit:

```typescript
const parallelGuardMiddleware: Middleware = async (request, env, ctx, next) => {
  const { authToken, url } = getCtx(request);

  // Run auth and rate-limit checks simultaneously
  const [authResult, rateLimitResult] = await Promise.all([
    verifyToken(authToken, env.JWT_SECRET),
    checkRateLimit(env, url.pathname),
  ]);

  if (!authResult.valid) return new Response("Unauthorized", { status: 401 });
  if (!rateLimitResult.allowed) return new Response("Too Many Requests", { status: 429 });

  return next();
};

async function verifyToken(token: string | null, secret: string): Promise<{ valid: boolean }> {
  if (!token) return { valid: false };
  try {
    // Lightweight HMAC verify — no network call
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"],
    );
    const [header, payload, sig] = token.replace("Bearer ", "").split(".");
    const data = new TextEncoder().encode(`${header}.${payload}`);
    const sigBytes = Uint8Array.from(atob(sig.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
    const valid = await crypto.subtle.verify("HMAC", key, sigBytes, data);
    return { valid };
  } catch {
    return { valid: false };
  }
}
```

## Streaming Response Passthrough

Avoid buffering the response body in middleware that only modifies headers:

```typescript
const addHeadersMiddleware: Middleware = async (request, env, ctx, next) => {
  const response = await next();

  // Construct new Headers without touching the body
  const headers = new Headers(response.headers);
  headers.set("x-powered-by", "Cloudflare Workers");
  headers.set("x-request-id", crypto.randomUUID());
  headers.set("timing-allow-origin", "*");

  // Stream body directly — no buffering
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};
```

## Avoiding Clone in Logging Middleware

Logging middleware often clones the response to read the body for debug logs. Avoid this in production — use `tee` only when sampling:

```typescript
const SAMPLE_RATE = 0.01; // 1% sampling

const loggingMiddleware: Middleware = async (request, env, ctx, next) => {
  const start = Date.now();
  const { url } = getCtx(request);

  const response = await next();
  const duration = Date.now() - start;

  // Log metadata only — never clone response body in production
  ctx.waitUntil(
    env.ANALYTICS.writeDataPoint({
      blobs: [url.pathname, response.status.toString()],
      doubles: [duration],
      indexes: [url.hostname],
    }),
  );

  // Expensive body logging only on sampled requests
  if (Math.random() < SAMPLE_RATE) {
    const [a, b] = response.clone().body!.tee();
    ctx.waitUntil(logBody(b, env));
    return new Response(a, { status: response.status, headers: response.headers });
  }

  return response;
};

async function logBody(stream: ReadableStream, env: Env): Promise<void> {
  const text = await new Response(stream).text();
  console.log("sampled body:", text.slice(0, 512));
}
```

## Anti-patterns
- Calling `request.clone()` in every middleware layer — each clone copies the body buffer and adds GC pressure
- Sequential `await` for independent checks (auth, rate-limit, geo-block) — run them with `Promise.all`
- Re-parsing `new URL(request.url)` in multiple middleware — URL construction allocates; parse once and share
- Using `response.json()` in middleware that only needs a header — it buffers the entire body unnecessarily

## Gotchas
- `WeakMap`-keyed context is garbage-collected with the `Request` object; no manual cleanup needed
- `response.body.tee()` in logging creates two streams; if the main stream is not consumed the Worker may leak memory in long-running requests
- `crypto.subtle` operations are asynchronous but CPU-bound — parallelising two `subtle.verify` calls does not reduce CPU time, only wall time
- `ctx.waitUntil` is essential for fire-and-forget analytics; without it the Worker may be terminated before the write completes

## Verification
1. Add `server-timing` markers at each middleware boundary and compare total overhead before/after parallelisation
2. Use `wrangler dev --inspector-port 9229` and Chrome DevTools to profile CPU time per middleware function
3. Run `wrk -t4 -c100 -d30s <worker-url>` load test and compare P95 latency with and without parallel guard middleware
4. Check Worker CPU time in Cloudflare Workers Analytics — middleware overhead should be < 2 ms for non-compute layers

## Related
- [workers-cpu-time-optimization.md](workers-cpu-time-optimization.md)
- [workers-cold-start-optimization.md](workers-cold-start-optimization.md)
- [workers-response-streaming-ttfb-optimization.md](workers-response-streaming-ttfb-optimization.md)
- [api-rate-limiting-algorithms.md](api-rate-limiting-algorithms.md)

## Sources
- Cloudflare Workers Runtime API: Request — https://developers.cloudflare.com/workers/runtime-apis/request/
- MDN: ReadableStream.tee() — https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream/tee
- Hono.js source: middleware composition patterns — https://github.com/honojs/hono
