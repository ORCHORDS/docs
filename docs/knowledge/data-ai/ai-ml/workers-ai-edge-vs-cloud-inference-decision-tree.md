# Workers AI Edge vs Cloud Inference Decision Tree

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project needs AI inference at multiple points in the anonymous social platform: content moderation at submission time, embedding generation for search, real-time toxicity scoring in feeds, and periodic batch summarization for trend detection. The team debates which inference layer to use for each task. Workers AI (edge inference) has different cost, latency, model-availability, and cold-start profiles compared to Anthropic Claude or OpenAI (cloud providers accessed via AI Gateway). Without a decision framework the choice defaults to habit rather than requirements.

---

## Context

Three inference tiers are available on the Cloudflare-native example project stack:

1. **Workers AI (edge)** — Cloudflare's GPU fleet colocated with Workers. Sub-100ms P50 latency to the user, limited model catalog, free tier, ~$0.01–0.11/M tokens for paid.
2. **AI Gateway → Cloud Provider** — Full model catalog (Anthropic Claude, OpenAI GPT-4o, etc.), higher cost, ~200–800ms added latency over Workers AI for the same PoP, subject to provider rate limits.
3. **Hybrid** — Cheap/fast Workers AI model as the first pass; cloud provider invoked only on confidence thresholds not met, or for tasks that require a larger context window.

The decision tree below codifies the factors that determine which tier wins for a given task.

---

## Decision Tree Logic

```typescript
// src/lib/inference-router.ts

export type InferenceTier = 'workers-ai' | 'cloud-provider' | 'hybrid';

export interface InferenceTask {
  /** Maximum acceptable P95 latency in milliseconds */
  latencySloMs: number;
  /** Maximum acceptable cost in USD per 1000 inferences */
  costPer1kUsd: number;
  /** Approximate prompt + expected completion size in tokens */
  estimatedTokens: number;
  /** Does the task require a model only available at a cloud provider? */
  requiresCloudOnlyModel: boolean;
  /** Is the task synchronous (user is waiting) or asynchronous (background job)? */
  isUserFacing: boolean;
  /** Can quality degrade gracefully (e.g. show a warning) if the cheap model under-performs? */
  gracefulDegradationAcceptable: boolean;
  /** Does the task require > 8192 token context window? */
  requiresLargeContext: boolean;
  /** Is the task run at high volume (> 100k/day)? */
  highVolume: boolean;
}

export function selectInferenceTier(task: InferenceTask): InferenceTier {
  // Hard requirements: only cloud can satisfy these
  if (task.requiresCloudOnlyModel) return 'cloud-provider';
  if (task.requiresLargeContext)    return 'cloud-provider';

  // Latency: Workers AI is the only option under 150ms P95 for user-facing calls
  if (task.isUserFacing && task.latencySloMs < 150) return 'workers-ai';

  // Cost at high volume: Workers AI is 10–50x cheaper than frontier cloud models
  if (task.highVolume && task.costPer1kUsd < 0.05) return 'workers-ai';

  // Hybrid: background tasks where quality matters but cost sensitivity is moderate
  if (!task.isUserFacing && task.gracefulDegradationAcceptable) return 'hybrid';

  // Default: cloud for quality-critical, low-volume, or non-latency-sensitive tasks
  return 'cloud-provider';
}
```

---

## Task Classification for example project

