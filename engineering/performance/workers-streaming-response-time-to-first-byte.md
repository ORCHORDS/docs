# Optimising Time-to-First-Byte with Streaming Responses in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Server-Rendered HTML pages show high TTFB in Chrome DevTools / Web Vitals even though the Workers CPU time is low. The browser receives nothing until the entire response body is assembled — often blocked on a downstream database or API call that feeds the page footer or a sidebar widget. Users experience a blank screen, Largest Contentful Paint is delayed, and Core Web Vitals scores suffer.

## Context

HTTP/1.1 and HTTP/2 both support chunked / streaming response bodies. A Cloudflare Worker can return a `Response` whose body is a `ReadableStream` rather than a fully-buffered string. The browser renders HTML incrementally as chunks arrive, so the `<head>` and above-the-fold content can appear before slower data (user-specific widgets, analytics, recommendations) is even fetched.

The pattern is sometimes called "out-of-order streaming" or "streaming SSR" and mirrors what React's `renderToPipeableStream` does server-side, but implemented directly in Workers without a framework.

Key primitives:
- `TransformStream` — a {writable, readable} pair; write chunks to `writable.getWriter()`, consume from `readable`.
- `ReadableStream` with an underlying source `pull` function — lazy, backpressure-aware chunk generation.
- `enqueue` / `close` on a `ReadableStreamDefaultController` for push-based streaming.
- Workers Analytics Engine — for logging real TTFB from the edge perspective.

## Solution

### Pattern 1 — TransformStream for incremental HTML

```typescript
// src/streaming-html.ts

export async function streamHtmlResponse(
  request: Request,
  env: Env
): Promise<Response> {
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const enc = new TextEncoder();

  const write = (html: string) =>
    writer.write(enc.encode(html));

  // Start streaming the response immediately — the async body builds in background.
  // Workers will flush chunks as soon as they are written.
  const responsePromise = new Response(readable, {
    headers: {
      'content-type': 'text/html; charset=utf-8',
      // Disable nginx / CDN buffering so chunks reach the browser immediately.
      'x-accel-buffering': 'no',
      // Transfer-Encoding: chunked is set automatically when body is a stream.
    },
  });

  // Build the body asynchronously — this runs concurrently with the response
  // being sent to the client.
  (async () => {
    try {
      // 1. Critical above-the-fold content — flushed immediately.
      await write(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Dashboard</title>
  <link rel="stylesheet" >
</head>
<body>
<header>
  <nav><!-- static nav --></nav>
</header>
<main>
`);

      // 2. Fetch primary data and stream as soon as it arrives.
      const primaryData = await fetchPrimaryData(env);
      await write(`
  <section class="hero">
    <h1>${escapeHtml(primaryData.title)}</h1>
    <p>${escapeHtml(primaryData.summary)}</p>
  </section>
`);

      // 3. Placeholder for slow widgets — renders immediately, hydrated later.
      await write(`
  <section class="widgets" id="widgets">
    <div class="skeleton" aria-busy="true">Loading recommendations…</div>
  </section>
`);

      // 4. Slow secondary data — browser already has above-the-fold rendered.
      const [recommendations, recentActivity] = await Promise.all([
        fetchRecommendations(env, primaryData.userId),
        fetchRecentActivity(env, primaryData.userId),
      ]);

      // 5. Inline script that replaces the skeleton with real content.
      await write(`
  <script>
    document.getElementById('widgets').innerHTML = ${JSON.stringify(
      renderWidgetsHtml(recommendations, recentActivity)
    )};
  </script>
`);

      // 6. Footer & closing tags.
      await write(`
</main>
<footer>© 2026 example.com</footer>
</body>
</html>
`);
    } catch (err) {
      // Surface error as an inline HTML comment — never swallow silently.
      await write(`<!-- stream error: ${String(err)} -->`);
      // Optionally write an error UI here.
    } finally {
      await writer.close();
    }
  })();

  return responsePromise;
}
```

### Pattern 2 — Streaming JSON with ReadableStream

```typescript
// src/streaming-json.ts
// Useful for large datasets: stream a JSON array line-by-line (NDJSON / JSON streaming).

export function streamJsonArray<T>(
  source: AsyncIterable<T>
): Response {
  const enc = new TextEncoder();
  let first = true;

  const readable = new ReadableStream<Uint8Array>({
    async pull(controller) {
      // Fetch one item at a time; WritableStream provides backpressure.
      for await (const item of source) {
        const prefix = first ? '[' : ',';
        first = false;
        controller.enqueue(
          enc.encode(`${prefix}${JSON.stringify(item)}\n`)
        );
        // Yield control so the runtime can flush and apply backpressure.
        return;
      }
      // Close the JSON array.
      controller.enqueue(enc.encode(first ? '[]' : ']'));
      controller.close();
    },
  });

  return new Response(readable, {
    headers: {
       'content-type': 'application/json',
      'transfer-encoding': 'chunked',
    },
  });
}

