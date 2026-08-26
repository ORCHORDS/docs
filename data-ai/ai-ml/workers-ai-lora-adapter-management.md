# Workers AI LoRA Adapter Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You have fine-tuned a domain-specific LoRA adapter (customer support tone, legal
language, medical terminology) on top of a base model like `@cf/meta/llama-3.1-8b-instruct`
and need to serve it through Workers AI without managing dedicated GPU infrastructure.
Requests using the default base model return generic responses; adapter-augmented
inference must feel instant with no cold-start penalty between adapters.

## Context

Cloudflare Workers AI supports LoRA (Low-Rank Adaptation) adapter injection at
inference time for selected base models. You upload the adapter weights once via the
Workers AI REST API, then reference the adapter by name in each `run()` call. The
platform merges the adapter into the base model during inference with no extra latency
observable at the Worker level. Key constraints:

- Supported base models: `@cf/meta/llama-3.1-8b-instruct`, `@cf/mistral/mistral-7b-instruct-v0.1`
  and a growing set—always check the catalog.
- Adapter format: safetensors, rank ≤ 64, target modules must match the base model
  architecture.
- Max adapter size: 100 MB per upload.
- Adapter names are account-scoped; two Workers in the same account share the same
  adapter namespace.

## Uploading an Adapter

Use the Cloudflare REST API (or `wrangler ai finetune`) to register the adapter before
the Worker references it.

```bash
# Upload adapter weights via the fine-tunes API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/ai/finetunes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "@cf/meta/llama-3.1-8b-instruct",
    "name": "customer-support-v2",
    "description": "Support tone adapter, trained on 12k ticket pairs"
  }'
# Response contains { "result": { "finetune_id": "ft-abc123" } }

# Upload the safetensors file to the returned finetune_id
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/ai/finetunes/ft-abc123/finetune-assets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -F "file_name=adapter_model.safetensors" \
  -F "file=@./adapter_model.safetensors"

# List registered adapters
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/ai/finetunes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

Wrangler shorthand (equivalent):

```bash
wrangler ai finetune upload \
  --model "@cf/meta/llama-3.1-8b-instruct" \
  --name "customer-support-v2" \
  ./adapter_model.safetensors
```

## Invoking an Adapter from a Worker

Pass the `finetune` field inside the `run()` options object. The value is the adapter
name (not the `finetune_id`):

```typescript
// src/index.ts
interface Env {
  AI: Ai;
}

const ADAPTER_MAP: Record<string, string> = {
  support: "customer-support-v2",
  legal:   "legal-language-v1",
  default: "",           // empty string = base model, no adapter
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const domain = url.searchParams.get("domain") ?? "default";
    const userMessage = await request.text();

    const adapterName = ADAPTER_MAP[domain] ?? "";

    const runOptions: AiRunOptions = adapterName
      ? { finetune: adapterName }
      : {};

    const response = await env.AI.run(
      "@cf/meta/llama-3.1-8b-instruct",
      {
        messages: [
          {
            role: "system",
            content: "You are a helpful assistant.",
          },
          { role: "user", content: userMessage },
        ],
        max_tokens: 512,
        temperature: 0.3,
      },
      runOptions,
    );

    const text =
      typeof response === "object" && "response" in response
        ? (response as { response: string }).response
        : "";

    return new Response(text, {
      headers: { "Content-Type": "text/plain" },
    });
  },
};
```

```jsonc
// wrangler.jsonc
{
  "name": "lora-router",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" }
}
```

## Adapter Lifecycle and Versioning

Treat adapter versions the same as code versions. Use a naming convention that embeds
the semantic version and prevents accidental overwrites:

```typescript
// scripts/deploy-adapter.ts  (runs outside Workers, in CI)
import { execSync } from "node:child_process";

const VERSION = process.env.ADAPTER_VERSION ?? "0.0.0";
const MODEL   = "@cf/meta/llama-3.1-8b-instruct";
const NAME    = `customer-support-v${VERSION}`;

// Upload new adapter under versioned name
execSync(
  `wrangler ai finetune upload --model "${MODEL}" --name "${NAME}" ./adapter.safetensors`,
  { stdio: "inherit" },
);

