# Workers AI Model Deprecation Migration ADR

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Cloudflare announced end-of-life for `@cf/meta/llama-2-7b-chat-int8` with 60 days notice. The model was embedded in four production Workers serving content summarisation, search ranking, tag extraction, and a customer-facing chat feature. Without a structured migration plan, teams risk rushed last-minute migrations, inconsistent output quality, and uncoordinated rollouts that affect downstream consumers.

## Context

Workers AI binds model identifiers as string literals in Worker source code. When a model is deprecated the binding silently falls back to a Cloudflare-chosen successor model or begins returning errors—the behaviour is not guaranteed to be stable. The platform had no centralised model registry, no evaluation harness to compare model outputs before migration, and no feature-flag mechanism to roll out the new model incrementally. This ADR documents the decision to treat Workers AI model identifiers as versioned, environment-scoped dependencies managed through a central registry, and to enforce migration through a phased rollout with automated quality gates.

## Timeline

- **2026-04-01** — Cloudflare publishes deprecation notice for `@cf/meta/llama-2-7b-chat-int8`; EOL set for 2026-06-01.
- **2026-04-05** — Platform team discovers the notice via changelog monitoring; four Workers identified as consumers.
- **2026-04-08** — ADR drafted; candidate successor models evaluated: `@cf/meta/llama-3-8b-instruct` and `@cf/mistral/mistral-7b-instruct-v0.1`.
- **2026-04-15** — Offline evaluation run on 500 golden test cases per feature; score comparisons documented.
- **2026-04-22** — Feature-flag-gated migration deployed to 1% of traffic for the tag-extraction Worker.
- **2026-05-01** — 1% rollout expanded to 100% after 7 days of metric parity.
- **2026-05-10** — Chat Worker migrated last (highest risk); A/B test run for 14 days.
- **2026-05-25** — All four Workers migrated; old model identifier removed from codebase.
- **2026-06-01** — Deprecated model EOL; no production impact.

## Root Cause

The original design embedded model identifiers as hardcoded string literals scattered across Worker source files, with no shared configuration layer:

```typescript
// Before: model identifier hardcoded in each Worker
// summarisation-worker/src/index.ts
const result = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  messages: [{ role: 'user', content: prompt }],
});

// search-ranking-worker/src/index.ts
const score = await env.AI.run('@cf/meta/llama-2-7b-chat-int8', {
  messages: [{ role: 'user', content: rankingPrompt }],
});
```

This meant:
1. There was no single place to update when a model is deprecated.
2. Different Workers could drift to different model versions unintentionally.
3. No evaluation framework existed to compare model quality before switching.
4. No feature flag mechanism allowed incremental rollout of a model change.

## Fix Applied

**Decision**: adopt a central model registry stored in KV, with model identifiers resolved at runtime and overridable per-environment via feature flags.

```typescript
// packages/ai-client/src/model-registry.ts

export const MODEL_REGISTRY = {
  'summarisation':    '@cf/meta/llama-3-8b-instruct',
  'search-ranking':   '@cf/meta/llama-3-8b-instruct',
  'tag-extraction':   '@cf/mistral/mistral-7b-instruct-v0.1',
  'customer-chat':    '@cf/meta/llama-3-8b-instruct',
} as const;

export type ModelAlias = keyof typeof MODEL_REGISTRY;

export async function resolveModel(
  alias: ModelAlias,
  env: Env,
): Promise<string> {
  // KV override takes precedence (used for canary rollouts)
  const override = await env.KV_CONFIG.get(`ai_model:${alias}`);
  return override ?? MODEL_REGISTRY[alias];
}
```

```typescript
// packages/ai-client/src/run.ts

export async function runModel(
  alias: ModelAlias,
  input: AiTextGenerationInput,
  env: Env,
): Promise<AiTextGenerationOutput> {
  const model = await resolveModel(alias, env);

  const start = Date.now();
  const result = await env.AI.run(model as BaseAiTextGenerationModels, input);
  const latency = Date.now() - start;

  // Emit telemetry with model identifier for observability
  env.ANALYTICS.writeDataPoint({
    indexes: [alias, model],
    doubles: [latency],
    blobs: ['ai_inference'],
  });

  return result;
}
```

**Evaluation harness** for pre-migration quality gating:

```typescript
// scripts/evaluate-model.ts
import goldenCases from './golden-cases.json';

async function evaluateModel(
  alias: ModelAlias,
  candidateModel: string,
  baselineModel: string,
) {
  let wins = 0, losses = 0, ties = 0;

  for (const { input, expectedKeywords } of goldenCases[alias]) {
    const [baseline, candidate] = await Promise.all([
      runModelDirect(baselineModel, input),
      runModelDirect(candidateModel, input),
    ]);

    const baselineScore = score(baseline, expectedKeywords);
    const candidateScore = score(candidate, expectedKeywords);

    if (candidateScore > baselineScore) wins++;
    else if (candidateScore < baselineScore) losses++;
    else ties++;
  }

  console.log(`${alias}: wins=${wins} losses=${losses} ties=${ties}`);
  // Gate: candidate must win or tie on ≥80% of cases
  if ((wins + ties) / goldenCases[alias].length < 0.8) {
    throw new Error(`Model ${candidateModel} did not meet quality bar for ${alias}`);
  }
}
```

