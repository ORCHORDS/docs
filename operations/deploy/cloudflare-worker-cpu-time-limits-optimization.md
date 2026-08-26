# cloudflare-worker-cpu-time-limits-optimization

**Issue:** Managing Cloudflare Worker CPU time limits (50ms bundled
plan) — profiling, offloading, streaming, and mobile client retry
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

Worker requests fail intermittently with HTTP 503 and the Cloudflare
error code `1102` ("Worker exceeded CPU time limit"). The failures
cluster around specific endpoints — typically image processing,
PDF generation, or complex JSON transformation — and spike during
mobile traffic bursts when the payload size is larger than typical
desktop requests. Mobile clients with no retry logic show these as
blank screens or stalled loading spinners.

## Context

Cloudflare Workers on the **Bundled** plan are limited to **50 ms of
CPU time per request** (not wall-clock time — I/O await does not
count). The **Unbound** plan raises this to 30 seconds of CPU time.
Exceeding the 50 ms limit causes an immediate `1102` response;
the Worker is not given extra time. Heavy work such as synchronous
crypto, in-memory sorting of large arrays, or third-party WASM
modules are the typical culprits.

**Source:** Cloudflare Docs — Limits; Cloudflare Blog — Workers CPU
time profiling.

## CPU time plan comparison

```
+-------------------+-----------+-----------+---------------------+
| Plan              | CPU limit | Wall-clock| Pricing             |
+-------------------+-----------+-----------+---------------------+
| Free              | 10 ms     | 30 s (I/O)| Free (100k req/day) |
| Bundled (default) | 50 ms     | 30 s (I/O)| $5/mo (10M req)     |
| Unbound           | 30 s      | 30 s (I/O)| $0.02/M req-s       |
+-------------------+-----------+-----------+---------------------+
```

Upgrade to Unbound only after verifying the work genuinely needs more
than 50 ms. Optimising first can bring 90% of cases back under 50 ms.

## The "profiling CPU-heavy handlers" pattern

Use `Date.now()` checkpoints inside the handler during development.
Cloudflare does not expose a CPU-time API, but wall-clock deltas
around synchronous code (with no awaits between checkpoints) are a
reasonable approximation:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const t0 = Date.now();

    const body = await req.json() as { items: unknown[] };

    const t1 = Date.now();
    const transformed = heavyTransform(body.items); // synchronous
    const t2 = Date.now();

    const result = await env.DB.prepare(
      "INSERT INTO results VALUES (?)",
    ).bind(JSON.stringify(transformed)).run();
    const t3 = Date.now();

    console.log(JSON.stringify({
      parseMs:     t1 - t0,
      transformMs: t2 - t1,  // <-- this is CPU time
      dbMs:        t3 - t2,  // <-- this is I/O (doesn't count)
    }));

    return Response.json(result);
  },
};
```

Check `transformMs` in Cloudflare Workers Logs (Tail Workers or
`wrangler tail`). Any synchronous block over 10 ms is a candidate
for offloading.

## The "offload to Cloudflare Queues" pattern

For work that does not need a synchronous response, push to a Queue
and return a 202 immediately. The Queue consumer runs in a separate
Worker invocation with its own CPU budget:

```typescript
// Producer Worker — returns in <5 ms
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const payload = await req.json();
    await env.WORK_QUEUE.send(payload);
    return new Response(null, { status: 202 });
  },
};
```

```typescript
// Consumer Worker — heavy work happens here
export default {
  async queue(
    batch: MessageBatch<unknown>,
    env: Env,
  ): Promise<void> {
    for (const msg of batch.messages) {
      await heavyTransform(msg.body, env);
      msg.ack();
    }
  },
};
```

```toml
# wrangler.toml (consumer Worker)
[[queues.consumers]]
queue          = "work-queue"
max_batch_size = 10
max_retries    = 3
```

The mobile client polls a status endpoint or subscribes to a
WebSocket / Server-Sent Event for the result.

## The "streaming response to avoid timeout" pattern

For large response payloads, stream the output using
`TransformStream` so the CPU budget is consumed in small chunks
across multiple ticks, rather than one large synchronous block:

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    // Start streaming immediately; run heavy work in the background
    const work = (async () => {
      const rows = await env.DB.prepare("SELECT * FROM large_table")
        .all();

      for (const row of rows.results) {
        // Each JSON.stringify + write yields to the event loop
        await writer.write(
          encoder.encode(JSON.stringify(row) + "\n"),
        );
      }
      await writer.close();
    })();

    // Return the readable stream before work is complete
    const response = new Response(readable, {
      headers: { "Content-Type": "application/x-ndjson" },
    });

    // Ensure the work promise is tracked (Workers tracks ctx.waitUntil
    // for cleanup, but the stream keeps the request alive here)
    return response;
  },
};
```

