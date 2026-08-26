# Workers AI Streaming via Server-Sent Events

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Users see a blank screen for 3–8 seconds while a long Workers AI response is generated, then the
full text appears at once. You want a ChatGPT-style typewriter effect: tokens appear incrementally
in the browser as they are produced. Workers AI supports streaming inference; the challenge is
bridging the raw `ReadableStream` from the binding into the SSE wire format browsers expect and
handling the `[DONE]` sentinel correctly.

## Context

Server-Sent Events (SSE) is the standard HTTP-based unidirectional streaming mechanism supported
natively by all modern browsers via the `EventSource` API (and by `fetch` with
`ReadableStream` on the client). Workers AI returns a `ReadableStream<Uint8Array>` when
`stream: true` is set on a text-generation or chat call. The stream delivers newline-delimited JSON
objects, each prefixed with `data: `, and terminates with `data: [DONE]` — identical to the OpenAI
streaming format. A Cloudflare Worker can pass this stream straight through to the browser after
setting the appropriate `Content-Type: text/event-stream` header, or transform it before forwarding.

Key SSE wire format rules:
- Each message is one or more `field: value\n` lines followed by a blank line `\n`.
- The `data` field carries the payload.
- `data: [DONE]` signals end-of-stream (browser-side code must recognise and close the connection).
- The response header must include `Cache-Control: no-cache` to prevent buffering by CDN layers.

## Minimal Pass-Through SSE Endpoint

The simplest implementation passes the Workers AI stream directly to the browser. No transformation
needed because the binding already emits SSE-formatted chunks.

```typescript
// src/stream.ts
import type { Env } from "./types";

export async function handleStreamRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const { messages } = await request.json<{
    messages: Array<{ role: string; content: string }>;
  }>();

  // stream: true returns ReadableStream<Uint8Array>
  const aiStream = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages,
    max_tokens: 1024,
    stream: true,
  });

  if (!(aiStream instanceof ReadableStream)) {
    // Fallback: model returned full response (shouldn't happen with stream:true)
    const text = (aiStream as { response?: string }).response ?? "";
    return new Response(`data: ${JSON.stringify({ response: text })}\ndata: [DONE]\n\n`, {
      headers: sseHeaders(),
    });
  }

  return new Response(aiStream as ReadableStream, {
    headers: sseHeaders(),
  });
}

function sseHeaders(): HeadersInit {
  return {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    // Allow browser EventSource from any origin (restrict in production):
    "Access-Control-Allow-Origin": "*",
  };
}
```

## Transforming the Stream (Token Extraction)

When you need to inspect, filter, or augment each token before forwarding, set up a
`TransformStream` between the Workers AI output and the browser.

```typescript
// src/streamTransform.ts

interface AiStreamChunk {
  response?: string;    // partial token from Workers AI
  p?: string;          // padding field (ignore)
}

/**
 * Transform raw Workers AI SSE bytes into structured SSE chunks,
 * optionally filtering or augmenting each token.
 */
export function createTokenTransform(): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? ""; // retain incomplete last line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();

        if (payload === "[DONE]") {
          // Forward the terminator unchanged
          controller.enqueue(encoder.encode("data: [DONE]\n\n"));
          continue;
        }

        try {
          const parsed: AiStreamChunk = JSON.parse(payload);
          if (!parsed.response) continue;

          // Augment or filter the token here:
          const token = parsed.response; // e.g. sanitise HTML

          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ token })}\n\n`)
          );
        } catch {
          // Malformed JSON chunk — skip
        }
      }
    },
    flush(controller) {
      // Flush any remaining buffer content
      if (buffer.startsWith("data: ")) {
        controller.enqueue(new TextEncoder().encode(buffer + "\n\n"));
      }
    },
  });
}
```

```typescript
// src/streamWithTransform.ts
import { createTokenTransform } from "./streamTransform";
import type { Env } from "./types";

