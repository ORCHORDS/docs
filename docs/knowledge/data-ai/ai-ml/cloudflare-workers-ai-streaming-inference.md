# Cloudflare Workers AI — Streaming Inference

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project generates AI-powered post captions, content warnings, and reply suggestions. Without streaming, a 200-token response takes 4-6 s on LTE before the first byte appears, causing users to abandon the interaction. Streaming via Server-Sent Events (SSE) delivers tokens as they are generated, cutting perceived latency to under 400 ms for first token on Wi-Fi.

## Context

Cloudflare Workers AI exposes streaming inference through the `stream: true` binding parameter. The Worker returns a `ReadableStream<Uint8Array>` whose chunks are newline-delimited SSE frames (`data: {...}\n\n`). Desktop clients consume this with the browser `EventSource` API; mobile clients (React Native, native iOS/Android) use `fetch` with a `ReadableStream` body reader since `EventSource` is unavailable in the mobile JS runtime and requires a polyfill. Token budget management prevents runaway generation from consuming the per-account daily token quota.

---

## 1. Enabling Streaming in a Worker

Workers AI inference is accessed via `env.AI.run()`. Pass `stream: true` to receive a `ReadableStream` instead of a resolved JSON object.

```typescript
// src/workers/ai-stream.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { prompt, maxTokens = 256 } = await request.json<{
      prompt: string;
      maxTokens?: number;
    }>();

    // Sanitize before forwarding — see llm-prompt-injection-defense-workers.md
    const sanitized = sanitizePrompt(prompt);

    const stream = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      {
        messages: [
          { role: 'system', content: example project_SYSTEM_PROMPT },
          { role: 'user', content: sanitized },
        ],
        stream: true,           // key flag
        max_tokens: maxTokens,  // hard cap — see §4
      }
    );

    // Workers AI returns ReadableStream<Uint8Array> when stream:true
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': 'https://example.com',
      },
    });
  },
};
```

The binding requires `AI` declared in `wrangler.toml`:

```toml
[ai]
binding = "AI"
```

---

## 2. SSE Frame Format

Each chunk from Workers AI is an SSE frame. The stream ends with `data: [DONE]`.

```
data: {"response":"Hey"}

data: {"response":" there"}

data: {"response":"!"}

data: [DONE]
```

Parse defensively — the `response` field may be absent on the final frame, and non-data lines (comments starting with `:`) must be skipped.

```typescript
// Shared parser — works in both browser and React Native
export function parseSSEChunk(raw: string): string | null {
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data: ')) continue;
    const payload = line.slice(6).trim();
    if (payload === '[DONE]') return null;
    try {
      const obj = JSON.parse(payload);
      return obj.response ?? obj.token ?? null;
    } catch {
      return null;
    }
  }
  return null;
}
```

---

## 3. Desktop: EventSource vs. fetch Streaming

`EventSource` is the native browser SSE interface but only supports GET and has no request body. Because example project sends a POST body with the prompt, desktop uses `fetch` with `ReadableStream` exactly like mobile.

```typescript
// client/src/hooks/useAIStream.ts (React, desktop)
export async function streamGeneration(
  prompt: string,
  onToken: (tok: string) => void,
  signal: AbortSignal
): Promise<void> {
  const res = await fetch('/api/ai/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, maxTokens: 200 }),
    signal,
  });

  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    const token = parseSSEChunk(text);
    if (token) onToken(token);
  }
}
```

---

## 4. Mobile: React Native ReadableStream Handling

React Native's `fetch` does not buffer the full body before resolving; it streams via `response.body`. On older RN versions (< 0.72) `ReadableStream` support is incomplete — use the `react-native-fetch-api` polyfill or relay through a WebSocket bridge.

```typescript
// mobile/src/services/aiStream.ts (React Native 0.73+)
export async function streamGenerationMobile(
  prompt: string,
  onToken: (tok: string) => void,
  signal: AbortSignal
): Promise<void> {
  const res = await fetch('https://api.example.com/ai/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${await getSessionToken()}`,
    },
    body: JSON.stringify({
      prompt,
      maxTokens: 128, // Lower budget on mobile — see §5
    }),
    // @ts-ignore — RN requires explicit opt-in
    reactNative: { textStreaming: true },
    signal,
  });

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames may be split across chunks — accumulate until \n\n
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';

    for (const frame of frames) {
      const token = parseSSEChunk(frame);
      if (token) onToken(token);
    }
  }
}
```

**Key difference**: buffer accumulation is mandatory on mobile because chunk boundaries rarely align with SSE frame boundaries over a cellular connection.

---

## 5. Token Budget Management

Workers AI charges per token (input + output). Uncontrolled generation erodes daily quotas fast on a social platform with many concurrent users.

```
Model context limits (as of mid-2026):
┌──────────────────────────────────────────┬──────────┬──────────┐
│ Model                                    │ Context  │ Max out  │
├──────────────────────────────────────────┼──────────┼──────────┤
│ @cf/meta/llama-3.1-8b-instruct           │  8 192   │  4 096   │
│ @cf/meta/llama-3.2-1b-instruct           │  4 096   │  2 048   │
│ @cf/mistral/mistral-7b-instruct-v0.2     │  4 096   │  2 048   │
│ @cf/google/gemma-2b-it-lora              │  8 192   │  1 024   │
└──────────────────────────────────────────┴──────────┴──────────┘
```

Token budget policy for example project by feature:

```typescript
const TOKEN_BUDGETS: Record<string, number> = {
  caption_suggestion: 80,    // Short captions
  content_warning:    40,    // One-liner CW
  reply_suggestion:   120,   // Slightly longer
  moderation_label:   20,    // Classification only
} as const;

