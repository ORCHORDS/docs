# Workers Streaming JSON Response Frontend Parsing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker returns a large JSON payload — search results, AI token output, or a DB cursor — and the browser has to wait for the full body before rendering anything. You want the browser to start rendering rows as they arrive, the same way streaming HTML works but with structured data that TypeScript can type-check.

## Context

`fetch()` exposes the response body as a `ReadableStream<Uint8Array>`. Standard `response.json()` buffers the entire body before parsing. Three streaming-friendly formats are in common use on Workers: **newline-delimited JSON (NDJSON)**, **JSON streaming arrays**, and **JSON chunks inside SSE frames**. Each has different parser requirements on the frontend. Cloudflare Workers support all three via `TransformStream` and `ReadableStream` on the server side.

---

## 1. Workers: Emit NDJSON (one JSON object per line)

```typescript
// worker/search.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
    const writer = writable.getWriter();
    const enc = new TextEncoder();

    // Stream rows from a D1 cursor
    const stmt = env.DB.prepare('SELECT * FROM products WHERE active = 1');
    const { results } = await stmt.all<{ id: number; name: string; price: number }>();

    (async () => {
      for (const row of results) {
        await writer.write(enc.encode(JSON.stringify(row) + '\n'));
      }
      await writer.close();
    })();

    return new Response(readable, {
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Transfer-Encoding': 'chunked',
        'Cache-Control': 'no-store',
      },
    });
  },
} satisfies ExportedHandler<Env>;

interface Env { DB: D1Database; }
```

---

## 2. Frontend: NDJSON Line-Splitting Transform

```typescript
// lib/ndjson-stream.ts
/** Splits a Uint8Array ReadableStream on newlines and yields parsed objects. */
export async function* parseNDJSON<T>(
  stream: ReadableStream<Uint8Array>
): AsyncGenerator<T> {
  const dec = new TextDecoder();
  let buffer = '';

  for await (const chunk of streamToAsyncIterable(stream)) {
    buffer += dec.decode(chunk, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';          // last item may be incomplete
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed) yield JSON.parse(trimmed) as T;
    }
  }
  // Flush remainder
  const trimmed = buffer.trim();
  if (trimmed) yield JSON.parse(trimmed) as T;
}

function streamToAsyncIterable(
  stream: ReadableStream<Uint8Array>
): AsyncIterable<Uint8Array> {
  const reader = stream.getReader();
  return {
    [Symbol.asyncIterator]() {
      return {
        async next() {
          const { done, value } = await reader.read();
          if (done) return { done: true, value: undefined as unknown as Uint8Array };
          return { done: false, value };
        },
        async return() {
          await reader.cancel();
          return { done: true, value: undefined as unknown as Uint8Array };
        },
      };
    },
  };
}
```

---

## 3. React Integration with Progressive Rendering

```typescript
// hooks/use-streaming-search.ts
import { useState, useCallback, useRef } from 'react';
import { parseNDJSON } from '../lib/ndjson-stream';

interface Product { id: number; name: string; price: number; }

export function useStreamingSearch() {
  const [rows, setRows] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(async (query: string) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setRows([]);
    setLoading(true);

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
        signal: ac.signal,
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      for await (const product of parseNDJSON<Product>(res.body)) {
        if (ac.signal.aborted) break;
        // Batch state updates in the same microtask tick to reduce re-renders
        setRows((prev) => [...prev, product]);
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const cancel = useCallback(() => abortRef.current?.abort(), []);
  return { rows, loading, search, cancel };
}
```

---

## 4. Workers: SSE-Wrapped JSON for LLM Token Streaming

```typescript
// worker/ai-stream.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { readable, writable } = new TransformStream<string, string>();
    const writer = writable.getWriter();
    const enc = new TextEncoder();

    const aiStream = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [{ role: 'user', content: 'Explain Workers streaming.' }],
      stream: true,
    }) as ReadableStream<Uint8Array>;

    // Wrap each AI chunk in an SSE event so the browser can use EventSource
    (async () => {
      const dec = new TextDecoder();
      for await (const chunk of streamToAsyncIterable(aiStream)) {
        const text = dec.decode(chunk, { stream: true });
        const data = JSON.stringify({ token: text });
        await writer.write(enc.encode(`data: ${data}\n\n`));
      }
      await writer.write(enc.encode('data: [DONE]\n\n'));
      await writer.close();
    })();

    function* streamToAsyncIterable(s: ReadableStream<Uint8Array>) { /* same as above */ }

    return new Response(readable as unknown as ReadableStream<Uint8Array>, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
      },
    });
  },
} satisfies ExportedHandler<Env>;

interface Env { AI: Ai; }
```