export async function handleTransformedStream(
  request: Request,
  env: Env
): Promise<Response> {
  const { messages } = await request.json<{
    messages: Array<{ role: string; content: string }>;
  }>();

  const aiStream = (await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages,
    max_tokens: 1024,
    stream: true,
  })) as ReadableStream<Uint8Array>;

  const transformed = aiStream.pipeThrough(createTokenTransform());

  return new Response(transformed, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
```

## Browser Client (EventSource)

```html
<!-- public/index.html -->
<script>
async function streamChat(userMessage) {
  const outputEl = document.getElementById("output");
  outputEl.textContent = "";

  // EventSource only supports GET; use fetch + ReadableStream for POST.
  const response = await fetch("/api/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: [{ role: "user", content: userMessage }],
    }),
  });

  if (!response.ok || !response.body) {
    outputEl.textContent = "Error: " + response.status;
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;

      try {
        const parsed = JSON.parse(data);
        // Works with both pass-through (parsed.response) and transformed (parsed.token):
        outputEl.textContent += parsed.response ?? parsed.token ?? "";
      } catch { /* ignore */ }
    }
  }
}
</script>
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "ai-sse-worker"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"
```

## Handling CORS for Cross-Origin SSE

If the Worker is on a different origin than the frontend, add CORS preflight handling.

```typescript
// src/cors.ts
export function handleOptions(request: Request): Response | null {
  if (request.method !== "OPTIONS") return null;
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Max-Age": "86400",
    },
  });
}
```

## Anti-patterns

- **Buffering the full Workers AI stream before returning** — this defeats the entire purpose.
  Never `await response.text()` on the AI stream before piping it forward.
- **Using `EventSource` for POST requests** — `EventSource` only supports GET. Use `fetch` with
  `ReadableStream` on the client side for POST-based SSE (as shown above).
- **Forgetting `Cache-Control: no-cache`** — Cloudflare's CDN layer may buffer SSE responses
  without this header, causing the browser to receive tokens in large batches rather than one by one.
- **Not forwarding `[DONE]`** — if the client never sees the sentinel it hangs the connection open.
  Always forward or emit `data: [DONE]\n\n` at stream end.
- **Wrapping the stream in a JSON response body** — `new Response(JSON.stringify(stream))` serialises
  the stream object reference, not its bytes. Pass the `ReadableStream` directly as the `Response`
  body.

## Gotchas

- Workers AI `stream: true` is not supported by all models. Check the model's documentation page;
  unsupported models return the full response object even when `stream: true` is set.
- The AI Gateway does **not** cache streaming responses. If you route through AI Gateway with
  `cf-aig-cache-ttl`, it is ignored for streamed calls.
- Cloudflare's CDN will not compress `text/event-stream` responses. The slight overhead of SSE
  framing (`data: ` prefix, double newline) is acceptable — typically +6–8 bytes per token.
- `Connection: keep-alive` is advisory in HTTP/2; browsers using HTTP/2 connections ignore it but
  still stream correctly.
- If using the Workers AI REST API (not the binding) through AI Gateway, the response body is
  already in SSE format — pipe `response.body` directly without double-encoding.

## Verification

```bash
# Test SSE output with curl — tokens should appear incrementally:
curl -N -X POST http://localhost:8787/api/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Count from 1 to 20 slowly."}]}'

# Each line should look like:
# data: {"response":"1"}
# data: {"response":","}
# ...
# data: [DONE]
```

## Related

- `cloudflare-workers-ai-streaming-inference.md` — binding-level streaming fundamentals
- `llm-streaming-responses.md` — generic streaming patterns across providers
- `ai-gateway-caching.md` — why SSE bypasses AI Gateway cache
- `workers-ai-inference-parameter-tuning.md` — controlling token generation rate indirectly via max_tokens

## Sources

- Cloudflare Workers AI streaming docs: https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/#using-streaming
- MDN Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- Cloudflare Workers `ReadableStream` / `TransformStream`: https://developers.cloudflare.com/workers/runtime-apis/streams/
- AI Gateway caching and streaming: https://developers.cloudflare.com/ai-gateway/configuration/caching/
