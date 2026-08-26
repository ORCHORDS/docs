# Workers AI: Streaming Text Generation

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to stream LLM text responses token-by-token from Workers AI to a browser or API client to reduce perceived latency, power chat-style UIs, or deliver progressive completions without waiting for the full inference result.

## Context

Workers AI exposes a `stream` option on the AI binding's `.run()` call. When enabled, the binding returns a `ReadableStream<Uint8Array>` encoded in Server-Sent Events (SSE) format. The worker pipes this stream directly through `Response`, allowing the client to receive tokens as they are generated. This works with any text-generation model available in the Workers AI catalog (e.g., `@cf/meta/llama-3.1-8b-instruct`, `@cf/mistral/mistral-7b-instruct-v0.1`).

Key constraints:
- Streaming responses must not be cached at the edge.
- The SSE envelope follows the OpenAI-compatible `data: {"response":"..."}` format for most models.
- Workers have a 30-second CPU time limit; long generations should be tested under `wrangler dev --remote` to catch wall-clock timeouts.
- `TransformStream` can be inserted in the pipeline for token filtering, logging, or rate-limiting without buffering the entire response.

## Solution

### 1. Basic streaming worker

```typescript
// src/index.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { prompt, max_tokens = 512 } = await request.json<{
      prompt: string;
      max_tokens?: number;
    }>();

    if (!prompt?.trim()) {
      return new Response(JSON.stringify({ error: 'prompt is required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const stream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      {
        prompt,
        max_tokens,
        stream: true,   // <-- key option
      }
    ) as ReadableStream;

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  },
};
```

### 2. SSE token interception with TransformStream

Insert a `TransformStream` to count tokens and log them to Analytics Engine without buffering the full response:

```typescript
function tokenCountingTransform(
  onComplete: (count: number) => void
): TransformStream<Uint8Array, Uint8Array> {
  let tokenCount = 0;
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  return new TransformStream({
    transform(chunk, controller) {
      const text = decoder.decode(chunk, { stream: true });

      // SSE lines: "data: {\"response\":\"token\"}\n\n"
      for (const line of text.split('\n')) {
        if (line.startsWith('data: ') && line !== 'data: [DONE]') {
          try {
            const parsed = JSON.parse(line.slice(6)) as { response?: string };
            if (parsed.response) tokenCount += 1; // approx 1 token per SSE event
          } catch {
            // malformed line — pass through
          }
        }
      }

      controller.enqueue(chunk);
    },
    flush() {
      onComplete(tokenCount);
    },
  });
}

// Usage inside fetch handler:
const rawStream = await env.AI.run(
  '@cf/meta/llama-3.1-8b-instruct',
  { prompt, stream: true }
) as ReadableStream;

const { readable, writable } = tokenCountingTransform((count) => {
  // fire-and-forget analytics
  env.ANALYTICS.writeDataPoint({
    blobs: [prompt.slice(0, 64)],
    doubles: [count],
    indexes: ['stream-token-count'],
  });
});

rawStream.pipeTo(writable); // no await — stream continues in background

return new Response(readable, {
  headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' },
});
```

### 3. Client-side EventSource consumption

```typescript
// Browser / client-side TypeScript
function streamCompletion(
  prompt: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: Event) => void
): () => void {
  // EventSource requires GET; for POST payloads use fetch + ReadableStream
  const controller = new AbortController();

  fetch('/api/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onError(new Event('error'));
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) { onDone(); break; }

        const text = decoder.decode(value, { stream: true });
        for (const line of text.split('\n')) {
          if (line === 'data: [DONE]') { onDone(); return; }
          if (line.startsWith('data: ')) {
            try {
              const { response } = JSON.parse(line.slice(6)) as { response: string };
              if (response) onToken(response);
            } catch { /* skip */ }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err);
    });

  // Return cancel function
  return () => controller.abort();
}
```

### 4. Stream cancellation from server side

```typescript
// Honour client disconnect to avoid wasting AI compute
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json<{ prompt: string }>();

    const stream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      { prompt, stream: true }
    ) as ReadableStream;

    // When the client closes the connection, cancel the upstream stream
    request.signal.addEventListener('abort', () => {
      stream.cancel().catch(() => {});
    });

    return new Response(stream, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' },
    });
  },
};
```

### 5. Error handling inside a stream

```typescript
async function safeStream(
  env: Env,
  prompt: string
): Promise<Response> {
  let stream: ReadableStream;

  try {
    stream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      { prompt, stream: true }
    ) as ReadableStream;
  } catch (err) {
    // AI binding threw before stream started (quota, model unavailable, etc.)
    const body = `data: ${JSON.stringify({ error: String(err) })}\n\ndata: [DONE]\n\n`;
    return new Response(body, {
      status: 200, // keep 200 so EventSource doesn't retry infinitely
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' },
    });
  }

  return new Response(stream, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' },
  });
}
```

## Implementation Details

- The Workers AI binding serialises the SSE payload; each `data:` line carries a JSON object with a `response` string field and an optional `p` (token probability) field depending on the model.
- `[DONE]` sentinel is the last SSE event and mirrors OpenAI's streaming protocol, making adapter code simpler.
- Setting `max_tokens` controls the maximum stream length. Without it the model uses its default context window which may exhaust CPU time on large prompts.
- Workers AI streaming does **not** support concurrent `pipeTo` / `tee` targets — clone the stream with `stream.tee()` if you need a secondary consumer.
- `wrangler.toml` binding declaration: `[[ai]]` with `binding = "AI"` is all that is required — no Workers AI plan flags needed for beta access.

## Anti-patterns

- **Buffering the full stream before responding**: defeats the purpose; never call `new Response(await streamToText(stream))`.
- **Setting `Cache-Control: public`** on SSE responses: causes edge caches to serve stale completions to other users.
- **Ignoring `request.signal`**: wastes AI quota after the client disconnects.
- **Using `EventSource` for POST**: `EventSource` only supports GET; use `fetch` + `ReadableStream` reader for POST bodies.
- **Parsing SSE with `split('\\n\\n')` only**: chunks can arrive mid-event; maintain a line buffer across chunks.

## Gotchas

- Workers free tier CPU time (10 ms) is insufficient for streaming inference — use the paid Workers plan or `wrangler dev --remote` for realistic local testing.
- The `stream` option silently falls back to non-streaming for models that do not support it; check the model capability page before shipping.
- Cloudflare's default `waitUntil` semantics do not apply inside a piped stream — analytics calls after `pipeTo` must be wrapped in `ctx.waitUntil`.
- Durable Objects and Workers AI streaming can conflict if the DO's websocket handler buffers chunks; pipe directly to a `WebSocket.send` inside the message loop instead.

## Verification

```bash
# Local remote dev
wrangler dev --remote

# cURL streaming test
curl -N -X POST http://localhost:8787/api/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Count from 1 to 5, one word per line."}'

# Expected output (token-by-token SSE lines):
# data: {"response":"1"}
# data: {"response":"\n"}
# ...
# data: [DONE]
```

## Related

- `documentation/docs/policies/ai-ml/workers-ai-prompt-caching-kv.md` — cache completed responses to avoid repeat inference.
- `documentation/docs/policies/ai-ml/workers-ai-function-calling-tools.md` — structured outputs that pair with streaming.
- Cloudflare Workers AI docs: https://developers.cloudflare.com/workers-ai/

## Sources

- Cloudflare Workers AI Streaming docs: https://developers.cloudflare.com/workers-ai/configuration/bindings/#stream-responses
- SSE specification (W3C): https://html.spec.whatwg.org/multipage/server-sent-events.html
- Workers Runtime API — ReadableStream: https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/
