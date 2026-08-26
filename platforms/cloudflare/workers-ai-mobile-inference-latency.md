# workers-ai-mobile-inference-latency

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project AI moderation and content-suggestion routes hit P95
latency of 4-10 s after idle periods. On LTE-fringe / 3G the SSE
stream stalls mid-generation after a radio handoff, leaving the
mobile client with a partial suggestion and no recovery path.

## Context

Every anonymous post passes through a Workers AI classifier
(content moderation) and an optional suggestion model, both called
via `env.AI` inside a single Worker. Mobile clients consume results
over SSE. Repeated moderation requests (spam phrases, common slurs)
route through AI Gateway for caching and observability.

## 1. GPU Cold-Start vs Warm Latency

Worker isolate cold-starts are sub-5 ms (V8 reuse). GPU model
loading is a separate cost that applies only when model weights are
not resident in GPU memory at the serving PoP.

```
Condition                  Added latency   Notes
-------------------------  --------------  ----------------------------
Worker isolate cold        < 5 ms          V8 isolate reuse
GPU warm, popular model    0 ms            Llama/Qwen stay loaded
GPU warm, less-used model  50-150 ms       Weights resident, ctx clear
GPU cold, rare model       200-800 ms      Weights loaded from storage
```

For example project use Llama 3 / Qwen 3 catalog models — kept warm
globally across Cloudflare's GPU PoPs. Reserve niche fine-tuned
models for async background queues, not the real-time mobile path.

## 2. SSE Streaming on Mobile: Partial Delivery and Interruptions

Workers AI returns a `ReadableStream` when `stream: true`.
Wrapping it in `Response.json()` triggers Cloudflare's edge buffer
(holds ≤128 KB before first flush). Pass the stream directly:

```typescript
async fetch(req: Request, env: Env): Promise<Response> {
  const stream = await env.AI.run(
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    { messages: buildMessages(req), stream: true },
  );
  return new Response(stream as ReadableStream, { headers: {
    "Content-Type":      "text/event-stream",
    "Cache-Control":     "no-cache",
    "X-Accel-Buffering": "no",
  }});
}
```

Each SSE event must carry an `id:` field and the first event
should include `retry: 3000\n\n` so the mobile browser waits 3 s
before reconnecting rather than hammering the endpoint.

## 3. Retry-on-Disconnect for Mobile SSE Consumers

example project uses POST with auth headers; native `EventSource` is
GET-only and cannot be used. Use a `fetch`-based generator:

```typescript
async function* streamWithRetry(url: string, body: object) {
  let lastId = 0;
  for (let i = 0; i < 4; i++) {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type":  "application/json",
        "Last-Event-ID": String(lastId),
        "Authorization": `Bearer ${getToken()}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    });
    const reader = r.body!.getReader();
    const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) return;
      const chunk = dec.decode(value);
      const m = chunk.match(/^id:\s*(\d+)/m);
      if (m) lastId = parseInt(m[1]);
      yield chunk;
    }
  }
}
```

Persist generation state by session ID so the Worker can resume
from `lastId` when the mobile client reconnects.

## 4. GPU PoP Routing vs Smart Placement for CPU Workers

```
                    Workers AI (GPU)         Smart Placement (CPU)
