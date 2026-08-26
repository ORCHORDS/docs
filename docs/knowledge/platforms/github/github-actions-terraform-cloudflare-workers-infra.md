# GitHub Actions Terraform Plan/Apply for Cloudflare Workers Infrastructure

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare Workers projects reach a point where KV namespaces, D1 databases, R2 buckets, Queues, and Hyperdrive
configs are provisioned by hand and drift between environments. Reproducible infrastructure requires Terraform
with the Cloudflare provider. The challenge is integrating Terraform plan/apply safely into GitHub Actions:
surfacing plan diffs as PR comments, gating apply behind environment protection rules, and storing Terraform
state in an R2-compatible backend — all without storing long-lived credentials in CI secrets.

## Context

The Cloudflare Terraform provider (cloudflare/cloudflare) covers KV namespaces, D1 databases, R2 buckets,
Workers scripts, and access policies. Terraform state can be stored in an S3-compatible backend using R2's S3
API. GitHub Actions OIDC is used to obtain short-lived Cloudflare API tokens (via the OIDC Cloudflare token
binding), eliminating the need to rotate a long-lived `CLOUDFLARE_API_TOKEN` secret. The PR plan is posted as
a comment via the `peter-evans/create-or-update-comment` action pattern, and apply is blocked by a GitHub
environment with required reviewers.

---

## Terraform Configuration for Workers Infrastructure

```hcl
# infra/main.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

  # R2 as S3-compatible Terraform state backend
  backend "s3" {
    bucket                      = "my-tf-state"
    key                         = "workers/terraform.tfstate"
    region                      = "auto"
    endpoint                    = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
    # Credentials come from env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  }
}

provider "cloudflare" {
  # api_token injected via CLOUDFLARE_API_TOKEN env var
}

variable "account_id" { type = string }
variable "zone_id"    { type = string }
variable "environment" {
  type    = string
  default = "production"
}

resource "cloudflare_workers_kv_namespace" "cache" {
  account_id = var.account_id
  title      = "cache-${var.environment}"
}

resource "cloudflare_d1_database" "main" {
  account_id = var.account_id
  name       = "main-${var.environment}"
}

resource "cloudflare_r2_bucket" "assets" {
  account_id = var.account_id
  name       = "assets-${var.environment}"
  location   = "WEUR"
}

output "kv_namespace_id" { value = cloudflare_workers_kv_namespace.cache.id }
output "d1_database_id"  { value = cloudflare_d1_database.main.id }
output "r2_bucket_name"  { value = cloudflare_r2_bucket.assets.name }
```

---

## Plan Workflow: Comment on Pull Request

```yaml
# .github/workflows/terraform-plan.yml
name: Terraform Plan

on:
  pull_request:
    paths:
      - "infra/**"
      - ".github/workflows/terraform-*.yml"

permissions:
  contents: read
  pull-requests: write
  id-token: write   # required for OIDC

jobs:
  plan:
    runs-on: ubuntu-24.04
    defaults:
      run:
        working-directory: infra

    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.10.x"
          terraform_wrapper: true   # enables ${{ steps.plan.outputs.stdout }}

      - name: Configure R2 backend credentials
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_STATE_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_STATE_SECRET_ACCESS_KEY }}
        run: terraform init -input=false

      - name: Terraform Validate
        run: terraform validate -no-color

      - name: Terraform Plan
        id: plan
        continue-on-error: true
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          TF_VAR_account_id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          TF_VAR_zone_id: ${{ secrets.CLOUDFLARE_ZONE_ID }}
          TF_VAR_environment: production
        run: terraform plan -no-color -out=tfplan 2>&1

      - name: Post plan as PR comment
        uses: actions/github-script@v7
        env:
          PLAN_OUTPUT: ${{ steps.plan.outputs.stdout }}
        with:
          script: |
            const output = process.env.PLAN_OUTPUT;
            const status = `${{ steps.plan.outcome }}` === 'success' ? '✅ Success' : '❌ Failed';
            const body = `## Terraform Plan — ${status}

            <details><summary>Show Plan</summary>

            \`\`\`hcl
            ${output.slice(0, 60000)}
            \`\`\`
            </details>

            *Pusher: @${{ github.actor }}, Action: \`${{ github.event_name }}\`*`;

            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
            });

            const existing = comments.find(c => c.body.startsWith('## Terraform Plan'));
            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existing.id,
                body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body,
              });
            }

            if ('${{ steps.plan.outcome }}' === 'failure') core.setFailed('Terraform plan failed');
```

---

## Apply Workflow: Environment-Gated

```yaml
# .github/workflows/terraform-apply.yml
name: Terraform Apply

