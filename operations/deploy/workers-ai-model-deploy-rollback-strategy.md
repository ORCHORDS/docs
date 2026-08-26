# Workers AI Model Deploy Rollback Strategy

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Workers AI application deploys a new model version (e.g. upgrading from `@cf/meta/llama-3.1-8b-instruct` to `@cf/meta/llama-3.3-70b-instruct-fp8-fast`) and immediately sees elevated latency, degraded output quality, or unexpected billing spikes. The team needs a tested rollback path that restores the previous model without a full redeployment cycle.

## Context
Cloudflare Workers AI model bindings are declared in `wrangler.toml` as `ai` bindings; the model ID is passed at call time (`env.AI.run(modelId, input)`), not as a static binding parameter. This means model selection can be controlled at runtime via a KV flag or environment variable, enabling zero-code-change rollbacks. Workers Versions gradual rollout further allows traffic steering between a new model version and the prior one.

## Model Version Strategy in wrangler.toml

```toml
# wrangler.toml
name = "ai-inference-worker"
compatibility_date = "2026-08-01"
main = "src/index.ts"

[ai]
binding = "AI"

# Store active model ID and fallback in environment variables
# so rollback is a wrangler deploy --var change, not a code change.
[vars]
AI_MODEL_PRIMARY   = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
AI_MODEL_FALLBACK  = "@cf/meta/llama-3.1-8b-instruct"
AI_ROLLBACK_ACTIVE = "false"   # flip to "true" to instant-rollback

[[kv_namespaces]]
binding = "MODEL_FLAGS"
id      = "YOUR_KV_NAMESPACE_ID"
```

## Runtime Model Selection with Automatic Fallback

```typescript
// src/index.ts
import { Env } from "./types";

export interface Env {
  AI: Ai;
  MODEL_FLAGS: KVNamespace;
  AI_MODEL_PRIMARY: string;
  AI_MODEL_FALLBACK: string;
  AI_ROLLBACK_ACTIVE: string;
}

interface InferenceRequest {
  prompt: string;
  max_tokens?: number;
}

async function resolveModel(env: Env): Promise<string> {
  // KV flag takes highest precedence (instant, no redeploy required)
  const kvFlag = await env.MODEL_FLAGS.get("rollback_active");
  if (kvFlag === "true") return env.AI_MODEL_FALLBACK;

  // Environment variable is second precedence (requires wrangler deploy --var)
  if (env.AI_ROLLBACK_ACTIVE === "true") return env.AI_MODEL_FALLBACK;

  return env.AI_MODEL_PRIMARY;
}

async function runWithFallback(
  env: Env,
  model: string,
  input: Record<string, unknown>,
  ctx: ExecutionContext
): Promise<{ response: AiTextGenerationOutput; model_used: string }> {
  try {
    const response = await env.AI.run(model as BaseAiTextGenerationModels, input as never);
    return { response, model_used: model };
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);

    // Automatic fallback on model errors (rate-limit, deprecation, overload)
    if (
      errMsg.includes("model not available") ||
      errMsg.includes("rate limit") ||
      errMsg.includes("5")
    ) {
      console.warn(`Model ${model} failed (${errMsg}), falling back to ${env.AI_MODEL_FALLBACK}`);

      // Persist the flag so subsequent requests don't keep hitting the bad model
      ctx.waitUntil(
        env.MODEL_FLAGS.put("rollback_active", "true", { expirationTtl: 3600 })
      );

      const fallbackResponse = await env.AI.run(
        env.AI_MODEL_FALLBACK as BaseAiTextGenerationModels,
        input as never
      );
      return { response: fallbackResponse, model_used: env.AI_MODEL_FALLBACK };
    }
    throw err;
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = (await request.json()) as InferenceRequest;
    const model = await resolveModel(env);

    const input = {
      messages: [{ role: "user", content: body.prompt }],
      max_tokens: body.max_tokens ?? 512,
    };

    const { response, model_used } = await runWithFallback(env, model, input, ctx);

    return Response.json({
      result: response,
      model_used,
      rollback_active: model_used === env.AI_MODEL_FALLBACK,
    });
  },
};
```

## Rollback Runbook (Manual Steps)

```bash
#!/usr/bin/env bash
# scripts/ai-model-rollback.sh
# Usage: ./ai-model-rollback.sh [activate|deactivate]
set -euo pipefail

ACTION=${1:-activate}
WORKER=${WORKER_NAME:?}
KV_NAMESPACE_ID=${MODEL_FLAGS_KV_ID:?}

case "$ACTION" in
  activate)
    echo "Activating AI model rollback for ${WORKER}..."
    # Instant KV-based rollback — takes effect on next request, no redeploy
    wrangler kv key put "rollback_active" "true" \
      --namespace-id "${KV_NAMESPACE_ID}"

    echo "Rollback active. Primary model bypassed; fallback serving traffic."
    echo "Monitor with: wrangler tail ${WORKER} --format=pretty"
    ;;

  deactivate)
    echo "Deactivating rollback for ${WORKER}..."
    wrangler kv key put "rollback_active" "false" \
      --namespace-id "${KV_NAMESPACE_ID}"
    echo "Primary model restored."
    ;;

  *)
    echo "Usage: $0 [activate|deactivate]" >&2
    exit 1
    ;;
esac
```

