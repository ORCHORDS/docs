# Pulumi Cloudflare Workers AI Binding Config

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to run AI inference at the edge — text generation, embeddings, image classification, speech-to-text — inside a Cloudflare Worker without managing GPU infrastructure. The binding configuration needs to be reproducible across environments and managed as code alongside the rest of your Cloudflare stack.

## Context

Cloudflare Workers AI exposes a `cloudflare.WorkersAI` binding that gives Workers scripts access to a curated catalogue of models (Llama, Mistral, Whisper, CLIP, etc.) running on Cloudflare's GPU fleet. The binding is declared in the Worker script's `bindings` array as type `"ai"` and accessed at runtime via `env.AI.run(modelName, inputs)`. In Pulumi TypeScript (provider ≥ 5.x), the AI binding is specified inside the `cloudflare.WorkerScript` resource's `aiBinding` block — no separate resource is needed. Workers AI requests are billed per neuron (inference unit) and the binding is always account-scoped.

---

## Provider and Project Setup

```typescript
// package.json (relevant deps)
// "@pulumi/cloudflare": "^5.4.0"
// "@pulumi/pulumi": "^3.x"

import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import * as fs from "fs";

const config = new pulumi.Config();
const accountId = config.requireSecret("cloudflareAccountId");
const zoneId = config.require("cloudflareZoneId");
```

## Worker Script with AI Binding

```typescript
// worker-ai.ts

const workerCode = fs.readFileSync("./src/worker.ts", "utf-8");

const aiWorker = new cloudflare.WorkerScript("ai-inference-worker", {
  accountId: accountId,
  name: "ai-inference-worker",
  content: workerCode,
  module: true,  // ES Module format — required for AI binding

  // AI binding — exposes env.AI in the worker
  aiBindings: [
    {
      name: "AI",  // accessed as env.AI in the worker
    },
  ],

  // Optional: KV for caching inference results
  kvNamespaceBindings: [
    {
      name: "INFERENCE_CACHE",
      namespaceId: inferenceCache.id,
    },
  ],
});
```

## Worker Runtime Code (TypeScript)

```typescript
// src/worker.ts
interface Env {
  AI: Ai;
  INFERENCE_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/generate" && request.method === "POST") {
      const { prompt, stream } = await request.json<{ prompt: string; stream?: boolean }>();

      if (stream) {
        // Streaming text generation
        const aiStream = await env.AI.run(
          "@cf/meta/llama-3.1-8b-instruct",
          { prompt, stream: true }
        ) as ReadableStream;

        return new Response(aiStream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }

      const result = await env.AI.run(
        "@cf/meta/llama-3.1-8b-instruct",
        { prompt }
      ) as { response: string };

      return Response.json({ text: result.response });
    }

    if (path === "/embed" && request.method === "POST") {
      const { text } = await request.json<{ text: string | string[] }>();
      const result = await env.AI.run(
        "@cf/baai/bge-base-en-v1.5",
        { text: Array.isArray(text) ? text : [text] }
      ) as { data: number[][] };

      return Response.json({ embeddings: result.data });
    }

    if (path === "/classify-image" && request.method === "POST") {
      const arrayBuffer = await request.arrayBuffer();
      const result = await env.AI.run(
        "@cf/microsoft/resnet-50",
        { image: [...new Uint8Array(arrayBuffer)] }
      ) as Array<{ label: string; score: number }>;

      return Response.json({ classifications: result });
    }

    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Multi-model Worker with KV Cache

```typescript
// Full Pulumi config with KV cache and AI binding
const inferenceCache = new cloudflare.WorkersKvNamespace("inference-cache", {
  accountId: accountId,
  title: "inference-cache",
});

const multiModelWorker = new cloudflare.WorkerScript("multi-model-worker", {
  accountId: accountId,
  name: "multi-model-worker",
  content: fs.readFileSync("./src/multi-model.ts", "utf-8"),
  module: true,

  aiBindings: [{ name: "AI" }],

  kvNamespaceBindings: [
    {
      name: "INFERENCE_CACHE",
      namespaceId: inferenceCache.id,
    },
  ],

  // Environment variable for cache TTL
  plainTextBindings: [
    { name: "CACHE_TTL_SECONDS", text: "3600" },
  ],
});
```

## Worker Route and Custom Domain

```typescript
// Route the AI worker to a specific path
const aiWorkerRoute = new cloudflare.WorkerRoute("ai-worker-route", {
  zoneId: zoneId,
  pattern: "api.example.com/ai/*",
  scriptName: aiWorker.name,
});

