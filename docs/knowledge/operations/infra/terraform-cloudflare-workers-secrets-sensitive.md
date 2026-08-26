# Terraform Cloudflare Workers Secrets Sensitive Values
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Worker secrets set via `wrangler secret put` are not tracked in Terraform state, so
they drift from IaC. Conversely, teams that move secrets into Terraform resources
accidentally log them in CI output or store them in plaintext in `.tfstate` files in S3.
Workers secrets need Terraform lifecycle management with proper sensitive value handling,
state encryption, and integration with secret stores like Vault or SOPS.

## Context

The Cloudflare Terraform provider manages Worker secrets via the
`cloudflare_workers_secret` resource (provider v4.35+). This resource stores the
secret value in Terraform state as a sensitive string. To avoid plaintext exposure:

- Mark all secret values as `sensitive = true` in variable declarations
- Encrypt Terraform state at rest (S3 SSE, R2 bucket default encryption, or
  Terraform Cloud encrypted state)
- Source secret values from environment variables, Vault dynamic secrets, or
  `external` data sources – never from `terraform.tfvars` committed to git
- Use `terraform plan -out` with `-var` flags or `TF_VAR_` env vars for CI

Provider v4.40+ also supports `write_only` arguments that prevent the secret value
from being stored in state at all (see Terraform write-only arguments RFC). Prefer
this where available.

## Declaring a Workers Secret Resource

```hcl
# terraform/modules/workers-secrets/variables.tf
variable "account_id"   { type = string }
variable "worker_name"  { type = string }

variable "database_url" {
  type        = string
  sensitive   = true
  description = "PostgreSQL connection string for the Worker"
}

variable "stripe_secret_key" {
  type      = string
  sensitive = true
}

variable "jwt_signing_secret" {
  type      = string
  sensitive = true
}

# terraform/modules/workers-secrets/main.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

resource "cloudflare_workers_secret" "database_url" {
  account_id  = var.account_id
  script_name = var.worker_name
  name        = "DATABASE_URL"
  text        = var.database_url
}

resource "cloudflare_workers_secret" "stripe_key" {
  account_id  = var.account_id
  script_name = var.worker_name
  name        = "STRIPE_SECRET_KEY"
  text        = var.stripe_secret_key
}

resource "cloudflare_workers_secret" "jwt_secret" {
  account_id  = var.account_id
  script_name = var.worker_name
  name        = "JWT_SIGNING_SECRET"
  text        = var.jwt_signing_secret
}
```

## Sourcing Secret Values from Environment Variables in CI

Never put secret values in `.tfvars` files. Inject them as `TF_VAR_` environment
variables in CI:

```yaml
# .github/workflows/deploy-secrets.yml
name: Deploy Worker Secrets

on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - "terraform/modules/workers-secrets/**"

jobs:
  apply:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.x"

      - name: Terraform Init
        run: terraform -chdir=terraform/environments/production init
        env:
          TF_VAR_account_id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          AWS_ACCESS_KEY_ID: ${{ secrets.TF_STATE_ACCESS_KEY }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.TF_STATE_SECRET_KEY }}

      - name: Terraform Apply
        run: terraform -chdir=terraform/environments/production apply -auto-approve
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          TF_VAR_account_id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          TF_VAR_worker_name: "api-worker-production"
          TF_VAR_database_url: ${{ secrets.DATABASE_URL }}
          TF_VAR_stripe_secret_key: ${{ secrets.STRIPE_SECRET_KEY }}
          TF_VAR_jwt_signing_secret: ${{ secrets.JWT_SIGNING_SECRET }}
```

## Sourcing Secrets from Vault

For teams running HashiCorp Vault, pull secrets dynamically at plan time using the
Vault Terraform provider:

```hcl
# terraform/modules/workers-secrets/vault.tf
terraform {
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "~> 4.4"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

data "vault_kv_secret_v2" "worker_secrets" {
  mount = "kv"
  name  = "cloudflare/workers/${var.worker_name}/${var.env}"
}

resource "cloudflare_workers_secret" "database_url" {
  account_id  = var.account_id
  script_name = var.worker_name
  name        = "DATABASE_URL"
  text        = data.vault_kv_secret_v2.worker_secrets.data["DATABASE_URL"]
}

resource "cloudflare_workers_secret" "stripe_key" {
  account_id  = var.account_id
  script_name = var.worker_name
  name        = "STRIPE_SECRET_KEY"
  text        = data.vault_kv_secret_v2.worker_secrets.data["STRIPE_SECRET_KEY"]
}
```

Vault KV path convention: `kv/cloudflare/workers/{worker_name}/{env}`. Store all
secrets for one Worker in a single KV entry to minimise Vault lease count.

## Preventing Secrets from Appearing in Plan Output

Terraform prints `(sensitive value)` for variables marked `sensitive = true`. Verify
your variable declarations have this set:

