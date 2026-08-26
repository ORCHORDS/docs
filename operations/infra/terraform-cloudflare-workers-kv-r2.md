# Terraform for Cloudflare Workers, KV Namespaces, and R2 Buckets

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your team manages multiple Cloudflare Workers with associated KV namespaces, R2 buckets, and scheduled cron triggers across staging and production environments. Manual dashboard changes lead to configuration drift, untracked secrets, and deployment inconsistencies between environments. You need Infrastructure-as-Code to make every resource declarative, reviewable, and promotable through environments.

---

## Context
The `cloudflare/cloudflare` Terraform provider (v4+) covers Workers scripts, KV namespaces, R2 buckets, and cron triggers as first-class resources. Terraform Cloud (or HCP Terraform) stores remote state per workspace, enabling separate `staging` and `production` workspaces that share module code but differ in variable values. The Worker script content is read from the local build artifact so that `wrangler build` produces the bundle and Terraform uploads it — keeping Wrangler as the build tool and Terraform as the infrastructure manager. Environment-specific workspaces allow `terraform workspace select staging` before a plan, ensuring no cross-environment blast radius.

---

## Section 1 — Provider and Backend Config

```hcl
# terraform/versions.tf
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }

  backend "remote" {
    organization = "orchords"
    workspaces {
      # Workspace names: "workers-staging", "workers-production"
      prefix = "workers-"
    }
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

```hcl
# terraform/variables.tf
variable "cloudflare_api_token" {
  description = "Cloudflare API token with Workers, KV, R2, and Zone permissions"
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the target domain"
}

variable "environment" {
  description = "Deployment environment: staging or production"
  default     = "staging"
}

variable "worker_name" {
  description = "Name of the Worker script"
  default     = "orchords-api"
}
```

## Section 2 — Worker, KV, R2, and Cron Resources

```hcl
# terraform/main.tf

# ── KV Namespaces ──────────────────────────────────────────────────────────────
resource "cloudflare_workers_kv_namespace" "cache" {
  account_id = var.cloudflare_account_id
  title      = "${var.worker_name}-cache-${var.environment}"
}

resource "cloudflare_workers_kv_namespace" "sessions" {
  account_id = var.cloudflare_account_id
  title      = "${var.worker_name}-sessions-${var.environment}"
}

# ── R2 Buckets ─────────────────────────────────────────────────────────────────
resource "cloudflare_r2_bucket" "assets" {
  account_id = var.cloudflare_account_id
  name       = "${var.worker_name}-assets-${var.environment}"
  location   = "WEUR" # Western Europe; omit for automatic placement
}

resource "cloudflare_r2_bucket" "uploads" {
  account_id = var.cloudflare_account_id
  name       = "${var.worker_name}-uploads-${var.environment}"
  location   = "WEUR"
}

# ── Worker Script ──────────────────────────────────────────────────────────────
# Build the Worker before running terraform apply:
#   wrangler build --outdir=dist
resource "cloudflare_worker_script" "api" {
  account_id = var.cloudflare_account_id
  name       = "${var.worker_name}-${var.environment}"
  content    = file("${path.module}/../dist/index.js")

  kv_namespace_binding {
    name         = "CACHE_KV"
    namespace_id = cloudflare_workers_kv_namespace.cache.id
  }

  kv_namespace_binding {
    name         = "SESSIONS_KV"
    namespace_id = cloudflare_workers_kv_namespace.sessions.id
  }

  r2_bucket_binding {
    name        = "ASSETS_BUCKET"
    bucket_name = cloudflare_r2_bucket.assets.name
  }

  r2_bucket_binding {
    name        = "UPLOADS_BUCKET"
    bucket_name = cloudflare_r2_bucket.uploads.name
  }

  plain_text_binding {
    name = "ENVIRONMENT"
    text = var.environment
  }

  secret_text_binding {
    name = "API_SECRET"
    # Set TF_VAR_api_secret in CI or Terraform Cloud variable set
    text = var.api_secret
  }
}

variable "api_secret" {
  description = "API secret injected as Worker secret binding"
  sensitive   = true
}

