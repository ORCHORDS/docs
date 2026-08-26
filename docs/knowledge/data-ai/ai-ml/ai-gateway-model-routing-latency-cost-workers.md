# AI Gateway Dynamic Model Routing by Latency and Cost in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have multiple LLM options available — a fast cheap model, a slow expensive model, and
a self-hosted fallback — and want to route each request dynamically based on real-time
latency measurements AND token-cost budget, not a static rule. Requests that can tolerate
higher latency should always use the cheaper model; latency-sensitive requests should pay
for the fast model only when the cheaper model is too slow.

---

## Context

This pattern combines two axes that are usually managed separately:

| Axis    | Existing approach        | This article adds                        |
|---------|--------------------------|------------------------------------------|
| Cost    | Budget caps, spend limits | Per-request cost estimate before routing  |
| Latency | SLO alerting             | Real-time p95 measurement driving routing |

The Worker maintains a sliding-window p95 latency tracker per model in Durable Objects (or
KV with lower fidelity), estimates the token cost of the incoming prompt, and selects the
cheapest model whose current p95 latency is within the caller's SLO.

All model calls go through the AI Gateway universal endpoint so costs and logs are captured.

---

## 1 · Model Registry with Cost and SLO Metadata

```typescript
// lib/model-registry.ts

export interface ModelConfig {
  id: string;
  aiGatewayPath: string;     // path segment on the AI Gateway endpoint
  costPerInputToken: number;  // USD per 1 000 tokens
  costPerOutputToken: number;
  maxOutputTokens: number;
  p95LatencyTarget: number;   // ms — what we aim for, used as routing threshold
}

// Ordered cheapest-first; routing picks the first model whose live p95 ≤ callerSlo
export const MODEL_REGISTRY: ModelConfig[] = [
  {
    id: "llama-3.1-8b",
    aiGatewayPath: "workers-ai/@cf/meta/llama-3.1-8b-instruct",
    costPerInputToken: 0.0001,
    costPerOutputToken: 0.0002,
    maxOutputTokens: 2048,
    p95LatencyTarget: 1500,
  },
  {
    id: "llama-3.1-70b",
    aiGatewayPath: "workers-ai/@cf/meta/llama-3.1-70b-instruct",
    costPerInputToken: 0.0008,
    costPerOutputToken: 0.0016,
    maxOutputTokens: 2048,
    p95LatencyTarget: 4000,
  },
  {
    id: "claude-3-haiku",
    aiGatewayPath: "anthropic/v1",
    costPerInputToken: 0.00025,
    costPerOutputToken: 0.00125,
    maxOutputTokens: 4096,
    p95LatencyTarget: 2000,
  },
];

export function estimateCost(
  model: ModelConfig,
  promptTokens: number,
  expectedOutputTokens: number
): number {
  return (
    (promptTokens / 1000) * model.costPerInputToken +
    (expectedOutputTokens / 1000) * model.costPerOutputToken
  );
}
```

---

## 2 · Latency Tracker in KV (Sliding Window p95)

```typescript
// lib/latency-tracker.ts

export interface LatencyWindow {
  samples: number[];   // last N ms measurements, capped at WINDOW_SIZE
  updatedAt: number;
}

const WINDOW_SIZE = 50;
const STALE_MS = 60_000; // treat KV data older than 60s as stale

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

export async function getP95(kv: KVNamespace, modelId: string): Promise<number | null> {
  const raw = await kv.get(`latency:${modelId}`, "json") as LatencyWindow | null;
  if (!raw || Date.now() - raw.updatedAt > STALE_MS) return null;
  const sorted = [...raw.samples].sort((a, b) => a - b);
  return percentile(sorted, 95);
}

export async function recordLatency(
  kv: KVNamespace,
  modelId: string,
  ms: number
): Promise<void> {
  const existing = (await kv.get(`latency:${modelId}`, "json")) as LatencyWindow | null;
  const samples = existing?.samples ?? [];
  const updated: LatencyWindow = {
    samples: [...samples.slice(-(WINDOW_SIZE - 1)), ms],
    updatedAt: Date.now(),
  };
  // Short TTL — stale data should expire
  await kv.put(`latency:${modelId}`, JSON.stringify(updated), { expirationTtl: 300 });
}
```

