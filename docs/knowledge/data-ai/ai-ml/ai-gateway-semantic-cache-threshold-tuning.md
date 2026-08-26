# AI Gateway Semantic Cache Similarity Threshold Tuning

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have enabled semantic caching on AI Gateway to cut inference costs, but either:
(a) the cache hit rate is too low because the threshold is too strict, or
(b) semantically similar but meaningfully different prompts are returning the same
cached answer, causing incorrect responses. You need to understand how to measure and
tune the similarity threshold correctly.

## Context

AI Gateway's semantic cache stores prompt–response pairs indexed by the embedding of
the prompt. On each new request it computes the embedding of the incoming prompt and
returns the cached response if the cosine similarity score meets or exceeds a
configurable threshold (0.0 to 1.0). A higher threshold means stricter matching
(fewer false hits, lower cache rate); a lower threshold means more aggressive caching
(higher hit rate, more risk of false hits).

The default threshold is approximately 0.95. Most teams need to run a calibration
experiment before deviating from the default.

---

## 1. Reading Cache Hit Metrics from AI Gateway Logs

```typescript
// src/cache-metrics.ts
// Pull logs via the AI Gateway Logs API to compute hit rate by threshold

interface AigLogEntry {
  id: string;
  provider: string;
  model: string;
  cached: boolean;
  similarity_score: number | null; // populated only when a cache candidate was found
  created_at: string;
  status_code: number;
}

export async function fetchRecentLogs(
  accountId: string,
  gatewayId: string,
  apiToken: string,
  limit = 1000
): Promise<AigLogEntry[]> {
  const url =
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/ai-gateway/gateways/${gatewayId}/logs?limit=${limit}&order_by=created_at&order=desc`;

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${apiToken}` },
  });

  const body = await res.json<{ result: AigLogEntry[] }>();
  return body.result;
}

export function computeHitRateByThreshold(
  logs: AigLogEntry[],
  threshold: number
): { hitRate: number; totalRequests: number; cacheHits: number } {
  const totalRequests = logs.length;
  const cacheHits = logs.filter(
    (l) => l.similarity_score !== null && l.similarity_score >= threshold
  ).length;

  return {
    hitRate: totalRequests > 0 ? cacheHits / totalRequests : 0,
    totalRequests,
    cacheHits,
  };
}
```

---

## 2. Threshold Sweep Analysis

```typescript
// src/threshold-sweep.ts
// Evaluate multiple threshold candidates against the same log dataset

export function sweepThresholds(logs: AigLogEntry[]): void {
  const thresholds = [0.80, 0.85, 0.90, 0.92, 0.95, 0.97, 0.99, 1.00];

  console.log('Threshold | Hit Rate | Cache Hits | Total');
  console.log('----------|----------|------------|------');

  for (const t of thresholds) {
    const { hitRate, cacheHits, totalRequests } = computeHitRateByThreshold(logs, t);
    console.log(
      `${t.toFixed(2)}      | ${(hitRate * 100).toFixed(1)}%    | ${cacheHits}          | ${totalRequests}`
    );
  }
}

// Run this offline against exported logs (not in a hot-path Worker):
// const logs = await fetchRecentLogs(accountId, gatewayId, apiToken, 5000);
// sweepThresholds(logs);
```

Plot hit rate vs threshold and look for the "elbow": the point where lowering the
threshold further gives diminishing returns in hit rate but increasing risk of wrong
answers.

---

## 3. Validating Cache Quality with Spot Checks

```typescript
// src/cache-quality.ts
// For each cached hit in the logs, compare the stored prompt vs the incoming prompt
// to identify false positives (cached but semantically different)

interface PromptPair {
  cachedPrompt: string;
  incomingPrompt: string;
  similarityScore: number;
  response: string;
}

export async function spotCheckFalsePositives(
  pairs: PromptPair[],
  threshold: number
): Promise<void> {
  const suspects = pairs.filter(
    (p) => p.similarityScore >= threshold && p.similarityScore < threshold + 0.03
  );

  console.log(
    `\n=== Spot check: ${suspects.length} near-threshold cache hits ===\n`
  );

  for (const pair of suspects.slice(0, 10)) {
    console.log(`Score: ${pair.similarityScore.toFixed(4)}`);
    console.log(`Cached:   ${pair.cachedPrompt.slice(0, 100)}`);
    console.log(`Incoming: ${pair.incomingPrompt.slice(0, 100)}`);
    console.log(`Response: ${pair.response.slice(0, 100)}\n`);
  }
}
```