on:
  push:
    branches: [main]
    paths:
      - "infra/**"

permissions:
  contents: read
  id-token: write

jobs:
  apply:
    runs-on: ubuntu-24.04
    environment: production    # requires reviewer approval via GitHub environment protection
    defaults:
      run:
        working-directory: infra

    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.10.x"

      - name: Terraform Init
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_STATE_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_STATE_SECRET_ACCESS_KEY }}
        run: terraform init -input=false

      - name: Terraform Apply
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          TF_VAR_account_id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          TF_VAR_zone_id: ${{ secrets.CLOUDFLARE_ZONE_ID }}
          TF_VAR_environment: production
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_STATE_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_STATE_SECRET_ACCESS_KEY }}
        run: terraform apply -auto-approve -no-color

      - name: Export outputs to wrangler.toml patch
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          KV_ID=$(terraform output -raw kv_namespace_id)
          D1_ID=$(terraform output -raw d1_database_id)

          # Patch wrangler.toml in the repo root (via a commit or repository dispatch)
          echo "KV_NAMESPACE_ID=$KV_ID" >> "$GITHUB_ENV"
          echo "D1_DATABASE_ID=$D1_ID" >> "$GITHUB_ENV"
```

---

## Propagating Terraform Outputs to Wrangler Deploy

After Terraform provisions resources, their IDs must flow into the subsequent Workers deploy workflow. Use
GitHub repository variables (set via the API) to bridge the two workflows without hardcoding IDs.

```typescript
// scripts/update-gh-vars.ts — runs as a post-apply step
const REPO = process.env.GITHUB_REPOSITORY!;
const TOKEN = process.env.GH_TOKEN!;

async function upsertVar(name: string, value: string): Promise<void> {
  const base = `https://api.github.com/repos/${REPO}/actions/variables/${name}`;
  const existing = await fetch(base, {
    headers: { Authorization: `Bearer ${TOKEN}`, Accept: "application/vnd.github+json" },
  });

  const method = existing.status === 200 ? "PATCH" : "POST";
  const url = method === "POST"
    ? `https://api.github.com/repos/${REPO}/actions/variables`
    : base;

  await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name, value }),
  });
}

await upsertVar("KV_NAMESPACE_ID", process.env.KV_NAMESPACE_ID!);
await upsertVar("D1_DATABASE_ID", process.env.D1_DATABASE_ID!);
```

---

## Anti-patterns

- **Running `terraform apply` on pull requests** — applying on PRs allows contributors to provision arbitrary
  Cloudflare resources before review. Always restrict apply to pushes on the default branch behind an
  environment gate.
- **Committing `terraform.tfstate` to the repository** — state files contain plaintext resource IDs and
  potentially sensitive values. Use the R2 S3-compatible backend exclusively.
- **Using a Cloudflare Global API Key** — the Global Key has unrestricted access to your entire account.
  Always use a scoped API token with only the permissions needed by the Terraform provider resources in use.
- **Skipping `terraform validate` in CI** — plan will catch syntax errors but validate runs faster and
  catches provider schema mismatches before hitting the Cloudflare API.

---

## Gotchas

- The Cloudflare Terraform provider does **not** support importing existing D1 databases created by Wrangler
  (`wrangler d1 create`). Bootstrap new databases via Terraform from the start, or use `terraform import`
  with the existing database UUID before adding the resource block.
- R2 buckets configured as Terraform state backends require separate R2 API tokens with `Object Read & Write`
  permission — distinct from the Cloudflare API token used to provision Workers infrastructure.
- The `terraform_wrapper: true` setting for `hashicorp/setup-terraform` is required to capture plan output
  in `steps.plan.outputs.stdout`; without it the output variable is empty.
- Cloudflare rate limits the Terraform provider's API calls; large plans with many resources may hit 429s.
  Set `TF_LOG=DEBUG` to identify which API calls are being throttled.

---

## Verification

```bash
# Local plan against production state
cd infra
terraform init
terraform plan -var="account_id=$CF_ACCOUNT_ID" -var="zone_id=$CF_ZONE_ID"

# Confirm state backend connectivity
terraform state list

# Verify outputs match deployed wrangler.toml
terraform output kv_namespace_id
wrangler kv namespace list | jq '.[] | select(.title == "cache-production") | .id'
```

---

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-environment-protection.md`
- `github-actions-oidc-cloudflare.md`
- `github-actions-dynamic-environment-variables-d1-config.md`

---

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
- https://developers.cloudflare.com/r2/api/s3/api/
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://developer.hashicorp.com/terraform/language/settings/backends/s3
- https://github.com/hashicorp/setup-terraform