```hcl
# Correct – secret is masked in plan
variable "stripe_secret_key" {
  type      = string
  sensitive = true
}

# Wrong – value appears in plan output
variable "stripe_secret_key" {
  type = string
}
```

For the resource output, also mark outputs as sensitive if they reference secret values:

```hcl
output "worker_name" {
  value = cloudflare_workers_secret.stripe_key.script_name
  # script_name is not sensitive; the secret text itself is never in outputs
}

# Never do this:
# output "stripe_key_value" {
#   value     = cloudflare_workers_secret.stripe_key.text
#   sensitive = true
# }
# The `text` attribute is write-only in some provider versions;
# even when readable, never output secret values.
```

## State Encryption for Secret Residue

`cloudflare_workers_secret.text` may reside in `.tfstate`. Encrypt state at rest:

```hcl
# terraform/backends/r2.tf – R2 backend with server-side encryption
terraform {
  backend "s3" {
    bucket   = "tf-state-prod"
    key      = "workers/secrets/terraform.tfstate"
    region   = "auto"
    endpoint = "https://${ACCOUNT_ID}.r2.cloudflarestorage.com"

    # R2 enforces AES-256 at rest by default; no extra config needed.
    # Use access_key/secret_key from an R2-scoped API token.
    access_key = var.r2_access_key
    secret_key = var.r2_secret_key

    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
  }
}
```

For Terraform Cloud / Terraform Enterprise, state is encrypted by default. For S3:

```hcl
terraform {
  backend "s3" {
    bucket         = "tf-state"
    key            = "workers/secrets/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true                   # enforce SSE
    kms_key_id     = "arn:aws:kms:..."      # use a CMK, not the default AWS key
  }
}
```

## Rotating Secrets

Secret rotation is a `terraform apply` after updating the source value. For automated
rotation via CI:

```bash
# Trigger rotation workflow in GitHub Actions
gh workflow run deploy-secrets.yml \
  --ref main \
  -f reason="scheduled-rotation"
```

Terraform detects the changed value via the `text` attribute and issues a
`cloudflare_workers_secret` update (in-place, no resource recreation). The new secret
is live immediately after apply; the old secret is overwritten on Cloudflare's side.

## Anti-patterns

- **Storing secrets in `terraform.tfvars`** – these files are commonly committed to git
  accidentally. Use `TF_VAR_` env vars or Vault.
- **Using `terraform output` to read back secret values for debugging** – outputs
  marked sensitive still emit the value to stdout with `-json`. Pipe to a secrets store
  or use the Cloudflare API directly for debugging.
- **Recreating the Worker script resource to force a secret update** – `cloudflare_workers_secret`
  is independent of `cloudflare_workers_script`; updating a secret does not require
  redeploying the bundle.
- **Setting secrets via both wrangler and Terraform** – creates a split source of
  truth. One tool should own all secrets for a given Worker; migrate fully to Terraform
  or keep wrangler for manual overrides and document the ownership boundary.

## Gotchas

- `cloudflare_workers_secret` does not expose the current secret value via a read API
  (Cloudflare does not return secret values after creation). Terraform cannot detect
  drift if a secret is changed outside Terraform; `terraform plan` will always show
  no changes even if wrangler was used to override the value.
- Deleting a `cloudflare_workers_secret` resource removes the binding from the Worker.
  The Worker will receive `undefined` for that binding at runtime and likely throw.
  Use `lifecycle { prevent_destroy = true }` on production secrets.
- The `text` attribute in provider v4.40+ is `write_only = true` on some resource
  versions; it will not be stored in state. This is the desired behavior for security
  but means `terraform show` cannot display the current value.

## Verification

```bash
# Confirm secrets exist on the Worker (names only, not values)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/secrets" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | {name, type}'

# Confirm Terraform state does not have plaintext
terraform state show 'cloudflare_workers_secret.stripe_key' 2>/dev/null \
  | grep text   # should show "(sensitive value)" not the actual key

# Worker runtime test – secret should be accessible
curl "https://api-worker.example.com/__health" \
  | jq '.secrets_bound'  # custom health endpoint lists bound secret names
```

## Related

- `vault-cloudflare-workers-dynamic-secrets.md` – Vault dynamic secret generation
- `sops-age-gitops-secrets-management.md` – SOPS for encrypting secret files at rest
- `pulumi-esc-secrets-config-management.md` – Pulumi ESC as a secret source
- `workers-secrets-rotation-automation.md` – automated rotation runbook
- `cloudflare-workers-api-token-scoping.md` – API token least-privilege for secret management
- `terraform-write-only-arguments-secret-rotation.md` – Terraform write-only attribute pattern

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_secret
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developer.hashicorp.com/terraform/language/values/variables#suppressing-values-in-cli-output
- https://developer.hashicorp.com/terraform/language/state/sensitive-data
- https://developer.hashicorp.com/terraform/language/backend/s3
