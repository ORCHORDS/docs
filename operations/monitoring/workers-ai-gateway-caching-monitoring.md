# Workers AI Gateway Caching and Cost Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

AI inference is expensive. When multiple requests ask the same (or semantically similar)
question, paying for the same tokens repeatedly wastes budget. Workers AI Gateway sits
between your Worker and AI providers and caches responses, but without visibility into
cache hit rates, cost-avoidance figures, and provider fallback events you cannot tune
caching policies or catch gateway misconfiguration.

## Context

Workers AI Gateway is a Cloudflare product that proxies requests to Workers AI (and
external providers). It records every request in its own log, supports semantic caching,
rate-limiting, and provider fallback routing. Because it runs in the Cloudflare network,
you can pair its logs with Analytics Engine writes from a Tail Worker to build a
cost-and-cache dashboard without an external observability vendor.

Gateway logs are accessible via the Cloudflare REST API (`/ai-gateway/v1/`) and can be
pushed to Logpush destinations. Semantic cache hits appear as `cached: true` in the
response metadata header `cf-aig-cache-status`.

## Emitting Cache and Cost Events from the Gateway Worker

```typescript
// gateway-observer.ts
export interface GatewayRequestEvent {
  gatewayId: string;
  model: string;
  provider: string;
  cacheStatus: "HIT" | "MISS" | "BYPASS" | "EXPIRED";
  promptTokens: number;
  completionTokens: number;
  latencyMs: number;
  costUsdMicros: number; // estimated; use your own token-price table
}

export async function recordGatewayEvent(
  env: Env,
  event: GatewayRequestEvent
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: [
      event.gatewayId,
      event.model,
      event.provider,
      event.cacheStatus,
    ],
    doubles: [
      event.promptTokens,
      event.completionTokens,
      event.latencyMs,
      event.costUsdMicros,
    ],
    indexes: [event.model],
  });
}
```

## Wrapping the AI Gateway Fetch Call

```typescript
// ai-gateway-client.ts
const TOKEN_PRICE_USD_PER_MILLION: Record<string, { input: number; output: number }> = {
  "@cf/meta/llama-3.1-8b-instruct": { input: 0.08, output: 0.08 },
  "@cf/mistral/mistral-7b-instruct-v0.1": { input: 0.10, output: 0.10 },
};

export async function runWithGatewayObservability(
  env: Env,
  model: string,
  payload: object
): Promise<Response> {
  const gatewayUrl = `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.AI_GATEWAY_ID}/workers-ai/${model}`;

  const start = Date.now();
  const response = await fetch(gatewayUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
    },
    body: JSON.stringify(payload),
  });

  const latencyMs = Date.now() - start;
  const cacheHeader = response.headers.get("cf-aig-cache-status") ?? "MISS";
  const usageHeader = response.headers.get("cf-aig-token-usage");
  const usage = usageHeader ? JSON.parse(usageHeader) : { prompt_tokens: 0, completion_tokens: 0 };

  const price = TOKEN_PRICE_USD_PER_MILLION[model] ?? { input: 0, output: 0 };
  const costUsdMicros = Math.round(
    ((usage.prompt_tokens / 1_000_000) * price.input +
      (usage.completion_tokens / 1_000_000) * price.output) *
      1_000_000
  );

  await recordGatewayEvent(env, {
    gatewayId: env.AI_GATEWAY_ID,
    model,
    provider: "workers-ai",
    cacheStatus: cacheHeader as GatewayRequestEvent["cacheStatus"],
    promptTokens: usage.prompt_tokens,
    completionTokens: usage.completion_tokens,
    latencyMs,
    costUsdMicros,
  });

  return response;
}
```

## Querying Cache Hit Rate and Cost Savings via SQL API

```typescript
// cache-metrics-query.ts
export async function fetchGatewayCacheMetrics(
  env: Env,
  windowHours = 24
): Promise<{ hitRate: number; savedUsdMicros: number }> {
  const query = `
    SELECT
      blob4 AS cache_status,
      COUNT() AS requests,
      SUM(_sample_interval * double4) AS total_cost_usd_micros
    FROM ai_gateway_metrics
    WHERE timestamp > NOW() - INTERVAL '${windowHours}' HOUR
    GROUP BY cache_status
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const { data } = await resp.json<{ data: Array<{ cache_status: string; requests: number; total_cost_usd_micros: number }> }>();

  const total = data.reduce((s, r) => s + r.requests, 0);
  const hits = data.find((r) => r.cache_status === "HIT");
  const hitRate = total > 0 ? (hits?.requests ?? 0) / total : 0;
  const savedUsdMicros = hits?.total_cost_usd_micros ?? 0;

  return { hitRate, savedUsdMicros };
}
```

## Alerting on Low Cache Hit Rate via Durable Object Alarm

```typescript
// cache-alert.ts
export class GatewayCacheAlerter extends DurableObject {
  async alarm(): Promise<void> {
    const metrics = await fetchGatewayCacheMetrics(this.env, 1);

    if (metrics.hitRate < 0.3) {
      await fetch(this.env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `AI Gateway cache hit rate is ${(metrics.hitRate * 100).toFixed(1)}% — below 30% threshold. Semantic caching may be misconfigured or prompts are highly variable.`,
        }),
      });
    }

    this.ctx.storage.setAlarm(Date.now() + 60 * 60 * 1_000); // re-arm hourly
  }
}
```

## Anti-patterns

- Reading cost from the AI Gateway dashboard only — it has no programmatic alerting;
  write cost events yourself so you can alert in real-time.
- Using `cf-aig-cache-status: BYPASS` silently — BYPASS means the request opted out
  of caching (e.g., `cf-aig-skip-cache: true`); log it as a distinct status so you can
  find callers that accidentally disable caching.
- Storing raw prompt text in Analytics Engine blobs for debugging — blobs are logged
  to Cloudflare infrastructure; hash the prompt and store only the hash.
- Assuming cache HITs have zero latency — the cache lookup still traverses the network;
  track HIT latency separately to validate gateway placement.

## Gotchas

- Semantic caching requires the AI Gateway to be configured with an embedding model;
  it is off by default. Exact-match caching is always available.
- The `cf-aig-token-usage` header is set only on non-cached responses; for cache HITs
  the token count reflects the original response at cache-fill time.
- Analytics Engine `writeDataPoint` is best-effort — do not rely on it for billing
  reconciliation; use the AI Gateway REST API log for authoritative records.
- Cost calculations from token counts are estimates; actual billing comes from Cloudflare
  usage meters, not per-request headers.

## Verification

```bash
# Confirm gateway events are landing in Analytics Engine
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT blob4 AS cache_status, COUNT() AS n FROM ai_gateway_metrics GROUP BY cache_status ORDER BY n DESC LIMIT 10"}' \
  | jq '.data'

# Check gateway logs via REST API
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/ai-gateway/v1/$AI_GATEWAY_ID/logs?limit=5" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | {cached, model, duration_ms}'
```

## Related

- `workers-ai-inference-cost-analytics-engine-tracking.md`
- `workers-ai-inference-latency-analytics-engine.md`
- `workers-ai-token-usage-budget-analytics-engine.md`
- `kv-cache-hit-rate-analytics-engine-monitoring.md`
- `tail-worker-structured-log-sampling-strategies.md`

## Sources

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/ai-gateway/observability/analytics/
- https://developers.cloudflare.com/analytics/analytics-engine/
