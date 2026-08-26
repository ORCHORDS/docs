# Workers AI LoRA Adapter A/B Test Traffic Routing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have fine-tuned a LoRA adapter for your domain (e.g., a customer-support tone fine-tune on
`@cf/meta/llama-3.1-8b-instruct`) and need to validate it against the base model before full rollout. Splitting live
traffic between the adapter and the base model lets you measure quality, latency, and error rate in production with
real user prompts.

## Context

Workers AI supports LoRA adapters via the `lora` parameter on the AI binding. A/B routing in Workers is typically
done by hashing a stable user or session identifier to assign treatment groups deterministically — the same user
always hits the same variant within an experiment window. Experiment assignments and outcome metrics are recorded in
D1 for offline analysis. The approach generalises to multi-armed experiments: add more bucket boundaries and adapter
IDs without changing the routing logic.

## Experiment Configuration in KV

Store the active experiment spec in KV so it can be updated without a Worker redeploy.

```typescript
import type { Ai } from "@cloudflare/ai";

interface Env {
  AI: Ai;
  EXPERIMENT_KV: KVNamespace;
  DB: D1Database;
}

interface Variant {
  id: string;
  loraAdapterId: string | null; // null = base model
  trafficFraction: number;      // 0.0 – 1.0, must sum to 1.0 across variants
}

interface Experiment {
  id: string;
  model: string;
  variants: Variant[];
  active: boolean;
}

async function getExperiment(env: Env): Promise<Experiment | null> {
  const raw = await env.EXPERIMENT_KV.get("active_experiment", "json");
  return raw as Experiment | null;
}

// Example experiment stored in KV:
// {
//   "id": "lora-support-tone-v1",
//   "model": "@cf/meta/llama-3.1-8b-instruct",
//   "variants": [
//     { "id": "control", "loraAdapterId": null, "trafficFraction": 0.5 },
//     { "id": "treatment", "loraAdapterId": "support-tone-lora-v1", "trafficFraction": 0.5 }
//   ],
//   "active": true
// }
```

## Stable Bucket Assignment via Hash

Hash the user ID to a float in [0, 1) and select the variant whose cumulative fraction covers it.

```typescript
async function hashToBucket(userId: string, salt: string): Promise<number> {
  const input = `${salt}:${userId}`;
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(input)
  );
  // Take first 4 bytes as uint32, normalise to [0, 1)
  const view = new DataView(buf);
  const uint32 = view.getUint32(0, false);
  return uint32 / 0x100000000;
}

function selectVariant(bucket: number, variants: Variant[]): Variant {
  let cumulative = 0;
  for (const v of variants) {
    cumulative += v.trafficFraction;
    if (bucket < cumulative) return v;
  }
  // Fallback to last variant (handles floating point rounding)
  return variants[variants.length - 1];
}

async function assignVariant(
  env: Env,
  userId: string,
  experiment: Experiment
): Promise<Variant> {
  const bucket = await hashToBucket(userId, experiment.id);
  return selectVariant(bucket, experiment.variants);
}
```

## Inference with Optional LoRA Adapter

Run inference, passing the adapter ID only when the variant calls for it.

```typescript
interface InferenceResult {
  variantId: string;
  adapterId: string | null;
  response: string;
  latencyMs: number;
}

async function runInference(
  env: Env,
  model: string,
  messages: { role: string; content: string }[],
  variant: Variant
): Promise<InferenceResult> {
  const start = Date.now();

  const params: Record<string, unknown> = {
    messages,
    max_tokens: 512,
  };

  if (variant.loraAdapterId) {
    params.lora = variant.loraAdapterId;
  }

  const result = await (env.AI as any).run(model, params) as { response: string };

  return {
    variantId: variant.id,
    adapterId: variant.loraAdapterId,
    response: result.response,
    latencyMs: Date.now() - start,
  };
}
```

## Metric Recording and Worker Handler

Log variant, latency, and any downstream quality signal (e.g., thumbs-up from the user) to D1 for analysis.

```typescript
async function recordOutcome(
  env: Env,
  experimentId: string,
  userId: string,
  variantId: string,
  latencyMs: number,
  tokenCount?: number
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO ab_outcomes
       (experiment_id, user_id, variant_id, latency_ms, token_count, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(experimentId, userId, variantId, latencyMs, tokenCount ?? null, Date.now())
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { userId, messages } = (await request.json()) as {
      userId: string;
      messages: { role: string; content: string }[];
    };

    if (!userId || !messages?.length) {
      return new Response("userId and messages required", { status: 400 });
    }

    const experiment = await getExperiment(env);

    if (!experiment?.active) {
      // No active experiment — use base model directly
      const result = await (env.AI as any).run(
        "@cf/meta/llama-3.1-8b-instruct",
        { messages }
      ) as { response: string };
      return Response.json({ response: result.response, variant: "default" });
    }

    const variant = await assignVariant(env, userId, experiment);
    const inference = await runInference(
      env,
      experiment.model,
      messages,
      variant
    );

    // Fire-and-forget metric recording
    env.DB && recordOutcome(
      env,
      experiment.id,
      userId,
      variant.id,
      inference.latencyMs
    ).catch(console.error);

    return Response.json({
      response: inference.response,
      variant: inference.variantId,
      experimentId: experiment.id,
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Assigning variants randomly per request instead of per user — the same user will see different model behaviours
  across turns, producing noisy quality signals and a poor experience.
- Coupling experiment logic to Worker code rather than KV config — any change to traffic fractions then requires a
  new deployment, which also resets any cached experiment state.
- Measuring only latency — latency alone does not capture quality. Pair the experiment with a downstream quality
  signal (human rating, LLM-as-judge score, task completion) stored in the same D1 table.

## Gotchas

- Workers AI LoRA adapter IDs must be pre-uploaded via `wrangler ai finetune upload`. The `lora` parameter accepts
  the numeric ID returned by the upload command, not the human-readable name.
- Traffic fractions must sum exactly to 1.0 before being stored in KV. Add a validation step in your experiment
  management script; floating-point drift (e.g., three thirds) will cause the last variant to be under-assigned.
- The LoRA adapter must be compatible with the base model family and quantisation level deployed on Workers AI.
  Uploading a Mistral LoRA to a Llama binding silently produces garbage output.

## Verification

```bash
# Assign a set of user IDs and confirm ~50/50 split
for i in $(seq 1 100); do
  curl -s -X POST https://your-worker.workers.dev/ \
    -H "Content-Type: application/json" \
    -d "{\"userId\":\"user-$i\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}" \
    | jq -r '.variant'
done | sort | uniq -c
# Expected output: ~50 control, ~50 treatment

# Check D1 outcome table
wrangler d1 execute example project-db --command \
  "SELECT variant_id, COUNT(*) n, AVG(latency_ms) avg_ms FROM ab_outcomes GROUP BY variant_id"
```

## Related

- `ai-ml/workers-ai-lora-adapter-management.md`
- `ai-ml/llm-ab-testing.md`
- `ai-ml/llm-shadow-deployment.md`
- `ai-ml/ai-model-selection-workers-ai-inference.md`

## Sources

- https://developers.cloudflare.com/workers-ai/fine-tunes/loras/
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/kv/