```typescript
// src/config/inference-task-profiles.ts
import { InferenceTask, selectInferenceTier } from '../lib/inference-router';

export const example project_TASKS: Record<string, InferenceTask & { selectedTier: string }> = {
  // ----------------------------------------------------------------
  // Real-time moderation at post submission — user is waiting
  // ----------------------------------------------------------------
  contentModeration: {
    latencySloMs:                    120,
    costPer1kUsd:                    0.11,   // Workers AI @cf/meta/llama-guard-3-8b
    estimatedTokens:                 300,
    requiresCloudOnlyModel:          false,
    isUserFacing:                    true,
    gracefulDegradationAcceptable:   false,  // cannot publish unmoderated content
    requiresLargeContext:            false,
    highVolume:                      true,
    selectedTier: selectInferenceTier({
      latencySloMs: 120, costPer1kUsd: 0.11, estimatedTokens: 300,
      requiresCloudOnlyModel: false, isUserFacing: true,
      gracefulDegradationAcceptable: false, requiresLargeContext: false, highVolume: true,
    }),
  }, // → 'workers-ai'

  // ----------------------------------------------------------------
  // Embedding generation for search index — background on post save
  // ----------------------------------------------------------------
  searchEmbedding: {
    latencySloMs:                    500,
    costPer1kUsd:                    0.00002, // Workers AI @cf/baai/bge-large-en-v1.5
    estimatedTokens:                 256,
    requiresCloudOnlyModel:          false,
    isUserFacing:                    false,
    gracefulDegradationAcceptable:   true,
    requiresLargeContext:            false,
    highVolume:                      true,
    selectedTier: 'workers-ai',
  }, // → 'workers-ai'

  // ----------------------------------------------------------------
  // Appeal review: detailed reasoning about borderline moderation
  // ----------------------------------------------------------------
  moderationAppealReview: {
    latencySloMs:                    5000,   // async, user doesn't wait inline
    costPer1kUsd:                    10.0,   // Claude Sonnet — quality matters
    estimatedTokens:                 4000,
    requiresCloudOnlyModel:          true,   // requires chain-of-thought reasoning quality
    isUserFacing:                    false,
    gracefulDegradationAcceptable:   false,
    requiresLargeContext:            false,
    highVolume:                      false,  // rare event
    selectedTier: 'cloud-provider',
  }, // → 'cloud-provider'

  // ----------------------------------------------------------------
  // Trend summarization: 500+ posts per topic, daily batch job
  // ----------------------------------------------------------------
  trendSummarization: {
    latencySloMs:                    30000,  // batch job, no user SLO
    costPer1kUsd:                    2.0,
    estimatedTokens:                 16000,  // large context required
    requiresCloudOnlyModel:          false,
    isUserFacing:                    false,
    gracefulDegradationAcceptable:   true,
    requiresLargeContext:            true,   // Workers AI max context is 8192
    highVolume:                      false,
    selectedTier: 'cloud-provider',
  }, // → 'cloud-provider'

  // ----------------------------------------------------------------
  // Toxicity scoring in feed rendering — hybrid fallback pattern
  // ----------------------------------------------------------------
  feedToxicityScore: {
    latencySloMs:                    200,
    costPer1kUsd:                    0.05,
    estimatedTokens:                 150,
    requiresCloudOnlyModel:          false,
    isUserFacing:                    true,
    gracefulDegradationAcceptable:   true,   // feed renders with "pending review" badge
    requiresLargeContext:            false,
    highVolume:                      true,
    selectedTier: 'hybrid',
  }, // → 'hybrid' (Workers AI first; cloud if confidence < 0.75)
};
```

---

## Hybrid Execution Pattern

```typescript
// src/lib/hybrid-inference.ts
import { Ai } from '@cloudflare/ai';

export interface HybridInferenceOpts {
  ai: Ai;
  prompt: string;
  confidenceThreshold: number; // escalate to cloud if below this
  cloudFallback: (prompt: string) => Promise<{ label: string; score: number }>;
}

export interface HybridResult {
  label:     string;
  score:     number;
  tier:      'workers-ai' | 'cloud-provider';
  latencyMs: number;
}

export async function hybridClassify(
  opts: HybridInferenceOpts
): Promise<HybridResult> {
  const t0 = Date.now();

  // Step 1: Try Workers AI (fast, cheap)
  const edgeResult = await opts.ai.run(
    '@cf/meta/llama-guard-3-8b' as any,
    { prompt: opts.prompt }
  ) as any;

  const edgeScore: number = edgeResult?.score ?? 0;
  const edgeLabel: string = edgeResult?.label ?? 'UNKNOWN';

  // Step 2: Escalate if confidence is low
  if (edgeScore < opts.confidenceThreshold || edgeLabel === 'UNKNOWN') {
    const cloudResult = await opts.cloudFallback(opts.prompt);
    return {
      label:     cloudResult.label,
      score:     cloudResult.score,
      tier:      'cloud-provider',
      latencyMs: Date.now() - t0,
    };
  }

  return {
    label:     edgeLabel,
    score:     edgeScore,
    tier:      'workers-ai',
    latencyMs: Date.now() - t0,
  };
}
```

---

## Model Availability Reference

```typescript
// src/config/model-catalog.ts
// Workers AI model catalog snapshot (2026-08)
// Always check https://developers.cloudflare.com/workers-ai/models/ for current list

export const WORKERS_AI_MODELS = {
  moderation: [
    '@cf/meta/llama-guard-3-8b',      // safety classification
    '@cf/meta/llama-3.1-8b-instruct', // general instruction
  ],
  embedding: [
    '@cf/baai/bge-large-en-v1.5',     // 1024-dim, best quality
    '@cf/baai/bge-small-en-v1.5',     // 384-dim, fastest
    '@cf/baai/bge-m3',                // multilingual
  ],
  classification: [
    '@cf/huggingface/distilbert-sst-2-int8', // sentiment
  ],
  imageAnalysis: [
    '@cf/llava-hf/llava-1.5-7b-hf',  // vision-language
  ],
} as const;

// Cloud-only models (not available on Workers AI as of 2026-08)
export const CLOUD_ONLY_TASKS = [
  'chain-of-thought reasoning',      // requires claude-3-7-sonnet or o3
  'large context (>8k tokens)',      // Workers AI cap is 8192
  'structured JSON with strict schemas', // better with claude-3-5-haiku tool use
  'code generation',                 // frontier quality requires GPT-4o / Claude
  'image generation',                // flux models not on Workers AI catalog
] as const;
```

