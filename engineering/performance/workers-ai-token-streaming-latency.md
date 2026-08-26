# Workers AI Token Streaming Latency

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A chatbot endpoint backed by the native Workers AI binding returns the entire model
response in one block after 2–8 seconds of silence. Users see a blank input area while
the model generates. Switching to `stream: true` on the `env.AI.run()` call reduces
perceived latency dramatically — the first tokens arrive in 150–400 ms — but the
implementation has edge cases: streams that stall, encoding issues with the SSE framing,
timeout errors from the client before the stream completes, and difficulty forwarding the
stream when a Workers AI call sits behind another Worker or a D1 lookup.

## Context

Workers AI exposes two execution modes:

| Mode | API | Client receives | Latency profile |
|------|-----|-----------------|-----------------|
| Blocking | `await env.AI.run(model, opts)` | Complete response | Full generation time (2–10 s) |
| Streaming | `await env.AI.run(model, { stream: true })` | `ReadableStream` of SSE chunks | First chunk in 150–400 ms |

In streaming mode, `env.AI.run()` returns a `ReadableStream<Uint8Array>` immediately.
Each chunk is a Server-Sent Event (`data: {...}\n\n`). The stream ends with a
`data: [DONE]\n\n` sentinel. A Workers `Response` that wraps this stream begins
flushing to the HTTP/2 client as soon as the first chunk is enqueued — the runtime does
not buffer the body.

TTFB in streaming mode is dominated by:
1. Workers AI model cold-start (first request to a model not in active use at the PoP):
   adds 100–800 ms.
2. Model prefill time: time to process the prompt tokens before generation begins.
3. Workers subrequest overhead: `env.AI.run()` counts as one subrequest.

## Minimal Streaming Handler

```typescript
import { Ai } from '@cloudflare/ai';

interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json<{ prompt: string }>();

    const stream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      {
        prompt,
        stream: true,
        max_tokens: 512,
      },
    ) as ReadableStream;

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        // Required for EventSource in browsers that check CORS
        'Access-Control-Allow-Origin': '*',
      },
    });
  },
};
```

## Forwarding the Stream Through a Transform

Add token-level processing (content filtering, usage counting, stop-sequence detection)
without buffering the entire response:

```typescript
interface TokenChunk {
  response?: string;
}

function createTokenTransform(onToken: (token: string) => void): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  return new TransformStream({
    transform(chunk, controller) {
      const text = decoder.decode(chunk, { stream: true });
      // Each SSE frame: "data: {...}\n\n"
      for (const line of text.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ') || trimmed === 'data: [DONE]') {
          controller.enqueue(encoder.encode(`${line}\n`));
          continue;
        }
        try {
          const payload: TokenChunk = JSON.parse(trimmed.slice(6));
          if (payload.response) {
            onToken(payload.response);
          }
        } catch {
          // Malformed JSON in SSE chunk — pass through unchanged
        }
        controller.enqueue(encoder.encode(`${line}\n`));
      }
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt } = await request.json<{ prompt: string }>();

    let tokenCount = 0;
    const countingTransform = createTokenTransform(() => { tokenCount++; });

    const aiStream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      { prompt, stream: true, max_tokens: 256 },
    ) as ReadableStream<Uint8Array>;

    const transformed = aiStream.pipeThrough(countingTransform);

    // Log token count after the stream ends (non-blocking)
    const ctx = { waitUntil: (p: Promise<unknown>) => void p }; // passed from context
    // In practice use: context.waitUntil(logUsage(tokenCount, env))

    return new Response(transformed, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
    });
  },
};
```

## Prefill Latency Reduction: Prompt Caching

