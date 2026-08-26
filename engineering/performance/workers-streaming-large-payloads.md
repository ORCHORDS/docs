# Streaming Responses for Large Payload Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Worker fetches a 15 MB CSV export from R2, transforms it, and returns it to the client.  Without streaming, the Worker must buffer the entire response in memory, hitting the **128 MB Worker memory limit** under concurrent load and causing `Error: Worker exceeded memory limit` crashes.  A Worker serving AI-generated text from an upstream model returns nothing until the full generation completes, giving users a blank screen for 8–12 seconds.  A Worker proxying a database dump never starts sending bytes until the query finishes.  All three cases are solved by **streaming responses** using the WHATWG Streams API available in the Workers runtime.

## Context

The Workers runtime implements the **WHATWG Streams API** (`ReadableStream`, `WritableStream`, `TransformStream`) as first-class citizens.  A streaming `Response` body starts sending bytes to the client as soon as the first chunk is enqueued — the Worker does not need to hold the entire body in memory.

Memory model under streaming vs buffering:

| Approach | Peak memory | Time-to-first-byte | CPU billing |
|----------|-------------|-------------------|-------------|
| Buffer full body | equals body size | after full fetch | after full fetch |
| Stream body | ~chunk size (64 KB typical) | after first upstream byte | on each chunk |

Key primitives:

- **`ReadableStream`** — a pull-based source of chunks
- **`WritableStream`** — a sink that consumes chunks
- **`TransformStream`** — a {readable, writable} pair that transforms chunks in flight
- **`Response` with a `ReadableStream` body** — begins sending to the client immediately

CPU billing in Workers is wall-clock time while JavaScript is executing, not while awaiting I/O.  Streaming is therefore also cheaper: the Worker yields while the upstream sends the next chunk, and CPU billing is paused during that I/O wait.

## Section 1 — Direct Pass-Through Streaming from R2

The simplest streaming pattern: fetch a large object from R2 and pipe it directly to the client without buffering.

```javascript
// src/index.js
export default {
  async fetch(request, env) {
    const url     = new URL(request.url);
    const key     = url.pathname.slice(1);  // e.g. /exports/report-2026.csv

    const object  = await env.EXPORT_BUCKET.get(key);
    if (!object) {
      return new Response('Not found', { status: 404 });
    }

    // object.body is a ReadableStream — pass it directly to Response
    // The Worker holds only the current in-flight chunk in memory
    return new Response(object.body, {
      status:  200,
      headers: {
        'Content-Type':        object.httpMetadata?.contentType ?? 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${key.split('/').pop()}"`,
        // Tell caches not to buffer the response body
        'X-Accel-Buffering':   'no',
      },
    });
  },
};
```

`env.BUCKET.get(key).body` is a `ReadableStream<Uint8Array>`.  When you construct a `Response` with this stream as the body, the Workers runtime pipes chunks to the client as they arrive from R2, without holding the full object in memory.

## Section 2 — TransformStream for In-Flight Transformation

When you need to modify the body in transit (add headers to CSV rows, redact PII, convert newline encoding), use a `TransformStream`:

```javascript
// src/csv-redact-stream.js
/**
 * Redacts the email column (index 2) from a UTF-8 CSV stream.
 * Operates chunk-by-chunk; handles chunks that split across row boundaries.
 */
export function buildRedactTransform() {
  let buffer = '';

  return new TransformStream({
    transform(chunk, controller) {
      // Decode incoming Uint8Array chunk to string and append to carry-over buffer
      buffer += new TextDecoder().decode(chunk, { stream: true });

      const lines = buffer.split('\n');
      // Last element may be an incomplete line — keep it in the buffer
      buffer = lines.pop();

      for (const line of lines) {
        if (!line) {
          controller.enqueue(new TextEncoder().encode('\n'));
          continue;
        }
        const cols  = line.split(',');
        if (cols.length > 2) {
          cols[2] = '***REDACTED***';
        }
        controller.enqueue(new TextEncoder().encode(cols.join(',') + '\n'));
      }
    },

    flush(controller) {
      // Flush any remaining buffered content at stream end
      if (buffer) {
        const cols = buffer.split(',');
        if (cols.length > 2) cols[2] = '***REDACTED***';
        controller.enqueue(new TextEncoder().encode(cols.join(',')));
      }
    },
  });
}
```

```javascript
// src/index.js
import { buildRedactTransform } from './csv-redact-stream.js';

