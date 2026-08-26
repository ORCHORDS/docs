# Terraform Cloudflare Provider for Workers Infrastructure

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team wants to manage Cloudflare Workers, KV namespaces, D1 databases, R2 buckets, and Pages projects as versioned infrastructure code. Manual wrangler deploys drift between environments and there is no audit trail. You need a GitOps workflow where every infrastructure change is reviewed, approved, and applied via CI/CD.

## Context

The [Cloudflare Terraform provider](https://registry.terraform.io/providers/cloudflare/cloudflare/latest) supports the full Cloudflare developer platform surface. Terraform state tracks what is deployed, enabling plan/apply cycles and drift detection. This is complementary to `wrangler` — Terraform owns infra (namespaces, databases, buckets, routes) while wrangler handles code deployments, or Terraform can own both via `cloudflare_worker_script`.

Key provider version: `~> 4.0` as of mid-2026. The provider uses the Cloudflare REST API under the hood.

## Solution

```hcl
# versions.tf
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

  # Terraform Cloud remote state
  cloud {
    organization = "orchords"
    workspaces {
      name = "cloudflare-workers-prod"
    }
  }
}

# provider.tf
provider "cloudflare" {
  # CLOUDFLARE_API_TOKEN env var — never hardcode
  # Token needs: Workers Scripts:Edit, KV:Edit, D1:Edit, R2:Edit
  api_token = <redacted-secret>
}

# variables.tf
variable "cloudflare_api_token" {
  type        = string
  sensitive   = true
  description = "Scoped API token for Cloudflare Workers infra"
}

variable "account_id" {
  type        = string
  description = "Cloudflare account ID"
}

variable "zone_id" {
  type        = string
  description = "Cloudflare zone ID for route attachment"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Deployment environment label"
}

# kv.tf — KV namespace resources
resource "cloudflare_workers_kv_namespace" "sessions" {
  account_id = var.account_id
  title      = "sessions-${var.environment}"
}

resource "cloudflare_workers_kv_namespace" "config" {
  account_id = var.account_id
  title      = "config-${var.environment}"
}

# d1.tf — D1 database resources
resource "cloudflare_d1_database" "app_db" {
  account_id = var.account_id
  name       = "app-db-${var.environment}"
}

# r2.tf — R2 bucket resources
resource "cloudflare_r2_bucket" "assets" {
  account_id = var.account_id
  name       = "assets-${var.environment}"
  location   = "EEUR"
}

resource "cloudflare_r2_bucket" "uploads" {
  account_id = var.account_id
  name       = "uploads-${var.environment}"
  location   = "EEUR"
}

# worker.tf — Workers script resource
resource "cloudflare_worker_script" "api" {
  account_id = var.account_id
  name       = "api-${var.environment}"
  content    = file("${path.module}/dist/worker.js")
  module     = true

  kv_namespace_binding {
    name         = "SESSIONS"
    namespace_id = cloudflare_workers_kv_namespace.sessions.id
  }

  kv_namespace_binding {
    name         = "CONFIG"
    namespace_id = cloudflare_workers_kv_namespace.config.id
  }

  d1_database_binding {
    name        = "DB"
    database_id = cloudflare_d1_database.app_db.id
  }

  r2_bucket_binding {
    name        = "ASSETS"
    bucket_name = cloudflare_r2_bucket.assets.name
  }

  plain_text_binding {
    name = "ENVIRONMENT"
    text = var.environment
  }

  secret_text_binding {
    name = "JWT_SECRET"
    text = var.jwt_secret
  }
}

# routes.tf — attach Worker to a route
resource "cloudflare_worker_route" "api" {
  zone_id     = var.zone_id
  pattern     = "api.example.com/*"
  script_name = cloudflare_worker_script.api.name
}

# pages.tf — Pages project resource
resource "cloudflare_pages_project" "frontend" {
  account_id        = var.account_id
  name              = "frontend-${var.environment}"
  production_branch = "main"

  build_config {
    build_command       = "npm run build"
    destination_dir     = "dist"
    root_dir            = ""
    web_analytics_tag   = "abc123"
    web_analytics_token = var.web_analytics_token
  }

  deployment_configs {
    production {
      environment_variables = {
        NODE_ENV = "production"
      }
      kv_namespaces = {
        CONFIG = cloudflare_workers_kv_namespace.config.id
      }
    }
  }
}

# outputs.tf
output "kv_sessions_id" {
  value = cloudflare_workers_kv_namespace.sessions.id
}

output "d1_database_id" {
  value     = cloudflare_d1_database.app_db.id
  sensitive = false
}

output "r2_assets_bucket" {
  value = cloudflare_r2_bucket.assets.name
}
```

## Implementation Details

**API Token scopes required** — create a scoped token (not Global API Key) with these permissions:
- Account / Workers Scripts: Edit
- Account / Workers KV Storage: Edit
- Account / D1: Edit
- Account / R2 Storage: Edit
- Zone / Worker Routes: Edit
- Account / Pages: Edit

Store the token as a Terraform Cloud workspace variable marked **sensitive**. In local dev use `export CLOUDFLARE_API_TOKEN=...`.

**State management** — Terraform Cloud (or any S3-compatible backend) holds the state file. Never commit `terraform.tfstate` to git. Use workspace-per-environment isolation (e.g. `cloudflare-workers-staging`, `cloudflare-workers-prod`).

**Importing existing resources** — if you already have KV namespaces or Workers deployed:
```bash
terraform import cloudflare_workers_kv_namespace.sessions <account_id>/<namespace_id>
terraform import cloudflare_d1_database.app_db <account_id>/<database_id>
terraform import cloudflare_r2_bucket.assets <account_id>/<bucket_name>
terraform import cloudflare_worker_script.api <account_id>/<script_name>
```

**CI/CD with Terraform Cloud** — `.github/workflows/terraform.yml`:
```yaml
name: Terraform
on:
  push:
    branches: [main]
  pull_request:
jobs:
  terraform:
    runs-on: ubuntu-latest
    env:
      TF_CLOUD_ORGANIZATION: orchords
      TF_API_TOKEN: ${{ secrets.TF_API_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "~1.6"
          cli_config_credentials_token: ${{ secrets.TF_API_TOKEN }}
      - run: terraform init
      - run: terraform validate
      - run: terraform plan -out=tfplan
        if: github.event_name == 'pull_request'
      - run: terraform apply -auto-approve tfplan
        if: github.ref == 'refs/heads/main'
```

## Anti-patterns

- **Hardcoding `account_id` or `api_token` in `.tf` files** — use variables and environment-specific `.tfvars` files committed to the repo (without secrets), secrets in CI/Terraform Cloud.
- **One workspace for all environments** — workspace isolation prevents a staging `plan` from touching prod state.
- **Using Global API Key** — it has unrestricted access; scoped tokens limit blast radius.
- **Storing built `dist/worker.js` in git** — build in CI, reference from a CI artifact path, or use `null_resource` + `local-exec` to build before apply.
- **Skipping `terraform plan` review on PRs** — always post the plan as a PR comment (Terraform Cloud does this automatically with `TFC_COMMAND=plan`).

## Gotchas

- `cloudflare_worker_script` with `module = true` expects ESM format output; ensure your bundler outputs `format: 'esm'`.
- R2 bucket `name` must be globally unique within your account and lowercase-alphanumeric-hyphen only.
- D1 database names must be unique per account; adding `var.environment` suffix prevents collisions between workspaces.
- The `secret_text_binding` value is write-only in Terraform state — Terraform cannot detect if it drifts. Rotate secrets via `terraform apply` with an updated variable.
- Pages project `build_config` is only applied when Cloudflare Pages triggers a build from git; it does not affect direct API uploads.
- Provider `~> 4.0` introduced breaking changes from 3.x — do not mix versions across workspaces.

## Verification

```bash
# Check plan produces expected resources
terraform plan 2>&1 | grep -E '(will be created|will be updated|will be destroyed)'

# After apply, verify Worker is live
curl -I https://api.example.com/health

# Verify KV namespace exists
wrangler kv:namespace list | grep sessions-production

# Verify D1 database
wrangler d1 list | grep app-db-production

# Verify R2 bucket
wrangler r2 bucket list | grep assets-production

# Terraform state should show all resources
terraform state list
```

## Related

- `documentation/categories/infra/workers-pulumi-workers-deployment.md`
- `documentation/categories/infra/workers-wrangler-environments-matrix.md`
- `documentation/categories/infra/workers-multi-account-deployment.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/terraform/
- https://developer.hashicorp.com/terraform/cloud-docs
