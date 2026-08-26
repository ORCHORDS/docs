# Workers AI Streaming Responses via Server-Sent Events

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

LLM inference for long responses can take 10–30 seconds before the first byte arrives with a blocking request, leaving users staring at a blank UI. Enabling `stream: true` on the Workers AI call and piping chunks through a `TransformStream` formatted as Server-Sent Events (SSE) lets the browser start rendering tokens as they are generated, giving a ChatGPT-style streaming experience with no WebSocket overhead.

---

## Context

When `stream: true` is passed to `ai.run()`, Workers AI returns a `ReadableStream` of newline-delimited JSON chunks instead of a resolved string. Each chunk contains a `response` field with the latest token delta. The Worker wraps this stream in a `TransformStream` that reformats each chunk as an SSE `data:` line, sets the response headers to `text/event-stream`, and returns the streaming `Response` directly. On the client, a native `EventSource` or a `fetch`-with-ReadableStream consumes the events and appends tokens to the DOM. An `AbortController` on the Worker side enforces a hard timeout so runaway generations do not hold connections indefinitely.

---

## Section 1 — wrangler.toml

```toml
name = "streaming-ai-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[ai]
binding = "AI"

[limits]
cpu_ms = 30000   # allow up to 30 s CPU time for long generations
```

## Section 2 — Worker implementation (stream pipeline)

```typescript
import { Ai } from "@cloudflare/workers-types";

export interface Env {
  AI: Ai;
}

const MODEL = "@cf/meta/llama-3.1-8b-instruct";
const STREAM_TIMEOUT_MS = 25_000; // 25 s hard limit

/**
 * Build an SSE-formatted TransformStream.
 * Input:  ReadableStream<Uint8Array> of newline-delimited JSON chunks
 *         from Workers AI (each line: {"response":"token"})
 * Output: ReadableStream<Uint8Array> of SSE frames
 *         data: {"token":"..."}\n\n
 *         data: [DONE]\n\n
 */
function buildSseTransform(): TransformStream<Uint8Array, Uint8Array> {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = "";

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });

      // Split on newlines — Workers AI emits one JSON object per line
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? ""; // keep incomplete last line in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        let token = "";
        try {
          const parsed = JSON.parse(trimmed) as { response?: string };
          token = parsed.response ?? "";
        } catch {
          // Non-JSON line from the stream — skip
          continue;
        }

        if (token) {
          // SSE frame: data: <payload>\n\n
          const ssePayload = `data: ${JSON.stringify({ token })}\n\n`;
          controller.enqueue(encoder.encode(ssePayload));
        }
      }
    },

    flush(controller) {
      // Process any remaining buffered content
      if (buffer.trim()) {
        try {
          const parsed = JSON.parse(buffer.trim()) as { response?: string };
          if (parsed.response) {
            const ssePayload = `data: ${JSON.stringify({ token: parsed.response })}\n\n`;
            controller.enqueue(new TextEncoder().encode(ssePayload));
          }
        } catch {
          // ignore malformed tail
        }
      }
      // Signal end of stream
      controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only POST /stream is accepted
    if (request.method !== "POST" || new URL(request.url).pathname !== "/stream") {
      return new Response("Not Found", { status: 404 });
    }

    const { prompt, system } = (await request.json()) as {
      prompt?: string;
      system?: string;
    };

    if (!prompt?.trim()) {
      return Response.json({ error: "Missing prompt" }, { status: 400 });
    }

    // AbortController for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(new Error("Stream timeout exceeded")),
      STREAM_TIMEOUT_MS
    );

    let aiStream: ReadableStream<Uint8Array>;

    try {
      aiStream = (await env.AI.run(
        MODEL,
        {
          messages: [
            {
              role: "system",
              content: system ?? "You are a helpful assistant.",
            },
            { role: "user", content: prompt },
          ],
          stream: true,
          max_tokens: 1024,
        },
        { signal: controller.signal }
      )) as ReadableStream<Uint8Array>;
    } catch (err) {
      clearTimeout(timeoutId);
      return Response.json(
        { error: (err as Error).message },
        { status: 500 }
      );
    }

    // Pipe AI stream → SSE transform
    const sseStream = aiStream.pipeThrough(buildSseTransform());

    // Clear the timeout once the stream is fully consumed
    sseStream.pipeTo(new WritableStream()).finally(() => clearTimeout(timeoutId));

    return new Response(
      aiStream.pipeThrough(buildSseTransform()),
      {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          "X-Accel-Buffering": "no",   // disable Nginx buffering if behind a proxy
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  },
};
```

