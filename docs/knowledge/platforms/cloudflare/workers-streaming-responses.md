# workers-streaming-responses

**Issue:** How to stream large or chunked responses from a Cloudflare Worker without buffering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers have a 128 MB response body limit when buffering. For large payloads, AI token streams, or chunked APIs, you must use the Streams API to pass data through without materialising it in memory.

## Pattern / Solution

```typescript
// 1. TransformStream — modify chunks as they pass through
export default {
  async fetch(request: Request): Promise<Response> {
    const upstream = await fetch('https://api.example.com/stream');

    const { readable, writable } = new TransformStream({
      transform(chunk: Uint8Array, controller) {
        // e.g. prefix every chunk
        controller.enqueue(new TextEncoder().encode('data: '));
        controller.enqueue(chunk);
      },
    });

    upstream.body!.pipeTo(writable); // non-blocking pipe
    return new Response(readable, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Transfer-Encoding': 'chunked',
      },
    });
  },
};

// 2. ReadableStream constructor — generate chunks lazily
function streamJSON(records: AsyncIterable<object>): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(encoder.encode('['));
      let first = true;
      for await (const record of records) {
        if (!first) controller.enqueue(encoder.encode(','));
        controller.enqueue(encoder.encode(JSON.stringify(record)));
        first = false;
      }
      controller.enqueue(encoder.encode(']'));
      controller.close();
    },
  });
  return new Response(stream, { headers: { 'Content-Type': 'application/json' } });
}

// 3. Server-Sent Events (SSE) from an AI model stream
async function sseProxy(upstream: Response): Promise<Response> {
  const reader = upstream.body!.getReader();
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const enc = new TextEncoder();

  (async () => {
    while (true) {
      const { done, value } = await reader.read();
      if (done) { await writer.close(); break; }
      await writer.write(enc.encode(`data: ${JSON.stringify(value)}\n\n`));
    }
  })();

  return new Response(readable, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
  });
}
```

## Gotchas
- Do **not** `await upstream.text()` or `await upstream.json()` before forwarding — this buffers the full body.
- `pipeTo` returns a Promise; if you don't handle its rejection the Worker silently swallows errors. Attach `.catch()`.
- Cloudflare's edge will buffer up to 128 KB before flushing to the client; for true low-latency SSE add `Transfer-Encoding: chunked`.
- A `TransformStream` with no `transform` option is a passthrough — useful as a queue.
- Workers cannot send a response body larger than 128 MB total even when streamed.
- `controller.enqueue()` accepts `Uint8Array` only; strings must be encoded first.

## Related
- `workers-fetch-api-patterns.md`
- `workers-websocket-upgrade.md`
- `workers-best-practices.md`