// Write the active adapter name to KV so Workers pick it up without redeployment
execSync(
  `wrangler kv key put --binding ADAPTER_CONFIG "active_support_adapter" "${NAME}"`,
  { stdio: "inherit" },
);
```

Worker reads the active adapter name from KV, enabling instant rollback by writing the
previous version name back to KV:

```typescript
// Dynamic adapter resolution from KV
export default {
  async fetch(request: Request, env: Env & { ADAPTER_CONFIG: KVNamespace }): Promise<Response> {
    // Cached for 60 s to avoid KV read on every request
    const cacheKey = "active_support_adapter";
    const adapterName = await env.ADAPTER_CONFIG.get(cacheKey, {
      cacheTtl: 60,
    }) ?? "";

    const result = await env.AI.run(
      "@cf/meta/llama-3.1-8b-instruct",
      {
        messages: [{ role: "user", content: await request.text() }],
        max_tokens: 256,
      },
      adapterName ? { finetune: adapterName } : {},
    );

    return Response.json(result);
  },
};
```

Rollback: write the previous adapter name to KV; propagates within 60 seconds via
`cacheTtl`. No Worker redeployment needed.

## Anti-patterns

- **Hard-coding adapter names in Worker source**: prevents zero-downtime rollback. Use
  KV or environment variables with versioned names.
- **Reusing the same adapter name for new weights**: the platform may cache the old
  weights. Always use a new name (e.g., append a version suffix) when uploading
  updated weights.
- **Uploading PyTorch `.bin` files directly**: only safetensors are accepted. Convert
  with `python -c "from transformers import ...; model.save_pretrained('out', safe_serialization=True)"`.
- **Using adapters across incompatible base model versions**: if Cloudflare updates the
  base model weights, a previously working adapter may produce degraded output. Pin the
  base model version in the `run()` call once stable aliases are available.
- **Running adapter inference in the free tier at high concurrency**: adapter injection
  adds minimal per-token overhead but does consume more GPU memory than bare base model
  inference. Monitor costs via AI Gateway analytics.

## Gotchas

- **Adapter availability lag**: after upload, the adapter may take 30–120 seconds to
  propagate to all inference nodes. The first few requests during that window may fall
  back to the base model silently. Add a readiness probe in CI before switching KV.
- **`finetune` option silently ignored on unsupported models**: if you pass `finetune`
  to a model that does not support LoRA injection, Workers AI ignores the option and
  runs the base model. Validate the model catalog before referencing an adapter.
- **Adapter name case-sensitivity**: adapter names are case-sensitive. `Customer-Support-v2`
  and `customer-support-v2` are different adapters.
- **No streaming + adapter on some base models**: check the catalog; streaming is
  supported for most but not all LoRA-compatible models.
- **KV `cacheTtl` and stale-while-revalidate**: `cacheTtl` on KV `get()` means the
  Worker may use a stale adapter name for up to that many seconds after a KV write.
  Set it low (10–30 s) during active rollouts.

## Verification

```bash
# 1. Confirm adapter is listed
wrangler ai finetune list | grep "customer-support-v2"

# 2. Smoke-test adapter inference end-to-end
curl -s https://my-worker.example.workers.dev/?domain=support \
  -d "My order never arrived and I am frustrated." | jq .

# 3. Compare base model vs adapter output
wrangler ai run @cf/meta/llama-3.1-8b-instruct \
  --prompt "My order never arrived and I am frustrated."

# 4. Check AI Gateway logs to confirm finetune field is captured
wrangler ai gateway logs --gateway my-gateway | grep "customer-support"

# 5. Rollback test: write previous adapter name to KV and re-request within 60s
wrangler kv key put --binding ADAPTER_CONFIG \
  "active_support_adapter" "customer-support-v1"
curl -s https://my-worker.example.workers.dev/?domain=support \
  -d "Test message for rollback validation"
```

## Related

- `fine-tuning-data-preparation.md`
- `fine-tuning-when-to-use.md`
- `lora-qlora-parameter-efficient-finetuning.md`
- `workers-ai-function-calling-agentic-patterns.md`
- `model-versioning-strategy.md`
- `prompt-versioning.md`

## Sources

- Cloudflare Workers AI LoRA fine-tunes docs: https://developers.cloudflare.com/workers-ai/fine-tunes/
- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- `wrangler ai` CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#ai
- HuggingFace safetensors format: https://huggingface.co/docs/safetensors/index