## Section 3 — Client-side EventSource consumption

```typescript
// client.ts — runs in the browser
interface TokenEvent {
  token: string;
}

async function streamCompletion(
  prompt: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: Error) => void
): Promise<void> {
  // EventSource only supports GET; for POST payloads use fetch + ReadableStream
  const response = await fetch("/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok || !response.body) {
    onError(new Error(`HTTP ${response.status}`));
    return;
  }

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .getReader();

  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += value;
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const event of events) {
      const dataLine = event
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!dataLine) continue;

      const payload = dataLine.slice(6).trim();
      if (payload === "[DONE]") {
        onDone();
        return;
      }

      try {
        const { token } = JSON.parse(payload) as TokenEvent;
        if (token) onToken(token);
      } catch {
        // ignore malformed event
      }
    }
  }

  onDone();
}

// Usage example
const output = document.getElementById("output") as HTMLElement;
streamCompletion(
  "Explain Cloudflare Workers in simple terms.",
  (token) => { output.textContent += token; },
  () => { console.log("Stream complete"); },
  (err) => { console.error(err); }
);
```

---

## Anti-patterns

- **Using `EventSource` for POST requests** — `EventSource` only supports GET with no body; use `fetch()` with `response.body.getReader()` to stream POST responses instead.
- **No timeout on the AI stream** — Without an `AbortController` timeout, a stalled inference holds a Worker connection slot until the Worker's global CPU limit kills it, degrading throughput for other requests.
- **Buffering the full response before returning** — Awaiting `ai.run()` without `stream: true` blocks the response until the model finishes; always use `stream: true` for interactive UI use cases.
- **Forgetting `X-Accel-Buffering: no`** — Nginx and Cloudflare Cache both buffer responses by default; this header tells intermediaries to pass chunks through immediately.

---

## Gotchas

- Workers AI streaming requires `stream: true` at call time; toggling it after the response starts is not possible.
- The `AbortController.signal` parameter on `ai.run()` is supported in Workers AI bindings from compatibility date `2024-09-23` and later.
- SSE connections are limited by the browser's per-origin connection pool (typically 6); if you open many simultaneous streams, switch to HTTP/2 multiplexing or use a single shared `EventSource` with topic filtering.
- The `TransformStream` `flush()` callback is not guaranteed to fire if the client disconnects mid-stream; wrap cleanup logic in the outer `finally` block on the `pipeTo` call.
- Workers have a maximum response streaming duration; very long generations may be cut off by the platform's wall-clock limit even with a high `cpu_ms` setting.

---

## Verification

```bash
# Start dev server
npx wrangler dev --remote

# Stream a completion and watch tokens arrive
curl -N -X POST http://localhost:8787/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Write a short poem about distributed computing."}'

# Expected: SSE lines printed incrementally, ending with:
# data: [DONE]

# Verify timeout fires for an extremely long prompt
curl -N -X POST http://localhost:8787/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Count from 1 to 10000, one number per line."}'
```

---

## Related

- `workers-ai-structured-output-json-schema.md`
- `workers-ai-tool-calling-d1-queries.md`

---

## Sources

- Cloudflare Workers AI streaming docs — https://developers.cloudflare.com/workers-ai/configuration/how-to-use-streaming/
- MDN Server-Sent Events — https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- Streams API — https://developer.mozilla.org/en-US/docs/Web/API/Streams_API
