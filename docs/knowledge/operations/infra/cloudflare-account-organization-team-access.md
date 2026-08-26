# Cloudflare Account Organization and Team Access

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A growing engineering team begins sharing a single Cloudflare account with one
set of API tokens. A contractor accidentally modifies a production DNS record.
An intern's token leaks and has write access to every Zone. The billing page
is visible to all developers. Access control is entirely ad-hoc. This article
establishes a structured account hierarchy, role taxonomy, and token policy.

## Context

Cloudflare's access model (2026) offers three layers:

1. **Account members** — human users with account-scoped roles (Super Admin,
   Administrator, Read Only, etc.) granted at invite time.
2. **API tokens** — scoped machine credentials attached to the account (not a
   user), granting exact resource/permission pairs with optional IP restrictions
   and expiry.
3. **Account-scoped policies** — available on Business and Enterprise plans;
   control SSO via Access, enforce MFA, and restrict which email domains may
   join as members.

Multi-account setups (separate accounts per environment or per product) and
Cloudflare for Teams (Zero Trust organization) compose on top of this.

---

## Section 1: Account Role Taxonomy and Member Invitation

Define a minimal role set and stick to it. Cloudflare's built-in roles:

| Role | Scope | Use |
|------|-------|-----|
| Super Administrator | Full account | Account owner only (one person) |
| Administrator | Full account minus billing/ownership transfer | Team leads |
| DNS Administrator | DNS only, all zones | Dedicated DNS team |
| Cloudflare Workers Admin | Workers + KV + D1 + R2 | Platform engineers |
| Analytics | Read-only analytics | Data / BI team |
| Billing | Billing page | Finance only |
| Firewall | WAF rules only | Security team |

Invite a member via the Cloudflare dashboard or API:

```bash
# List current members
curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/members" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {email: .user.email, roles: [.roles[].name]}'

# Invite a new member with Workers Admin role
# First, look up the role ID
ROLE_ID=$(curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/roles" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq -r '.result[] | select(.name=="Cloudflare Workers Admin") | .id')

curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/members" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"newdev@company.com\",
    \"roles\": [\"$ROLE_ID\"]
  }"
```

Automate member lifecycle with Terraform:

```hcl
# terraform/cloudflare-iam/members.tf
data "cloudflare_account_roles" "all" {
  account_id = var.cloudflare_account_id
}

locals {
  workers_admin_role_id = [
    for r in data.cloudflare_account_roles.all.roles :
    r.id if r.name == "Cloudflare Workers Admin"
  ][0]
}

resource "cloudflare_account_member" "platform_engineer" {
  for_each   = toset(var.platform_engineers)
  account_id = var.cloudflare_account_id
  email_address = each.value
  role_ids   = [local.workers_admin_role_id]
}
```

---

## Section 2: API Token Policy and Scoping

Never use Global API Keys. Every integration gets its own scoped API token
with the minimal required permissions.

```bash
# Create a scoped API token: read/write Workers in one zone only
curl -X POST "https://api.cloudflare.com/client/v4/user/tokens" \
  -H "Authorization: Bearer $CF_MASTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ci-deploy-prod-zone",
    "policies": [
      {
        "effect": "allow",
        "resources": {
          "com.cloudflare.api.account.zone.'"$ZONE_ID"'": "*"
        },
        "permission_groups": [
          {"id": "e17beae8b8cb423a99b1730f21238bed"},
          {"id": "c8fed203ed3043cba015a93ad1616fb8"}
        ]
      }
    ],
    "condition": {
      "request.ip": {
        "in": ["10.0.0.0/8", "203.0.113.0/24"]
      }
    },
    "not_before": "2026-08-22T00:00:00Z",
    "expires_on": "2027-08-22T00:00:00Z"
  }'
```

Common permission group IDs (verify these in your account with GET /user/tokens/permission_groups):

```
Workers Scripts Edit:   e17beae8b8cb423a99b1730f21238bed
Workers Scripts Read:   9d24387c6e8544e2bc4024a03991339a
DNS Write:              4755a26eedb94da69e1066d98aa820be
Zone Settings Edit:     3030687196b94b638145a3953da2b699
R2 Write:               2efd5506f9c8494dacb1fa10a3e7d5b6
D1 Write:               d2a7bb7872b74e5684d1b4dfd4a49ec9
Analytics Read:         8acbe5bb09c54c57fd3e71a583c85faa
Billing Read:           f12bfbf4e6b24bfe9f08050c9c7b2649
```

Token management as code:

```hcl
# terraform/cloudflare-iam/tokens.tf
resource "cloudflare_api_token" "ci_workers_deploy" {
  name = "ci-workers-deploy-${var.environment}"

  policy {
    effect = "allow"
    resources = {
      "com.cloudflare.api.account.zone.${var.zone_id}" = "*"
    }
    permission_groups = [
      data.cloudflare_api_token_permission_groups.all.permissions["Workers Scripts Write"],
      data.cloudflare_api_token_permission_groups.all.permissions["Workers Routes Write"],
    ]
  }

  condition {
    request_ip {
      in = var.allowed_cidr_blocks
    }
  }

  not_before = "2026-08-22T00:00:00Z"
  expires_on = "2027-08-22T23:59:59Z"
}

output "ci_workers_token" {
  value     = cloudflare_api_token.ci_workers_deploy.value
  sensitive = true
}
```