---

## 5. Frontend: Typed SSE JSON Consumer

```typescript
// lib/sse-json-stream.ts
interface TokenEvent { token: string; }

export async function* consumeSSEJSON(url: string, signal?: AbortSignal): AsyncGenerator<string> {
  const res = await fetch(url, { signal });
  if (!res.body) throw new Error('No response body');

  const dec = new TextDecoder();
  let buf = '';

  const reader = res.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });

      // SSE frames are separated by double newlines
      const frames = buf.split('\n\n');
      buf = frames.pop() ?? '';

      for (const frame of frames) {
        const dataLine = frame.split('\n').find((l) => l.startsWith('data: '));
        if (!dataLine) continue;
        const payload = dataLine.slice(6).trim();
        if (payload === '[DONE]') return;
        const parsed = JSON.parse(payload) as TokenEvent;
        yield parsed.token;
      }
    }
  } finally {
    reader.cancel();
  }
}
```

---

## 6. Batching State Updates to Avoid Render Flooding

```typescript
// hooks/use-token-stream.ts
import { useState, useCallback, useEffect, useRef } from 'react';
import { consumeSSEJSON } from '../lib/sse-json-stream';

export function useTokenStream(url: string | null) {
  const [output, setOutput] = useState('');
  const bufferRef = useRef('');

  useEffect(() => {
    if (!url) return;
    const ac = new AbortController();
    bufferRef.current = '';

    let rafId: number;
    const flush = () => {
      setOutput((prev) => prev + bufferRef.current);
      bufferRef.current = '';
    };

    (async () => {
      for await (const token of consumeSSEJSON(url, ac.signal)) {
        bufferRef.current += token;
        cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(flush); // Batch within one frame
      }
      flush(); // Final flush
    })();

    return () => {
      ac.abort();
      cancelAnimationFrame(rafId);
    };
  }, [url]);

  const reset = useCallback(() => setOutput(''), []);
  return { output, reset };
}
```

---

## Anti-patterns

- **Calling `response.json()` on a streaming response** — buffers the entire body; defeats the purpose entirely.
- **Emitting bare JSON arrays as a stream** — the browser cannot parse `[{...},{...}` until the closing `]` arrives; use NDJSON instead.
- **Setting `Content-Encoding: gzip` on streamed responses** — gzip requires the full body to compress; it prevents incremental delivery. Use `Transfer-Encoding: chunked` only.
- **Re-rendering on every token** — for LLM output with 30+ tokens/s, synchronous `setState` per token causes frame drops; batch via `requestAnimationFrame`.

## Gotchas

- Cloudflare's smart placement and cache layers may buffer responses unless `Cache-Control: no-store` or `X-Accel-Buffering: no` is set.
- `TransformStream` in Workers has a high-water mark of 1 chunk by default; large D1 result sets should use a small `queuingStrategy` to avoid holding unbounded memory.
- The `for await...of` on a `ReadableStream` is available in browsers since Chrome 124 / Firefox 110; for older targets use the reader loop pattern shown in section 5.
- NDJSON lines can exceed 64 KB for blob-heavy rows; the line-splitting buffer can grow large — consider limiting row size on the DB side.

## Verification

```bash
# Confirm chunked delivery — watch bytes arrive incrementally:
curl -N --no-buffer https://your-worker.workers.dev/api/search?q=test | head -20

# Verify Content-Type for NDJSON:
curl -sI https://your-worker.workers.dev/api/search | grep content-type
# Expect: content-type: application/x-ndjson

# Time to first byte:
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" \
  https://your-worker.workers.dev/api/search?q=test
```

## Related

- `server-sent-events-streaming-ui.md`
- `streaming-html-workers-react-rendertopipeablestream.md`
- `cloudflare-workers-ai-edge-inference-ui.md`
- `react-suspense-boundaries.md`
- `hono-cloudflare-workers-frontend-api.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/streams/
- https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams
- https://datatracker.ietf.org/doc/html/rfc7464 (JSON Text Sequences / NDJSON)
- https://html.spec.whatwg.org/multipage/server-sent-events.html
