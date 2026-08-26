# Workers ReadableStream TransformStream Processing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Workers handler reads an entire upstream response body into memory before transforming and forwarding it, causing unnecessary memory pressure and delaying time-to-first-byte for the client. `TransformStream` lets you process, filter, or rewrite response bodies chunk-by-chunk without buffering the full payload.

## Context
Cloudflare Workers expose the WHATWG Streams API — `ReadableStream`, `WritableStream`, and `TransformStream` — with native V8 integration. Rather than `await response.text()` (which buffers the entire body), you can pipe a stream through a `TransformStream` and return the transformed `ReadableStream` directly as the response body. This keeps peak memory proportional to chunk size rather than total payload size, enables streaming TTFB improvements, and works within the 128 MB isolate memory limit even for large files.

## Basic TransformStream: Inject a Response Header Token
Strip or inject tokens in streamed HTML without reading the full document.

```typescript
// src/html-inject.ts
export function injectNonce(stream: ReadableStream, nonce: string): ReadableStream {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      // Replace <script> tags with <script nonce="..."> chunk by chunk.
      const text = decoder.decode(chunk, { stream: true });
      const rewritten = text.replace(/<script(?![^>]*nonce)/g, `<script nonce="${nonce}"`);
      controller.enqueue(encoder.encode(rewritten));
    },
    flush(controller) {
      // Decode any remaining bytes held by the streaming decoder.
      const remaining = decoder.decode();
      if (remaining) controller.enqueue(encoder.encode(remaining));
    },
  });

  stream.pipeTo(writable).catch(() => {/* upstream closed */});
  return readable;
}

// src/worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch(request);
    const nonce = crypto.randomUUID();
    const transformed = injectNonce(upstream.body!, nonce);

    return new Response(transformed, {
      status: upstream.status,
      headers: upstream.headers,
    });
  },
};
```

## Filtering Rows from a Streamed NDJSON Response
Process a newline-delimited JSON stream from an upstream API, dropping rows that fail validation, without buffering the entire dataset.

```typescript
// src/ndjson-filter.ts
export function filterNdjson<T>(
  stream: ReadableStream<Uint8Array>,
  predicate: (row: T) => boolean
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      // Keep the last (possibly incomplete) line in the buffer.
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const row = JSON.parse(line) as T;
          if (predicate(row)) {
            controller.enqueue(encoder.encode(line + "\n"));
          }
        } catch {
          // Drop malformed lines silently or log via Tail Worker.
        }
      }
    },
    flush(controller) {
      if (buffer.trim()) {
        try {
          const row = JSON.parse(buffer) as T;
          if (predicate(row)) {
            controller.enqueue(encoder.encode(buffer + "\n"));
          }
        } catch { /* ignore */ }
      }
    },
  });

  stream.pipeTo(writable).catch(() => {});
  return readable;
}
```

## Composing Multiple TransformStreams in a Pipeline
Chain transformers using `pipeThrough()` for separation of concerns.

```typescript
// src/pipeline.ts
import { CompressionStream } from "compression-streams-polyfill"; // provided natively in Workers

function uppercaseStream(): TransformStream<Uint8Array, Uint8Array> {
  const dec = new TextDecoder();
  const enc = new TextEncoder();
  return new TransformStream({
    transform(chunk, controller) {
      controller.enqueue(enc.encode(dec.decode(chunk, { stream: true }).toUpperCase()));
    },
  });
}

export default {
  async fetch(request: Request): Promise<Response> {
    const upstream = await fetch("https://example.com/large-dataset.txt");

    const pipeline = upstream.body!
      .pipeThrough(uppercaseStream())          // Step 1: transform text
      .pipeThrough(new CompressionStream("br")); // Step 2: Brotli-compress output

    return new Response(pipeline, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Encoding": "br",
        "Transfer-Encoding": "chunked",
      },
    });
  },
};
```

Each `pipeThrough()` adds a `TransformStream` stage; V8 backpressure propagates automatically through the chain — the upstream fetch only delivers bytes as fast as the client consumes them.

## Anti-patterns
- Calling `await response.arrayBuffer()` or `await response.text()` before transforming — buffers the entire body, losing all streaming benefits.
- Starting the `pipeTo()` call inside the `transform` callback — it must be initiated before chunks arrive.
- Forgetting `{ stream: true }` in `TextDecoder.decode()` when processing multi-byte UTF-8 sequences that span chunk boundaries — this corrupts characters.
- Not implementing `flush()` — incomplete buffered state (partial line, remaining decoder bytes) silently drops the last chunk.
- Swallowing errors from `pipeTo()` without any observability — log upstream errors to a Tail Worker or Analytics Engine.

## Gotchas
- `TransformStream` backpressure is respected only when the consumer reads the `readable` side; if you call `pipeTo()` without returning the readable to the client, the stream is consumed immediately in the background with no backpressure.
- Workers have a 30-second wall-clock limit on stream duration (Paid plans) — very large files may time out mid-stream on Free plans (10 s limit).
- `CompressionStream("br")` is available natively in Workers without a polyfill as of mid-2024; check `wrangler.toml` compatibility date `2024-09-23` or later.
- `pipeThrough()` does not clone the stream — once piped, the original readable is locked and cannot be read again; use `tee()` if you need to branch.
- The `cancel` reason passed by the client when they abort the response does not automatically cancel the upstream fetch — you must wire up `AbortController` manually.

## Verification
```bash
# Confirm streaming TTFB improvement with curl
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://your.worker.dev/stream

# Check memory stays flat under load with wrangler tail
wrangler tail --format=json | jq 'select(.event.request) | .wallTime, .cpuTime'

# Verify Brotli encoding applied
curl -H "Accept-Encoding: br" -I https://your.worker.dev/stream | grep content-encoding
```

## Related
- [`workers-streaming-large-payloads.md`](workers-streaming-large-payloads.md)
- [`workers-response-streaming-ttfb-optimization.md`](workers-response-streaming-ttfb-optimization.md)
- [`workers-streaming-response-tee-optimization.md`](workers-streaming-response-tee-optimization.md)
- [`workers-response-compression-brotli-zstd.md`](workers-response-compression-brotli-zstd.md)
- [`streaming-json-parsing.md`](streaming-json-parsing.md)

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
- https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/
- https://streams.spec.whatwg.org/#ts-model
- https://developers.cloudflare.com/workers/platform/limits/#streaming
- https://developer.mozilla.org/en-US/docs/Web/API/TextDecoder/decode