**Canary rollout via KV flag**:

```typescript
// Canary: route 5% of traffic to new model
// Set via wrangler:
// wrangler kv key put --namespace-id=... ai_model:summarisation "@cf/meta/llama-3-8b-instruct" --percentage 5

// Runtime canary logic in resolveModel:
export async function resolveModel(alias: ModelAlias, env: Env): Promise<string> {
  const override = await env.KV_CONFIG.get(`ai_model:${alias}`);
  if (!override) return MODEL_REGISTRY[alias];

  const [model, percentageStr] = override.split(':percentage=');
  const percentage = percentageStr ? parseInt(percentageStr) : 100;

  if (percentage < 100 && Math.random() * 100 > percentage) {
    return MODEL_REGISTRY[alias]; // old model
  }
  return model; // new model
}
```

## What We Learned

1. **Model identifiers are versioned dependencies** and must be treated with the same discipline as npm package versions—pinned, centrally managed, and changed through a controlled upgrade path.
2. **Deprecation notices require an immediate triage pass** to count how many Workers are affected. Without a registry, this requires a codebase-wide search which is error-prone.
3. **Quality evaluation before migration is non-negotiable for customer-facing AI features.** Different models produce meaningfully different outputs; "compatible" does not mean "equivalent."
4. **Feature-flag-gated canary rollouts for model switches** allow rapid rollback if output quality degrades in production, which golden-case evaluation may not fully capture.
5. **Telemetry must include the model identifier**, not just the alias, so dashboards can show which model served each request during a migration.

## Prevention

- **Automated deprecation monitoring**: subscribe to the Cloudflare Workers AI changelog via an RSS-to-webhook pipeline; create a GitHub issue automatically when a model used by any Worker is announced for deprecation.
- **Model registry linting**: add a CI check that validates all `env.AI.run()` calls use `runModel()` from the shared client—no raw string literals allowed.
- **60-day SLO for model migrations**: once a deprecation is detected, a migration plan must be opened within 5 business days and completed at least 7 days before EOL.
- **Golden case test suite per alias**: maintain a minimum of 100 golden cases per model alias in the repo; run them in CI against the current registered model on every merge.

## Anti-patterns

- Hardcoding model identifier strings at the call site in each Worker.
- Migrating models without a quality evaluation step against representative inputs.
- Performing a big-bang model switch across all Workers simultaneously.
- Not emitting the resolved model identifier in telemetry, making it impossible to correlate quality regressions with model changes.
- Treating Workers AI model identifiers as stable forever without monitoring deprecation notices.

## Gotchas

- Cloudflare may silently reroute requests for a deprecated model to a successor without error—the response schema may differ in subtle ways (e.g., different stop reason field names) that cause downstream parsing failures.
- `@cf/` model identifiers are **not** semantic versions; a new model under a different identifier may have a different context window, tokenizer, or output format even if the task description sounds equivalent.
- KV reads in `resolveModel` add latency to every AI inference call; cache the resolved model in a module-level `Map` keyed by alias with a short TTL to avoid the overhead on high-throughput Workers.
- The Workers AI binding does not expose the underlying model identifier in the response object, so you must log it yourself before the call.
- Some models are gated by Cloudflare account tier; a model that works in a paid account may not be available in the free tier used by staging.

## Verification

1. After migration, run the full golden case evaluation suite for each alias and confirm pass rate ≥95%.
2. Check Analytics Engine for the `ai_inference` data points; confirm the new model identifier appears and the old one stops appearing within 10 minutes of full rollout.
3. Monitor `p99` inference latency for 48 hours post-migration; flag if it increases by more than 20% compared to the baseline model.
4. Confirm the deprecated model identifier no longer appears in any `env.AI.run()` call via `grep -r 'llama-2-7b-chat-int8' .` returning no results.

## Related

- [Workers AI Rate Limit Exceeded Production Incident](workers-ai-rate-limit-exceeded-production-incident.md)
- [Workers AI Cold Start Latency Production Lesson](workers-ai-cold-start-latency-production-lesson.md)
- [Upstream Deprecation Signal to Migration Deadline](upstream-deprecation-signal-to-migration-deadline.md)
- [Architecture Decision Records ADR Workflow](architecture-decision-records-adr-workflow.md)

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/changelog/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
