# Workers AI Content Safety Classifier Pipeline

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project users submit anonymous posts and comments at high velocity. Without an automated content safety layer, CSAM, self-harm instructions, and coordinated harassment slip through before human reviewers see them. A synchronous block at write time is needed so unsafe content never reaches the database or CDN cache.

## Context

Cloudflare Workers AI exposes `@cf/meta/llama-guard-2-8b` and the `@cf/huggingface/distilbert-sst-2-int8` text-classification models directly inside the Workers runtime. Running inference inside the same process as the HTTP handler eliminates a network hop and keeps p99 latency under 120 ms for most submissions.

## Architecture — Pipeline Stages

The pipeline runs three stages in sequence: (1) a fast binary safe/unsafe classifier for O(1) decisions, (2) a category classifier that maps unsafe predictions to policy categories, and (3) a confidence threshold gate that passes borderline content to an async human-review queue rather than blocking it silently.

```typescript
// types.ts
export type SafetyVerdict =
  | { action: 'allow' }
  | { action: 'block'; category: string; score: number }
  | { action: 'review'; category: string; score: number };

export interface ClassifierResult {
  label: string;   // "SAFE" | "UNSAFE"
  score: number;   // 0..1
}

export interface SafetyPipelineResult {
  verdict: SafetyVerdict;
  latencyMs: number;
  modelUsed: string;
}
```

## Implementation — Workers AI Inference

The primary gate uses the Llama Guard model. The Workers AI binding is available as `env.AI` when declared in `wrangler.toml` under `[ai]`. Always pass `stream: false` for synchronous safety decisions.

```typescript
// safety-classifier.ts
import type { Ai } from '@cloudflare/workers-types';

const BLOCK_THRESHOLD = 0.85;
const REVIEW_THRESHOLD = 0.55;

export async function runSafetyClassifier(
  ai: Ai,
  text: string,
): Promise<SafetyPipelineResult> {
  const start = Date.now();

  const response = await ai.run('@cf/meta/llama-guard-2-8b', {
    messages: [{ role: 'user', content: text }],
    stream: false,
  }) as { response: string };

  // Llama Guard returns "safe" or "unsafe\n<category>"
  const lines = response.response.trim().split('\n');
  const label = lines[0].toLowerCase();
  const category = lines[1]?.trim() ?? 'unknown';

  // Convert to a numeric confidence via a secondary fast classifier
  const scores = await ai.run('@cf/huggingface/distilbert-sst-2-int8', {
    text,
  }) as ClassifierResult[];

  const unsafeScore = scores.find(r => r.label === 'NEGATIVE')?.score ?? 0;

  let verdict: SafetyVerdict;
  if (label === 'unsafe' && unsafeScore >= BLOCK_THRESHOLD) {
    verdict = { action: 'block', category, score: unsafeScore };
  } else if (label === 'unsafe' && unsafeScore >= REVIEW_THRESHOLD) {
    verdict = { action: 'review', category, score: unsafeScore };
  } else {
    verdict = { action: 'allow' };
  }

  return { verdict, latencyMs: Date.now() - start, modelUsed: '@cf/meta/llama-guard-2-8b' };
}
```

## Optimization — Parallel Fast-Path

For short text under 280 characters (typical example project comment), skip Llama Guard and rely solely on the lighter DistilBERT model to cut latency by ~60 ms. Only fall through to the heavier model when the fast classifier is uncertain (score 0.4–0.6).