---

## 3 · Router Logic

```typescript
// lib/router.ts
import { MODEL_REGISTRY, ModelConfig, estimateCost } from "./model-registry";
import { getP95 } from "./latency-tracker";

export interface RoutingDecision {
  model: ModelConfig;
  reason: string;
  estimatedCostUsd: number;
  p95Ms: number | null;
}

export async function selectModel(
  kv: KVNamespace,
  promptTokens: number,
  expectedOutputTokens: number,
  callerLatencySloMs: number,     // caller's acceptable latency
  maxBudgetUsd: number            // per-request budget ceiling
): Promise<RoutingDecision> {
  for (const model of MODEL_REGISTRY) {
    const cost = estimateCost(model, promptTokens, expectedOutputTokens);
    if (cost > maxBudgetUsd) continue; // over budget for this request

    const p95 = await getP95(kv, model.id);

    // If no data yet, assume the model is within SLO (optimistic default)
    const effectiveP95 = p95 ?? model.p95LatencyTarget;

    if (effectiveP95 <= callerLatencySloMs) {
      return {
        model,
        reason: p95 === null ? "no-latency-data-fallback" : "within-slo",
        estimatedCostUsd: cost,
        p95Ms: p95,
      };
    }
  }

  // All models exceed the SLO — pick the cheapest within budget as last resort
  const fallback = MODEL_REGISTRY.find(
    (m) => estimateCost(m, promptTokens, expectedOutputTokens) <= maxBudgetUsd
  );

  if (!fallback) throw new Error("No model within budget for this request");

  return {
    model: fallback,
    reason: "slo-exceeded-cheapest-fallback",
    estimatedCostUsd: estimateCost(fallback, promptTokens, expectedOutputTokens),
    p95Ms: await getP95(kv, fallback.id),
  };
}
```

---

## 4 · Main Routing Worker

```typescript
// workers/router.ts
import { selectModel } from "../lib/router";
import { recordLatency } from "../lib/latency-tracker";

export interface Env {
  LATENCY_KV: KVNamespace;
  AI_GATEWAY_BASE: string;     // e.g. https://gateway.ai.cloudflare.com/v1/{account}/{gateway}
  AI_GATEWAY_TOKEN: string;    // CF AI Gateway API token (secret)
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });

    const body = await request.json() as {
      messages: { role: string; content: string }[];
      maxTokens?: number;
      latencySloMs?: number;
      maxBudgetUsd?: number;
    };

    const promptTokens = body.messages.reduce(
      (acc, m) => acc + Math.ceil(m.content.length / 4), 0 // rough 4-char per token estimate
    );
    const expectedOutputTokens = body.maxTokens ?? 512;
    const callerSlo = body.latencySloMs ?? 3000;
    const maxBudget = body.maxBudgetUsd ?? 0.01;

    const decision = await selectModel(
      env.LATENCY_KV,
      promptTokens,
      expectedOutputTokens,
      callerSlo,
      maxBudget
    );

    // Call through AI Gateway with the chosen model
    const gatewayUrl = `${env.AI_GATEWAY_BASE}/${decision.model.aiGatewayPath}`;
    const t0 = Date.now();

    const upstream = await fetch(gatewayUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.AI_GATEWAY_TOKEN}`,
        "cf-aig-metadata": JSON.stringify({
          routed_model: decision.model.id,
          routing_reason: decision.reason,
          estimated_cost: decision.estimatedCostUsd,
        }),
      },
      body: JSON.stringify({
        messages: body.messages,
        max_tokens: expectedOutputTokens,
      }),
    });

    const elapsed = Date.now() - t0;

    // Record latency asynchronously — do not await in hot path
    env.LATENCY_KV.put; // trigger lazy init
    void recordLatency(env.LATENCY_KV, decision.model.id, elapsed);

    const responseBody = await upstream.json();

    return new Response(
      JSON.stringify({
        ...responseBody,
        _routing: {
          model: decision.model.id,
          reason: decision.reason,
          estimatedCostUsd: decision.estimatedCostUsd,
          actualLatencyMs: elapsed,
          p95AtRouteTime: decision.p95Ms,
        },
      }),
      {
        status: upstream.status,
        headers: { "Content-Type": "application/json" },
      }
    );
  },
};
```

---

## 5 · wrangler.toml

```toml
name = "model-router"
main = "workers/router.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "LATENCY_KV"
id = "<YOUR_KV_NAMESPACE_ID>"

