# AI Gateway Cache TTL Configuration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Repeated AI Gateway requests with identical prompts hit the upstream provider every time, running up
token costs and adding latency. Alternatively, cached responses linger too long for fast-moving
contexts (live sports scores, news summaries) or for models where determinism matters less than
freshness. You need per-request, per-endpoint, or per-tenant control over how long cached responses
are reused.

## Context

AI Gateway sits in front of every provider (OpenAI, Workers AI, Anthropic, Hugging Face, etc.) and
maintains a semantic or exact-match cache. Cache TTL — the number of seconds a stored response is
served without a fresh upstream call — defaults to `300` (5 minutes) when caching is enabled in the
Gateway dashboard. That single global TTL rarely fits all workloads. High-frequency QA bots benefit
from an hours-long TTL; streaming summarisers of live feeds need `0` (bypass). Cloudflare surfaces
TTL control through two mechanisms: the `cf-aig-cache-ttl` request header and the `cacheTtl` field
in the Cloudflare REST API when creating or updating a Gateway.

AI Gateway caching is available on all plans. The `cf-aig-cache-ttl` header override requires the
Gateway to have caching enabled; without it the header is silently ignored.

## Setting TTL per Request via Header

Add `cf-aig-cache-ttl: <seconds>` to the forwarded request. A value of `0` bypasses the cache
entirely for that request (a fresh call is always made). Maximum accepted value is `2592000` (30 days).