------------------  -----------------------  ---------------------
Goal                Nearest GPU capacity     Nearest data dep
User proximity      Same continent           May route away from user
Opt-in              Automatic (no config)    placement: smart
Backbone hop        10-50 ms always          Varies by topology
```

Do not enable Smart Placement on the moderation Worker. The AI
binding self-routes to the nearest GPU PoP; Smart Placement would
steer toward the D1 replica instead, adding 80-200 ms. If DB reads
bottleneck, split into a thin edge Worker (AI, default placement)
and a data Worker (Smart Placement, D1).

## 5. TTFT vs Total Generation Time and the Batching Trade-off

TTFT governs perceived mobile responsiveness. It is GPU-bound,
not bandwidth-bound: the first token is tiny (< 1 KB) so slow
links do not delay it. Typical warm figures: TTFT ~250-600 ms,
throughput ~30-60 tok/s, 200-token response ~3-7 s total.

Stream content suggestions (> 40 tokens, real-time UX, not
cacheable). Batch moderation verdicts (short, deterministic,
cacheable). A 50-token suggestion delivered via SSE feels instant;
batch-delivered it arrives 1-2 s later with no progress signal.

## 6. AI Gateway Caching for Repeated Mobile Requests

Spam phrases repeat across thousands of posts. AI Gateway
exact-match caching returns repeated verdicts at ~5-20 ms vs
400-800 ms live. The gateway adds 20-60 ms per call; only route
non-streaming batch moderation through it, never SSE streams.

```typescript
// GW_URL = https://gateway.ai.cloudflare.com/v1/$ACCT/$GW
//          /workers-ai/@cf/meta/llama-3.1-8b-instruct
const r = await fetch(GW_URL, {
  method: "POST",
  headers: {
    "Authorization":    `Bearer ${env.CF_API_TOKEN}`,
    "Content-Type":     "application/json",
    "cf-aig-cache-ttl": "86400",   // cache verdict 24 h
  },
  body: JSON.stringify({
    messages: buildModerationPrompt(normalise(text)),
  }),
});
const hit = r.headers.get("cf-cache-status"); // HIT | MISS
```

Normalise input (`toLowerCase`, collapsed whitespace, strip user
IDs) to maximise exact-match hit rate. Semantic caching is on
Cloudflare's roadmap but not GA as of 2026-08.

## Anti-patterns

- Wrapping the AI `ReadableStream` in `Response.json()` — buffers
  the entire generation before the client sees any tokens.
- Using `EventSource` for POST endpoints — GET-only; no auth
  headers; use a `fetch`-based streaming loop instead.
- Enabling `placement: smart` on an AI-binding Worker — routes
  toward the DB PoP, away from the GPU PoP, adding 80-200 ms.
- Routing SSE calls through AI Gateway — caching silently skips,
  adding 30-60 ms with no benefit.
- Choosing a niche fine-tuned model for real-time mobile — 200-800 ms
  GPU cold-start penalty after any idle period.
- Including user IDs or request timestamps in cached prompts —
  cache key changes every call, 0% hit rate.

## Gotchas

- Edge buffers ≤128 KB before first flush; `X-Accel-Buffering: no`
  suppresses this for SSE responses.
- `Last-Event-ID` is absent on first request; seed the server
  cursor from a client query param on the initial connection.
- iOS Safari may ignore the SSE `retry:` field; implement
  back-off in the mobile client regardless.
- AI Gateway analytics (cache hit rate, latency) live in
  **AI > AI Gateway > Analytics**, not in Workers Logs.
- GPU PoPs are a subset of Cloudflare's 300+ locations; the
  Worker-to-GPU backbone hop (10-50 ms) is always present.

## Verification

```bash
# 1. Confirm tokens trickle, not batch-delivered at end
curl -N -X POST https://example project.example.com/api/suggest \
  -d '{"text":"rewrite this"}' --no-buffer

# 2. AI Gateway cache hit on moderation (run twice, compare)
curl -si -X POST "$GW_URL" \
  -H "cf-aig-cache-ttl: 86400" \
  -d '{"messages":[{"role":"user","content":"buy pills"}]}' \
  | grep -i cf-cache-status   # MISS → HIT on repeat

# 3. TTFT proxy — target < 0.65 s on warm GPU
curl -o /dev/null -w "%{time_starttransfer}\n" \
  -X POST https://example project.example.com/api/suggest \
  -d '{"text":"test"}'
```

## Related

- `cloudflare/ai-gateway-best-practices.md`
- `cloudflare/ai-gateway-fallback-caching-streaming.md`
- `cloudflare/workers-streaming-responses.md`
- `cloudflare/smart-placement-best-practices.md`
- `cloudflare/durable-objects-websocket-mobile-reconnect.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/ai-gateway/features/caching
- https://developers.cloudflare.com/agents/api-reference/http-sse/
- https://developers.cloudflare.com/workers/configuration/placement/
- https://blog.cloudflare.com/workers-ai/
- https://blog.cloudflare.com/how-cloudflare-runs-more-ai-models-on-fewer-gpus/
- https://blog.cloudflare.com/best-place-region-earth-inference/
- https://github.com/mastra-ai/mastra/issues/13584
