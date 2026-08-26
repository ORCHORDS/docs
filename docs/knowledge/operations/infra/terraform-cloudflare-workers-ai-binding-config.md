# Terraform Cloudflare Workers AI Binding Config

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project platform (example.com) needs to run on-device content moderation, embedding generation,
and toxicity classification at the edge without round-tripping to a centralised ML API. Hardcoding
API tokens inside Worker bundles creates rotation headaches and surface area for credential leaks.
Terraform should own the binding lifecycle so Workers access AI models as first-class environment
resources rather than authenticated HTTP calls.

## Context

Cloudflare Workers AI exposes GPU-backed inference models (text classification, embeddings,
image labelling, LLMs) via the `AI` binding injected into a Worker's execution context.
The Cloudflare Terraform provider (`cloudflare/cloudflare` ≥ 4.40) surfaces this through the
`ai_binding` block inside `cloudflare_worker_script`, enabling IaC-driven binding management.
No separate `cloudflare_workers_ai` resource exists; the binding is an attribute of the script.

## Resource Definition — cloudflare_worker_script with ai_binding

Each Worker that needs model access declares an `ai_binding` block. The `name` becomes the
JavaScript global identifier inside the Worker (e.g. `env.AI`). Multiple bindings are allowed
but Cloudflare enforces one Workers AI binding per script in most plan tiers.

```hcl
resource "cloudflare_worker_script" "moderation" {
  account_id = var.cloudflare_account_id
  name       = "example project-content-moderation"
  content    = file("${path.module}/dist/moderation.js")

  ai_binding {
    name = "AI"
  }

  # Optional: restrict which routes trigger this worker
  plain_text_binding {
    name  = "ENVIRONMENT"
    text  = var.environment
  }

  compatibility_date = "2025-09-01"
}
```

Inside the Worker (`moderation.js`) the binding is accessed as:

```javascript
export default {
  async fetch(request, env) {
    const { results } = await env.AI.run(
      "@cf/meta/llama-guard-3-8b",
      { messages: [{ role: "user", content: await request.text() }] }
    );
    return Response.json(results);
  }
};
```

## Configuration — Variable Inputs and Model Selection

Model identifiers are not part of the binding declaration; they are passed at runtime as Worker
code constants or KV-backed config. Externalise the model slug so it can be updated without
re-provisioning the binding.

```hcl
variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID that owns the Workers AI entitlement"
}

variable "environment" {
  type    = string
  default = "production"
}

locals {
  moderation_models = {
    production = "@cf/meta/llama-guard-3-8b"
    staging    = "@cf/huggingface/distilbert-sst-2-int8"
  }
}

resource "cloudflare_worker_script" "embedding" {
  account_id = var.cloudflare_account_id
  name       = "example project-embedding-generator"
  content    = templatefile("${path.module}/dist/embedding.js", {
    model = local.moderation_models[var.environment]
  })

  ai_binding {
    name = "AI"
  }

  compatibility_date = "2025-09-01"
}
```

`templatefile` injects the model slug as a JS constant at bundle time, keeping the Terraform
state free of model-selection logic that belongs in code.

## CI Integration — GitHub Actions Plan + Apply

Workers AI bindings carry no separate secret; the binding itself acts as the credential. Gate
deployment behind a plan review step so accidental model changes surface before apply.

```yaml
# .github/workflows/workers-ai-deploy.yml
name: Deploy Workers AI Scripts

on:
  push:
    branches: [main]
    paths:
      - "infra/workers-ai/**"
      - "workers/moderation/**"

jobs:
  plan:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Build Worker bundle
        run: |
          cd workers/moderation
          npm ci
          npm run build          # outputs dist/moderation.js

      - name: Terraform Init
        run: terraform -chdir=infra/workers-ai init
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Terraform Plan
        run: terraform -chdir=infra/workers-ai plan -out=tfplan
        env:
          TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}
          TF_VAR_environment: production

      - uses: actions/upload-artifact@v4
        with:
          name: tfplan
          path: infra/workers-ai/tfplan

  apply:
    needs: plan
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: tfplan
          path: infra/workers-ai/

      - name: Terraform Apply
        run: terraform -chdir=infra/workers-ai apply tfplan
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Outputs and Downstream Bindings

Export the Worker script name so downstream resources (e.g., routes, KV namespace bindings)
can reference it without hardcoding.

```hcl
output "moderation_worker_name" {
  value       = cloudflare_worker_script.moderation.name
  description = "Script name for route and service binding references"
}

# Attach to a zone route
resource "cloudflare_worker_route" "moderation_route" {
  zone_id     = var.cloudflare_zone_id
  pattern     = "example.com/api/moderate*"
  script_name = cloudflare_worker_script.moderation.name
}
```

## Anti-patterns

- Storing Cloudflare API tokens inside the Worker bundle to call the AI REST API — use the
  `ai_binding` instead; the binding requires no token and is scoped to the account automatically.
- Using `content = file(...)` pointing at a non-built source file — always build/minify first
  or Terraform will deploy raw TypeScript which Workers cannot parse.
- Omitting `compatibility_date` — without it Workers run on a legacy flag set that may lack
  the AI binding runtime APIs.
- Hardcoding model slugs in HCL — model names change; put them in the Worker code or a KV
  config store.
- Creating one giant Worker with all AI tasks — keep moderation, embedding, and classification
  as separate scripts to stay within CPU/memory limits per invocation.

## Gotchas

- The `ai_binding` block name is case-sensitive and must match the JavaScript identifier exactly
  (`"AI"` ≠ `"ai"`).
- Workers AI usage is billed per neuron (not per invocation). The Terraform plan will never
  show cost impact — monitor via Workers AI Analytics in the dashboard.
- Uploading a new `content` always triggers a Worker script update even if only the AI binding
  changed; Cloudflare re-deploys the full script.
- `cloudflare_worker_script` does not diff `content` semantically — a whitespace-only change
  in the JS bundle causes an unnecessary deploy.
- Free plans include a limited Workers AI quota; staging and production should share a paid
  account or use separate accounts with separate tokens.

## Verification

```bash
# Confirm binding is present in deployed script metadata
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/example project-content-moderation/bindings" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.type=="ai")'

# Smoke-test the Worker endpoint
curl -s -X POST https://example.com/api/moderate \
  -H "Content-Type: text/plain" \
  --data "test post content" | jq .
```

Expected binding response includes `"type": "ai"` and `"name": "AI"`.

## Related

- `cloudflare-workers-ai-edge-inference.md` — runtime usage patterns for Workers AI models
- `terraform-cloudflare-workers-secrets-sensitive.md` — managing secrets alongside AI bindings
- `terraform-cloudflare-provider-workers-d1.md` — pairing AI inference results with D1 storage
- `cloudflare-workers-kv-namespace-terraform.md` — externalising model config via KV

## Sources

- https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_script
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
