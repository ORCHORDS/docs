# Terraform Workspace Multi-Account Cloudflare Organization

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare organization has multiple accounts (e.g., one per business unit, or separate production / staging / sandbox accounts under an Enterprise subscription). You need Terraform workspaces to target different accounts with isolated state, shared modules, and a single CI pipeline — without hardcoding account IDs or leaking tokens across environments.

## Context

Cloudflare Enterprise supports multiple accounts under one organization. Common patterns include a "sandbox" account for experimentation, "staging" per team, and a "production" account with tighter IAM. Terraform workspaces map one workspace to one Cloudflare account. The Cloudflare provider is configured via workspace-specific variables rather than static `provider` blocks, allowing the same module to deploy to any account. State is stored in a shared backend (Terraform Cloud, S3+DynamoDB, or Cloudflare R2 with native backend support) with workspace-prefixed state keys.

## 1. Backend and Workspace Layout

```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket               = "tf-state-org"
    key                  = "cloudflare/terraform.tfstate"
    region               = "us-east-1"
    workspace_key_prefix = "cloudflare"
    # actual state path: cloudflare/<workspace>/terraform.tfstate
  }

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }

  required_version = ">= 1.9"
}
```

Workspace names map to account IDs via a local lookup:

```hcl
# locals.tf
locals {
  workspace_config = {
    sandbox = {
      account_id     = "aaa111bbb222ccc333ddd444eee555ff"
      zone_id        = "111aaa222bbb333ccc444ddd555eee66"
      environment    = "sandbox"
      worker_cpu_ms  = 10   # lenient limits in sandbox
    }
    staging = {
      account_id     = "bbb222ccc333ddd444eee555fff666aa"
      zone_id        = "222bbb333ccc444ddd555eee666fff77"
      environment    = "staging"
      worker_cpu_ms  = 50
    }
    production = {
      account_id     = "ccc333ddd444eee555fff666aaa111bb"
      zone_id        = "333ccc444ddd555eee666fff111aaa88"
      environment    = "production"
      worker_cpu_ms  = 50
    }
  }

  cfg = local.workspace_config[terraform.workspace]
}
```

## 2. Per-Workspace Provider Credentials

```hcl
# provider.tf
variable "cloudflare_api_tokens" {
  type      = map(string)
  sensitive = true
  description = "Map of workspace -> Cloudflare API token. Populated from CI secret store."
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

In CI, secrets are injected per workspace:

```yaml
# .github/workflows/terraform.yml
- name: Set workspace token
  run: |
    WORKSPACE="${{ inputs.workspace }}"  # e.g. "production"
    TOKEN_VAR="CF_TOKEN_${WORKSPACE^^}" # CF_TOKEN_PRODUCTION
    echo "TF_VAR_cloudflare_api_tokens={\"$WORKSPACE\":\"${!TOKEN_VAR}\"}" >> "$GITHUB_ENV"
  env:
    CF_TOKEN_SANDBOX:    ${{ secrets.CF_TOKEN_SANDBOX }}
    CF_TOKEN_STAGING:    ${{ secrets.CF_TOKEN_STAGING }}
    CF_TOKEN_PRODUCTION: ${{ secrets.CF_TOKEN_PRODUCTION }}
```

Never pass all three tokens to all workspaces — each CI job receives only the token for its target workspace.

## 3. Workspace-Aware Module Calls

```hcl
# main.tf
module "workers_platform" {
  source     = "./modules/workers-platform"
  account_id = local.cfg.account_id
  zone_id    = local.cfg.zone_id
  env        = local.cfg.environment
}

module "access_policies" {
  source     = "./modules/access-policies"
  account_id = local.cfg.account_id
  env        = local.cfg.environment
}
```

The modules receive only the resolved values; they have no workspace-awareness themselves, making them reusable and testable in isolation.

## 4. Promoting Resources Across Workspaces

Promotion follows a read-export-apply pattern rather than `terraform state mv` (which cannot cross backends):

```bash
#!/usr/bin/env bash
# scripts/promote.sh  -- promotes a module output from staging to production

SRC_WORKSPACE="staging"
DST_WORKSPACE="production"

# 1. Export the value from staging state
WORKER_NAME=$(terraform -chdir=. workspace select "$SRC_WORKSPACE" > /dev/null \
  && terraform output -raw worker_script_name)

# 2. Pass it as a variable override to production plan
terraform workspace select "$DST_WORKSPACE"
terraform plan \
  -var "promoted_worker_name=$WORKER_NAME" \
  -out promote.tfplan

