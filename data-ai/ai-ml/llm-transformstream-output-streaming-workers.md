# LLM Output Streaming with TransformStream in Workers

date: 2026-08-24 / author: example.com / status: production

---

## Symptom / Use-case

A Workers AI streaming inference call produces a `ReadableStream` of SSE chunks that must be
transformed before reaching the client — stripping `data:` prefixes, merging partial JSON deltas,
injecting per-chunk metadata (token count, latency), or re-encoding for a different protocol.
Trying to do this with string concatenation and manual splitting across multiple `read()` calls
produces brittle code. `TransformStream` gives you a typed pipeline that handles backpressure,
buffering, and error propagation correctly inside a Cloudflare Worker.

## Context

The Web Streams API `TransformStream` is fully available in Cloudflare Workers. It pairs a
`WritableStream` (the transform input) and a `ReadableStream` (the transform output) with a
`transformer` object implementing `transform(chunk, controller)` and optionally `flush(controller)`.

Workers AI's `stream: true` mode returns a `ReadableStream<Uint8Array>` of SSE-formatted lines.
Each line looks like `data: {"response":"hello","p":"..."}

`. You need to:
1. Pipe the AI stream through a `TextDecoderStream` to get string chunks.
2. Pipe through a custom `TransformStream` that buffers incomplete lines, parses SSE, and
   emits clean `{delta, done}` objects.
3. Pipe through a `TextEncoderStream` (or a custom encoder) to send the final bytes to the client.

---

## SSE line parser TransformStream

```typescript
// src/sse-parser.ts

export interface SseChunk {
  delta: string;
  done: boolean;
}

/**
 * Transforms raw SSE text chunks into structured SseChunk objects.
 * Handles partial lines across chunk boundaries by buffering.
 */
export function createSseParserStream(): TransformStream<string, SseChunk> {
  let lineBuffer = "";

  return new TransformStream<string, SseChunk>({
    transform(chunk, controller) {
      lineBuffer += chunk;
      const lines = lineBuffer.split("\n");

      // Keep the last (potentially incomplete) line in the buffer
      lineBuffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;

        const payload = trimmed.slice(5).trim();

        if (payload === "[DONE]") {
          controller.enqueue({ delta: "", done: true });
          return;
        }

        try {
          const parsed = JSON.parse(payload);
          const delta: string =
            parsed?.response ??
            parsed?.choices?.[0]?.delta?.content ??
            "";
          if (delta) {
            controller.enqueue({ delta, done: false });
          }
        } catch {
          // Malformed JSON in SSE chunk — skip silently
        }
      }
    },

    flush(controller) {
      // Flush any remaining buffer on stream end
      if (lineBuffer.trim().startsWith("data:")) {
        try {
          const payload = lineBuffer.trim().slice(5).trim();
          if (payload !== "[DONE]") {
            const parsed = JSON.parse(payload);
            const delta: string = parsed?.response ?? "";
            if (delta) controller.enqueue({ delta, done: false });
          }
        } catch { /* ignore */ }
      }
      controller.enqueue({ delta: "", done: true });
    },
  });
}
```

---

## Token-counting and metadata injection TransformStream

```typescript
// src/token-counter.ts
import type { SseChunk } from "./sse-parser";

export interface EnrichedChunk {
  delta: string;
  done: boolean;
  tokensSoFar: number;
  elapsedMs: number;
}

/**
 * Wraps each SseChunk with running token count and elapsed time metadata.
 * Uses a rough 4-chars-per-token estimate; replace with a proper tokeniser if needed.
 */
export function createMetadataInjectorStream(
  startTime: number,
): TransformStream<SseChunk, EnrichedChunk> {
  let totalChars = 0;

  return new TransformStream<SseChunk, EnrichedChunk>({
    transform(chunk, controller) {
      totalChars += chunk.delta.length;
      controller.enqueue({
        delta: chunk.delta,
        done: chunk.done,
        tokensSoFar: Math.ceil(totalChars / 4),
        elapsedMs: Date.now() - startTime,
      });
    },
  });
}
```

---

## Re-serialise to client SSE format

```typescript
// src/sse-serialiser.ts
import type { EnrichedChunk } from "./token-counter";

/**
 * Converts EnrichedChunk objects back to SSE-formatted strings for the HTTP response.
 * Clients consuming the stream receive standard `data: {...}\n\n` events.
 */
export function createSseSerialiserStream(): TransformStream<EnrichedChunk, string> {
  return new TransformStream<EnrichedChunk, string>({
    transform(chunk, controller) {
      const payload = JSON.stringify({
        delta: chunk.delta,
        done: chunk.done,
        tokens: chunk.tokensSoFar,
        ms: chunk.elapsedMs,
      });
      controller.enqueue(`data: ${payload}\n\n`);
    },
    flush(controller) {
      controller.enqueue("data: [DONE]\n\n");
    },
  });
}
```

---

## Worker entry point assembling the pipeline

