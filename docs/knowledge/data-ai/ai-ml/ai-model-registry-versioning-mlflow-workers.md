# AI Model Registry Versioning with MLflow and Workers AI

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Model Drift Without a Version Gate

Deploying a new fine-tuned model by overwriting a single endpoint URL is a recipe for
silent regression. Without a registry, there is no canonical answer to "which model was
serving traffic at 14:32 UTC on Tuesday?" — making rollbacks, audits, and A/B comparisons
impossible.

MLflow Model Registry provides a structured lifecycle: Staging → Production → Archived.
Pairing it with Workers AI and Cloudflare KV gives you a lightweight control plane:
Workers read the active model version from KV (updated by a Queue consumer reacting to
MLflow webhooks), so traffic routing changes propagate globally in seconds without a
code redeploy.

This architecture keeps the heavy ML tooling (MLflow, training infrastructure) entirely
off the critical request path. Workers AI serves inference; MLflow tracks lineage; KV
carries the routing signal; Queues decouple the transition webhook so it cannot block
production traffic.

## Context

- Model registry: MLflow (self-hosted or Databricks managed)
- Runtime: Cloudflare Workers (ESM)
- Inference: Workers AI (LoRA fine-tuned models via R2-backed adapters)
- Routing signal: Cloudflare KV
- Transition hooks: Cloudflare Queues
- Language: TypeScript + Python (MLflow webhook handler)

## MLflow Webhook → Queue Producer

MLflow fires HTTP webhooks on model version transitions. A lightweight Worker receives
the webhook and enqueues the event — never applying the change synchronously so the
webhook response cannot time out.

```ts
// src/mlflow-webhook.ts
export interface Env {
  MODEL_TRANSITION_QUEUE: Queue<ModelTransitionEvent>;
  MLFLOW_WEBHOOK_SECRET: string;
}

export interface ModelTransitionEvent {
  modelName: string;
  version: string;
  toStage: "Staging" | "Production" | "Archived";
  triggeredBy: string;
  timestamp: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Verify HMAC signature from MLflow
    const sig = request.headers.get("X-Mlflow-Signature") ?? "";
    const body = await request.text();
    const expected = await hmacSha256(env.MLFLOW_WEBHOOK_SECRET, body);
    if (!timingSafeEqual(sig, expected)) {
      return new Response("Unauthorized", { status: 401 });
    }

    const payload = JSON.parse(body) as {
      event_type: string;
      data: {
        name: string;
        version: string;
        to_stage: string;
        user_id: string;
      };
    };

    if (payload.event_type !== "MODEL_VERSION_TRANSITIONED_STAGE") {
      return new Response("ignored", { status: 200 });
    }

    const event: ModelTransitionEvent = {
      modelName: payload.data.name,
      version: payload.data.version,
      toStage: payload.data.to_stage as ModelTransitionEvent["toStage"],
      triggeredBy: payload.data.user_id,
      timestamp: Date.now(),
    };

    await env.MODEL_TRANSITION_QUEUE.send(event);
    return new Response("queued", { status: 202 });
  },
};

async function hmacSha256(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
```

## Queue Consumer: KV Routing Table Update

The consumer applies the transition to KV only when the stage is `Production`, recording
the previous version for instant rollback capability.

```ts
// src/model-transition-consumer.ts
export interface Env {
  MODEL_ROUTING_KV: KVNamespace;
  METRICS_DB: D1Database;
}

interface RoutingEntry {
  version: string;
  previousVersion: string | null;
  promotedAt: number;
  promotedBy: string;
}

export default {
  async queue(
    batch: MessageBatch<ModelTransitionEvent>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;

      if (event.toStage !== "Production") {
        // Record stage change in audit log but don't update routing
        await env.METRICS_DB.prepare(
          `INSERT INTO model_transitions
             (model_name, version, to_stage, triggered_by, ts)
           VALUES (?, ?, ?, ?, unixepoch())`
        )
          .bind(event.modelName, event.version, event.toStage, event.triggeredBy)
          .run();
        msg.ack();
        continue;
      }

      const kvKey = `model:routing:${event.modelName}`;
      const existing = await env.MODEL_ROUTING_KV.get<RoutingEntry>(kvKey, "json");

      const entry: RoutingEntry = {
        version: event.version,
        previousVersion: existing?.version ?? null,
        promotedAt: event.timestamp,
        promotedBy: event.triggeredBy,
      };

      await env.MODEL_ROUTING_KV.put(kvKey, JSON.stringify(entry), {
        metadata: { updatedAt: new Date(event.timestamp).toISOString() },
      });

      await env.METRICS_DB.prepare(
        `INSERT INTO model_transitions
           (model_name, version, to_stage, triggered_by, ts)
         VALUES (?, ?, 'Production', ?, unixepoch())`
      )
        .bind(event.modelName, event.version, event.triggeredBy)
        .run();

      msg.ack();
    }
  },
};
```