Each `writer.write()` yields the event loop, distributing CPU
across multiple microtasks and reducing peak CPU per tick.

## The "mobile client retry on 503" pattern

Mobile clients should distinguish a transient `1102` CPU overrun
(503) from a permanent error. Apply exponential backoff with a
short initial delay:

```swift
// iOS — URLSession retry wrapper (Swift)
func fetch(url: URL, attempt: Int = 0) async throws -> Data {
    let (data, response) = try await URLSession.shared.data(from: url)
    let http = response as! HTTPURLResponse
    if http.statusCode == 503 && attempt < 3 {
        let delay = pow(2.0, Double(attempt)) * 0.5  // 0.5s, 1s, 2s
        try await Task.sleep(nanoseconds: UInt64(delay * 1e9))
        return try await fetch(url: url, attempt: attempt + 1)
    }
    guard http.statusCode == 200 else {
        throw APIError.http(http.statusCode)
    }
    return data
}
```

```kotlin
// Android — Retrofit + OkHttp interceptor (Kotlin)
class RetryInterceptor(private val maxRetries: Int = 3) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        var attempt = 0
        var response: Response
        do {
            response = chain.proceed(chain.request())
            if (response.code != 503) return response
            response.close()
            Thread.sleep((500L * (1 shl attempt)))
            attempt++
        } while (attempt <= maxRetries)
        return response
    }
}
```

Cap retries at 3; surface a user-visible error after the third
failure rather than spinning silently.

## Anti-patterns

- **Synchronous WASM image encoding in a fetch handler.** WASM
  modules are fast but still consume CPU; a 512 KB PNG encode easily
  exceeds 50 ms. Offload to Queues or Cloudflare Images.
- **Running `JSON.parse` on megabyte payloads synchronously.**
  Large JSON parses are CPU-bound. Stream the request body with a
  streaming JSON parser, or gate request size at 64 KB.
- **Upgrading to Unbound without profiling first.** Unbound costs
  more and the underlying problem may be solvable in under 50 ms.
- **Retrying on the mobile client with no backoff.** A 503 storm
  from many mobile retrying simultaneously amplifies the CPU
  overrun and causes a cascade.
- **Ignoring `cf-ray` in retry logic.** Log the `cf-ray` header
  from the 503 response; it links to the specific Worker invocation
  in Cloudflare Logs for debugging.

## Gotchas

- CPU time limit is per-request, not per-Worker. A single Worker
  can handle many concurrent requests; each gets its own 50 ms
  budget independently.
- `crypto.subtle` operations (e.g. `importKey`, `sign`) are
  partially async but some phases are synchronous. Profile them
  individually.
- `wrangler tail` shows CPU time in the invocation log for each
  request: `"cpuTime": 48` (milliseconds). Set up an alert if
  p95 cpuTime exceeds 40 ms — you need headroom.
- Queue consumer Workers on the Bundled plan also have a 50 ms
  CPU limit *per message batch call*, not per message. Process
  fewer items per batch if each item is CPU-heavy.

## Verification

- **Profiling:** `wrangler tail --env production --format pretty`
  shows `cpuTime` per request. Confirm heavy endpoints are below
  40 ms after optimisation.
- **503 rate:** Cloudflare dashboard → Workers → Error rate chart
  shows `1102` errors drop to 0 after offloading heavy work.
- **Mobile:** Run the retry path in a network test (Charles Proxy
  or similar), inject 503 responses, and confirm the client retries
  3 times with backoff and then surfaces an error UI.

## Related

- `documentation/categories/deploy/wrangler-deploy-github-actions-workers.md`
- `documentation/categories/deploy/canary-workers-gradual-traffic-split.md`
- `documentation/categories/deploy/deploy-cold-start-prewarming.md`
- `documentation/categories/ai-ml/llm-streaming-responses.md`
- `documentation/categories/ai-ml/llm-timeout-handling.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/queues/reference/configuration/
- https://developers.cloudflare.com/workers/observability/\
  logs/workers-logs/