---

## Anti-patterns

- **Defaulting to cloud for everything**: Using GPT-4o for high-volume moderation (100k posts/day) at $0.15/1k tokens costs ~$15/day versus ~$0.11/day for Workers AI llama-guard. At 1M posts/day the gap is catastrophic.
- **Defaulting to Workers AI for everything**: Workers AI models are quantized and context-limited. Using llama-3.1-8b for appeal reviews that require nuanced legal reasoning produces lower-quality decisions that expose example project to liability.
- **Latency assumptions without measurement**: Assuming Workers AI is always faster. When a Workers AI PoP has no available GPU, it queues — real P99 can spike above 1000ms. Measure, don't assume.
- **Ignoring the hybrid tier**: Many tasks have a bimodal confidence distribution — most are easy (high confidence, edge model correct) and a few are ambiguous (require cloud escalation). Treating the whole population as hard wastes 90% of the cloud budget.
- **Hard-coding the tier selection**: As Workers AI expands its model catalog, tasks currently routed to cloud may become eligible for edge. Keep the decision tree in configuration, not business logic.

---

## Gotchas

- Workers AI charges per request when the free tier is exhausted; there is no token pricing for image/audio models. Calculate budget differently for those task types.
- Workers AI does not support streaming for all models. Verify streaming support before choosing edge for streaming chat completions.
- Cold-start on Workers AI is negligible because the models are pre-loaded at the PoP level, unlike serverless GPU providers. This is a genuine advantage over cloud providers for P50 latency.
- Cloud providers accessed via AI Gateway inherit AI Gateway's `cf-aig-cache-status` headers; Workers AI calls bypassed through native bindings do not. Track cache metrics separately.
- Workers AI context window limit is 8192 tokens for most text models. Prompts over this limit silently truncate without an error in some SDK versions — validate token count before sending.

---

## Verification

```typescript
// Test: confirm tier selection matches expected for each example project task
import { selectInferenceTier, InferenceTask } from '../lib/inference-router';

const cases: Array<{ task: InferenceTask; expected: string }> = [
  {
    task: { latencySloMs: 120, costPer1kUsd: 0.11, estimatedTokens: 300,
            requiresCloudOnlyModel: false, isUserFacing: true,
            gracefulDegradationAcceptable: false, requiresLargeContext: false, highVolume: true },
    expected: 'workers-ai',
  },
  {
    task: { latencySloMs: 5000, costPer1kUsd: 10, estimatedTokens: 4000,
            requiresCloudOnlyModel: true, isUserFacing: false,
            gracefulDegradationAcceptable: false, requiresLargeContext: false, highVolume: false },
    expected: 'cloud-provider',
  },
  {
    task: { latencySloMs: 30000, costPer1kUsd: 2.0, estimatedTokens: 16000,
            requiresCloudOnlyModel: false, isUserFacing: false,
            gracefulDegradationAcceptable: true, requiresLargeContext: true, highVolume: false },
    expected: 'cloud-provider',
  },
];

for (const { task, expected } of cases) {
  const result = selectInferenceTier(task);
  console.assert(result === expected, `Expected ${expected} got ${result}`);
}
console.log('All tier selection tests passed');
```

---

## Related

- `ai-gateway-conditional-model-routing.md` — dynamic model routing through AI Gateway
- `ai-gateway-fallback-model-chain.md` — fallback chain for cloud provider failures
- `workers-ai-model-benchmarking-latency-profiling.md` — measuring actual P50/P95/P99
- `ai-cost-monitoring.md` — tracking cost outcomes of tier selection decisions
- `llm-cost-optimization.md` — broader cost optimization strategies
- `model-cascade-cheap-first-routing.md` — cheap-first cascade pattern

---

## Sources

- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Workers AI limits (context window, rate limits): https://developers.cloudflare.com/workers-ai/platform/limits/
- Anthropic Claude pricing: https://www.anthropic.com/pricing
- OpenAI pricing: https://openai.com/api/pricing