## Workers AI Inference with A/B Traffic Split

KV holds the canonical production version. A `abSplit` flag in KV lets operators send
a percentage of traffic to a canary version without touching the Queue pipeline.

```ts
// src/inference-worker.ts
export interface Env {
  AI: Ai;
  MODEL_ROUTING_KV: KVNamespace;
}

interface AbConfig {
  canaryVersion: string;
  canaryPercent: number; // 0–100
}

async function resolveModelVersion(
  modelName: string,
  env: Env
): Promise<string> {
  const [routing, abRaw] = await Promise.all([
    env.MODEL_ROUTING_KV.get<{ version: string }>(`model:routing:${modelName}`, "json"),
    env.MODEL_ROUTING_KV.get<AbConfig>(`model:ab:${modelName}`, "json"),
  ]);

  if (!routing) throw new Error(`No routing entry for model: ${modelName}`);

  if (abRaw && Math.random() * 100 < abRaw.canaryPercent) {
    return abRaw.canaryVersion;
  }

  return routing.version;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { modelName, prompt } = await request.json<{
      modelName: string;
      prompt: string;
    }>();

    const version = await resolveModelVersion(modelName, env);

    // Workers AI LoRA model ID format: @cf/account/model:version
    const modelId = `@cf/org/${modelName}:${version}` as Parameters<Ai["run"]>[0];

    const result = await env.AI.run(modelId, {
      messages: [{ role: "user", content: prompt }],
      max_tokens: 512,
    });

    return Response.json({
      response: (result as { response: string }).response,
      servedVersion: version,
    });
  },
};
```

## Anti-patterns

- Writing the KV routing entry synchronously inside the webhook handler — a slow KV
  write or timeout drops the transition silently.
- Using model version numbers as sequential integers without namespace — clashes across
  model names are inevitable in large registries.
- Sending A/B split percentage as part of each inference request — that lets callers
  manipulate which version they hit; keep the split config server-side in KV.
- Skipping the audit D1 write for non-Production transitions — Staging promotions are
  important lineage events even if they don't change live routing.

## Gotchas

- KV consistency is eventually consistent across regions; a promotion may take up to
  ~60 s to propagate globally — design canary rollouts to tolerate a brief mixed window.
- MLflow's webhook payload schema differs between OSS (v1) and Databricks (v2); validate
  the `event_type` field before assuming field names.
- Workers AI LoRA adapter IDs are account-scoped; a version string must map to an R2
  object path that has already been uploaded before the KV entry is written.
- Queue consumers run at-least-once; make the KV write idempotent by comparing the
  incoming version to the stored version before overwriting.

## Verification

```ts
// test/routing.test.ts
// Simulate a Production transition and assert KV is updated
const mockKV = new Map<string, string>();
const fakeEnv = {
  MODEL_ROUTING_KV: {
    get: async (k: string) => mockKV.get(k) ? JSON.parse(mockKV.get(k)!) : null,
    put: async (k: string, v: string) => { mockKV.set(k, v); },
  },
  METRICS_DB: { prepare: () => ({ bind: () => ({ run: async () => ({}) }) }) },
} as unknown as Env;

const event: ModelTransitionEvent = {
  modelName: "my-llm",
  version: "42",
  toStage: "Production",
  triggeredBy: "ci-bot",
  timestamp: Date.now(),
};

await handler.queue({ messages: [{ body: event, ack: () => {} }] }, fakeEnv);
const entry = JSON.parse(mockKV.get("model:routing:my-llm")!);
console.assert(entry.version === "42", "version mismatch");
console.log("routing test passed");
```

## Related

- [AI Feature Flag Patterns](ai-feature-flag-patterns.md)
- [AI Model Selection Workers AI Inference](ai-model-selection-workers-ai-inference.md)
- [AI Cost Monitoring](ai-cost-monitoring.md)
- [AI Evaluation Reproducibility](ai-evaluation-reproducibility-and-measurement-uncertainty.md)
- [Distillation Pipeline Local](distillation-pipeline-local.md)

## Sources

- https://mlflow.org/docs/latest/model-registry.html
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers-ai/
- https://mlflow.org/docs/latest/tracking.html#logging-to-a-remote-server
