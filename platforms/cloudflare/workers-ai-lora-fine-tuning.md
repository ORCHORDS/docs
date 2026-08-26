# Workers AI LoRA Fine-Tuning

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A generic foundation model (e.g., Llama 3.1 8B) produces off-brand output because it was not trained on your product vocabulary or writing style. Full fine-tuning is cost-prohibitive and requires shipping a new model checkpoint. You want to apply lightweight domain adaptation that can be loaded on-the-fly at inference time without switching base model weights, and you want inference to run in Cloudflare's global edge network — not a single-region GPU cluster.

## Context

LoRA (Low-Rank Adaptation) is a parameter-efficient fine-tuning technique. Instead of updating all model weights, LoRA freezes the original weights and injects small trainable rank-decomposition matrices (the "adapter") into the attention layers. The resulting adapter file is orders of magnitude smaller than the full model (typically 10–200 MB vs. 4–14 GB for the base model).

Workers AI supports LoRA adapters for a subset of supported base models. The workflow is:

1. **Train** the LoRA adapter offline (Hugging Face `peft`, `axolotl`, or similar)
2. **Upload** the adapter to Cloudflare's model storage via the Finetunes API
3. **Reference** the adapter by name/ID at inference time in `ai.run()`
4. Cloudflare merges adapter weights into the base model on the inference GPU at request time

This means you pay for base model hosting once; each adapter is a small delta loaded at inference time. Multiple adapters for the same base model can be hot-swapped per request.

## Supported Base Models (as of 2026)

| Model | Context | Quantization |
|---|---|---|
| `@cf/meta/llama-3.1-8b-instruct` | 128k | int8 |
| `@cf/meta/llama-3.2-3b-instruct` | 128k | int8 |
| `@cf/mistral/mistral-7b-instruct-v0.2-lora` | 32k | int4/int8 |
| `@cf/google/gemma-7b-it-lora` | 8k | int4 |

Check `https://developers.cloudflare.com/workers-ai/models/` for the current list — models are added regularly. Only models with `-lora` suffix or that list `lora` in their properties support adapter injection.

## Training a LoRA Adapter (Offline)

```python
# train_lora.py — run on your own GPU or a cloud GPU instance
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, TaskType
from datasets import load_dataset
import transformers, torch

model_id = "meta-llama/Meta-Llama-3.1-8B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_id)

bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb_config)

lora_config = LoraConfig(
    r=16,                     # rank — higher = more capacity, larger adapter file
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],  # inject into attention Q and V
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# trainable params: 6,815,744 || all params: 8,037,531,648 || trainable%: 0.08%

# ... train on your dataset ...
model.save_pretrained("./my-lora-adapter")
# Produces: adapter_config.json + adapter_model.safetensors
```

The output of `save_pretrained` is a directory containing:
- `adapter_config.json` — LoRA hyperparameters
- `adapter_model.safetensors` — the trainable weights (~50 MB for r=16)

## Uploading the Adapter to Workers AI

```bash
# 1. Create a finetune entry
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/finetunes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "@cf/meta/llama-3.1-8b-instruct",
    "name": "my-product-lora",
    "description": "Domain adaptation for product docs Q&A"
  }'
# Save the returned "id" as FINETUNE_ID

# 2. Upload adapter_config.json
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/finetunes/${FINETUNE_ID}/finetune-assets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -F "file_name=adapter_config.json" \
  -F "file=@./my-lora-adapter/adapter_config.json"

# 3. Upload adapter_model.safetensors
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/finetunes/${FINETUNE_ID}/finetune-assets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -F "file_name=adapter_model.safetensors" \
  -F "file=@./my-lora-adapter/adapter_model.safetensors"
```

## Using the Adapter in a Worker

```typescript
// src/index.ts
export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { question } = await request.json<{ question: string }>();

    const messages: RoleScopedChatInput[] = [
      {
        role: 'system',
        content:
          'You are a helpful assistant for Acme Corp product documentation. ' +
          'Answer questions using Acme-specific terminology.',
      },
      { role: 'user', content: question },
    ];

    const result = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      {
        messages,
        // Reference the adapter by its finetune ID
        lora: 'FINETUNE_ID_HERE',
        max_tokens: 512,
        temperature: 0.3,
      },
    );

    return Response.json({ answer: (result as { response: string }).response });
  },
} satisfies ExportedHandler<Env>;
```