// Usage:
const rows = db.query('SELECT * FROM events ORDER BY ts DESC').iterable();
return streamJsonArray(rows);
```

### Pattern 3 — Measuring TTFB via Analytics Engine

```typescript
// src/ttfb-instrumentation.ts
import { Env } from './types';

export function instrumentTtfb(
  response: Response,
  env: Env,
  requestStart: number,
  pathname: string
): Response {
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();

  let firstChunkWritten = false;

  const instrumentedReadable = new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = response.body!.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            controller.close();
            break;
          }
          if (!firstChunkWritten) {
            firstChunkWritten = true;
            const ttfbMs = Date.now() - requestStart;

            // Write to Analytics Engine (non-blocking).
            env.ANALYTICS.writeDataPoint({
              blobs: [pathname],
              doubles: [ttfbMs],
              indexes: ['ttfb'],
            });
          }
          controller.enqueue(value);
        }
      } catch (err) {
        controller.error(err);
      }
    },
  });

  return new Response(instrumentedReadable, {
    status: response.status,
    headers: response.headers,
  });
}

// In worker fetch handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    const response = await streamHtmlResponse(request, env);
    return instrumentTtfb(response, env, start, new URL(request.url).pathname);
  },
};
```

### Pattern 4 — Deferring non-critical sections with `<template>` + client hydration

```typescript
// Emit a <template> tag for below-the-fold content.
// This is parsed by the browser but not rendered, avoiding layout cost.
await write(`
<template id="deferred-recommendations">
  ${rawRecommendationsHtml}
</template>
<script defer ></script>
`);
```

## Implementation Details

**Worker CPU budget and streaming.** The Workers runtime suspends a Worker's CPU execution while awaiting I/O (fetch, KV, DO). During that suspension the already-written stream chunks are flushed downstream. Effectively the Worker's CPU time is near-zero during upstream waits while the browser is actively receiving and rendering earlier chunks.

**Compression.** When using streaming, ensure `Content-Encoding: gzip/br` is not set by your worker unless you are compressing the stream yourself (via `CompressionStream`). Cloudflare's edge will apply compression to the stream transparently at the CDN layer.

**TransformStream vs ReadableStream.** `TransformStream` is easier to write imperatively (push via `writer.write()`). `ReadableStream` with a `pull` controller is better for pull-based sources (databases, queues) because it naturally applies backpressure.

## Anti-patterns

- **`await response.text()` before returning.** This fully buffers the body and negates all streaming benefits. Always pipe or pass the `ReadableStream` directly.
- **Writing the entire `<html>...</html>` in one `write()` call.** Makes the stream a no-op — the browser still waits for one large chunk. Break writes at logical above/below-fold boundaries.
- **Not closing the writer in `finally`.** If an exception is thrown mid-stream, the browser hangs waiting for more data. Always `writer.close()` or `writer.abort(err)` in a `finally` block.
- **Setting `Cache-Control: public` on streamed personalised pages.** Cloudflare will not cache a streaming response by default, but an explicit `max-age` can cause it to buffer the full body before caching — defeating streaming.

## Gotchas

- `TransformStream` chunks must be `Uint8Array` when used as a HTTP response body, not strings. Always `TextEncoder.encode()` your HTML strings.
- The Workers `Request` object's `cf.cacheEverything` flag will buffer the full response before caching — do not combine with streaming responses.
- HTTP/1.1 requires `Transfer-Encoding: chunked` to stream, but Workers sets this automatically when the body is a `ReadableStream`. HTTP/2 always streams frames without a special header.
- Some Workers-proxied origins strip `x-accel-buffering`; set it on the Worker's own Response, not on the upstream response.

## Verification

```bash
# Measure TTFB with curl's time_starttransfer:
curl -o /dev/null -s -w \
  "DNS: %{time_namelookup}s | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s\n" \
  https://your-worker.example.com/dashboard

# Verify chunks arrive incrementally (should see multiple Transfer-Encoding chunks):
curl -N --raw https://your-worker.example.com/dashboard | xxd | head -60

# Query Analytics Engine for p95 TTFB:
wrangler d1 execute prod-db --command \
  "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY ttfb_ms) FROM ttfb_log WHERE ts > now() - interval '1 hour';"

# Lighthouse CLI for field TTFB:
npx lighthouse https://your-worker.example.com/dashboard --only-audits=server-response-time --output=json | jq '.audits["server-response-time"].numericValue'
```

Target: TTFB < 200 ms for above-the-fold content even when slow data takes 1–2 s.

## Related

- `workers-cache-api-fine-grained-control.md` — cache fully-rendered static pages to eliminate TTFB entirely.
- `workers-request-coalescing-durable-objects.md` — reduce upstream calls that block stream start.
- `workers-connection-keep-alive-upstream.md` — reduce per-fetch TCP setup cost that delays stream start.

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/streams/
- https://developer.mozilla.org/en-US/docs/Web/API/TransformStream
- https://web.dev/ttfb/
- https://developers.cloudflare.com/analytics/analytics-engine/