function getMaxTokens(feature: string, isMobile: boolean): number {
  const base = TOKEN_BUDGETS[feature] ?? 100;
  // Mobile: halve budget to reduce streaming duration on LTE
  return isMobile ? Math.ceil(base * 0.6) : base;
}
```

Per-user rate limiting via Durable Objects prevents a single user from exhausting quota:

```typescript
// DO: UserAIQuota
export class UserAIQuota {
  private tokens = 0;
  private resetAt = 0;

  async canSpend(requested: number): Promise<boolean> {
    const now = Date.now();
    if (now > this.resetAt) {
      this.tokens = 0;
      this.resetAt = now + 86_400_000; // 24 h window
    }
    if (this.tokens + requested > 10_000) return false; // 10k tokens/user/day
    this.tokens += requested;
    return true;
  }
}
```

---

## 6. Abort and Timeout Handling

Mobile networks drop frequently. Always provide an `AbortController` with a deadline so dangling stream connections do not accumulate on the Worker.

```typescript
// Worker-side: enforce server timeout via TransformStream
function addStreamTimeout(
  source: ReadableStream,
  timeoutMs = 15_000
): ReadableStream {
  let timer: ReturnType<typeof setTimeout>;
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();

  timer = setTimeout(async () => {
    await writer.abort(new Error('Stream timeout'));
  }, timeoutMs);

  source.pipeTo(
    new WritableStream({
      write: (chunk) => writer.write(chunk),
      close: () => { clearTimeout(timer); writer.close(); },
      abort: (e) => { clearTimeout(timer); writer.abort(e); },
    })
  );

  return readable;
}
```

---

## Anti-Patterns

- **Returning the raw stream without setting `Content-Type: text/event-stream`** — browsers treat the response as a download; Cloudflare cache may buffer the entire body.
- **Using EventSource with a POST body** — EventSource is GET-only; use `fetch` for example project's prompt POST.
- **No `max_tokens` cap** — a single adversarial prompt can drain the daily token quota.
- **Buffering the full response before forwarding** — defeats streaming; adds latency equal to full generation time.
- **Omitting the `AbortSignal`** — Workers keep generating even after the client disconnects, wasting tokens.

## Gotchas

- `env.AI.run()` with `stream: true` returns a `ReadableStream<Uint8Array>`, not a `Response`. Wrap it in `new Response(stream, { headers })`.
- The final SSE frame is `data: [DONE]\n\n` (literal string, not JSON). Parsing it as JSON throws; guard with `if (payload === '[DONE]') return null`.
- Workers AI may emit empty `data: \n\n` keepalive frames during slow inference. Skip frames where `response` is `undefined`.
- On Cloudflare's edge, a streaming Worker has a **30-second CPU time limit** (Paid plan). Long generations must fit within this window; split long requests across multiple Worker calls if needed.
- React Native `fetch` streaming requires `reactNative: { textStreaming: true }` in fetch options (RN 0.72+) or the body is fully buffered before resolution.

## Verification

```bash
# Confirm streaming response arrives chunk-by-chunk
curl -N -X POST https://api.example.com/ai/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Write a short caption","maxTokens":50}' \
  --no-buffer

# Expected: SSE frames printed as they arrive, not all at once
# data: {"response":"Here"}
# data: {"response":" is"}
# ...
# data: [DONE]

# Measure time-to-first-byte
curl -o /dev/null -w "TTFB: %{time_starttransfer}s\n" \
  -X POST https://api.example.com/ai/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Hello","maxTokens":5}' -s
# Target: < 1.5 s TTFB on standard Workers AI tier
```

## Related

- `llm-streaming-responses.md` — general streaming patterns
- `llm-context-window-cloudflare-workers.md` — context window limits per model
- `ai-gateway-request-caching-cost-control.md` — cache streaming responses to save tokens
- `llm-prompt-injection-defense-workers.md` — sanitize `prompt` before `env.AI.run()`
- `ai-cost-monitoring.md` — token quota dashboards

## Sources

- Cloudflare Workers AI documentation: developers.cloudflare.com/workers-ai
- Cloudflare Workers AI Models catalog: developers.cloudflare.com/workers-ai/models
- SSE specification: html.spec.whatwg.org/multipage/server-sent-events.html
- React Native fetch streaming: reactnative.dev/docs/network