`wrangler.toml`:
```toml
name = "product-qa"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"
```

## Streaming with LoRA

LoRA adapters are fully compatible with streaming inference:

```typescript
const stream = await env.AI.run(
  '@cf/meta/llama-3.1-8b-instruct',
  {
    messages,
    lora: 'FINETUNE_ID_HERE',
    stream: true,
    max_tokens: 1024,
  },
);

// stream is a ReadableStream of SSE chunks
return new Response(stream, {
  headers: {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
  },
});
```

## Listing and Managing Finetunes

```bash
# List all uploaded finetunes for an account
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/finetunes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {id, name, model, created_at}'

# Delete a finetune
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/finetunes/${FINETUNE_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

## Local Testing with Wrangler

```bash
# Run locally — the adapter is fetched from Cloudflare's servers even in local dev
wrangler dev --remote

# Or test via curl against local dev server
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the Acme Corp refund policy?"}'
```

> Local development (`wrangler dev` without `--remote`) does not support LoRA adapters because the local AI simulation does not download model weights. Always use `--remote` for LoRA testing.

## Anti-patterns

- **Using a LoRA adapter with a base model it was not trained on** — adapter weight shapes must match the base model's attention dimensions exactly. Mismatches produce garbled output or runtime errors.
- **Setting `r` (rank) higher than needed** — r=64 produces a ~200 MB adapter and slower merge at inference time; r=8 or r=16 is sufficient for domain adaptation. Match rank to task complexity.
- **Uploading `adapter_model.bin` (PyTorch format) instead of `.safetensors`** — Workers AI requires the `.safetensors` format. Convert with `peft`'s `save_pretrained()` which now defaults to safetensors, or convert manually with `safetensors-convert`.
- **Hardcoding the finetune ID in Worker code** — store it in a Worker secret or environment variable so adapter rollouts don't require code deploys.
- **Fine-tuning on private PII and uploading to Cloudflare** — adapter weights can memorize training data. Ensure training data is scrubbed or anonymized before training any adapter you upload to a third-party service.

## Gotchas

- The finetune ID is account-scoped, not zone-scoped. Any Worker in the account can reference it by ID.
- Adapter loading adds latency to the first request on a cold GPU; subsequent requests on a warm worker with the same adapter are unaffected.
- Workers AI currently does not support multiple LoRA adapters stacked on a single inference call. Each `ai.run()` call can reference at most one `lora` ID.
- There is no automatic model version pinning for LoRA adapters. If Cloudflare updates the base model weights behind the same model name, adapter compatibility is not guaranteed. Pin to a versioned model slug when stability is critical.
- The `@cf/mistral/mistral-7b-instruct-v0.2-lora` model ID explicitly indicates LoRA support in its name; other models must be verified in the documentation as the support matrix changes.
- Adapter training in int4/int8 quantized space (QLoRA) is supported; however, uploading a QLoRA adapter trained against a different quantization than the deployed model may degrade quality.

## Verification

```bash
# Confirm finetune assets were uploaded
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/ai/finetunes/${FINETUNE_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result.files_uploaded'

# Test inference with the adapter
curl -X POST https://product-qa.example.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I reset my Acme account password?"}' \
  | jq '.answer'

# Compare adapter output vs base model output by temporarily removing the lora param
```

## Related

- `workers-ai-2026.md` — Workers AI capabilities overview
- `workers-ai-edge-inference.md` — base model inference patterns
- `workers-ai-inference-gateway.md` — AI Gateway for logging and caching AI requests
- `ai-gateway-best-practices.md` — cost control, prompt caching, fallback routing

## Sources

- https://developers.cloudflare.com/workers-ai/fine-tunes/lora/
- https://developers.cloudflare.com/workers-ai/fine-tunes/
- https://developers.cloudflare.com/api/resources/ai/subresources/finetunes/
- https://huggingface.co/docs/peft/index
- https://developers.cloudflare.com/workers-ai/models/
