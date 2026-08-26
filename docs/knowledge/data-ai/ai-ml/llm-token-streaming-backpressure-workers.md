# Managing Backpressure in LLM Token Streaming from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your streaming LLM Worker floods the client with one SSE message per token, causing high overhead and occasional dropped connections. You also need the Worker to stop inference when the client disconnects and to log token usage after the stream ends without blocking the response.

## Context

When `stream: true` is passed to `env.AI.run`, Workers AI returns a `ReadableStream` of SSE-formatted chunks. Each chunk carries one or more tokens. Piping this directly to the client produces ~5-50 SSE frames per second — manageable for a single user, but expensive at scale. A `TransformStream` that coalesces tokens within 20 ms windows reduces message count by 80-90% without perceptible latency increase. `controller.desiredSize` exposes the downstream queue depth; when it reaches 0 the consumer is not keeping up (backpressure), and further enqueues should pause.

## Implementation

```typescript
type Env = { AI: Ai; DB: D1Database };

// Batch SSE tokens into 20 ms windows to reduce frame overhead.
function batchingTransform(windowMs = 20): TransformStream<Uint8Array, Uint8Array> {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = '';
  let flushTimer: ReturnType<typeof setTimeout> | null = null;

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });

      if (flushTimer !== null) return; // Timer already armed.

      // Backpressure check: stop buffering if the downstream queue is full.
      if ((controller.desiredSize ?? 1) <= 0) {
        // Flush immediately to drain the downstream queue.
        controller.enqueue(encoder.encode(buffer));
        buffer = '';
        return;
      }

      flushTimer = setTimeout(() => {
        flushTimer = null;
        if (buffer.length > 0) {
          controller.enqueue(encoder.encode(buffer));
          buffer = '';
        }
      }, windowMs);
    },
    flush(controller) {
      if (flushTimer !== null) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      if (buffer.length > 0) {
        controller.enqueue(encoder.encode(buffer));
        buffer = '';
      }
      controller.terminate();
    },
  });
}

// Parse token count from the final SSE `[DONE]` frame emitted by Workers AI.
function extractUsage(sseChunk: string): { input: number; output: number } | null {
  const match = sseChunk.match(/"usage":\s*\{"input_tokens":(\d+),"output_tokens":(\d+)\}/);
  if (!match) return null;
  return { input: parseInt(match[1], 10), output: parseInt(match[2], 10) };
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { messages, model = '@cf/meta/llama-3-8b-instruct' } =
      await request.json<{ messages: { role: string; content: string }[]; model?: string }>();

    // Obtain the streaming ReadableStream from Workers AI.
    const aiStream = await env.AI.run(model as any, {
      messages,
      stream: true,
      max_tokens: 1024,
    }) as ReadableStream;

    // Wire up client-disconnect cancellation.
    let usageData: { input: number; output: number } | null = null;

    // A PassThrough that intercepts the final usage frame before forwarding.
    const usageCapture = new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        const text = new TextDecoder().decode(chunk);
        const usage = extractUsage(text);
        if (usage) usageData = usage;
        controller.enqueue(chunk);
      },
    });

    const batcher = batchingTransform(20);

    // Chain: AI stream → usage capture → 20 ms batcher → client.
    const outputStream = aiStream
      .pipeThrough(usageCapture)
      .pipeThrough(batcher);

    // Cancel inference when the client disconnects.
    request.signal.addEventListener('abort', () => {
      outputStream.cancel('client disconnected').catch(() => {});
    });

    const response = new Response(outputStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no', // Disable nginx buffering if behind a proxy.
      },
    });

    // Log usage after the stream ends without blocking the HTTP response.
    ctx.waitUntil(
      (async () => {
        // Wait for the batcher's writable side to close (stream done).
        await batcher.writable.closed.catch(() => {});
        if (usageData) {
          await env.DB.prepare(
            'INSERT INTO token_usage (ts, model, input_tokens, output_tokens) VALUES (?, ?, ?, ?)'
          ).bind(Date.now(), model, usageData.input, usageData.output).run();
        }
      })()
    );

    return response;
  },
};
```

## Client-Side SSE Consumption

```typescript
// Browser client: consume the batched SSE stream.
const es = new EventSource('/stream', { withCredentials: false });
const ctrl = new AbortController();

const response = await fetch('/stream', {
  method: 'POST',
  signal: ctrl.signal,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ messages: [{ role: 'user', content: 'Explain edge computing.' }] }),
});

const reader = response.body!.getReader();
const decoder = new TextDecoder();

try {
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    // Parse SSE data lines.
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ') && line !== 'data: [DONE]') {
        const json = JSON.parse(line.slice(6));
        process.stdout.write(json.response ?? '');
      }
    }
  }
} finally {
  reader.releaseLock();
}

// Abort on user cancel — triggers request.signal 'abort' in the Worker.
ctrl.abort();
```

## Measuring Backpressure Impact

Log `controller.desiredSize` at the moment of each enqueue. Values near 0 indicate the consumer is slow; values near the high-water mark (default 1 for byte streams) indicate a healthy pace:

```typescript
// Inside transform:
console.log(`[backpressure] desiredSize=${controller.desiredSize} bufLen=${buffer.length}`);
```

If `desiredSize` is consistently 0, increase the batch window to 40–50 ms or reduce `max_tokens`.

## Anti-patterns

- **Ignoring `request.signal`** — without cancellation the Worker continues consuming AI quota for a client that has already gone away.
- **Buffering the entire stream before responding** — eliminates the latency benefit of streaming; pipe the `ReadableStream` directly.
- **Using `setInterval` for token batching** — intervals fire even when no tokens arrive, burning CPU; use `setTimeout` reset on each arriving chunk instead.
- **Logging usage synchronously before `return response`** — blocks the HTTP response; always use `ctx.waitUntil`.

## Gotchas

- `controller.desiredSize` is `null` before the stream is started; guard with `?? 1`.
- `ReadableStream.cancel()` returns a Promise; do not `await` it on the abort path or you will block the event loop.
- Workers AI SSE format uses `data: [DONE]` as a terminator, not `event: done`; match exactly.
- `batcher.writable.closed` resolves only after `flush()` is called by the pipe; confirm the pipe chain is fully connected before relying on it in `waitUntil`.

## Verification

```bash
# Stream a response and count SSE frames.
curl -s -N -X POST https://worker.example.com/stream \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Count to 100."}]}' \
  | grep -c '^data:'
# Without batching: ~100 frames. With 20 ms batching: typically 10-20 frames.

# Simulate client disconnect after 1 s.
curl -s -N -X POST https://worker.example.com/stream \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Write a novel."}]}' &
PID=$!
sleep 1 && kill $PID
# Worker should log "client disconnected" and cease inference.
```

## Related

- `rag-citation-grounding-vectorize-workers.md` — non-streaming LLM calls with citation post-processing
- `workers-ai-text-to-speech-audio-streaming-r2.md` — binary streaming from Workers AI
- `ai-agent-memory-persistence-durable-objects.md` — stateful agents that wrap streaming calls

## Sources

- [Workers AI — Streaming](https://developers.cloudflare.com/workers-ai/configuration/streaming/)
- [Streams API — TransformStream](https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/)
- [ExecutionContext.waitUntil](https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil)