## CI Gate: Model Smoke Test Before Full Deploy

```yaml
# .github/workflows/ai-model-smoke-test.yml
name: AI Model Smoke Test

on:
  push:
    branches: [main]
    paths:
      - wrangler.toml
      - src/**

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Deploy canary version (10% traffic)
        run: |
          npx wrangler versions upload
          VERSION_ID=$(npx wrangler versions list --json | jq -r '.[0].id')
          npx wrangler versions deploy \
            --version-id "${VERSION_ID}" \
            --percentage 10
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run model quality assertions
        run: npx tsx scripts/ai-smoke-test.ts
        env:
          WORKER_URL: ${{ vars.WORKER_URL }}
          EXPECTED_TOPIC_KEYWORDS: "deployment,infrastructure,rollback"
        timeout-minutes: 5

      - name: Promote to 100% if passing
        run: |
          VERSION_ID=$(npx wrangler versions list --json | jq -r '.[0].id')
          npx wrangler versions deploy \
            --version-id "${VERSION_ID}" \
            --percentage 100
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Rollback on failure
        if: failure()
        run: |
          PREV_VERSION=$(npx wrangler versions list --json | jq -r '.[1].id')
          npx wrangler versions deploy \
            --version-id "${PREV_VERSION}" \
            --percentage 100
          echo "ROLLBACK_TRIGGERED=true" >> "$GITHUB_ENV"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

```typescript
// scripts/ai-smoke-test.ts
const WORKER_URL = process.env.WORKER_URL!;
const KEYWORDS = (process.env.EXPECTED_TOPIC_KEYWORDS ?? "").split(",");

const TEST_CASES = [
  { prompt: "In one sentence, what is a deployment rollback?", min_words: 5 },
  { prompt: "Name one CI/CD tool.", min_words: 1 },
];

let failures = 0;

for (const tc of TEST_CASES) {
  const res = await fetch(WORKER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: tc.prompt, max_tokens: 128 }),
  });

  if (!res.ok) {
    console.error(`HTTP ${res.status} for prompt: "${tc.prompt}"`);
    failures++;
    continue;
  }

  const data = (await res.json()) as { result: { response: string }; model_used: string };
  const words = data.result.response?.trim().split(/\s+/) ?? [];

  if (words.length < tc.min_words) {
    console.error(`Response too short (${words.length} words): ${data.result.response}`);
    failures++;
  } else {
    console.log(`PASS [${data.model_used}]: "${data.result.response.slice(0, 80)}..."`);
  }
}

if (failures > 0) {
  console.error(`${failures} smoke test(s) failed.`);
  process.exit(1);
}
```

## Anti-patterns
- Hard-coding the model ID as a string literal in worker code instead of reading from env — prevents any rollback without a redeploy.
- Using only the KV flag without a code-level fallback — if the KV read fails the worker is stuck on the bad model.
- Deploying a new model to 100% traffic without a canary stage — removes all safe-rollback windows.
- Relying on Cloudflare's auto-fallback for quality degradation — the platform only falls back on availability errors, not semantic quality regressions.
- Ignoring `model_used` in response telemetry — makes it impossible to correlate latency spikes with model versions after the fact.

## Gotchas
- Workers AI model IDs include a channel suffix (`-fp8-fast`, `-awq`); upgrading the suffix silently changes quantization and token limits.
- KV writes in `ctx.waitUntil` are not guaranteed before the response is returned; the very next request may still hit the bad model once.
- `env.AI.run()` typings are generic; TypeScript will not catch an invalid model string at compile time — smoke tests are the only gate.
- Pricing differs between model sizes; rolling back from a 70B to an 8B model changes billing per-token immediately.
- The KV TTL on auto-set rollback flags (`expirationTtl: 3600`) means rollback will automatically expire; set it explicitly if permanent manual intervention is needed.

## Verification
1. Set `AI_ROLLBACK_ACTIVE = "true"` in `wrangler.toml` vars, deploy, and confirm `model_used` in the response is the fallback.
2. Trigger a KV-based rollback via `./scripts/ai-model-rollback.sh activate` and confirm the next request returns the fallback model without redeployment.
3. Intentionally pass an invalid model ID and confirm the automatic fallback engages and the KV flag is set.
4. Run the smoke test script against a staging worker and confirm it exits 0 on a good model and non-zero on a nonsense prompt response.
5. After deactivating rollback, confirm the primary model resumes and the `rollback_active` field in the response is `false`.

## Related
- `workers-ai-model-version-pin-deploy.md`
- `worker-versioning-gradual-rollout.md`
- `canary-workers-gradual-traffic-split.md`
- `deployment-health-gates-automated-rollback.md`
- `rollback-strategies-workers-pages.md`

## Sources
- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers/wrangler/commands/#versions
- https://developers.cloudflare.com/workers-ai/platform/error-handling/