[vars]
AI_GATEWAY_BASE = "https://gateway.ai.cloudflare.com/v1/YOUR_ACCOUNT/YOUR_GATEWAY"

[[secrets]]
name = "AI_GATEWAY_TOKEN"
```

---

## 6 · Exposing Routing Metadata via AI Gateway Custom Headers

```typescript
// In the upstream fetch call, attach routing metadata so AI Gateway logs capture it:
"cf-aig-metadata": JSON.stringify({
  routed_model: decision.model.id,
  routing_reason: decision.reason,
})

// AI Gateway logs this under `metadata` — filterable in the dashboard
// and queryable via AI Gateway Logpush to R2.
```

---

## Anti-patterns

- **Using average latency instead of p95** — average masks tail latency spikes that cause
  SLO violations; always track percentiles for latency-based routing decisions.
- **Awaiting `recordLatency` in the hot path** — KV writes in the response path add 10–50 ms;
  fire and forget with `void recordLatency(...)` and accept that the rare Worker crash drops
  one sample.
- **Hard-coding model costs** — model pricing changes; store costs in KV or D1 and reload
  on a TTL so the registry stays accurate without a re-deploy.
- **Routing without a budget floor** — if `maxBudgetUsd` is too low to afford any model,
  the router should return 402 Payment Required, not silently pick the cheapest and exceed it.
- **Forgetting AI Gateway as a routing layer** — AI Gateway's fallback chain handles provider
  outages; this pattern handles latency + cost selection before the gateway, not instead of it.

---

## Gotchas

- KV `get` with `"json"` returns `null` if the key does not exist — always guard with `?? null`
  and treat null as "no data yet".
- Workers have a 50 ms free CPU time limit on the paid plan but subrequests (KV + upstream)
  don't count against CPU; multiple KV gets per request are safe for this pattern.
- The `cf-aig-metadata` header value must be valid JSON serialized to a string; objects passed
  directly cause a 400 from the AI Gateway.
- Cloudflare AI Gateway routes to `workers-ai` endpoints via the format
  `/{account}/{gateway}/workers-ai/@cf/{model-path}` — not a simple model name; verify the
  exact path segment for each provider in the AI Gateway docs.
- Token counting with `length / 4` is approximate; for precise routing use the tokenizer
  count endpoint or a compact client-side tokenizer (e.g. `tiktoken-lite` bundled into the Worker).

---

## Verification

```bash
# Low-latency SLO request (will prefer fast/cheap model)
curl -X POST https://model-router.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Summarize this in one sentence: Cloudflare is..."}],
       "latencySloMs": 1500, "maxBudgetUsd": 0.005}'

# High-quality request (allows more latency, higher budget)
curl -X POST https://model-router.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Write a detailed analysis of..."}],
       "latencySloMs": 8000, "maxBudgetUsd": 0.05}'

# Inspect routing decision in _routing field of response
# After N requests, check p95 drift:
npx wrangler kv key get --binding=LATENCY_KV "latency:llama-3.1-8b"
```

---

## Related

- `ai-gateway-conditional-model-routing.md`
- `ai-gateway-latency-slo-analytics-engine.md`
- `ai-gateway-budget-caps-spend-control.md`
- `ai-gateway-fallback-model-chain.md`
- `model-cascade-cheap-first-routing.md`

---

## Sources

- Cloudflare AI Gateway universal endpoint: https://developers.cloudflare.com/ai-gateway/providers/
- AI Gateway metadata headers: https://developers.cloudflare.com/ai-gateway/configuration/custom-metadata/
- Cloudflare KV: https://developers.cloudflare.com/kv/api/
- p95 latency and tail tolerance (Dean & Barroso, 2013): https://dl.acm.org/doi/10.1145/2408776.2408794