Store token values in your secrets manager (Vault, AWS Secrets Manager) rather
than in CI environment variables where they appear in plaintext logs.

---

## Section 3: Multi-Account Environment Isolation

For teams managing production and non-production environments, separate Cloudflare
accounts eliminate blast radius from misconfigured rules or accidental deletions.

Recommended structure:

```
Cloudflare Organization
├── account: company-production
│   ├── zone: company.com
│   ├── Workers: all production scripts
│   ├── D1: production databases
│   └── R2: production buckets
├── account: company-staging
│   ├── zone: staging.company.com (or separate domain)
│   ├── Workers: staging scripts (deployed from PRs)
│   └── D1: staging databases
└── account: company-dev
    ├── zone: dev.company.internal (Cloudflare Tunnel)
    └── Workers: experimental
```

Wire Wrangler to the correct account per environment:

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"
account_id = "PROD_ACCOUNT_ID"   # production default

[env.staging]
account_id = "STAGING_ACCOUNT_ID"
name = "my-worker-staging"

[env.dev]
account_id = "DEV_ACCOUNT_ID"
name = "my-worker-dev"
```

```bash
# Deploy to staging account
wrangler deploy --env staging

# Deploy to production account
CLOUDFLARE_API_TOKEN=$PROD_TOKEN wrangler deploy
```

Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` environment variables
in CI rather than hardcoding in wrangler.toml. The environment variable takes
precedence over the TOML value.

Audit cross-account access: no human should hold Super Admin in both production
and non-production simultaneously. Separate email aliases (`devops-prod@company.com`,
`devops-staging@company.com`) make the boundary explicit in the audit log.

---

## Anti-patterns

- **Sharing the Global API Key**: it bypasses all scoping and cannot be rotated
  without generating a new key. Every integration that used it must be updated
  simultaneously—an operational disaster.
- **One token for all CI pipelines**: if the token leaks, every pipeline is
  compromised. Issue one token per pipeline or per service.
- **Super Admin for all engineers**: Super Admin can transfer domain ownership,
  delete the account, and modify billing. Only the account owner needs it.
- **Never-expiring tokens with no IP restriction**: even if a token never leaks
  deliberately, it may be exposed in a log. Set a 1-year expiry and restrict
  to known CI CIDR ranges.
- **Manual member management**: as the team grows, manual invitation becomes
  error-prone. Codify membership in Terraform from day one.
- **Single account for all environments**: a WAF rule misconfiguration pushed
  to production while testing blocks real traffic. Environment isolation is
  non-negotiable for business-critical zones.

---

## Gotchas

- Cloudflare account membership does not inherit to sub-accounts. You must
  explicitly manage membership in each account.
- The `cloudflare_account_member` Terraform resource sends a re-invitation email
  every `terraform apply` if the member has not yet accepted. Build an acceptance
  workflow or use `lifecycle { ignore_changes = [status] }`.
- API token permission group IDs change between API versions. Always look them up
  dynamically via `GET /user/tokens/permission_groups` rather than hardcoding.
- Removing a member via the API immediately revokes access but does not invalidate
  any API tokens that member may have created personally. Audit and rotate tokens
  when offboarding.
- Cloudflare Access (Zero Trust) and account membership are distinct; a user can
  be an Access policy subject without being an account member, and vice versa.
- Free and Pro plan accounts cannot restrict which email domains may join. You
  need Business or Enterprise for domain-locked invitations.

---

## Verification

```bash
# List all members and their roles
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/members" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq -r '.result[] | "\(.user.email)\t\([.roles[].name] | join(", "))"'

# Verify a token's permissions (use the token itself, not master)
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $THE_TOKEN_TO_CHECK" | jq .

# List all tokens on the account (requires account:read permission)
curl -s "https://api.cloudflare.com/client/v4/user/tokens" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq -r '.result[] | "\(.name)\t expires: \(.expires_on // "never")"'

# Terraform plan should show no unexpected membership changes
terraform -chdir=terraform/cloudflare-iam plan
```

Expected: every member has exactly the role they need, no member holds Super Admin
other than the account owner, and every token has an expiry date and IP condition.

---

## Related

- `/documentation/docs/policies/infra/cloudflare-dns-api.md`
- `/documentation/docs/policies/infra/terraform-cloudflare-provider-workers-d1.md`
- `/documentation/docs/policies/infra/secrets-management-vault.md`
- `/documentation/docs/policies/infra/aws-iam-least-privilege.md`
- `/documentation/docs/policies/infra/zero-trust-network-access.md`

---

## Sources

- Cloudflare API Token documentation: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- Cloudflare Account Members API: https://developers.cloudflare.com/api/resources/accounts/subresources/members/
- Terraform Cloudflare provider — account_member: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/account_member
- Cloudflare Zero Trust Access: https://developers.cloudflare.com/cloudflare-one/
- Cloudflare multi-account best practices: https://developers.cloudflare.com/fundamentals/account/account-security/