// Or a Workers subdomain (workers.dev)
const subdomain = new cloudflare.WorkersDomain("ai-worker-domain", {
  accountId: accountId,
  hostname: "ai-api.example.com",
  zoneId: zoneId,
  service: aiWorker.name,
});

export const workerName = aiWorker.name;
export const workerRoute = aiWorkerRoute.pattern;
```

## Model Catalog Reference as Pulumi Config

```typescript
// config.ts — model IDs as typed constants to avoid typos
export const MODELS = {
  // Text generation
  llama31_8b: "@cf/meta/llama-3.1-8b-instruct",
  llama31_70b: "@cf/meta/llama-3.1-70b-instruct",
  mistral7b: "@cf/mistral/mistral-7b-instruct-v0.1",

  // Embeddings
  bgeBaseEn: "@cf/baai/bge-base-en-v1.5",
  bgeLargeEn: "@cf/baai/bge-large-en-v1.5",

  // Image classification
  resnet50: "@cf/microsoft/resnet-50",

  // Speech-to-text
  whisperTiny: "@cf/openai/whisper-tiny-en",

  // Translation
  m2m100: "@cf/meta/m2m100-1.2b",
} as const;

// Inject as Worker binding so the Worker can reference at runtime
const modelConfigWorker = new cloudflare.WorkerScript("model-config-worker", {
  accountId: accountId,
  name: "model-config-worker",
  content: fs.readFileSync("./src/worker.ts", "utf-8"),
  module: true,

  aiBindings: [{ name: "AI" }],

  plainTextBindings: [
    { name: "DEFAULT_TEXT_MODEL", text: MODELS.llama31_8b },
    { name: "DEFAULT_EMBED_MODEL", text: MODELS.bgeBaseEn },
  ],
});
```

---

## Anti-patterns

- **Calling `env.AI.run()` on every request without caching**: LLM inference is expensive in latency and neurons. Cache deterministic inputs (summarisation, classification) in KV with the prompt as the key.
- **Using a single large model for all tasks**: Run embeddings with `bge-base-en-v1.5` and classification with `resnet-50` rather than routing everything through a 70B model.
- **Hardcoding model IDs in worker source code**: Model IDs change when Cloudflare updates the catalogue. Store them as `plainTextBindings` or Worker secrets so you can update without redeploying source.
- **Ignoring the 10 ms CPU time limit on non-Unbound Workers**: AI inference runs off-CPU on Cloudflare's GPU fleet, but parsing and post-processing the response does count against your CPU budget. Use `module: true` and `compatibilityFlags: ["nodejs_compat"]` to avoid hitting limits.
- **Not setting `module: true`**: AI bindings require ES Module format. Service Worker format (`module: false`) does not support the `aiBindings` block.

## Gotchas

- The `aiBindings` block has a single required field: `name`. There is no `modelName` field — the model is chosen at runtime in `env.AI.run(modelName, ...)`.
- Workers AI is an account-level resource; you cannot restrict a binding to a specific zone.
- Free tier Workers AI requests are rate-limited; production workloads require a Workers Paid plan. Check `@cf/meta/llama-3.1-70b-instruct` — it is only available on certain plans.
- Streaming responses (`stream: true`) return a `ReadableStream`; you must pass it directly to the `Response` constructor. Awaiting it fully defeats the purpose.
- The AI binding does not appear as a separate Pulumi resource — it is embedded in the `WorkerScript` resource. Changing `aiBindings[].name` triggers a Worker redeploy.

## Verification

```bash
# Deploy with Pulumi
pulumi up --stack prod

# Test text generation endpoint
curl -s -X POST https://ai-api.example.com/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}' | jq '.text'

# Test embeddings endpoint
curl -s -X POST https://ai-api.example.com/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}' | jq '.embeddings | length'

# Confirm binding is present in Cloudflare API
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/ai-inference-worker/bindings" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | select(.type == "ai")'
```

## Related

- `terraform-cloudflare-workers-ai-binding-config.md`
- `pulumi-cloudflare-workers-infrastructure-as-code.md`
- `cloudflare-workers-ai-edge-inference.md`
- `workers-cold-start-bundle-size-optimization.md`

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/api-docs/workerscript/
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/ai-binding/