# ── Cron Trigger ───────────────────────────────────────────────────────────────
resource "cloudflare_worker_cron_trigger" "cleanup" {
  account_id  = var.cloudflare_account_id
  script_name = cloudflare_worker_script.api.name
  schedules   = ["0 3 * * *"] # daily at 03:00 UTC
}

# ── Outputs ────────────────────────────────────────────────────────────────────
output "cache_kv_id" {
  value = cloudflare_workers_kv_namespace.cache.id
}

output "assets_bucket_name" {
  value = cloudflare_r2_bucket.assets.name
}

output "worker_script_name" {
  value = cloudflare_worker_script.api.name
}
```

## Section 3 — CI/CD and Workspace Workflow

```bash
# ── Initial setup ──────────────────────────────────────────────────────────────
cd terraform
terraform init   # connects to Terraform Cloud remote backend

# ── Staging deploy ─────────────────────────────────────────────────────────────
export TF_WORKSPACE=workers-staging
export TF_VAR_cloudflare_api_token="$CF_API_TOKEN"
export TF_VAR_cloudflare_account_id="$CF_ACCOUNT_ID"
export TF_VAR_cloudflare_zone_id="$CF_ZONE_ID"
export TF_VAR_environment="staging"
export TF_VAR_api_secret="$STAGING_API_SECRET"

# Build Worker bundle first
npx wrangler build --outdir=dist

terraform plan  -out=staging.tfplan
terraform apply staging.tfplan

# ── Production deploy ──────────────────────────────────────────────────────────
export TF_WORKSPACE=workers-production
export TF_VAR_environment="production"
export TF_VAR_api_secret="$PROD_API_SECRET"

terraform plan  -out=prod.tfplan
terraform apply prod.tfplan

# ── Drift detection (run in CI on schedule) ────────────────────────────────────
terraform plan -detailed-exitcode 2>&1 | tee plan.out
# Exit code 2 means drift detected — alert or auto-apply depending on policy

# ── Import an existing KV namespace created outside Terraform ──────────────────
terraform import \
  cloudflare_workers_kv_namespace.cache \
  "$CF_ACCOUNT_ID/<existing-namespace-id>"
```

---

## Anti-patterns
- **Storing `cloudflare_api_token` in terraform.tfvars committed to git** — use Terraform Cloud variable sets or CI environment variables marked as sensitive.
- **Using a single workspace for all environments** — a failed staging plan blocks production; keep them in separate workspaces.
- **Uploading the Worker bundle with `wrangler deploy` and managing bindings with Terraform** — let Terraform own the full resource including bindings; mixing tools causes drift.
- **Omitting the `location` on R2 buckets** — without it Cloudflare uses automatic placement, which may differ between runs and cause resource recreation.

---

## Gotchas
- The `cloudflare_worker_script` resource replaces the script on every `apply` if `content` changes — this is expected but causes a brief cold-start window.
- Terraform Cloud free tier limits to 500 managed resources; R2 buckets and KV namespaces each count as one resource.
- `secret_text_binding` values are write-only in the Terraform state — Terraform cannot detect if the secret was rotated outside Terraform, so drift detection will not flag it.
- R2 bucket names must be globally unique per account and follow DNS label rules (lowercase, hyphens, max 63 chars).
- `cloudflare_worker_cron_trigger` requires the script to already exist; it must depend on `cloudflare_worker_script` (Terraform resolves this automatically via the reference).

---

## Verification

```bash
# List all managed resources in the current workspace
terraform state list

# Show the KV namespace resource details
terraform state show cloudflare_workers_kv_namespace.cache

# Confirm the cron trigger was registered
wrangler triggers list --name "${WORKER_NAME}-${ENVIRONMENT}"

# Verify R2 bucket exists
wrangler r2 bucket list | grep "${WORKER_NAME}"

# Check Worker is deployed and handling requests
curl -s -o /dev/null -w "%{http_code}" \
  https://<your-worker-subdomain>.workers.dev/health
```

---

## Related
- `workers-custom-domain-certificate-pages.md`
- `cloudflare-tunnel-private-service-workers.md`

---

## Sources
- Cloudflare Terraform Provider — https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
- `cloudflare_worker_script` resource — https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_script
- Terraform Cloud remote backend — https://developer.hashicorp.com/terraform/cloud-docs/run/remote-operations
