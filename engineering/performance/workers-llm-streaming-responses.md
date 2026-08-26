# Streaming Responses for LLM Output with Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

An application proxies requests to a large language model API (Anthropic, OpenAI, or a
self-hosted model behind a Workers AI binding). Without streaming, the Worker must buffer
the entire completion before forwarding it. For a 500-token response at ~25 tokens/s,
that means the client stares at a blank screen for 20 seconds. With streaming, the first
tokens arrive in under 200 ms and the perceived latency collapses. Implementing streaming
correctly inside a Worker requires understanding TransformStream, Server-Sent Events
framing, and backpressure.

## Context

LLM APIs expose responses as a stream of `data: {...}\n\n` Server-Sent Events (SSE).
The client expects the same SSE wire format. A Worker sits in the middle: it must forward
chunks as they arrive, apply optional transforms (content filtering, usage accounting,
token streaming rate limiting), and terminate the stream cleanly on model completion or
upstream error. The Workers runtime fully supports `ReadableStream`, `WritableStream`, and
`TransformStream`, and the `Response` constructor accepts a `ReadableStream` body — the
runtime begins flushing to the client as soon as the first chunk enqueues.

## Pass-Through Streaming Proxy

The minimal viable proxy: pipe the upstream SSE body directly to the client with no
transformation. Zero buffering, sub-200 ms TTFB.

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const upstream = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-5",
        max_tokens: 1024,
        stream: true,
        messages: await req.json(),
      }),
    });

    if (!upstream.ok) {
      const err = await upstream.text();
      return new Response(err, { status: upstream.status });
    }

    // Forward the ReadableStream body directly; Worker never buffers
    return new Response(upstream.body, {
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
        "x-accel-buffering": "no", // Tell any reverse proxy not to buffer
      },
    });
  },
};
```

`x-accel-buffering: no` prevents nginx-family proxies upstream of the client from
accumulating chunks. Cloudflare itself does not buffer SSE responses on its edge.

## Transform Stream for Token Counting and Filtering

When you need to inspect or modify chunks in flight, insert a `TransformStream` between
the upstream response body and the client. The transform runs per-chunk with no
additional round-trip latency.

```typescript
function makeTokenCounter(): { stream: TransformStream; getCount: () => number } {
  let tokenCount = 0;

  const stream = new TransformStream({
    transform(chunk: Uint8Array, controller) {
      const text = new TextDecoder().decode(chunk);

      // SSE lines: "data: {...}" or "data: [DONE]"
      for (const line of text.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") continue;
        try {
          const event = JSON.parse(payload);
          const delta = event?.delta?.text ?? event?.choices?.[0]?.delta?.content ?? "";
          // Rough token estimate: 1 token ≈ 4 chars
          tokenCount += Math.ceil(delta.length / 4);
        } catch {
          // Malformed chunk; pass through
        }
      }

      controller.enqueue(chunk);
    },
  });

  return { stream, getCount: () => tokenCount };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const upstream = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
      },
      body: JSON.stringify({ model: "claude-sonnet-4-5", max_tokens: 1024,
        stream: true, messages: await req.json() }),
    });

    if (!upstream.ok) return new Response(await upstream.text(), { status: 502 });

    const { stream, getCount } = makeTokenCounter();

    // Pipe upstream through the counter transform
    upstream.body!.pipeTo(stream.writable).finally(() => {
      // Log usage after stream closes — use waitUntil to avoid holding the response
      console.log(`tokens_out=${getCount()}`);
    });

    return new Response(stream.readable, {
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
    });
  },
};
```

## Workers AI Binding Streaming

When the model runs on Cloudflare's own GPU fleet via the `@cf/anthropic/*` or
`@cf/meta/*` bindings, streaming uses the same pattern but the binding returns a
`ReadableStream` directly rather than an HTTP `Response`.

```typescript
interface Env {
  AI: Ai;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.json<{ messages: { role: string; content: string }[] }>();

    const stream = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: body.messages,
      stream: true,
    });

    // env.AI.run returns a ReadableStream<Uint8Array> when stream:true
    return new Response(stream as ReadableStream, {
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      },
    });
  },
};
```

Workers AI billing counts tokens, not wall-clock time, so streaming does not change
cost; it only improves perceived latency.

## Client-Side EventSource Consumption

```typescript
// Browser client
const source = new EventSource("/api/llm-stream");
let output = "";

source.addEventListener("message", (e) => {
  if (e.data === "[DONE]") {
    source.close();
    return;
  }
  try {
    const event = JSON.parse(e.data);
    const delta = event?.delta?.text ?? event?.choices?.[0]?.delta?.content ?? "";
    output += delta;
    document.getElementById("output")!.textContent = output;
  } catch {
    // ignore heartbeat or non-JSON lines
  }
});

source.addEventListener("error", () => {
  source.close();
  console.error("Stream ended with error");
});
```

For `fetch`-based clients (useful when you need POST with a body), use a
`ReadableStreamDefaultReader` directly against the fetch response body.

## Anti-patterns

**Buffering the full response before forwarding** — calling `await upstream.text()` or
`await upstream.json()` on a streaming endpoint defeats the purpose entirely and often
times out on long completions.

**Missing `cache-control: no-cache`** — without this header, CDN edge nodes may attempt
to cache the stream, causing the first-byte to stall until Cloudflare decides the
response is not cacheable.

**Not handling the `[DONE]` sentinel** — passing the `[DONE]` chunk through a
`JSON.parse` throws; the transform must guard against it before parsing.

**Ignoring stream errors in `pipeTo`** — if the upstream closes unexpectedly, the
`WritableStream` will reject. Attach `.catch()` or use `.finally()` to log and
potentially send an error SSE event to the client.

**Using `response.clone()` then streaming** — cloning a large streaming response causes
full buffering in memory of one branch. Avoid clone on streaming responses.

## Gotchas

- Workers have a **default CPU time limit of 10 ms** on the free tier (50 ms on paid).
  The timer is paused while waiting on I/O, so a 20-second stream is fine as long as
  each `transform()` callback runs quickly. Avoid heavy synchronous work inside
  `transform()`.
- **`pipeTo` vs `pipeThrough`**: use `pipeThrough(transformStream)` to attach a
  transform in a chain; use `pipeTo(writableStream)` as the terminal sink. Mixing them
  incorrectly can leave a stream in an unresolved locked state.
- Cloudflare's edge caches SSE responses if `cache-control` permits it; always set
  `no-store` or `no-cache` on streamed AI responses.
- `TextDecoder` inside a `TransformStream` may split a multi-byte UTF-8 character
  across two chunks. Use `new TextDecoder(undefined, { fatal: false })` and accumulate
  a buffer if you need to parse complete characters.

## Verification

```bash
# Confirm chunks arrive incrementally (not all at once)
curl -N -H "content-type: application/json" \
  -d '{"messages":[{"role":"user","content":"Count to 20 slowly"}]}' \
  https://worker.example.com/api/llm-stream

# Measure TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" \
  -N https://worker.example.com/api/llm-stream
```

Check Workers Logs for the token count logged via `console.log` to verify the
accounting path is executing after stream close.

## Related

- `workers-streaming-large-payloads.md`
- `sse-vs-websockets-real-time-streaming.md`
- `workers-cpu-time-optimization.md`
- `workers-subrequest-fanout-parallelism.md`

## Sources

- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/#stream-the-response
- https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
- https://developers.cloudflare.com/workers/runtime-apis/response/
- https://docs.anthropic.com/en/api/messages-streaming