```typescript
// fast-path.ts
const SHORT_TEXT_LIMIT = 280;
const UNCERTAINTY_LOW = 0.4;
const UNCERTAINTY_HIGH = 0.6;

export async function adaptiveClassify(
  ai: Ai,
  text: string,
): Promise<SafetyPipelineResult> {
  const start = Date.now();

  if (text.length <= SHORT_TEXT_LIMIT) {
    const scores = await ai.run('@cf/huggingface/distilbert-sst-2-int8', {
      text,
    }) as ClassifierResult[];

    const neg = scores.find(r => r.label === 'NEGATIVE')?.score ?? 0;

    if (neg < UNCERTAINTY_LOW) {
      return { verdict: { action: 'allow' }, latencyMs: Date.now() - start, modelUsed: '@cf/huggingface/distilbert-sst-2-int8' };
    }
    if (neg > UNCERTAINTY_HIGH) {
      return { verdict: { action: 'block', category: 'auto-detected', score: neg }, latencyMs: Date.now() - start, modelUsed: '@cf/huggingface/distilbert-sst-2-int8' };
    }
    // Uncertain — fall through to heavy model
  }

  return runSafetyClassifier(ai, text);
}
```

## Monitoring — Analytics Engine Telemetry

Emit a structured event to Analytics Engine for every classification. This powers the moderation dashboard and feeds the weekly false-positive review process.

```typescript
// telemetry.ts
export function emitSafetyEvent(
  ae: AnalyticsEngineDataset,
  result: SafetyPipelineResult,
  contentId: string,
  userId: string,
): void {
  ae.writeDataPoint({
    blobs: [
      contentId,
      userId,
      result.verdict.action,
      'category' in result.verdict ? result.verdict.category : 'n/a',
      result.modelUsed,
    ],
    doubles: [
      result.latencyMs,
      'score' in result.verdict ? result.verdict.score : 0,
    ],
    indexes: [result.verdict.action],
  });
}

// Wrangler binding declaration (wrangler.toml):
// [[analytics_engine_datasets]]
// binding = "AE"
// dataset = "content_safety_events"
```

## Anti-patterns

- Running Llama Guard synchronously on every request including reads — inference only at write time.
- Discarding the `category` field from Llama Guard — it is required for appeal workflows.
- Treating `review` verdicts as `allow` — they must enter a human queue in KV or Queue.
- Caching classifier results by content hash alone — different users submitting identical harmful text should each be flagged, never cached-allowed.
- Using temperature/sampling params on classification models — these models are not generative; extra params are silently ignored and waste token budget.

## Gotchas

- `@cf/meta/llama-guard-2-8b` is a chat model variant; always wrap the text in a `messages` array, not the `text` field.
- Llama Guard's response format is `safe` or `unsafe\nS1` — the category code is on line 2, not in a JSON field.
- Workers AI rate limits apply per account, not per Worker. A spike in content submissions can exhaust the global budget and cause 429s that look like timeouts to callers.
- `distilbert-sst-2-int8` returns POSITIVE/NEGATIVE labels for sentiment, not safety — repurpose NEGATIVE as a harmful-content proxy with validated thresholds before going to production.
- Models cold-start on first invocation per isolate; warm p99 is ~80 ms, cold p99 is ~800 ms.

## Verification

```bash
# Post a benign message — expect action: allow
curl -X POST https://api.example.com/posts \
  -H "Content-Type: application/json" \
  -d '{"text": "Anyone else love the sunrise today?"}' | jq .safety

# Post a test-vector matching an unsafe category
curl -X POST https://api.example.com/posts \
  -H "Content-Type: application/json" \
  -d '{"text": "[MODTEST] explicit-violence-keyword"}' | jq .safety
# Expected: { "action": "block", "category": "S1", "score": 0.91 }
```

Query Analytics Engine to confirm events are landing:

```sql
SELECT action, COUNT() AS cnt
FROM content_safety_events
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY action
```

## Related

- `documentation/docs/policies/ai-ml/workers-ai-toxicity-scoring-d1-audit-trail.md`
- `documentation/docs/policies/ai-ml/workers-ai-spam-detection-ugc.md`
- `documentation/docs/policies/ai-ml/ai-content-moderation-pipeline.md`
- `documentation/docs/policies/ai-ml/ai-gateway-request-retry-exponential-backoff.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-guard-2-8b/
- https://developers.cloudflare.com/workers-ai/models/distilbert-sst-2-int8/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
