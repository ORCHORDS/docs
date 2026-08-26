# workers-best-practices

**Issue:** Workers best practices — performance, cost, limits
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Worker is slow. The CPU time is 100ms. The
response time is 500ms. You don't know where the time
goes.

## Root cause
**Workers have specific patterns.** Optimize for them.

**Source:** CF Workers docs.

## The "cold start" pattern

For cold start:
- **Minimize imports:** Smaller bundle = faster start
- **Avoid top-level await:** Blocks the event loop
- **Lazy load:** Dynamic imports

```ts
// ❌ Bad: top-level await
const config = await fetch('https://api.example.com/config').then(r => r.json());

// ✅ Good: lazy
async function getConfig() {
  return fetch('https://api.example.com/config').then(r => r.json());
}
```

The cold start is fast.

## The "memory" pattern

For memory:
- **Minimize closures:** Hold less
- **Use streams:** For large data
- **Stream the response:** Don't buffer

```ts
// ❌ Bad: buffer the whole response
const response = await fetch('https://api.example.com/data');
const text = await response.text();

// ✅ Good: stream
const response = await fetch('https://api.example.com/data');
return new Response(response.body, response);
```

The memory is minimized.

## The "CPU" pattern

For CPU:
- **Offload heavy work:** Use a queue
- **Cache:** Reduce repeated work
- **Optimize loops:** Avoid O(n²)

```ts
// ❌ Bad: O(n²)
for (const a of items) {
  for (const b of items) {
    if (a.id === b.id) { /* ... */ }
  }
}

// ✅ Good: O(n) with a Map
const map = new Map(items.map(i => [i.id, i]));
for (const a of items) {
  const b = map.get(a.id);
  // ...
}
```

The CPU is optimized.

## The "streaming" pattern

For streaming, use ReadableStream:
```ts
function streamResponse(items: Item[]): Response {
  const stream = new ReadableStream({
    start(controller) {
      for (const item of items) {
        controller.enqueue(new TextEncoder().encode(JSON.stringify(item) + '\n'));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: { 'content-type': 'application/x-ndjson' },
  });
}
```

The response is streamed.

## The "waitUntil" pattern

For background work, use `ctx.waitUntil`:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // 1. Return immediately
    const response = new Response('OK');

    // 2. Background work (continues after response)
    ctx.waitUntil(doBackgroundWork(env));

    return response;
  },
};
```

The work continues in the background.

## The "binding" pattern

For bindings, the env is the DI:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Use env.DB, env.R2, env.KV, env.AI, etc.
    const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind('u_1').first();
    return Response.json(user);
  },
};
```

The bindings are the deps.

## The "CPU limit" pattern

For CPU limits:
- **Free:** 10ms
- **Paid:** 30s (default), 5min (unbound)
- **Long-running:** Use a queue

```toml
# wrangler.toml - longer CPU
[limits]
cpu_ms = 300000  # 5 min
```

The limit is configured.

## The "Worker limits" pattern

For Worker limits:
- **CPU time:** 30s (paid)
- **Memory:** 128MB
- **Bundle size:** 10MB
- **Subrequests:** 50 per request
- **Response size:** 6MB (CF) / unlimited (custom domain)

The limits are checked.

## The "caching" pattern

For caching:
- **Cache API:** `caches.default`
- **Cache-Control:** Browser/CDN cache
- **Stale-While-Revalidate:** Stale + refresh

```ts
const cache = caches.default;
const cached = await cache.match(request);
if (cached) return cached;

const response = await fetchFromOrigin(env);
const cacheable = new Response(response.body, {
  status: response.status,
  headers: { 'cache-control': 'public, max-age=300' },
});
await cache.put(request, cacheable.clone());

return response;
```

The response is cached.

## The "rate limit" pattern

For rate limiting:
- **Per-IP:** Use CF header
- **Per-user:** In the handler
- **Headers:** IETF standard

```ts
const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
// Use a rate limit check
```

The rate limit is enforced.

## The "auth" pattern

For auth:
- **JWT:** In a cookie or header
- **API key:** In a header
- **Session:** In a cookie

```ts
const auth = request.headers.get('authorization');
if (!auth?.startsWith('Bearer ')) {
  return new Response('Unauthorized', { status: 401 });
}
const token = auth.slice(7);
const user = await verifyToken(token, env);
if (!user) return new Response('Unauthorized', { status: 401 });
```

The auth is verified.

## The "error handling" pattern

For errors:
- **Try-catch:** Around the handler
- **Structured logs:** With context
- **Return proper status:** 4xx / 5xx

```ts
try {
  return await handleRequest(request, env);
} catch (err) {
  logEvent('error', 'error', { error: String(err), url: request.url });
  return new Response('Internal error', { status: 500 });
}
```

The error is handled.

## The "Worker observability" pattern

For observability:
- **Worker Analytics:** CF dashboard
- **Workers Logs:** Tail logs
- **Custom metrics:** Analytics Engine

```ts
metrics.increment('worker.requests_total', { endpoint: '/api/users' });
metrics.histogram('worker.duration_ms', duration, { endpoint: '/api/users' });
```

The Worker is monitored.

## The "Worker anti-pattern" anti-patterns

### 1. Top-level await
- **Issue:** Cold start
- **Fix:** Lazy

### 2. Heavy sync work
- **Issue:** CPU timeout
- **Fix:** Queue

### 3. Buffer large responses
- **Issue:** Memory
- **Fix:** Stream

### 4. No cache
- **Issue:** Repeat work
- **Fix:** Cache

### 5. Tight loop
- **Issue:** CPU
- **Fix:** Optimize

## Verification
- **Test:** Cold start is fast (< 50ms)
- **Test:** CPU is low
- **Test:** Cache works
- **Live:** Worker metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "top-level await" anti-pattern.** Lazy.
- **The "heavy sync work" anti-pattern.** Queue.
- **The "buffer large" anti-pattern.** Stream.

## Related
- `cloudflare/workers-resource-limits.md`
- `cloudflare/workers-cache-api.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `cloudflare/workers-rpc.md`
- `cloudflare/durable-objects-patterns.md`
- CF docs: https://developers.cloudflare.com/workers/