export default {
  async fetch(request, env) {
    const object = await env.EXPORT_BUCKET.get('exports/users.csv');
    if (!object) return new Response('Not found', { status: 404 });

    const { readable, writable } = buildRedactTransform();

    // Pipe R2 stream → TransformStream → Response body
    // pipeThrough is non-blocking — the Worker exits the fetch handler
    // while the pipe continues in the background
    const redactedStream = object.body.pipeThrough({ readable, writable });

    return new Response(redactedStream, {
      headers: { 'Content-Type': 'text/csv' },
    });
  },
};
```

**Key insight:** `pipeThrough` returns a new `ReadableStream` that is backed by the transform.  The Worker's fetch handler returns immediately with this stream as the response body; the runtime drives the pipe asynchronously.

## Section 3 — Server-Sent Events and AI Generation Streaming

LLM API responses stream tokens as they are generated.  Wrapping this in a Worker with proper SSE formatting:

```javascript
// src/ai-stream.js
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const { prompt } = await request.json();

    // Call the upstream AI API — it returns a streaming body
    const upstream = await fetch('https://api.example.com/v1/generate', {
      method:  'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${env.AI_API_KEY}`,
        Accept:          'text/event-stream',
      },
      body: JSON.stringify({ prompt, stream: true }),
    });

    if (!upstream.ok) {
      return new Response('Upstream error', { status: 502 });
    }

    // Transform raw upstream chunks into SSE-formatted lines
    const sseTransform = new TransformStream({
      transform(chunk, controller) {
        const text  = new TextDecoder().decode(chunk);
        const lines = text.split('\n').filter(l => l.startsWith('data: '));

        for (const line of lines) {
          if (line === 'data: [DONE]') {
            controller.enqueue(new TextEncoder().encode('data: [DONE]\n\n'));
            return;
          }
          try {
            const json  = JSON.parse(line.slice(6));
            const token = json.choices?.[0]?.delta?.content ?? '';
            if (token) {
              controller.enqueue(
                new TextEncoder().encode(`data: ${JSON.stringify({ token })}\n\n`)
              );
            }
          } catch {
            // Skip malformed chunks
          }
        }
      },
    });

    return new Response(upstream.body.pipeThrough(sseTransform), {
      headers: {
        'Content-Type':      'text/event-stream',
        'Cache-Control':     'no-cache',
        'Transfer-Encoding': 'chunked',
        'X-Accel-Buffering': 'no',
      },
    });
  },
};
```

This pattern gives users sub-second **time-to-first-token** regardless of total generation time, dramatically improving perceived performance for generative UIs.

## Section 4 — Streaming with Backpressure and Flow Control

When the upstream produces data faster than the downstream (client) can consume it, you must respect **backpressure** to avoid accumulating an unbounded in-memory buffer.

```javascript
// src/controlled-pipe.js
export async function pipeWithBackpressure(readable, writable) {
  const reader = readable.getReader();
  const writer = writable.getWriter();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Wait until the write is drained before reading the next chunk
      // This is backpressure: the reader slows down when the writer is full
      await writer.write(value);
      // writer.write() returns a Promise that resolves when the chunk
      // has been consumed by the downstream, not just buffered
    }
    await writer.close();
  } catch (err) {
    await writer.abort(err);
    throw err;
  } finally {
    reader.releaseLock();
    writer.releaseLock();
  }
}
```

In practice, using the built-in `ReadableStream.pipeTo(writable)` handles backpressure automatically:

```javascript
export default {
  async fetch(request, env) {
    const { readable, writable } = new TransformStream();

    // pipeTo handles backpressure natively — no manual loop needed
    const pipePromise = upstreamReadable.pipeTo(writable);

    // ctx.waitUntil ensures the pipe continues after the response is returned
    // (required when you return the readable end as the response body)
    // In this case we return readable directly — pipeTo drives the pipe
    return new Response(readable, {
      headers: { 'Content-Type': 'application/octet-stream' },
    });
  },
};
```

**Note on `pipeTo` vs manual loops:** `ReadableStream.pipeTo(writable)` is the preferred API.  The manual loop above is educational; use `pipeTo` or `pipeThrough` in production code.

## Anti-patterns

- **Calling `response.arrayBuffer()` or `response.text()` on large R2 objects** — these methods buffer the entire body into memory.  Use `response.body` (a `ReadableStream`) instead and pipe it.
- **Nesting multiple `await response.json()` calls on streaming responses** — each `.json()` call consumes the stream.  A stream can only be read once; clone it with `response.clone()` if you need to consume the body in two places.
- **Ignoring the `flush` handler in TransformStream** — if your transform buffers partial state (e.g., incomplete lines), always implement `flush()` to emit the remainder when the stream ends.  Omitting it silently drops the last chunk.
- **Setting `Transfer-Encoding: chunked` manually** — Workers automatically set chunked encoding when the response body is a stream.  Setting it manually can cause double-encoding issues in some proxies.
- **Streaming without `X-Accel-Buffering: no`** — Nginx and some CDN layers buffer streaming responses by default.  Set this header when your Worker sits behind a proxy.

## Gotchas

- Workers have a **30-second wall-clock limit** on fetch handlers (subrequest timeout).  A very large file that takes longer than 30 s to fully pipe will be aborted.  For files expected to exceed 30 s, use **signed R2 URLs** and redirect the client to fetch directly from R2.
- `ReadableStream.cancel()` must be called if you abandon reading mid-stream, otherwise the upstream connection is held open until the Worker times out.
- Cloudflare's cache does **not** cache streaming responses where the content length is unknown (no `Content-Length` header).  If you need edge caching of large files, cache the R2 presigned URL response instead.
- In Miniflare (local dev), some streaming behaviors differ from production — test streaming scenarios against `wrangler dev --remote` for accuracy.
- The Workers runtime limits the number of concurrent in-flight subrequests to **6 per Worker invocation**.  Streaming many R2 objects in parallel can hit this limit.

## Verification

1. Fetch a 50 MB R2 object through the streaming Worker.  Monitor the Worker's memory usage via `wrangler tail` and confirm it stays under 10 MB throughout the transfer, rather than spiking to 50 MB.
2. Use `curl --no-buffer` to verify bytes arrive progressively rather than all at once: `curl --no-buffer https://your-worker.dev/large-file.csv | pv > /dev/null` — you should see a steady throughput rather than a burst after a long wait.
3. For the SSE endpoint, open the browser DevTools Network tab, select the SSE response, and confirm the **EventStream** panel shows tokens arriving one by one, not batched at the end.

## Related

- `cloudflare-workers-performance.md` — Worker memory and CPU model
- `workers-cpu-time-optimization.md` — CPU budget management
- `sse-vs-websockets-real-time-streaming.md` — choosing the right streaming transport
- `cloudflare-r2-presigned-cdn-acceleration.md` — serving large files via R2 directly
- `workers-queues-background-offload.md` — offloading heavy processing to Queues

## Sources

- WHATWG Streams API: https://streams.spec.whatwg.org/
- Workers Streams documentation: https://developers.cloudflare.com/workers/runtime-apis/streams/
- R2 object streaming: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- TransformStream reference: https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
