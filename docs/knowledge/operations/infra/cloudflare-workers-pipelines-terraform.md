# Cloudflare Workers Pipelines Infrastructure as Code with Terraform

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to ingest high-volume event streams — frontend click events, server-side audit
logs, or IoT sensor readings — directly into Cloudflare R2 without running a separate
ingestion fleet. Cloudflare Pipelines lets a Worker (or HTTP clients) push batched
events that are durably buffered and written to an R2 bucket. When managing multiple
environments the resource must be declarative: manually creating pipelines through the
dashboard causes drift and cannot be reproduced reliably for staging vs. production.

## Context

Cloudflare Pipelines (GA, 2025) is an account-scoped resource that provides a
durable, ordered event buffer between producers and an R2 sink. Key properties:

- **Endpoint** – each pipeline gets a unique `https://<id>.pipelines.cloudflarepipelines.com`
  HTTPS URL for direct HTTP ingestion, _and_ a Workers binding for zero-latency writes.
- **Batch settings** – configurable `max_duration_seconds` and `max_mb` control how
  often the pipeline flushes to the R2 sink before emitting a new object.
- **Compression** – GZIP or none; recommended to enable for text-heavy payloads.
- **R2 sink path** – objects land at `<bucket>/<prefix>/<timestamp>-<uuid>.<ext>`.
- **Terraform resource** – `cloudflare_pipeline` (provider ≥ 4.40, requires
  `cloudflare:accountId`).

Pipelines are not zone-scoped; they live on the account and a Worker in any zone can
write to them.

## 1. Provider and Variable Setup

```hcl
# versions.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
  required_version = ">= 1.9"
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token" {
  description = "API token with Pipelines:Edit + R2:Edit + Workers:Edit permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "environment" {
  description = "Deployment environment: staging | production"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be 'staging' or 'production'."
  }
}
```

## 2. R2 Bucket for the Pipeline Sink

```hcl
# r2.tf
resource "cloudflare_r2_bucket" "events" {
  account_id = var.cloudflare_account_id
  name       = "events-${var.environment}"
  location   = "WEUR"
}
```

## 3. Pipeline Resource

```hcl
# pipeline.tf
resource "cloudflare_pipeline" "events" {
  account_id = var.cloudflare_account_id
  name       = "events-pipeline-${var.environment}"

  # R2 destination
  destination = {
    type   = "r2"
    format = "json"

    path = {
      bucket = cloudflare_r2_bucket.events.name
      prefix = "raw/"
      filename = "${!timestamp()}-${!uuid()}"
    }

    compression = {
      type = "gzip"
    }

    batch = {
      max_duration_seconds = var.environment == "production" ? 60 : 300
      max_mb               = var.environment == "production" ? 100 : 10
    }
  }
}
```

## 4. Worker that Writes to the Pipeline

```typescript
// src/index.ts
export interface Env {
  EVENTS_PIPELINE: Pipeline;
}

interface Pipeline {
  send(events: unknown[]): Promise<void>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json<unknown[]>();
    const events = Array.isArray(body) ? body : [body];

    // Validate and timestamp each event before writing
    const stamped = events.map((e) => ({
      ...(typeof e === "object" && e !== null ? e : { raw: e }),
      _ingestedAt: new Date().toISOString(),
    }));

    await env.EVENTS_PIPELINE.send(stamped);
    return new Response(JSON.stringify({ accepted: stamped.length }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## 5. Worker Script with Pipeline Binding in Terraform

```hcl
# worker.tf
resource "cloudflare_worker_script" "ingestor" {
  account_id = var.cloudflare_account_id
  name       = "event-ingestor-${var.environment}"
  content    = file("${path.module}/dist/index.js")
  module     = true

  pipeline_binding {
    name        = "EVENTS_PIPELINE"
    pipeline_id = cloudflare_pipeline.events.id
  }
}

resource "cloudflare_worker_route" "ingestor" {
  zone_id     = var.zone_id
  pattern     = "events.${var.domain}/ingest"
  script_name = cloudflare_worker_script.ingestor.name
}
```

## 6. Output the Pipeline Endpoint for HTTP Producers

```hcl
# outputs.tf
output "pipeline_endpoint" {
  description = "HTTPS endpoint for direct HTTP event ingestion (no Worker needed)"
  value       = cloudflare_pipeline.events.endpoint
}

output "pipeline_id" {
  description = "Pipeline ID — use as wrangler.toml pipeline_binding id"
  value       = cloudflare_pipeline.events.id
}

output "r2_bucket_name" {
  description = "R2 bucket receiving pipeline flushes"
  value       = cloudflare_r2_bucket.events.name
}
```

## Anti-patterns

- **Reusing a single pipeline across environments** — because pipelines are
  account-scoped, a bug in the staging Worker can inject corrupted records into the
  production R2 bucket if the binding points to the same pipeline. Always create
  separate pipeline resources per environment.
- **Setting `max_duration_seconds` too high in production** — a 10-minute flush
  interval means events could be lost if the pipeline is recreated or the account hits a
  limit. Keep production flush intervals under 2 minutes.
- **Skipping the `module = true` flag on the Worker** — pipeline bindings only work
  in ES module format Workers; a Service Worker format script silently ignores the
  binding and throws at runtime.
- **Writing unbounded arrays to the pipeline** — `send()` accepts up to 10,000 events
  in one call. Exceeding the limit returns a 413; batch client-side before calling.

## Gotchas

- `cloudflare_pipeline` does not support import of pipelines created via the dashboard
  in provider versions below 4.42; run `terraform import` only after upgrading.
- Destroying a pipeline does not destroy the R2 bucket or its contents. Add an explicit
  `depends_on` and lifecycle guard on the bucket when the bucket must follow the pipeline.
- The `filename` field in `destination.path` uses a Cloudflare expression, not HCL
  interpolation. Use `${!timestamp()}` (Cloudflare syntax), not `${timestamp()}` (HCL).
- Pipeline bindings do not appear in `wrangler.toml`'s standard section yet — add
  them under `[[pipelines]]` and keep the Terraform binding as the authoritative source.

## Verification

```bash
# Confirm pipeline is live
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pipelines" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].name'

# Send a test event via the pipeline HTTP endpoint
curl -s -X POST \
  "$(terraform output -raw pipeline_endpoint)" \
  -H "Content-Type: application/json" \
  -d '[{"test": true, "source": "terraform-verify"}]'

# Confirm an object landed in R2 within the flush window
wrangler r2 object list events-production --prefix raw/ --limit 5
```

## Related

- `cloudflare-r2-backup-restore-strategy.md` — lifecycle rules on the sink bucket
- `terraform-cloudflare-workers-runtime-version-management.md` — pinning the Worker runtime
- `pulumi-cloudflare-queue-consumer-worker-binding.md` — alternative pull-based queue pattern
- `workers-subrequest-budget-management.md` — pipeline send counts as a subrequest

## Sources

- Cloudflare Pipelines documentation: https://developers.cloudflare.com/pipelines/
- Terraform `cloudflare_pipeline` resource: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/pipeline
- Workers Pipelines binding reference: https://developers.cloudflare.com/workers/runtime-apis/bindings/pipelines/