```typescript
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { prompt, ttlSeconds } = await request.json<{
      prompt: string;
      ttlSeconds?: number;
    }>();

    // Dynamic TTL: callers can opt in to longer caching for stable prompts,
    // or pass 0 to force a live call for volatile contexts.
    const cacheTtl = ttlSeconds ?? 300;

    const gatewayUrl =
      `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}` +
      `/${env.GATEWAY_ID}/workers-ai/@cf/meta/llama-3.1-8b-instruct`;

    const aiResponse = await fetch(gatewayUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
        // Per-request TTL override — shadows the gateway-level default.
        "cf-aig-cache-ttl": String(cacheTtl),
      },
      body: JSON.stringify({
        messages: [{ role: "user", content: prompt }],
        max_tokens: 512,
      }),
    });

    return new Response(aiResponse.body, {
      headers: { "Content-Type": "application/json" },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Setting a Gateway-Level Default TTL via REST API

When creating or patching a gateway, pass `cache_ttl` to set the account-wide default for that
gateway. This removes the need for every caller to send the header.

```typescript
// scripts/update-gateway-ttl.ts  (run with: npx wrangler exec)
async function setGatewayTtl(
  accountId: string,
  gatewayId: string,
  apiToken: string,
  ttlSeconds: number
): Promise<void> {
  const url =
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/ai-gateway/gateways/${gatewayId}`;

  const res = await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      cache_invalidate_on_update: false,
      cache_ttl: ttlSeconds,        // gateway-level default
      collect_logs: true,
      rate_limiting_interval: 0,
      rate_limiting_limit: 0,
      rate_limiting_technique: "fixed",
    }),
  });

  const data = await res.json();
  if (!data.success) throw new Error(JSON.stringify(data.errors));
  console.log(`Gateway TTL updated to ${ttlSeconds}s`);
}
```

## Per-Tenant TTL Strategy with KV

Multi-tenant APIs often need per-customer freshness guarantees. Store TTL preferences in KV and
read them before forwarding to the gateway.

```typescript
// src/tenantCache.ts
interface TenantCacheConfig {
  ttlSeconds: number;
  bypassForStreaming: boolean;
}

const DEFAULT_CONFIG: TenantCacheConfig = {
  ttlSeconds: 300,
  bypassForStreaming: true,
};

export async function getTenantTtl(
  kv: KVNamespace,
  tenantId: string
): Promise<number> {
  const raw = await kv.get<TenantCacheConfig>(
    `tenant:${tenantId}:cache_config`,
    "json"
  );
  return (raw ?? DEFAULT_CONFIG).ttlSeconds;
}

export async function gatewayFetch(
  gatewayBaseUrl: string,
  authToken: string,
  body: unknown,
  ttlSeconds: number
): Promise<Response> {
  return fetch(`${gatewayBaseUrl}/workers-ai/@cf/meta/llama-3.1-8b-instruct`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
      "cf-aig-cache-ttl": String(ttlSeconds),
    },
    body: JSON.stringify(body),
  });
}
```

## Cache Bypass for Streaming Requests

Streaming responses (`stream: true`) are **not cached** by AI Gateway regardless of the TTL header.
Explicitly setting `cf-aig-cache-ttl: 0` for streaming requests is harmless but redundant — include
it as documentation intent.

```typescript
async function streamingRequest(
  gatewayUrl: string,
  token: string,
  prompt: string
): Promise<ReadableStream<Uint8Array>> {
  const res = await fetch(gatewayUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "cf-aig-cache-ttl": "0", // explicit bypass; streaming skips cache anyway
    },
    body: JSON.stringify({
      messages: [{ role: "user", content: prompt }],
      stream: true,
    }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Gateway error: ${res.status}`);
  }
  return res.body;
}
```

## Anti-patterns

- **Setting a very long TTL globally** — a 24 h gateway default will serve stale tool-augmented
  responses that embed dates, prices, or user context. Use short defaults and let stable workloads
  opt in to longer TTLs via the header.
- **Caching by exact prompt string only** — if prompts include a `requestId` or timestamp, every
  request is a cache miss. Normalise prompts (strip non-semantic fields) before they reach the
  gateway, or use semantic caching.
- **Expecting TTL headers to work without caching enabled** — the gateway ignores `cf-aig-cache-ttl`
  when the cache feature is disabled in the dashboard. Check `Cache Settings` in the AI Gateway UI
  first.
- **Forgetting that `cf-aig-skip-cache: true` overrides TTL** — this header forces a miss regardless
  of the TTL value. Don't mix both headers on the same request.

## Gotchas

- `cf-aig-cache-ttl: 0` is bypass, not "cache forever". Use a large value like `2592000` for
  immutable responses.
- TTL counts from the moment the response is first stored, not from each subsequent hit.
- AI Gateway does not expose a `Cache-Status` response header by default; check the Gateway Logs tab
  for hit/miss classification per request.
- The REST API `cache_ttl` field sets the **default**; per-request headers always win over it.
- Gateway caching is scoped per gateway ID, not per Cloudflare account. Two gateways for dev and
  prod can have different TTLs.

## Verification

```bash
# 1. Make the same request twice; compare latency — the second should be <50 ms if cached.
curl -s -w "\nTotal: %{time_total}s\n" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "cf-aig-cache-ttl: 3600" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is 2+2?"}]}' \
  "https://gateway.ai.cloudflare.com/v1/$ACCOUNT_ID/$GATEWAY_ID/workers-ai/@cf/meta/llama-3.1-8b-instruct"

# 2. Check the AI Gateway Logs in the dashboard for cache: HIT vs MISS.

# 3. Verify gateway-level TTL via API:
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai-gateway/gateways/$GATEWAY_ID" \
  | jq '.result.cache_ttl'
```

## Related

- `ai-gateway-caching.md` — enabling/disabling caching and semantic cache overview
- `ai-gateway-request-caching-cost-control.md` — cost reduction patterns with caching
- `ai-gateway-semantic-cache-threshold-tuning.md` — similarity threshold for semantic cache hits
- `ai-gateway-rate-limiting.md` — combining rate limits with cache to control spend

## Sources

- Cloudflare AI Gateway docs — Cache: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- AI Gateway REST API reference: https://developers.cloudflare.com/api/operations/ai-gateway-update-gateway
- `cf-aig-cache-ttl` header reference: https://developers.cloudflare.com/ai-gateway/configuration/caching/#skip-cache-on-specific-requests