Workers AI does not expose a native prompt cache API, but prompt prefill time scales
with token count. Keep system prompts short and push variable content to the user turn.
For repeated calls with identical system prompts, the model may benefit from KV-cached
context windows passed as structured messages:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userMessage } = await request.json<{ userMessage: string }>();

    // Keep the system prompt compact to reduce prefill tokens
    const messages = [
      {
        role: 'system' as const,
        content: 'You are a concise assistant. Reply in under 100 words.',
      },
      { role: 'user' as const, content: userMessage },
    ];

    const stream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      { messages, stream: true, max_tokens: 256, temperature: 0 },
    ) as ReadableStream;

    return new Response(stream, {
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
    });
  },
};
```

## Model Selection for Latency vs. Quality

Workers AI hosts several models with different latency profiles. Choose based on your
TTFB and generation-rate requirements:

| Model | First token (warm) | Tokens/s | Use case |
|-------|--------------------|----------|----------|
| `@cf/meta/llama-3.1-8b-instruct` | ~150 ms | ~60 | Chat, classification |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | ~300 ms | ~40 | Complex reasoning |
| `@cf/qwen/qwen2.5-coder-32b-instruct` | ~400 ms | ~30 | Code generation |
| `@cf/mistral/mistral-7b-instruct-v0.2` | ~120 ms | ~70 | Low-latency chat |

Route model choice at the edge based on detected task complexity:

```typescript
function selectModel(prompt: string): string {
  const isCode = /```|function|class|import |SELECT |CREATE TABLE/i.test(prompt);
  const isLong = prompt.split(/\s+/).length > 200;

  if (isCode) return '@cf/qwen/qwen2.5-coder-32b-instruct';
  if (isLong) return '@cf/meta/llama-3.3-70b-instruct-fp8-fast';
  return '@cf/meta/llama-3.1-8b-instruct';
}
```

## Client-Side EventSource Consumption

```typescript
// Browser client consuming the SSE stream
function streamCompletion(prompt: string, onToken: (t: string) => void): void {
  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  }).then(async (res) => {
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ') || line === 'data: [DONE]') continue;
        try {
          const chunk = JSON.parse(line.slice(6));
          if (chunk.response) onToken(chunk.response);
        } catch { /* malformed chunk */ }
      }
    }
  });
}
```

## Anti-patterns

- **Not setting `Content-Type: text/event-stream`**: browsers buffer the response body
  until they recognise it as SSE. Without the correct content-type, the entire stream is
  buffered and delivered at once, defeating streaming.
- **Awaiting `env.AI.run()` without `stream: true` then streaming the result**: this
  buffers the full response in the Worker before writing to the client — TTFB equals the
  full generation time.
- **Using a `Response` with a buffered body then piping**: `return new Response(await
  stream.text())` is equivalent to blocking mode. Always pipe the `ReadableStream`
  directly into the `Response` constructor.
- **Running sequential AI calls**: each `env.AI.run()` is a subrequest. Running two AI
  calls sequentially doubles the generation wait. Fan-out is rarely needed for single
  prompts, but avoid inadvertent sequential calls in loops.

## Gotchas

- Workers AI streaming requires the `stream: true` option explicitly. The return type
  changes from `AiTextGenerationOutput` to `ReadableStream<Uint8Array>` — TypeScript
  needs a type assertion because the union return type is not narrowed automatically.
- Workers AI model warm-up adds 100–800 ms on the first request to a model after a cold
  period at a PoP. Subsequent requests on the same PoP are warm. There is no manual
  "keep-warm" API.
- The `[DONE]` sentinel is a string, not a JSON object. SSE parsers that always call
  `JSON.parse()` without checking for `[DONE]` will throw on the final frame.
- Workers AI counts against the same 50 simultaneous subrequest limit per invocation as
  `fetch()`. For a Worker that also fans out to KV or D1, budget subrequests carefully.
- Cloudflare's network terminates HTTP/2 streams at the edge. If the client uses
  `EventSource` (which uses HTTP/1.1 in many browsers), the stream is upgraded to SSE
  over HTTP/1.1. HTTP/2 clients using `fetch()` stream over a multiplexed connection.

## Verification

1. Measure TTFB with `curl --no-buffer -s -o /dev/null -w "%{time_starttransfer}\n"
   -X POST -H "Content-Type: application/json" -d '{"prompt":"Hi"}' https://your-worker/`.
   Target: <500 ms on warm models.
2. In Chrome DevTools, open the Network tab, click the streaming response, then Timing.
   `Waiting (TTFB)` should be <500 ms; `Content Download` should increase incrementally
   as tokens arrive, not in one jump at the end.
3. Add a Cloudflare Worker Analytics Engine event on each request with model name,
   `stream: true/false`, and TTFB. Track P50/P99 TTFB per model using GraphQL API.
4. Verify no buffering by tailing logs: `wrangler tail --format pretty` and checking that
   the Worker response is sent before the AI run completes.

## Related

- `workers-llm-streaming-responses.md`
- `workers-ai-inference-response-caching.md`
- `workers-response-streaming-ttfb-optimization.md`
- `sse-vs-websockets-real-time-streaming.md`
- `workers-fetch-connection-reuse-tcp.md`

## Sources

- Workers AI Run API — https://developers.cloudflare.com/workers-ai/get-started/workers-binding/
- Workers AI Models Catalog — https://developers.cloudflare.com/workers-ai/models/
- Workers AI Streaming — https://developers.cloudflare.com/workers-ai/configuration/streaming/
- WHATWG Streams API — https://streams.spec.whatwg.org/
- Server-Sent Events — https://html.spec.whatwg.org/multipage/server-sent-events.html