Manually review the output. If near-threshold pairs look meaningfully different in
intent, raise the threshold. If they look equivalent, your threshold is well-calibrated.

---

## 4. Setting the Threshold via API

```typescript
// src/configure-gateway.ts
// Update the semantic cache threshold via the AI Gateway REST API

export async function setSemanticCacheThreshold(
  accountId: string,
  gatewayId: string,
  apiToken: string,
  threshold: number // 0.0 – 1.0
): Promise<void> {
  if (threshold < 0 || threshold > 1) {
    throw new RangeError(`threshold must be 0–1, got ${threshold}`);
  }

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/ai-gateway/gateways/${gatewayId}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        cache_type: 'semantic',
        cache_ttl: 3600,                    // seconds; tune per use-case
        semantic_similarity: threshold,     // the threshold field
      }),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to update gateway: ${err}`);
  }

  console.log(`Semantic cache threshold updated to ${threshold}`);
}
```

---

## 5. Per-Request Cache Bypass for Dynamic Prompts

```typescript
// src/gateway-request.ts
// Some prompts (e.g. those containing current date, user name, real-time data)
// must never be served from semantic cache

export async function callGateway(
  env: Env,
  prompt: string,
  options: { bypassCache?: boolean } = {}
): Promise<string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${env.CF_API_TOKEN}`,
  };

  if (options.bypassCache) {
    // AI Gateway respects Cache-Control: no-store to skip both exact and semantic cache
    headers['Cache-Control'] = 'no-store';
  }

  const res = await fetch(
    `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.GATEWAY_ID}/workers-ai/@cf/meta/llama-3.1-8b-instruct`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({
        messages: [{ role: 'user', content: prompt }],
      }),
    }
  );

  const data = await res.json<{ result: { response: string } }>();
  return data.result.response;
}
```

---

## 6. Threshold Recommendations by Prompt Type

| Prompt category | Recommended threshold | Rationale |
|---|---|---|
| FAQ / knowledge base Q&A | 0.90 – 0.92 | Questions are rephrasings of the same factual query |
| Code generation | 0.97 – 0.99 | Small wording changes alter the generated code |
| Summarisation | 0.85 – 0.90 | Different documents with similar descriptions diverge |
| Classification / routing | 0.88 – 0.93 | Categories map to discrete labels; paraphrases match |
| Creative / open-ended | 0.98 – 1.00 | Caching creative output is rarely safe |

---

## Anti-patterns

- **Setting threshold at 0.80 globally** to maximise cache hits without checking
  whether near-threshold pairs are semantically equivalent.
- **Caching prompts that embed real-time data** (e.g., "What is the weather in London
  right now?") — the `no-store` header bypass should be applied to all time-sensitive
  prompts.
- **Never reviewing cache hit logs** — the gateway logs `similarity_score` for every
  cache candidate; ignoring this data means you cannot detect threshold drift as your
  user prompts evolve.
- **Relying on semantic cache as a substitute for deterministic exact-match cache** —
  for identical repeated prompts, AI Gateway applies exact-match caching first;
  semantic cache only activates when the exact match misses.

---

## Gotchas

- Semantic cache is powered by an embedding model that the gateway chooses internally.
  If your prompts are in a language other than English, the internal embedding model's
  multilingual coverage affects accuracy.
- The similarity score in logs reflects the score at query time; if you lower the
  threshold later, existing cache entries are re-evaluated against the new threshold on
  the next matching request.
- `cache_ttl` and `semantic_similarity` are set at the gateway level, not per-request.
  If you need different TTLs or thresholds for different endpoints, use separate
  gateway IDs.
- Semantic cache does not deduplicate concurrent identical requests during cache
  population. Under a cold-start burst, many requests may pass through to the model
  before the cache is warm.

---

## Verification

```typescript
// Verify the currently configured threshold
async function readCurrentThreshold(
  accountId: string,
  gatewayId: string,
  apiToken: string
): Promise<number | null> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai-gateway/gateways/${gatewayId}`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const body = await res.json<{
    result: { semantic_similarity: number | null };
  }>();
  return body.result.semantic_similarity ?? null;
}
```

---

## Related

- `ai-gateway-caching.md`
- `ai-gateway-request-caching-cost-control.md`
- `semantic-caching-patterns.md`
- `similarity-threshold-tuning.md`
- `cloudflare-ai-gateway-observability.md`

---

## Sources

- AI Gateway semantic cache docs: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- AI Gateway logs API: https://developers.cloudflare.com/ai-gateway/reference/logs/
- Cloudflare AI Gateway configuration API: https://developers.cloudflare.com/api/resources/ai_gateway/
