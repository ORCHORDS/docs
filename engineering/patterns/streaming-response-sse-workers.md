# Streaming Responses with Server-Sent Events in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need to stream real-time data (LLM token-by-token output, progress updates, live logs) from a Cloudflare Worker to a browser without polling. Server-Sent Events (SSE) are the lightest-weight protocol for server-to-client push over HTTP/1.1 and HTTP/2.

## Context
Cloudflare Workers expose `ReadableStream`, `TransformStream`, and `WritableStream` following the WHATWG Streams API. An SSE response is an `text/event-stream` body that never closes until the client disconnects. Workers have a 30-second CPU limit per invocation but the *wall-clock* limit is 100 seconds for subrequest streaming; pair with `ctx.waitUntil` to keep the isolate alive while flushing.

## Basic SSE Endpoint
The response must set `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `Connection: keep-alive`. Each event is a `data:` line followed by a blank line.

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'GET') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { readable, writable } = new TransformStream<string, string>();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    const stream = async () => {
      try {
        for (let i = 1; i <= 5; i++) {
          const payload = `data: ${JSON.stringify({ step: i, ts: Date.now() })}\n\n`;
          await writer.write(encoder.encode(payload));
          await scheduler.wait(300); // built-in Workers scheduler
        }
        await writer.write(encoder.encode('event: done\ndata: {}\n\n'));
      } finally {
        await writer.close();
      }
    };

    ctx.waitUntil(stream());

    return new Response(readable as unknown as ReadableStream<Uint8Array>, {
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-store',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no', // disable nginx/CDN buffering
      },
    });
  },
};
```

## Proxying a Streaming Upstream API
When the upstream (e.g. an LLM provider) already returns an SSE stream, pipe it through directly rather than buffering.

```typescript
async function proxyStream(upstreamUrl: string, authToken: string): Promise<Response> {
  const upstream = await fetch(upstreamUrl, {
    headers: { Authorization: `Bearer ${authToken}` },
  });

  if (!upstream.ok || !upstream.body) {
    return new Response('Upstream error', { status: 502 });
  }

  // Pipe body unchanged; add a transform to inject a custom event prefix if needed
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      controller.enqueue(chunk);
    },
  });

  upstream.body.pipeTo(writable).catch(() => {/* client disconnected */});

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache',
      'Transfer-Encoding': 'chunked',
    },
  });
}
```

## Heartbeat to Prevent Proxy Timeouts
Intermediate proxies (including Cloudflare's own edge) may close idle SSE connections. Send a `: heartbeat` comment line every 15 seconds.

```typescript
async function streamWithHeartbeat(
  writer: WritableStreamDefaultWriter<Uint8Array>,
  workFn: (emit: (data: string, event?: string) => Promise<void>) => Promise<void>,
): Promise<void> {
  const enc = new TextEncoder();
  const emit = async (data: string, event = 'message') => {
    const line = event === 'message'
      ? `data: ${data}\n\n`
      : `event: ${event}\ndata: ${data}\n\n`;
    await writer.write(enc.encode(line));
  };

  const heartbeat = setInterval(async () => {
    try {
      await writer.write(enc.encode(': heartbeat\n\n'));
    } catch {
      clearInterval(heartbeat);
    }
  }, 15_000);

  try {
    await workFn(emit);
  } finally {
    clearInterval(heartbeat);
    await writer.close().catch(() => {});
  }
}
```

## Backpressure and Error Propagation
Writers can signal backpressure via `writer.desiredSize`. Always check whether the client has disconnected before writing to avoid masking upstream errors.

```typescript
async function writeWithBackpressure(
  writer: WritableStreamDefaultWriter<Uint8Array>,
  chunks: AsyncIterable<Uint8Array>,
): Promise<void> {
  for await (const chunk of chunks) {
    // Wait for internal buffer to drain before writing more
    if ((writer.desiredSize ?? 1) <= 0) {
      await writer.ready;
    }
    try {
      await writer.write(chunk);
    } catch {
      // Client disconnected; abort upstream fetch
      return;
    }
  }
}
```

## Anti-patterns
- Buffering the entire SSE response in memory before streaming — defeats latency gains and risks OOM on large payloads.
- Forgetting `X-Accel-Buffering: no` — Cloudflare's own edge buffers by default on some plans; this header disables it.
- Using `setInterval` without clearing it in the `finally` block — leaks the interval until the isolate is recycled.
- Sending raw newlines inside `data:` fields — newlines split SSE events; JSON-encode or base64-encode multi-line content.
- Relying on SSE for bidirectional communication — SSE is server-to-client only; use WebSockets (Durable Objects) for two-way.

## Gotchas
- `scheduler.wait()` is a Workers-specific API and not available in Node.js test environments; mock it in unit tests.
- Workers do not support HTTP/2 server push; SSE over HTTP/2 works fine but has per-stream rather than per-connection limits.
- The 100-second wall-clock limit applies to free and unbound plans; paid plans with Unbound usage model have no wall-clock limit.
- Response compression (`Content-Encoding: gzip`) breaks streaming — ensure `Accept-Encoding` is stripped or the response opts out.
- If the client reconnects with `Last-Event-ID`, your Worker must handle replay; add an `id:` field per event and store events in KV for the replay window.

## Verification
1. `curl -N https://your-worker.example.com/sse` — the `-N` flag disables buffering; confirm events arrive in real-time.
2. Browser `EventSource` API: `new EventSource('/sse').onmessage = e => console.log(e.data)` in DevTools.
3. Wrangler local dev: `wrangler dev --port 8787` and check the response with `curl -N http://localhost:8787/sse`.
4. Validate heartbeats appear in Wireshark/tcpdump every ~15 s when the work function idles.

## Related
- `/documentation/categories/patterns/request-hedging-latency.md`
- `/documentation/categories/patterns/exponential-backoff-jitter-workers.md`
- `/documentation/categories/patterns/correlation-id-propagation-workers.md`

## Sources
- https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- https://developers.cloudflare.com/workers/runtime-apis/streams/
- https://developers.cloudflare.com/workers/platform/limits/
