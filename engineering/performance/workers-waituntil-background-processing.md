# Workers waitUntil Background Processing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
A Cloudflare Worker response is delayed because logging, cache priming, or analytics writes block the request path. Moving that work off the critical path with `ctx.waitUntil()` recovers 30–120 ms of tail latency without sacrificing observability.

## Context
Every Workers invocation has two time budgets: the CPU time budget that gates the response, and a separate `waitUntil` budget that keeps the isolate alive after `Response` is returned. Background tasks registered via `ctx.waitUntil(promise)` run concurrently once the response is sent, up to the platform limit (typically 30 s wall-clock, same CPU budget as the foreground). Misusing `waitUntil` — awaiting it before `return`, nesting it inside other async chains, or using it for truly critical writes — is the most common source of avoidable response latency.

## Pattern 1 — Fire-and-Forget Analytics Write

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const response = await handleRequest(request, env);

    // Do NOT await — register as background work
    ctx.waitUntil(
      writeAnalytics(env, {
        url: request.url,
        status: response.status,
        durationMs: Date.now() - start,
        cf: request.cf,
      })
    );

    return response;
  },
};

async function writeAnalytics(env: Env, data: AnalyticsRow): Promise<void> {
  // Analytics Engine write — non-critical, safe to do post-response
  env.ANALYTICS.writeDataPoint({
    blobs: [data.url, String(data.status)],
    doubles: [data.durationMs],
    indexes: [new URL(data.url).pathname.slice(0, 32)],
  });
}
```

## Pattern 2 — Cache Priming After Cache Miss

```typescript
async function fetchWithCachePrime(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) return cached;

  const origin = await fetch(request);
  if (!origin.ok) return origin;

  // Clone before consuming — cache.put() consumes the body
  const toCache = origin.clone();
  const cacheControl = origin.headers.get("Cache-Control") ?? "public, max-age=60";

  ctx.waitUntil(
    cache.put(
      request,
      new Response(toCache.body, {
        status: toCache.status,
        headers: {
          ...Object.fromEntries(toCache.headers),
          "Cache-Control": cacheControl,
        },
      }),
    ),
  );

  return origin;
}
```

## Pattern 3 — Batched KV Write After Response

```typescript
// Accumulate writes across the request, flush post-response
interface PendingWrite {
  key: string;
  value: string;
  expirationTtl?: number;
}

async function flushKvWrites(env: Env, writes: PendingWrite[]): Promise<void> {
  await Promise.allSettled(
    writes.map((w) =>
      env.KV.put(w.key, w.value, w.expirationTtl ? { expirationTtl: w.expirationTtl } : undefined),
    ),
  );
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const pendingWrites: PendingWrite[] = [];

    const response = await handleRequest(request, env, pendingWrites);

    if (pendingWrites.length > 0) {
      ctx.waitUntil(flushKvWrites(env, pendingWrites));
    }

    return response;
  },
};
```

## Pattern 4 — Parallel Background Fan-Out

```typescript
// Multiple independent post-response tasks, all registered on one waitUntil
async function runPostResponseTasks(
  request: Request,
  env: Env,
  response: Response,
  durationMs: number,
): Promise<void> {
  await Promise.allSettled([
    // Purge stale downstream cache entries
    purgeEdgeCacheEntries(env, response.headers.get("X-Cache-Tags") ?? ""),
    // Write audit log to D1
    appendAuditLog(env.DB, {
      method: request.method,
      path: new URL(request.url).pathname,
      status: response.status,
      durationMs,
      ts: Date.now(),
    }),
    // Notify downstream webhook on writes
    request.method !== "GET"
      ? notifyWebhook(env.WEBHOOK_SECRET, request, response)
      : Promise.resolve(),
  ]);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const t0 = Date.now();
    const response = await handleRequest(request, env);

    ctx.waitUntil(runPostResponseTasks(request, env, response, Date.now() - t0));

    return response;
  },
};
```

## Pattern 5 — Deferred Queue Enqueue to Smooth Bursts

```typescript
// Collecting queue messages during request processing is fine,
// but the actual enqueue can happen post-response to hide network RTT.
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const events: Record<string, unknown>[] = [];
    const response = await handleRequest(request, env, events);

    if (events.length > 0) {
      ctx.waitUntil(
        env.EVENT_QUEUE.sendBatch(
          events.map((body) => ({ body })),
        ),
      );
    }

    return response;
  },
};
```

## Anti-patterns
- Awaiting `ctx.waitUntil()` before `return` — this negates the entire benefit; `waitUntil` accepts a Promise, not a value you need to await yourself
- Registering database writes that must be consistent before the response (e.g., payment records) as background tasks — use `waitUntil` only for idempotent or fire-and-forget operations
- Calling `ctx.waitUntil()` inside the background Promise itself — nesting is not supported; register all tasks at the top-level handler
- Running CPU-intensive work (e.g., large JSON transforms, crypto) as background tasks without accounting for the shared CPU budget
- Ignoring errors from `waitUntil` promises — always wrap with `Promise.allSettled` or `.catch()` to prevent unhandled rejections that may silently abort the background work

## Gotchas
- `waitUntil` wall-clock limit is 30 s by default; tasks that exceed it are killed without retries — ensure background work is bounded
- If the Worker is invoked via a Durable Object RPC, `ctx.waitUntil()` is available but the DO instance may hibernate before the task completes; prefer the DO's own alarm for long-running post-response work
- `caches.default.put()` inside `waitUntil` works correctly in production but is a no-op in `wrangler dev` local mode — test with `wrangler dev --remote` for cache interactions
- CPU time consumed by `waitUntil` tasks counts toward the total invocation budget and can trigger `Exceeded CPU time` errors even after the response is sent
- Response cloning (`response.clone()`) must happen before the response body is consumed by the caller — clone before returning if you need to read the body inside a background task

## Verification
```bash
# Confirm background task latency is excluded from response timing
wrangler tail --format json | jq '.outcome, .wallTime, .cpuTime'

# Look for 'waitUntil exceeded' in tail logs
wrangler tail --format json | jq 'select(.exceptions[].name == "Error") | .exceptions'

# Synthetic request timing comparison (with vs without waitUntil offload)
curl -o /dev/null -s -w "time_total: %{time_total}\n" https://example.workers.dev/endpoint
```

## Related
- `workers-subrequest-fanout-parallelism.md`
- `workers-queues-background-offload.md`
- `analytics-engine-write-throughput-batching.md`
- `kv-pipeline-bulk-operations-workers.md`
- `durable-objects-alarm-write-coalescing.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/context/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/queues/reference/how-queues-works/
