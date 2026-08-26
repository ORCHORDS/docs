# Terraform Cloudflare Access Application Policy

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project platform runs internal tooling — an admin dashboard, a Grafana instance, a Wrangler
tail log viewer — that must be reachable by the engineering team but not the public. Manually
maintaining allow-lists in the Cloudflare Zero Trust dashboard leads to configuration drift
between staging and production and makes onboarding/offboarding error-prone. Terraform should
own the full lifecycle of Access Applications and their associated Policies so team membership
changes are expressed as pull requests.

## Context

Cloudflare Zero Trust Access (`cloudflare_access_application` + `cloudflare_access_policy`)
provides identity-aware proxy enforcement in front of any origin. Users authenticate via an
identity provider (GitHub OAuth, Google Workspace, OTP email) before Cloudflare forwards the
request. The Terraform provider exposes both resources and their relationship through a
`application_id` reference on the policy. Provider version ≥ 4.38 is required for the
`reusable_policies` block introduced in 2025.

## Resource Definition — cloudflare_access_application

The application resource binds a Zero Trust policy to a domain or hostname. For example project the
admin dashboard lives at `admin.example.com` behind HTTPS.

```hcl
resource "cloudflare_access_application" "admin_dashboard" {
  account_id       = var.cloudflare_account_id
  name             = "example project Admin Dashboard"
  domain           = "admin.example.com"
  type             = "self_hosted"
  session_duration = "8h"

  # Prevent users from bypassing Access via a direct origin request
  app_launcher_visible = false

  # CORS settings for the SPA
  cors_headers {
    allowed_origins = ["https://admin.example.com"]
    allowed_methods = ["GET", "POST", "OPTIONS"]
    allow_credentials = true
    max_age           = 86400
  }

  # Show a custom block page instead of a generic 403
  custom_deny_message = "Access to the example project admin panel is restricted to team members."
  custom_deny_url     = "https://example.com/denied"
}

resource "cloudflare_access_application" "grafana" {
  account_id       = var.cloudflare_account_id
  name             = "example project Grafana"
  domain           = "metrics.example.com"
  type             = "self_hosted"
  session_duration = "24h"
  app_launcher_visible = true
}
```

## Configuration — cloudflare_access_policy

Policies define the allow/deny rules. Each application can have multiple policies evaluated
in precedence order. example project uses a GitHub OAuth IdP; team membership is checked via the
`github_organization` rule.

```hcl
data "cloudflare_access_identity_provider" "github" {
  account_id = var.cloudflare_account_id
  name       = "GitHub"
}

# Allow policy: engineering team via GitHub org membership
resource "cloudflare_access_policy" "admin_allow" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_access_application.admin_dashboard.id
  name           = "Allow example project Engineering Team"
  decision       = "allow"
  precedence     = 1

  include {
    github {
      name                 = "example project-engineering"       # GitHub org name
      identity_provider_id = data.cloudflare_access_identity_provider.github.id
      teams                = ["core-backend", "infra"]  # GitHub team slugs
    }
  }

  require {
    # Enforce email domain as a second check
    email_domain = ["example.com"]
  }
}

# Bypass policy: allow Cloudflare IPs for health-check routes
resource "cloudflare_access_policy" "health_bypass" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_access_application.admin_dashboard.id
  name           = "Bypass Health Check"
  decision       = "bypass"
  precedence     = 0   # evaluated first

  include {
    ip_range = ["103.21.244.0/22", "103.22.200.0/22"]  # CF health-check CIDRs
  }
}

# Service token policy: allow automated CI/CD scraping of Grafana
resource "cloudflare_access_service_token" "ci_grafana" {
  account_id = var.cloudflare_account_id
  name       = "CI Grafana Reader"
  min_days_for_renewal = 30
}

resource "cloudflare_access_policy" "grafana_ci_allow" {
  account_id     = var.cloudflare_account_id
  application_id = cloudflare_access_application.grafana.id
  name           = "Allow CI Service Token"
  decision       = "allow"
  precedence     = 0

  include {
    service_token = [cloudflare_access_service_token.ci_grafana.id]
  }
}
```

## CI Integration — State and Secrets

Service token credentials are sensitive outputs. Store them in GitHub Actions secrets via
Terraform output.

