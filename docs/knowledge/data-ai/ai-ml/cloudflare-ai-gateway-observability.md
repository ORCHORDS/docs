# cloudflare-ai-gateway-observability

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project LLM calls produce no visibility into per-provider
latency or cost. Mobile clients show spinner timeouts with
no indication whether the failure was GPU cold-start, a
third-party provider outage, or rate-limit rejection. Repeat
queries from identical mobile sessions burn provider tokens
on cache-eligible prompts.

## Context

example project is a Next.js static export on Cloudflare Pages
with a Worker API backend, D1 for storage, and R2 for media.
LLM calls (moderation verdicts, content suggestions, post
summaries) go through `env.AI` (Workers AI) or direct fetch
to Anthropic/OpenAI. AI Gateway sits between the Worker and
every provider as a unified control plane.

## 1. Gateway vs Direct: When Each Makes Sense

```
Decision                   Use Gateway   Use Direct
-------------------------  ------------  ----------
Multiple providers          Yes           No
Single-provider, < 1 req/s  No            Yes
Need cache on repeat calls  Yes           No
Need per-request logs       Yes           No
Need cost attribution       Yes           No
SSE / streaming response    No *          Yes
```

* Gateway caching silently skips streaming; add gateway for
  non-streaming verdicts; bypass for SSE content suggestions.

## 2. Binding and Gateway Wiring

```toml
# wrangler.toml
[ai]
binding = "AI"
```

```typescript
// Non-streaming moderation via gateway
const verdict = await env.AI.run(
  "@cf/meta/llama-3.1-8b-instruct",
  { messages: moderationPrompt(text) },
  {
    gateway: {
      id: "example project-ai-gw",
      skipCache: false,
      cacheTtl: 86400,   // 24 h — moderation verdicts stable
    },
  },
);
const hit = verdict.response?.headers?.get("cf-cache-status");
// "HIT" or "MISS"
```

For third-party providers, route through the universal URL:

```typescript
const GW = `https://gateway.ai.cloudflare.com/v1/${ACCOUNT}` +
            `/example project-ai-gw/anthropic/v1/messages`;

const r = await fetch(GW, {
  method: "POST",
  headers: {
    "x-api-key":         env.ANTHROPIC_KEY,
    "anthropic-version": "2023-06-01",
    "Content-Type":      "application/json",
    "cf-aig-cache-ttl":  "3600",
  },
  body: JSON.stringify({ model: "claude-3-5-haiku-20241022",
                         max_tokens: 200, messages }),
});
```

## 3. Observability: Mobile vs Desktop Request Patterns

Mobile sessions send shorter bursts at irregular intervals
(radio state-machine transitions). Desktop sessions batch
more tokens per request and sustain longer connections.

```
Metric              Mobile (LTE)   Desktop (WiFi)   Notes
------------------  -------------  ---------------  --------------------
Median prompt len   80-200 tokens  300-800 tokens   Short context, thumb
P50 latency         380 ms         420 ms           Near-parity on warm
P95 latency         2.1 s          1.2 s            Radio handoff adds ~1 s
Cache hit rate      55-70%         30-50%           Repeat content patterns
Retry rate          8-14%          2-4%             Radio interruption
```

Track device type from `cf-device-type` header (set by
Cloudflare automatically). Log it as a Gateway metadata tag
so the Analytics panel can filter per segment.

```typescript
const metadata = {
  deviceType: req.headers.get("cf-device-type") ?? "unknown",
  userId:     session.uid,
  route:      "moderation",
};
// Pass via cf-aig-metadata if using the universal endpoint
```

## 4. Cache Hit Rate Optimisation

Exact-match caching requires identical serialised JSON body.
Normalise before sending:

```typescript
function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 512);          // cap to avoid long-tail misses
}

