# Workers AI Streaming Text with ReadableStream and SSE

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want token-by-token streaming from a Workers AI text model so users see output as it is generated rather than waiting for the full response. Workers AI supports `stream: true` which returns an `EventSource`-compatible byte stream that you pipe through a `TransformStream` and return as a proper SSE `Response`.

---

## Context

When `stream: true` is passed to `env.AI.run`, Workers AI returns a `ReadableStream` of `EventSourceMessage` chunks rather than a plain string. Each chunk contains a `data:` line with a JSON payload holding a `response` delta and a terminal `[DONE]` sentinel. A `TransformStream` normalises the raw bytes into valid SSE format. The `Response` must carry `Content-Type: text/event-stream` and `Cache-Control: no-cache` headers, and the body must be the readable side of the transform. On the client, React reads the stream via `fetch` + `ReadableStream.getReader()` inside a `useEffect` hook so each token appends to local state without a full re-render cycle.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "ai-stream"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[ai]
binding = "AI"
```

---

## Section 2 — Streaming Worker

```typescript
// src/index.ts
export interface Env {
  AI: Ai;
}

const MODEL = "@cf/meta/llama-3.1-8b-instruct";

/**
 * TransformStream that converts raw Workers AI SSE bytes into clean
 * `data: <delta>\n\n` lines for browser EventSource / fetch-stream consumers.
 */
function makeSSETransform(): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed === "data: [DONE]") continue;

        // Workers AI emits `data: {"response":"token", ...}`
        if (trimmed.startsWith("data: ")) {
          try {
            const json = JSON.parse(trimmed.slice(6));
            const delta: string = json.response ?? "";
            if (delta) {
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ delta })}\n\n`));
            }
          } catch {
            // malformed chunk — skip
          }
        }
      }
    },
    flush(controller) {
      // Flush remaining buffer
      if (buffer.trim() && buffer.trim() !== "data: [DONE]") {
        try {
          const json = JSON.parse(buffer.trim().slice(6));
          const delta: string = json.response ?? "";
          if (delta) {
            const encoder2 = new TextEncoder();
            controller.enqueue(
              encoder2.encode(`data: ${JSON.stringify({ delta })}\n\n`)
            );
          }
        } catch { /* ignore */ }
      }
      const encoder3 = new TextEncoder();
      controller.enqueue(encoder3.encode("data: [DONE]\n\n"));
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const { prompt, system } = await request.json<{
      prompt: string;
      system?: string;
    }>();

    const messages = [
      ...(system ? [{ role: "system", content: system }] : []),
      { role: "user", content: prompt },
    ];

    // stream: true → ReadableStream
    const aiStream = (await env.AI.run(MODEL, {
      messages,
      stream: true,
    })) as ReadableStream<Uint8Array>;

    const { readable, writable } = makeSSETransform();
    aiStream.pipeTo(writable);

    return new Response(readable, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no", // disable Nginx buffering if proxied
      },
    });
  },
};
```

---

## Section 3 — React Client Hook

```typescript
// client/useAIStream.ts
import { useState, useCallback } from "react";

interface UseAIStreamResult {
  text: string;
  loading: boolean;
  error: string | null;
  stream: (prompt: string, system?: string) => Promise<void>;
  reset: () => void;
}

export function useAIStream(endpoint: string): UseAIStreamResult {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setText("");
    setError(null);
  }, []);

  const stream = useCallback(
    async (prompt: string, system?: string) => {
      setText("");
      setError(null);
      setLoading(true);

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, system }),
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body
          .pipeThrough(new TextDecoderStream())
          .getReader();

        let partialLine = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          partialLine += value;
          const events = partialLine.split("\n\n");
          partialLine = events.pop() ?? "";

          for (const event of events) {
            const dataLine = event
              .split("\n")
              .find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            const payload = dataLine.slice(6);
            if (payload === "[DONE]") return;
            try {
              const { delta } = JSON.parse(payload) as { delta: string };
              setText((prev) => prev + delta);
            } catch { /* skip malformed */ }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [endpoint]
  );

  return { text, loading, error, stream, reset };
}
```

---

## Anti-patterns

- **Returning `await env.AI.run(...)` directly as the Response body without a TransformStream** — the raw Workers AI stream emits its own framing that may not match what browsers expect from a standard EventSource.
- **Setting `Content-Type: application/json` on a streaming response** — browsers will buffer the entire response before making it available; always use `text/event-stream`.
- **Reading the stream inside a `useEffect` without aborting on unmount** — attach an `AbortController` and call `controller.abort()` in the cleanup function to prevent state updates on unmounted components.
- **Enabling `stream: true` alongside tool calling** — Workers AI does not support both simultaneously; use non-streaming for agentic flows.

---

## Gotchas

- The sentinel `data: [DONE]\n\n` must be emitted last or the client reader loop never exits cleanly.
- `X-Accel-Buffering: no` is required when your Worker sits behind an Nginx reverse proxy or Cloudflare for Teams gateway that buffers responses.
- `TextDecoderStream` is available in all modern browsers and in the Workers runtime; no polyfill needed.
- Very long streamed responses can trigger Cloudflare's 100-second response timeout — consider chunking long-form content into multiple requests.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Stream raw SSE tokens from the terminal
curl -sN -X POST https://ai-stream.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Count slowly from 1 to 10, one number per line."}'

# Expect incremental output lines like:
# data: {"delta":"1"}
# data: {"delta":"\n2"}
# ...
# data: [DONE]
```

---

## Related

- `workers-ai-tool-calling-function-dispatch.md`
- `workers-ai-rag-chunking-vectorize.md`

---

## Sources

- Cloudflare Workers AI streaming guide — https://developers.cloudflare.com/workers-ai/get-started/workers-api/#stream-response
- MDN ReadableStream — https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream
