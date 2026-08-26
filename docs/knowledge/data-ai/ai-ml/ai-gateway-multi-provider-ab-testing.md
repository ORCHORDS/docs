# AI Gateway Multi-Provider A/B Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need to compare response quality, latency, and cost across multiple LLM providers (e.g., OpenAI GPT-4o vs. Anthropic Claude 3.5 Sonnet vs. Google Gemini 2.0 Flash) on real production traffic before committing to one provider or pricing tier.

## Context
Cloudflare AI Gateway exposes a Universal Endpoint that accepts requests for multiple providers under a single URL. A Worker sits upstream, uses consistent hashing to assign each session or user to a provider bucket, and forwards requests to the appropriate AI Gateway provider path. Results, latency, and per-request metadata are logged to AI Gateway's built-in analytics and optionally mirrored to Analytics Engine for custom dashboards. A KV-backed control plane allows traffic splits to be adjusted without redeployment.

## Consistent Hashing for Stable User Assignment

Assign users to a provider deterministically using HMAC-SHA256 of the user ID and experiment salt. Stability ensures that a user always hits the same provider within an experiment period, making quality comparisons fair.

```typescript
// src/ab/assign.ts
export type Provider = 'openai' | 'anthropic' | 'google-ai';

export interface BucketConfig {
  provider: Provider;
  weight: number; // 0–100, must sum to 100
}

export async function assignProvider(
  userId: string,
  experimentSalt: string,
  buckets: BucketConfig[]
): Promise<Provider> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(experimentSalt),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(userId));
  const view = new DataView(sig);
  // Take first 4 bytes as unsigned int, map to 0–99
  const bucket = view.getUint32(0, false) % 100;

  let cumulative = 0;
  for (const b of buckets) {
    cumulative += b.weight;
    if (bucket < cumulative) return b.provider;
  }
  return buckets[buckets.length - 1].provider;
}
```

## Fetching Experiment Config from KV

Store the traffic split configuration in KV so it can be updated at runtime (e.g., ramping a new provider from 10% to 50%) without a Worker redeployment.

```typescript
// src/ab/config.ts
import type { BucketConfig, Provider } from './assign';

interface Env {
  EXPERIMENT_CONFIG: KVNamespace;
}

const DEFAULT_BUCKETS: BucketConfig[] = [
  { provider: 'openai', weight: 50 },
  { provider: 'anthropic', weight: 30 },
  { provider: 'google-ai', weight: 20 },
];

export async function getExperimentBuckets(
  env: Env,
  experimentId: string
): Promise<BucketConfig[]> {
  const raw = await env.EXPERIMENT_CONFIG.get(`experiment:${experimentId}:buckets`);
  if (!raw) return DEFAULT_BUCKETS;
  try {
    return JSON.parse(raw) as BucketConfig[];
  } catch {
    return DEFAULT_BUCKETS;
  }
}

export async function getExperimentSalt(env: Env, experimentId: string): Promise<string> {
  return (await env.EXPERIMENT_CONFIG.get(`experiment:${experimentId}:salt`)) ?? experimentId;
}
```

## Routing to AI Gateway Provider Paths

Cloudflare AI Gateway's Universal Endpoint maps provider paths as `/{account-id}/{gateway-id}/{provider}/`. Construct the correct URL based on the assigned provider and forward the OpenAI-compatible request body.

```typescript
// src/ab/router.ts
import type { Provider } from './assign';

interface Env {
  GATEWAY_ACCOUNT_ID: string;
  GATEWAY_ID: string;
  GATEWAY_TOKEN: string;
}

const PROVIDER_MODELS: Record<Provider, string> = {
  openai: 'gpt-4o',
  anthropic: 'claude-3-5-sonnet-20241022',
  'google-ai': 'gemini-2.0-flash',
};

const PROVIDER_PATH: Record<Provider, string> = {
  openai: 'openai',
  anthropic: 'anthropic',
  'google-ai': 'google-ai-studio',
};

export async function forwardToGateway(
  env: Env,
  provider: Provider,
  requestBody: Record<string, unknown>,
  extraHeaders: Record<string, string> = {}
): Promise<Response> {
  const model = PROVIDER_MODELS[provider];
  const path = PROVIDER_PATH[provider];
  const url = `https://gateway.ai.cloudflare.com/v1/${env.GATEWAY_ACCOUNT_ID}/${env.GATEWAY_ID}/${path}/chat/completions`;

  return fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GATEWAY_TOKEN}`,
      'Content-Type': 'application/json',
      ...extraHeaders,
    },
    body: JSON.stringify({ ...requestBody, model }),
  });
}
```

## Emitting Experiment Metrics to Analytics Engine

Log provider assignment, latency, token usage, and experiment ID to Analytics Engine for offline quality analysis.

```typescript
// src/ab/metrics.ts
interface Env {
  AE: AnalyticsEngineDataset;
}

export interface ExperimentMetric {
  experimentId: string;
  userId: string;
  provider: string;
  model: string;
  latencyMs: number;
  promptTokens: number;
  completionTokens: number;
  httpStatus: number;
}

export function emitExperimentMetric(env: Env, m: ExperimentMetric): void {
  env.AE.writeDataPoint({
    blobs: [m.experimentId, m.userId, m.provider, m.model],
    doubles: [m.latencyMs, m.promptTokens, m.completionTokens, m.httpStatus],
    indexes: [m.experimentId],
  });
}
```

## Full Worker Fetch Handler

Wire all components together: parse the request, assign a provider, forward, measure latency, emit metrics.

```typescript
// src/index.ts
interface Env {
  EXPERIMENT_CONFIG: KVNamespace;
  AE: AnalyticsEngineDataset;
  GATEWAY_ACCOUNT_ID: string;
  GATEWAY_ID: string;
  GATEWAY_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const experimentId = request.headers.get('X-Experiment-Id') ?? 'default';
    const userId = request.headers.get('X-User-Id') ?? crypto.randomUUID();

    const [buckets, salt] = await Promise.all([
      getExperimentBuckets(env, experimentId),
      getExperimentSalt(env, experimentId),
    ]);
    const provider = await assignProvider(userId, salt, buckets);

    const body = await request.json<Record<string, unknown>>();
    const startMs = Date.now();

    const upstream = await forwardToGateway(env, provider, body, {
      'cf-aig-metadata': JSON.stringify({ experimentId, userId, provider }),
    });

    const latencyMs = Date.now() - startMs;
    const responseBody = await upstream.json<{
      usage?: { prompt_tokens?: number; completion_tokens?: number };
    }>();

    emitExperimentMetric(env, {
      experimentId,
      userId,
      provider,
      model: (body.model as string) ?? 'unknown',
      latencyMs,
      promptTokens: responseBody.usage?.prompt_tokens ?? 0,
      completionTokens: responseBody.usage?.completion_tokens ?? 0,
      httpStatus: upstream.status,
    });

    return Response.json(responseBody, { status: upstream.status });
  },
};

import { getExperimentBuckets, getExperimentSalt } from './ab/config';
import { assignProvider } from './ab/assign';
import { forwardToGateway } from './ab/router';
import { emitExperimentMetric } from './ab/metrics';
```

## Querying Experiment Results from Analytics Engine

Use the GraphQL Analytics API to compare providers by median latency and average token cost.

```graphql
# Fetch experiment metrics aggregated by provider
query ExperimentSummary($accountId: String!, $expId: String!) {
  viewer {
    accounts(filter: { accountTag: $accountId }) {
      workersAnalyticsEngineAdaptiveGroups(
        filter: { blob1: $expId }
        limit: 10
        orderBy: [blob3_ASC]
      ) {
        avg { double1 }   # avg latencyMs
        sum { double2 double3 }  # total prompt + completion tokens
        dimensions { blob3 }    # provider
      }
    }
  }
}
```

## Anti-patterns
- Using random assignment per request instead of consistent hashing — users see different providers mid-session, poisoning quality comparisons
- Hard-coding traffic splits in Worker source — requires redeployment to adjust during a live experiment
- Forwarding streaming SSE responses while also trying to buffer the body for metrics — pick one or use a consumer Worker
- Running A/B tests across providers with different context window limits without truncating prompts consistently — skews quality scores
- Comparing cost without normalising by task difficulty or input length — longer prompts always cost more regardless of provider efficiency

## Gotchas
- Anthropic's API uses a different request schema (no `model` in OpenAI-compat path via Gateway); verify the Universal Endpoint normalises it
- `AnalyticsEngineDataset.writeDataPoint` is fire-and-forget and does not surface errors — wrap in try/catch to avoid silent loss
- The AI Gateway Universal Endpoint requires a separate API token with `AI Gateway:Edit` scope; the Workers API token alone is insufficient
- HMAC-SHA256 assignment is CPU-bound — it runs comfortably within Workers CPU limits but adds ~1 ms per request
- KV reads on the hot path add ~5–10 ms; use KV's `cacheTtl` option to serve experiment config from edge cache

## Verification
1. Send 1,000 test requests with random `X-User-Id` values and assert provider distribution matches configured weights (±3%).
2. Send 10 requests with the same `X-User-Id` and confirm all are routed to the same provider.
3. Update the KV split config and confirm new requests reflect the change within 60 seconds (KV propagation SLA).
4. Query Analytics Engine and confirm all three providers appear with non-zero row counts.

## Related
- [LLM A/B Testing](llm-ab-testing.md)
- [AI Gateway Universal Endpoint Provider Normalization](ai-gateway-universal-endpoint-provider-normalization.md)
- [LLM Fallback Provider Rotation](llm-fallback-provider-rotation.md)
- [AI Gateway Logging](ai-gateway-logging.md)

## Sources
- https://developers.cloudflare.com/ai-gateway/providers/universal/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://developers.cloudflare.com/ai-gateway/configuration/custom-metadata/