```hcl
# outputs.tf
output "ci_grafana_client_id" {
  value     = cloudflare_access_service_token.ci_grafana.client_id
  sensitive = false  # client_id is public
}

output "ci_grafana_client_secret" {
  value     = cloudflare_access_service_token.ci_grafana.client_secret
  sensitive = true
}
```

```yaml
# .github/workflows/access-policy-deploy.yml
name: Apply Zero Trust Access Policies

on:
  push:
    branches: [main]
    paths: ["infra/access/**"]

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Terraform Init
        working-directory: infra/access
        run: terraform init
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Terraform Apply
        working-directory: infra/access
        run: terraform apply -auto-approve
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Export service token to GitHub secrets
        run: |
          SECRET=$(terraform -chdir=infra/access output -raw ci_grafana_client_secret)
          gh secret set CF_ACCESS_CLIENT_SECRET --body "$SECRET"
        env:
          GH_TOKEN: ${{ secrets.GH_PAT }}
```

## Reusable Policies (Provider ≥ 4.38)

For shared rules (e.g., "any engineer can access") extract a reusable policy that multiple
applications reference, avoiding duplication.

```hcl
resource "cloudflare_access_policy" "engineering_reusable" {
  account_id = var.cloudflare_account_id
  name       = "example project Engineering Team — Reusable"
  decision   = "allow"
  # No application_id = this is a standalone reusable policy

  include {
    github {
      name                 = "example project-engineering"
      identity_provider_id = data.cloudflare_access_identity_provider.github.id
    }
  }
}

resource "cloudflare_access_application" "tail_log_viewer" {
  account_id       = var.cloudflare_account_id
  name             = "Wrangler Tail Log Viewer"
  domain           = "logs.example.com"
  type             = "self_hosted"
  session_duration = "4h"

  policies = [cloudflare_access_policy.engineering_reusable.id]
}
```

## Anti-patterns

- Setting `precedence` to the same value on two policies in the same application — Cloudflare
  evaluates them in arbitrary order and the result is non-deterministic.
- Omitting the `require` block on allow policies — without a hard requirement (email domain,
  country, IP range) a compromised IdP account grants immediate access.
- Using `decision = "bypass"` for entire applications instead of specific paths — bypass
  removes Access enforcement completely; prefer per-path service token policies.
- Storing service token client secrets in Terraform state unencrypted — use a remote backend
  (Terraform Cloud, S3 + KMS) with encryption at rest.
- Granting all team members access to production admin tools — segment by GitHub team slug
  and require PagerDuty on-call membership for destructive operations.

## Gotchas

- Destroying a `cloudflare_access_application` also revokes all active sessions immediately,
  logging out every user — schedule maintenance windows for policy teardowns.
- `cloudflare_access_service_token` regenerates `client_secret` on every `terraform apply`
  if `min_days_for_renewal` is not set; set it to avoid unnecessary secret rotations in CI.
- The `github` rule block requires the Cloudflare GitHub IdP to be pre-configured in the
  Zero Trust dashboard — it cannot be provisioned by Terraform in the same apply.
- Applications of type `self_hosted` require a Cloudflare-proxied DNS record for the domain;
  a DNS-only (grey-cloud) record will not enforce Access.
- `session_duration` strings must use Cloudflare's format (`"8h"`, `"1d"`, `"720h"`) — Go
  duration strings like `"8h0m0s"` are rejected.

## Verification

```bash
# List applications and confirm domain mapping
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {name, domain, session_duration}'

# List policies for the admin dashboard application
APP_ID=$(terraform -chdir=infra/access output -raw admin_dashboard_app_id)
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {name, decision, precedence}'

# Attempt unauthenticated access — should return 302 to Access login
curl -sI https://admin.example.com | grep -E "^(HTTP|location:)"
```

## Related

- `cloudflare-access-self-service-app-provisioning.md` — self-service app onboarding patterns
- `cloudflare-zero-trust-staging-prod-isolation.md` — separating staging and production Access policies
- `cloudflare-workers-api-token-scoping.md` — scoping API tokens for Access policy CI deployment
- `zero-trust-network-access.md` — Zero Trust network architecture overview

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/access_application
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/access_policy
- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