# 3. Review and apply
terraform apply promote.tfplan
```

For Terraform Cloud/Enterprise, use Remote State Data Sources instead:

```hcl
# Cross-workspace state reference (Terraform Cloud only)
data "terraform_remote_state" "staging" {
  backend = "remote"
  config = {
    organization = "my-org"
    workspaces = {
      name = "cloudflare-staging"
    }
  }
}

locals {
  promoted_worker_name = data.terraform_remote_state.staging.outputs.worker_script_name
}
```

## 5. Preventing Cross-Account Blast Radius

```hcl
# guards.tf
variable "workspace_guard" {
  type        = string
  description = "Must match terraform.workspace to prevent accidental cross-account apply"
}

resource "null_resource" "workspace_guard" {
  triggers = {
    always = timestamp()
  }

  provisioner "local-exec" {
    command = <<-EOT
      if [ "${var.workspace_guard}" != "${terraform.workspace}" ]; then
        echo "ERROR: workspace_guard '${var.workspace_guard}' != current workspace '${terraform.workspace}'" >&2
        exit 1
      fi
    EOT
  }
}
```

In CI, pass `-var workspace_guard=$WORKSPACE` where `$WORKSPACE` is the confirmed deployment target from the pipeline trigger. A typo or copypaste error in variable passing causes an explicit, actionable failure rather than silent cross-account deployment.

## 6. Module-Level Protect for Production

```hcl
# modules/workers-platform/main.tf
resource "cloudflare_worker_script" "api" {
  account_id = var.account_id
  name       = "api-${var.env}"
  content    = file("${path.module}/../../dist/api.js")

  lifecycle {
    prevent_destroy = var.env == "production" ? true : false
    # Note: conditional prevent_destroy requires Terraform >= 1.8
  }
}
```

## Anti-patterns

- **Using a single shared API token across all workspaces** — a compromised sandbox token has production blast radius. Each workspace must use a token scoped to only its target account.
- **Storing all account IDs in `terraform.tfvars` committed to git** — account IDs are not secrets, but including them in plaintext with workspace names creates a roadmap for attackers. Store in CI variables.
- **`terraform apply` without `-var workspace_guard`** — allows silent drift when the wrong workspace is selected. Always enforce the guard in CI.
- **Using `terraform workspace` as a feature flag inside modules** — modules should receive values via variables, never call `terraform.workspace` directly. This breaks module reusability and testability.
- **Sharing the same Cloudflare zone across workspaces** — DNS changes in staging pollute production. Each environment should have its own zone or use subdomain delegation.

## Gotchas

- `terraform workspace select` does not switch provider credentials; only the state file path changes. Credential selection must happen through variables, environment variables, or provider `alias` configurations.
- `prevent_destroy` with a conditional expression requires Terraform ≥ 1.8. Earlier versions treat the lifecycle block as static.
- The Cloudflare provider caches the account ID in some resource types — if the wrong token is active, plan may succeed but apply will 403 when it hits an account ID mismatch.
- Terraform Cloud workspaces and CLI workspaces are different concepts. If using Terraform Cloud, use separate Terraform Cloud workspaces (not `terraform workspace select`) and leverage workspace variables for per-environment tokens.
- `data "terraform_remote_state"` across workspaces only works when both workspaces use the same backend type.

## Verification

```bash
# List workspaces and confirm current
terraform workspace list

# Confirm state is isolated per workspace
terraform workspace select staging
terraform state list | grep cloudflare_worker_script

terraform workspace select production
terraform state list | grep cloudflare_worker_script

# Verify correct account_id in current plan
terraform plan -var 'workspace_guard=staging' 2>&1 | grep account_id

# Confirm account in use matches expected
curl -s "https://api.cloudflare.com/client/v4/accounts" \
  -H "Authorization: Bearer $CF_TOKEN_STAGING" | jq '.result[].id'
```

## Related

- `cloudflare-workers-multi-account-failover.md` — runtime failover across accounts
- `cloudflare-account-organization-team-access.md` — org-level access and team permissions
- `iac-best-practices.md` — general IaC hygiene including state locking
- `terraform-state-management-remote-backend.md` — backend configuration and locking
- `sops-age-gitops-secrets-management.md` — encrypting account IDs and tokens in git

## Sources

- https://developer.hashicorp.com/terraform/language/state/workspaces
- https://developers.cloudflare.com/fundamentals/account/account-security/api-tokens/
- https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle
- https://developer.hashicorp.com/terraform/language/state/remote-state-data
- https://developers.cloudflare.com/fundamentals/setup/manage-members/
