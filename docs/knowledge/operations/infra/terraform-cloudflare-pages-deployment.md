# Terraform: Managing Cloudflare Pages Deployments as IaC

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Cloudflare Pages projects are created manually in the dashboard and drift from the desired state;
branch-preview environments, custom domains, and build configs are inconsistent across projects.

## Context
The Cloudflare Terraform provider (`cloudflare/cloudflare`) exposes `cloudflare_pages_project`
and `cloudflare_pages_domain` resources that model Pages projects as declarative HCL.
Pairing this with `cloudflare_pages_deployment` (data source) and GitHub Actions OIDC allows
fully automated, auditable Pages infrastructure without dashboard clicks.
Build steps still run inside Cloudflare's build system; Terraform only manages project config and routing.

## Provider Setup and Remote State

```hcl
# terraform/providers.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "orchords-tf-state"
    key            = "cloudflare/pages/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

```hcl
# terraform/variables.tf
variable "cloudflare_api_token" {
  description = "API token with Pages:Edit and DNS:Edit permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "zone_id" {
  description = "Zone ID for custom domain routing"
  type        = string
}
```

## Pages Project Resource

```hcl
# terraform/pages.tf
resource "cloudflare_pages_project" "frontend" {
  account_id        = var.cloudflare_account_id
  name              = "orchords-frontend"
  production_branch = "main"

  build_config {
    build_command       = "pnpm run build"
    destination_dir     = "dist"
    root_dir            = "apps/web"
    web_analytics_token = var.web_analytics_token  # optional RUM
  }

  source {
    type = "github"
    config {
      owner                         = "orchords"
      repo_name                     = "monorepo"
      production_branch             = "main"
      pr_comments_enabled           = true
      deployments_enabled           = true
      production_deployment_enabled = true
      preview_branch_includes       = ["staging", "feat/*"]
      preview_branch_excludes       = ["dependabot/*"]
    }
  }

  deployment_configs {
    production {
      environment_variables = {
        NODE_VERSION = "22"
        NEXT_PUBLIC_API_URL = "https://api.example.com"
      }
      secrets = {
        STRIPE_SECRET_KEY = var.stripe_secret_key
      }
      kv_namespaces = {
        SESSION_STORE = cloudflare_workers_kv_namespace.sessions.id
      }
      compatibility_date  = "2026-01-01"
      compatibility_flags = ["nodejs_compat"]
    }

    preview {
      environment_variables = {
        NODE_VERSION = "22"
        NEXT_PUBLIC_API_URL = "https://api.staging.example.com"
      }
      secrets = {
        STRIPE_SECRET_KEY = var.stripe_secret_key_test
      }
      compatibility_date  = "2026-01-01"
      compatibility_flags = ["nodejs_compat"]
    }
  }
}
```

## Custom Domain and DNS Wiring

```hcl
# terraform/domains.tf
resource "cloudflare_pages_domain" "production" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.frontend.name
  domain       = "example.com"
}

resource "cloudflare_pages_domain" "www" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.frontend.name
  domain       = "www.example.com"
}

# CNAME record pointing to Pages deployment subdomain
resource "cloudflare_dns_record" "pages_root" {
  zone_id = var.zone_id
  name    = "example.com"
  type    = "CNAME"
  content = "${cloudflare_pages_project.frontend.subdomain}"
  proxied = true
  ttl     = 1  # auto when proxied
}

resource "cloudflare_dns_record" "pages_www" {
  zone_id = var.zone_id
  name    = "www"
  type    = "CNAME"
  content = "${cloudflare_pages_project.frontend.subdomain}"
  proxied = true
  ttl     = 1
}
```

## Outputs and Data Sources

```hcl
# terraform/outputs.tf
output "pages_subdomain" {
  value       = cloudflare_pages_project.frontend.subdomain
  description = "Default *.pages.dev subdomain"
}

output "pages_project_name" {
  value = cloudflare_pages_project.frontend.name
}

# Read the latest production deployment (useful in CI)
data "cloudflare_pages_deployment" "latest_prod" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.frontend.name
  id           = "latest"
}

output "latest_deployment_url" {
  value = data.cloudflare_pages_deployment.latest_prod.url
}
```

## CI/CD Integration with GitHub Actions OIDC

```yaml
# .github/workflows/tf-pages.yml
name: Terraform Pages

on:
  push:
    branches: [main]
    paths: ["terraform/pages/**"]
  pull_request:
    paths: ["terraform/pages/**"]

permissions:
  id-token: write
  contents: read

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/tf-state-reader
          aws-region: us-east-1

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.10.x"

      - run: terraform -chdir=terraform/pages init
      - run: terraform -chdir=terraform/pages plan -out=tfplan
        env:
          TF_VAR_cloudflare_api_token: ${{ secrets.CF_API_TOKEN }}
          TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}
          TF_VAR_zone_id: ${{ secrets.CF_ZONE_ID }}

  apply:
    needs: plan
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: terraform -chdir=terraform/pages apply -auto-approve tfplan
        env:
          TF_VAR_cloudflare_api_token: ${{ secrets.CF_API_TOKEN }}
```

## Anti-patterns
- Storing the Cloudflare API token in `terraform.tfvars` committed to the repo
- Using a Global API Key instead of a scoped API token (`Pages:Edit`, `DNS:Edit` only)
- Managing build output artifacts in Terraform — Cloudflare's build system handles that
- Creating Pages projects with `force_destroy = false` when a pipeline can recreate them; this causes stuck deletes
- Mixing Pages domain resources with Cloudflare `cloudflare_record` with wrong proxied settings, causing CNAME loop

## Gotchas
- `cloudflare_pages_domain` will stay in `Pending` state until Cloudflare verifies DNS; Terraform apply can time out — re-run after DNS propagates
- `secrets` in `deployment_configs` are write-only; `terraform plan` will always show a diff if the sensitive value changes in the variable
- `production_branch` must match exactly; a renamed default branch (`master` → `main`) requires a `terraform apply`
- KV namespace bindings reference the namespace ID, not the name — ensure KV resources are in the same root module or use a remote state data source
- `web_analytics_token` is distinct from Web Analytics Site tags; provision separately via `cloudflare_web_analytics_site`

## Verification
```bash
# Confirm project exists
terraform -chdir=terraform/pages state show cloudflare_pages_project.frontend

# Validate domain status via Cloudflare API
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/orchords-frontend/domains" \
  | jq '.result[] | {domain, status}'

# Check DNS propagation
dig +short CNAME example.com
```

## Related
- `/documentation/docs/policies/infra/terraform-cloudflare-provider-workers-d1.md`
- `/documentation/docs/policies/infra/cloudflare-account-organization-team-access.md`
- `/documentation/docs/policies/infra/dns-management-2026.md`
- `/documentation/docs/policies/infra/github-actions-oidc-cloudflare.md`

## Sources
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/pages_project
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/pages_domain
- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