```typescript
// src/index.ts
import { createSseParserStream } from "./sse-parser";
import { createMetadataInjectorStream } from "./token-counter";
import { createSseSerialiserStream } from "./sse-serialiser";

export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json() as {
      messages: Array<{ role: string; content: string }>;
    };

    if (!Array.isArray(body?.messages)) {
      return new Response(JSON.stringify({ error: "messages required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const startTime = Date.now();

    // Workers AI streaming call — returns ReadableStream<Uint8Array>
    const aiStream = await env.AI.run(
      "@cf/meta/llama-3.1-8b-instruct" as any,
      { messages: body.messages, stream: true },
    ) as ReadableStream<Uint8Array>;

    // Assemble the transform pipeline:
    //   Uint8Array → string (TextDecoderStream)
    //   → SseChunk (SSE parser)
    //   → EnrichedChunk (metadata injector)
    //   → string (SSE serialiser)
    //   → Uint8Array (TextEncoderStream)
    const pipeline = aiStream
      .pipeThrough(new TextDecoderStream())
      .pipeThrough(createSseParserStream())
      .pipeThrough(createMetadataInjectorStream(startTime))
      .pipeThrough(createSseSerialiserStream())
      .pipeThrough(new TextEncoderStream());

    return new Response(pipeline, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no", // Disable nginx/proxy buffering
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};
```

---

## Branching a stream to two consumers with tee()

```typescript
// src/tee-example.ts
// Use ReadableStream.tee() when you need to consume the AI stream twice —
// e.g., stream to the client AND simultaneously log tokens to Analytics Engine.

export interface Env {
  AI: Ai;
  AE: AnalyticsEngineDataset;
}

export async function teeStream(env: Env, messages: unknown[]): Promise<Response> {
  const aiStream = await (env.AI as any).run(
    "@cf/meta/llama-3.1-8b-instruct",
    { messages, stream: true },
  ) as ReadableStream<Uint8Array>;

  // tee() clones the stream into two independent ReadableStreams
  const [clientStream, logStream] = aiStream.tee();

  // Log branch — consume asynchronously without blocking the client stream
  const logTask = (async () => {
    const reader = logStream
      .pipeThrough(new TextDecoderStream())
      .getReader();
    let totalChars = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalChars += value.length;
    }
    env.AE.writeDataPoint({ doubles: [totalChars], indexes: ["stream-log"] });
  })();

  // Don't await logTask — let it run in the background via ctx.waitUntil if available
  logTask.catch(console.error);

  const clientPipeline = clientStream
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(createSseSerialiserStream())
    .pipeThrough(new TextEncoderStream());

  return new Response(clientPipeline, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}

// Inline import to avoid circular dep in this snippet
import { createSseSerialiserStream } from "./sse-serialiser";
```

## Anti-patterns

- **Buffering the full stream before transforming** — reading all chunks into a string before
  processing defeats the purpose of streaming and can exhaust memory on long responses.
- **Splitting on `\n\n` without buffering incomplete chunks** — SSE chunks can arrive mid-line;
  always maintain a line buffer in the `transform` method and flush it in `flush`.
- **Ignoring stream errors** — attach a `.catch` handler or use `pipeTo` with error handling; an
  uncaught error in the transform pipeline causes the client to see a truncated stream with no
  diagnostic.
- **Using `pipeThrough` after the stream has been consumed** — once you call `getReader()` on a
  `ReadableStream`, you cannot `pipeThrough` it; choose one consumption strategy.
- **Not setting `X-Accel-Buffering: no`** — reverse proxies and CDN layers may buffer SSE
  streams, causing clients to receive data in large batches instead of incrementally.

## Gotchas

- Workers AI streaming (`stream: true`) returns a `ReadableStream<Uint8Array>` but the TypeScript
  types on `Ai.run()` may not reflect this; cast the result to `ReadableStream<Uint8Array>`.
- `ReadableStream.tee()` buffers chunks in memory until both branches have consumed them; if the
  log branch falls behind the client branch, memory usage grows proportionally.
- `TextDecoderStream` is available in Workers but `TextDecoderStream` with `fatal: true` will
  throw on invalid UTF-8 sequences — use the default (replacement mode) for streaming text.
- The Workers CPU time limit applies to all transform work synchronously; long-running `transform`
  methods (e.g., expensive per-chunk NLP) can cause the Worker to exceed the CPU budget before the
  stream completes.
- Cloudflare's streaming response is not supported in Workers called via `service bindings` without
  enabling streaming in the binding configuration.

## Verification

```bash
# Stream the response and print chunks as they arrive
curl -sX POST https://your-worker.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Count from 1 to 10 slowly."}]}' \
  --no-buffer

# Confirm metadata fields appear in each chunk
curl -sX POST https://your-worker.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}' \
  --no-buffer | grep -o '"tokens":[0-9]*' | head -5
```

## Related

- `workers-ai-streaming-server-sent-events.md` — SSE streaming basics with Workers AI
- `cloudflare-workers-ai-streaming-inference.md` — Workers AI streaming inference overview
- `llm-streaming-responses.md` — general LLM streaming response patterns
- `llm-async-patterns.md` — async and concurrent request patterns for LLMs
- `workers-ai-pipeline-chaining-multi-model.md` — chaining multiple model calls in a pipeline

## Sources

- Web Streams API: https://developer.mozilla.org/en-US/docs/Web/API/Streams_API
- TransformStream: https://developer.mozilla.org/en-US/docs/Web/API/TransformStream
- Cloudflare Workers Streams: https://developers.cloudflare.com/workers/runtime-apis/streams/
- Workers AI streaming: https://developers.cloudflare.com/workers-ai/configuration/streaming/
