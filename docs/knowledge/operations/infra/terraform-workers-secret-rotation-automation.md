# Automating Cloudflare Workers Secret Rotation with Terraform and GitHub Actions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers secrets (API keys, signing secrets, DB passwords) age over time and must be rotated regularly to meet compliance requirements. Doing this manually is error-prone and leaves gaps in the audit trail.

## Context

Cloudflare exposes `cloudflare_worker_secret` as a Terraform resource. Combined with `random_password` for generation and GitHub Actions scheduled workflows, you can automate monthly zero-downtime rotation and write every event to a D1 audit table.

Requirements:
- Terraform >= 1.7
- Cloudflare provider >= 4.30
- D1 database already provisioned (see `cloudflare-d1-setup.md`)
- GitHub OIDC → Cloudflare API token with `Workers Scripts:Edit` + `D1:Write`

---

## Terraform: Secret Resource and Random Generation

```hcl
# terraform/modules/worker-secrets/main.tf

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.30"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

variable "account_id"    { type = string }
variable "worker_script" { type = string }
variable "environment"   { type = string }   # staging | production
variable "rotation_id"   { type = string }    # bumped each rotation cycle

# Generate a new 48-char alphanumeric secret.
# Keyed on rotation_id so each cycle produces a fresh value.
resource "random_password" "api_secret" {
  length           = 48
  special          = false
  keepers = {
    rotation_id = var.rotation_id
  }
}

# Write the new secret into the Worker.
resource "cloudflare_worker_secret" "api_secret" {
  account_id  = var.account_id
  script_name = var.worker_script
  name        = "API_SECRET"
  secret_text = random_password.api_secret.result
}

output "secret_version" {
  value     = var.rotation_id
  sensitive = false
}
```

```hcl
# terraform/environments/production/main.tf

module "worker_secrets" {
  source        = "../../modules/worker-secrets"
  account_id    = var.cloudflare_account_id
  worker_script = "api-gateway"
  environment   = "production"
  # Increment rotation_id to trigger a new secret on next apply.
  rotation_id   = "2026-08"
}
```

---

## GitHub Actions: Monthly Rotation Workflow

```yaml
# .github/workflows/rotate-worker-secrets.yml
name: Rotate Worker Secrets

on:
  schedule:
    - cron: '0 3 1 * *'   # 03:00 UTC on the 1st of every month
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: production
        type: choice
        options: [staging, production]

permissions:
  contents: write          # to bump rotation_id in HCL
  id-token: write          # OIDC → Cloudflare API token

env:
  TF_WORKSPACE: ${{ inputs.environment || 'production' }}

jobs:
  rotate:
    name: Rotate secrets (${{ inputs.environment || 'production' }})
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment || 'production' }}

    steps:
      - uses: actions/checkout@v4

      - name: Exchange OIDC token for Cloudflare API token
        id: cf-auth
        uses: cloudflare/cloudflare-github-action@v1
        with:
          audience: 'https://cloudflare.com'

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: '1.7.5'

      - name: Bump rotation_id
        run: |
          NEW_ID=$(date +%Y-%m)
          sed -i "s/rotation_id   = \".*\"/rotation_id   = \"${NEW_ID}\"/" \
            terraform/environments/${TF_WORKSPACE}/main.tf

      - name: Terraform Init
        run: terraform -chdir=terraform/environments/${TF_WORKSPACE} init

      - name: Terraform Plan
        run: terraform -chdir=terraform/environments/${TF_WORKSPACE} plan -out=tfplan

      - name: Terraform Apply  # Zero-downtime: new secret replaces old atomically
        run: terraform -chdir=terraform/environments/${TF_WORKSPACE} apply tfplan
        env:
          CLOUDFLARE_API_TOKEN: ${{ steps.cf-auth.outputs.api-token }}

      - name: Write audit record to D1
        run: |
          curl -s -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{ \"sql\": \"INSERT INTO secret_rotations(worker, environment, rotation_id, rotated_at, rotated_by) VALUES (?, ?, ?, datetime('now'), ?)\", \"params\": [\"api-gateway\", \"${TF_WORKSPACE}\", \"$(date +%Y-%m)\", \"github-actions\"] }"
        env:
          CF_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          D1_DB_ID:      ${{ vars.D1_AUDIT_DB_ID }}
          CLOUDFLARE_API_TOKEN: ${{ steps.cf-auth.outputs.api-token }}

      - name: Commit updated rotation_id
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add terraform/environments/${TF_WORKSPACE}/main.tf
          git commit -m "chore(secrets): bump rotation_id to $(date +%Y-%m) [skip ci]"
          git push
```

---

## D1 Audit Schema

```sql
-- Run once during initial setup
CREATE TABLE IF NOT EXISTS secret_rotations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  worker       TEXT    NOT NULL,
  environment  TEXT    NOT NULL,
  rotation_id  TEXT    NOT NULL,
  rotated_at   TEXT    NOT NULL,
  rotated_by   TEXT    NOT NULL DEFAULT 'unknown'
);

CREATE INDEX idx_secret_rotations_worker_env
  ON secret_rotations(worker, environment);
```

---

## Zero-Downtime Rotation Sequence

Cloudflare applies a new `cloudflare_worker_secret` atomically: the old value stays live until the API call completes, then the Worker immediately reads the new value on the next request. There is no window where the secret is absent.

For dependent consumers (e.g., a webhook caller that signs requests with your secret):
1. Deploy new secret via Terraform.
2. Distribute new secret to callers out-of-band (rotate their side).
3. Maintain a `PREVIOUS_API_SECRET` Worker secret with the old value for a grace period (24-48 h) so in-flight requests signed with the old key still pass.
4. After the grace period, remove `PREVIOUS_API_SECRET` in a follow-up Terraform apply.

---

## Anti-patterns

- **Hardcoding secrets in Terraform state**: `random_password` result is stored in state — ensure state backend is encrypted (Terraform Cloud or S3 + KMS).
- **Rotating all environments simultaneously**: use `workflow_dispatch` with environment input; stagger staging by a week before production.
- **Skipping the audit write**: if D1 write fails, the rotation still succeeded — treat audit failure as a non-blocking warning, alert separately.
- **Using `rotation_id = "static"` as a placeholder**: this prevents Terraform from ever regenerating the secret.

## Gotchas

- `cloudflare_worker_secret` is write-only: `terraform plan` will always show a diff if the resource is re-created, even if the value hasn't changed. Pin `rotation_id` in `keepers` to suppress spurious diffs.
- GitHub Actions OIDC → Cloudflare requires the Cloudflare account to have the GitHub OIDC integration configured under **Zero Trust > Settings > Authentication**.
- Terraform workspaces (`TF_WORKSPACE`) map 1:1 to environment directories here; do not use the default workspace for production.

## Verification

```bash
# Confirm the secret exists (value is masked)
terraform -chdir=terraform/environments/production output -json

# Query audit log
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT * FROM secret_rotations ORDER BY rotated_at DESC LIMIT 10"}'
```

## Related

- `cloudflare-access-service-token-rotation-automation.md`
- `cloudflare-d1-setup.md`
- `terraform-cloudflare-provider-upgrade.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_secret
- https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/password
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-cloud-providers
