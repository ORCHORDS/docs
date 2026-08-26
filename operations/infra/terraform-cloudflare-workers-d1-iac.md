# Terraform Infrastructure-as-Code for Cloudflare Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Manually creating Cloudflare Workers, D1 databases, and DNS routes through the dashboard creates configuration drift and makes disaster recovery unreliable. Teams need reproducible, version-controlled infrastructure that can be reviewed in pull requests and applied consistently across environments.

---

## Context

Cloudflare publishes an official Terraform provider (`cloudflare/cloudflare`) that covers Workers scripts, D1 databases, Worker domains, and KV namespaces. Terraform state can be stored in a Cloudflare R2 bucket using the S3-compatible backend, removing the need for an external state store such as AWS S3. Running `terraform plan` in CI before `terraform apply` catches destructive changes before they reach production. Existing resources created outside Terraform can be imported with `terraform import` to bring them under IaC management without recreation.

---

## Section 1 — Terraform configuration (`main.tf` + `backend.tf`)

```hcl
# backend.tf — state stored in Cloudflare R2
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    bucket                      = "tf-state-orchords"
    key                         = "workers/terraform.tfstate"
    region                      = "auto"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
    # endpoint injected via TF_VAR_r2_endpoint env var in CI
    endpoints = {
      s3 = var.r2_endpoint
    }
  }
}

# variables.tf
variable "cloudflare_account_id" { type = string }
variable "cloudflare_zone_id"    { type = string }
variable "r2_endpoint"           { type = string }

variable "worker_script_path" {
  type    = string
  default = "dist/worker.js"
}

# main.tf
provider "cloudflare" {
  # CLOUDFLARE_API_TOKEN env var is read automatically
}

# ── D1 database ──────────────────────────────────────────────────────────────
resource "cloudflare_d1_database" "main" {
  account_id = var.cloudflare_account_id
  name       = "orchords-main"
}

# ── Worker script ─────────────────────────────────────────────────────────────
resource "cloudflare_worker_script" "api" {
  account_id = var.cloudflare_account_id
  name       = "orchords-api"
  content    = file(var.worker_script_path)

  d1_database_binding {
    name        = "DB"
    database_id = cloudflare_d1_database.main.id
  }

  plain_text_binding {
    name = "ENVIRONMENT"
    text = "production"
  }

  compatibility_date  = "2024-09-23"
  compatibility_flags = ["nodejs_compat"]
}

# ── Custom domain for the Worker ──────────────────────────────────────────────
resource "cloudflare_worker_domain" "api" {
  account_id = var.cloudflare_account_id
  zone_id    = var.cloudflare_zone_id
  hostname   = "api.example.com"
  service    = cloudflare_worker_script.api.name
}

# ── DNS CNAME that the worker domain requires ─────────────────────────────────
resource "cloudflare_record" "api_cname" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  type    = "CNAME"
  value   = "orchords-api.orchords.workers.dev"
  proxied = true
}

# outputs.tf
output "d1_database_id" {
  value = cloudflare_d1_database.main.id
}

output "worker_script_name" {
  value = cloudflare_worker_script.api.name
}
```

---

## Section 2 — CI pipeline (GitHub Actions)

```yaml
# .github/workflows/terraform.yml
name: Terraform

on:
  pull_request:
    paths: ["infra/**"]
  push:
    branches: [main]
    paths: ["infra/**"]

env:
  TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}
  TF_VAR_cloudflare_zone_id:    ${{ secrets.CF_ZONE_ID }}
  TF_VAR_r2_endpoint:           ${{ secrets.R2_ENDPOINT }}
  CLOUDFLARE_API_TOKEN:         ${{ secrets.CF_API_TOKEN }}
  AWS_ACCESS_KEY_ID:            ${{ secrets.R2_ACCESS_KEY_ID }}
  AWS_SECRET_ACCESS_KEY:        ${{ secrets.R2_SECRET_ACCESS_KEY }}

jobs:
  plan:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: infra
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.x"

      - name: Build Worker bundle
        run: |
          cd ..
          npm ci
          npm run build          # emits dist/worker.js

      - run: terraform init
      - run: terraform validate
      - run: terraform plan -out=tfplan

      - name: Upload plan artifact
        if: github.event_name == 'pull_request'
        uses: actions/upload-artifact@v4
        with:
          name: tfplan
          path: infra/tfplan

  apply:
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    needs: plan
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: infra
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.x"
      - run: npm ci && npm run build
        working-directory: .
      - run: terraform init
      - run: terraform apply -auto-approve
```

---

## Section 3 — Importing existing resources

```bash
# Import a D1 database that was created in the dashboard
# Format: <account_id>/<database_id>
terraform import \
  cloudflare_d1_database.main \
  "${CF_ACCOUNT_ID}/${EXISTING_DB_ID}"

# Import an existing Worker script
# Format: <account_id>/<script_name>
terraform import \
  cloudflare_worker_script.api \
  "${CF_ACCOUNT_ID}/orchords-api"

# Import a DNS record
# Format: <zone_id>/<record_id>
terraform import \
  cloudflare_record.api_cname \
  "${CF_ZONE_ID}/${RECORD_ID}"

# After import, verify no destructive changes
terraform plan
```

---

## Anti-patterns

- **Storing Terraform state in git** — State contains sensitive outputs and causes merge conflicts; always use a remote backend such as R2.
- **Hardcoding API tokens in `.tf` files** — Use environment variables (`CLOUDFLARE_API_TOKEN`) or a secrets manager; never commit credentials.
- **Running `terraform apply` directly on PRs** — Always plan on PR and apply only after merge to main to prevent concurrent state mutations.
- **Using `cloudflare_worker_script` `content` with inline strings** — Build the Worker bundle before Terraform runs so the hash changes only when code changes, avoiding spurious redeploys.

---

## Gotchas

- The R2 S3-compatible backend requires `skip_credentials_validation = true`, `skip_metadata_api_check = true`, and `skip_region_validation = true` — missing any one causes init to fail with an AWS region error.
- `cloudflare_worker_domain` creates a Custom Domain (orange-cloud), not a Workers Route; the DNS record must be proxied (`proxied = true`) or the domain binding will be rejected.
- D1 database IDs are UUIDs that are generated on creation; use `terraform output d1_database_id` to retrieve the ID for `wrangler.toml` bindings in other environments.
- Terraform provider `~> 4.0` dropped the legacy `cloudflare_worker_route` resource for custom domains — use `cloudflare_worker_domain` instead.

---

## Verification

```bash
# Confirm state is stored remotely
terraform state list

# Check the deployed Worker is reachable
curl -sf https://api.example.com/health | jq .

# Confirm D1 binding is active
wrangler d1 execute orchords-main --command "SELECT 1"

# Verify no drift between state and live infrastructure
terraform plan -detailed-exitcode
# Exit code 0 = no changes; 2 = changes needed; 1 = error
```

---

## Related

- `workers-environment-parity-staging-prod.md`
- `cloudflare-dns-workers-route-management.md`

---

## Sources

- Cloudflare Terraform Provider — https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
- Terraform S3 Backend — https://developer.hashicorp.com/terraform/language/backend/s3
- Cloudflare R2 S3 Compatibility — https://developers.cloudflare.com/r2/api/s3/api/