const body = JSON.stringify({
  messages: [
    { role: "system", content: MODERATION_SYSTEM_PROMPT },
    { role: "user",   content: normalise(userText) },
  ],
});
```

Strip user IDs, timestamps, and session tokens from the
cached body — any difference produces a MISS.

```
Cache scenario              Hit rate   Saving
--------------------------  ---------  ------------------
Raw user text               5-15%      Minimal
Normalised text             45-65%     ~50% token saving
Normalised + template lock  60-75%     ~65% token saving
```

## 5. Latency Budgets and Rate Limiting

example project mobile P95 budget: 800 ms total for moderation
(client tap → verdict). Gateway adds 15-40 ms overhead vs
direct. Distribute the budget:

```
Component                    Budget (ms)   Notes
---------------------------  -----------  ----------------------
TLS + QUIC handshake (new)   0-80         Absent on keep-alive
Worker startup (warm)        < 5          V8 isolate reuse
AI Gateway overhead          15-40        Logging + cache check
GPU inference (warm, 8B)     200-600      llama-3.1-8b typical
D1 verdict write             20-60        Single INSERT
Response transfer (mobile)   10-50        Tiny JSON payload
```

Rate-limit per `cf-connecting-ip` to guard against anonymous
abuse without authenticated sessions:

```typescript
// In gateway dashboard: set rate limit 60 req/min per IP
// Worker-side guard for burst protection:
const limiter = await env.KV.get(`rl:${clientIp}`);
if (Number(limiter) > 30) {
  return new Response("rate limited", { status: 429 });
}
```

## 6. Reading Gateway Analytics Programmatically

```typescript
// Fetch gateway analytics via REST API
const resp = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCT}` +
  `/ai-gateway/gateways/example project-ai-gw/logs?` +
  `start=${start}&end=${end}&order=asc&per_page=1000`,
  { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } },
);
const { result } = await resp.json<{ result: GatewayLog[] }>();
const cacheHits = result.filter(r => r.cached).length;
const hitRate   = cacheHits / result.length;
```

Push daily hit-rate and P95 latency to a D1 metrics table
so mobile dashboards can query trends without leaving the
Cloudflare stack.

## Anti-patterns

- Routing SSE content-suggestion streams through the gateway
  — caching skips silently, adds 30-60 ms, no benefit.
- Including user IDs or timestamps in the cached message body
  — every request is a unique key, 0% hit rate.
- Enabling Smart Placement on the moderation Worker — routes
  to D1 PoP, not GPU PoP, adds 80-200 ms on AI calls.
- Reading gateway metrics only from the dashboard — export to
  D1 or Analytics Engine for programmatic alerting.
- Setting the same `cacheTtl` for all routes — long TTL on
  content suggestions surfaces stale tones; 0 TTL wastes the
  biggest saving on moderation verdicts.

## Gotchas

- `cf-cache-status` is on the gateway HTTP response, not the
  AI SDK return value; read it from raw fetch, not `env.AI.run`.
- AI Gateway analytics live in **AI > AI Gateway > Analytics**,
  not Workers Logs or Logpush — set up Logpush separately if
  you need logs in external SIEM.
- Mobile carriers using CGNAT share one IP across thousands of
  users; per-IP rate limits need generous thresholds or the
  gateway `cf-connecting-ip` deduplication header.
- Semantic caching (fuzzy matching) is on Cloudflare's roadmap
  but not GA as of 2026-08; exact-match normalisation is the
  current lever.
- Gateway cache TTL is wall-clock from first MISS, not sliding;
  high-frequency phrases reset on TTL expiry, causing a burst
  of MISS + GPU load every 24 h.

## Verification

```bash
# 1. First call should be MISS, second should be HIT
for i in 1 2; do
  curl -si -X POST \
    "https://gateway.ai.cloudflare.com/v1/$ACCT/example project-ai-gw/\
workers-ai/@cf/meta/llama-3.1-8b-instruct" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "cf-aig-cache-ttl: 86400" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"buy cheap pills"}]}' \
  | grep -i "cf-cache-status"
done

# 2. Check gateway overhead (should be < 50 ms extra vs direct)
curl -o /dev/null -w "total=%{time_total}\n" \
  https://example project.example.com/api/moderate -d '{"text":"test"}'

# 3. Confirm mobile device-type tag appears in gateway logs
curl "https://api.cloudflare.com/client/v4/accounts/$ACCT/\
ai-gateway/gateways/example project-ai-gw/logs?per_page=5" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.[].metadata.deviceType'
```

## Related

- `cloudflare/ai-gateway-best-practices.md`
- `cloudflare/ai-gateway-fallback-caching-streaming.md`
- `cloudflare/workers-ai-mobile-inference-latency.md`
- `cloudflare/rate-limiting-cgnat-mobile-fingerprinting.md`
- `ai-ml/workers-ai-text-classification-moderation.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/ai-gateway/features/caching/
- https://developers.cloudflare.com/ai-gateway/reference/api/
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://blog.cloudflare.com/cloudflare-ai-gateway-ga/
