# Cloudflare Zero Trust: Staging/Production Environment Isolation

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

Developers with production Cloudflare account access can accidentally deploy to production
instead of staging. A staging Worker that is misconfigured to use the production D1 database
corrupts real user data. A security researcher scanning the staging subdomain discovers an
unauthenticated endpoint that mirrors production API logic. A CI pipeline misconfiguration
runs database migrations against production when the environment variable `ENVIRONMENT` is
absent. All of these failures share a root cause: staging and production are not hard-isolated
— they share credentials, network access paths, or trust boundaries.

## Context

Cloudflare Zero Trust (CZT) provides the controls needed to make staging and production
genuinely separate environments at the network, identity, and application layers — not just
at the naming layer. This article is specifically about isolating Cloudflare-stack
workloads (Workers, D1, KV, R2, Durable Objects) from each other, complementing the generic
ZTNA perimeter controls in `zero-trust-network-access.md`.

The isolation strategy operates at four layers:
1. **Account-level separation** — staging on a separate Cloudflare account
2. **Access application policies** — staging routes require authentication; prod does not
3. **Network egress policies** — staging Workers cannot reach production data stores
4. **Deploy-time controls** — IaC policies that prevent cross-environment resource references

---

## Section 1: Account-Level Separation

The strongest isolation boundary is a separate Cloudflare account for staging. Workers,
KV namespaces, D1 databases, and R2 buckets in Account B (staging) have no resource-level
relationship to Account A (production). A developer mistake in staging cannot affect the
production account.

Account mapping:

| Account | Purpose | Allowed teams |
|---|---|---|
| `cf-prod` | Production only | Platform + on-call engineers |
| `cf-staging` | Staging + QA | All engineering |
| `cf-dev` | Per-developer sandboxes | Each developer's own sub-account |
| `cf-ops` | DNS zone, ZTNA policies, billing | Platform only |

Use Cloudflare's **Account Memberships** with separate roles per account. The email
`developer@org.com` is a member of `cf-staging` with `Workers Admin` but has no membership
in `cf-prod`.

```bash
# Add a developer to staging account only via API
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_STAGING_ACCOUNT_ID/members" \
  -H "Authorization: Bearer $CF_OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "developer@org.com",
    "roles": ["Workers Admin"]
  }' | jq '.success'

# Confirm they are NOT in prod
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_PROD_ACCOUNT_ID/members" \
  -H "Authorization: Bearer $CF_OPS_TOKEN" \
  | jq '.result[] | select(.user.email == "developer@org.com")'
# Expected: empty result
```

---

## Section 2: Cloudflare Access Policies on Staging Routes

The staging Worker route (`staging-api.example.com`) should require authentication so that:
- External scanners cannot enumerate staging endpoints
- Staging data cannot be accidentally treated as production by external integrations
- Access logs capture who accessed staging for audit

Cloudflare Access wraps the staging route with an identity check before the request reaches
the Worker.

```hcl
# terraform/access-policies.tf
resource "cloudflare_access_application" "staging_api" {
  provider         = cloudflare.ops
  zone_id          = var.cf_zone_id_ops
  name             = "Staging API"
  domain           = "staging-api.example.com"
  type             = "self_hosted"
  session_duration = "8h"

  # Only org-domain users, not guests
  allowed_idps = [var.okta_idp_id]
}

resource "cloudflare_access_policy" "staging_api_allow" {
  provider       = cloudflare.ops
  application_id = cloudflare_access_application.staging_api.id
  zone_id        = var.cf_zone_id_ops
  name           = "Allow org employees"
  precedence     = 1
  decision       = "allow"

  include {
    email_domain = ["yourorg.com"]
  }

  # CI/CD pipeline uses a service token to bypass interactive login
  include {
    service_token = [cloudflare_access_service_token.ci_staging.id]
  }

  require {
    # Require device posture: must be running WARP with corporate certificate
    device_posture = [var.warp_posture_check_id]
  }
}

resource "cloudflare_access_policy" "staging_api_deny_all" {
  provider       = cloudflare.ops
  application_id = cloudflare_access_application.staging_api.id
  zone_id        = var.cf_zone_id_ops
  name           = "Deny everyone else"
  precedence     = 2
  decision       = "deny"

  include {
    everyone = true
  }
}

# Service token for CI — no human login needed
resource "cloudflare_access_service_token" "ci_staging" {
  provider   = cloudflare.ops
  account_id = var.cf_account_id_ops
  name       = "CI staging access"
  min_days_for_renewal = 30
}
```

Production routes do NOT have an Access application in front — they are public by design.
Staging routes do. This is the key asymmetry.

---

## Section 3: Worker Egress Policies

Even with account separation, a staging Worker might receive a production `DATABASE_URL` via
a misconfigured secret. Cloudflare Zero Trust **Gateway Egress Policies** restrict which
external hosts a Worker can connect to by IP or hostname.

Configure Gateway HTTP policies in the ops account to block staging Workers from reaching
production data hosts:

```hcl
# Gateway policy: staging Workers cannot reach prod DB endpoints
resource "cloudflare_teams_rule" "block_staging_to_prod_db" {
  provider    = cloudflare.ops
  account_id  = var.cf_account_id_ops
  name        = "Block staging → prod database"
  description = "Prevents staging Workers from calling production PostgreSQL endpoints"
  precedence  = 10
  action      = "block"
  enabled     = true

  filters = ["http"]

  traffic = <<-EOT
    http.request.host in {"prod-db.internal.example.com" "prod-db-replica.internal.example.com"}
    and (cf.edge.server_ip in $staging_worker_egress_ips)
  EOT
}
```

Where `$staging_worker_egress_ips` is a Gateway List containing the egress IP ranges
assigned to the staging Cloudflare account. Obtain these from the Cloudflare dashboard
under **Zero Trust → Settings → Network → Egress**.

For Worker-to-Worker calls, use **Service Bindings** in wrangler.toml — these are
account-scoped by definition, so a staging Worker binding cannot point to a production
Worker.

```toml
# wrangler.toml (staging)
[env.staging]
name = "api-worker-staging"

[[env.staging.services]]
binding = "AUTH_SERVICE"
service = "auth-worker-staging"  # explicitly staging service name

# Production config — different wrangler.toml or env block
[env.production]
name = "api-worker-production"

[[env.production.services]]
binding = "AUTH_SERVICE"
service = "auth-worker-production"
```

---

## Section 4: IaC Policy Enforcement (Checkov)

Terraform plans that reference a production resource from a staging resource should fail
CI. Use Checkov custom checks:

```python
# .checkov/CF_CUSTOM_001_no_staging_prod_cross_ref.py
from checkov.common.models.enums import CheckResult, CheckCategories
from checkov.terraform.checks.resource.base_resource_check import BaseResourceCheck

class StagingProdCrossRefCheck(BaseResourceCheck):
    def __init__(self):
        name = "Ensure staging resources do not reference production resources"
        id = "CF_CUSTOM_001"
        supported_resources = [
            "cloudflare_worker_script",
            "cloudflare_kv_namespace",
        ]
        categories = [CheckCategories.GENERAL_SECURITY]
        super().__init__(name=name, id=id, categories=categories,
                         supported_resources=supported_resources)

    def scan_resource_conf(self, conf):
        resource_name = conf.get("name", [""])[0]
        # Staging resources must not reference prod account IDs or prod-named bindings
        if "staging" in resource_name:
            plain_text_bindings = conf.get("plain_text_binding", [])
            for binding in plain_text_bindings:
                if isinstance(binding, dict):
                    value = binding.get("text", [""])[0]
                    if "prod" in str(value).lower() or var.cf_account_id_primary in str(value):
                        return CheckResult.FAILED
        return CheckResult.PASSED

check = StagingProdCrossRefCheck()
```

```yaml
# .github/workflows/tf-security.yml
- name: Run Checkov on Terraform
  uses: bridgecrewio/checkov-action@v12
  with:
    directory: terraform/
    check: CF_CUSTOM_001
    external-checks-dir: .checkov/
```

---

## Section 5: Secrets Namespace Isolation

Staging and production must use separate secrets. Enforce this via naming conventions
and access control on the secrets store.

For Cloudflare Workers secrets, Wrangler's `--env` flag scopes secrets to an environment:

```bash
# Staging secret — stored in staging account context
wrangler secret put DATABASE_URL \
  --account-id "$CF_STAGING_ACCOUNT_ID" \
  --name api-worker-staging

# Production secret — stored in production account context
wrangler secret put DATABASE_URL \
  --account-id "$CF_PROD_ACCOUNT_ID" \
  --name api-worker-production
```

For Vault-sourced secrets, use separate Vault namespaces:

```hcl
# vault/secrets.tf
resource "vault_namespace" "staging" {
  path = "staging"
}

resource "vault_namespace" "production" {
  path = "production"
}

# Staging team can only read from staging namespace
resource "vault_policy" "staging_readers" {
  name = "staging-readers"

  policy = <<-EOT
    path "staging/cloudflare/*" {
      capabilities = ["read", "list"]
    }

    # Explicitly deny prod namespace
    path "production/*" {
      capabilities = ["deny"]
    }
  EOT
}
```

---

## Section 6: Observability — Detecting Cross-Environment Calls

Even with isolation, monitor for anomalies:

```typescript
// cross-env-detector/src/index.ts — Tail Worker attached to all production Workers
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      const logs = event.logs ?? [];
      for (const log of logs) {
        const message = String(log.message);
        // Alert if production Worker logs reference staging hostnames
        if (message.includes('staging') || message.includes('dev.workers.dev')) {
          console.error('CROSS_ENV_CALL_DETECTED', {
            worker: event.scriptName,
            message,
            ts: event.eventTimestamp,
          });
          // Page on-call
          await notifyOncall(event);
        }
      }
    }
  },
};
```

```bash
# Query Cloudflare Logpush for cross-env patterns
# (Requires Logpush to R2 or a SIEM)
jq 'select(.Outcome == "ok") | select(.Message | test("staging|dev.workers.dev"))' \
  /path/to/logpush/workers-trace-2026-08-22.json
```

---

## Anti-Patterns

- **Using the same Cloudflare account with different Worker names for staging vs prod** —
  this is naming isolation, not real isolation. A malformed Wrangler command with the wrong
  `--name` deploys to the wrong Worker. Use separate accounts.
- **Storing staging and prod secrets in the same secret manager path** — if the path
  `cloudflare/api-token` is shared, a staging script reading the wrong key gets prod access.
- **Putting Access in front of staging but not enforcing device posture** — an attacker who
  steals an org email account bypasses the Access policy. Require WARP enrollment + posture
  check as a second factor.
- **Allowing all internal Worker-to-Worker calls** — without Service Binding account
  scoping awareness, a staging Worker making HTTP calls to `https://auth-worker.example.com`
  hits the production Cloudflare Route, not the staging one. Always use Service Bindings
  or environment-specific hostnames.
- **Sharing R2 buckets across environments** — even with prefix-based separation, a
  misconfigured lifecycle rule or sync job can overwrite production objects from a staging
  bucket. Separate buckets in separate accounts.

---

## Gotchas

- Cloudflare Access service tokens used by CI expire. When a service token is not renewed
  before expiry, CI staging deployments start failing with 403. Set calendar reminders or
  automate renewal via the Access API.
- Gateway Egress Policies apply to WARP-enrolled devices and cloudflared tunnels, not to
  Workers directly unless Cloudflare Tunnel is used for egress. Confirm the routing model
  for your Worker egress before relying on Gateway to enforce isolation.
- The `cloudflare_teams_rule` Terraform resource applies globally to the account. A
  misconfigured policy that is too broad can block legitimate production traffic. Test all
  Gateway policies in report-only mode (`action = "block"` → `action = "allow"` first,
  with logging) before enforcing.
- Cloudflare Access JWT cookies are issued per zone. A cross-subdomain Access configuration
  (`staging-api.example.com` and `staging-admin.example.com`) requires a wildcard cookie
  domain or separate Access applications for each subdomain.

---

## Verification

```bash
# 1. Confirm staging Access application exists and requires auth
curl -s "https://staging-api.example.com/health" \
  | jq '.error'
# Expected: "access denied" or redirect to CF Access login

# 2. Confirm CI can authenticate with service token
curl -s \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  "https://staging-api.example.com/health" \
  | jq '.status'
# Expected: "ok"

# 3. Confirm production is NOT behind Access
curl -s "https://api.example.com/health" | jq '.status'
# Expected: "ok" without any auth headers

# 4. List account members — verify no staging-only dev appears in prod account
cf_members() {
  curl -s \
    "https://api.cloudflare.com/client/v4/accounts/$1/members" \
    -H "Authorization: Bearer $CF_OPS_TOKEN" \
    | jq -r '.result[].user.email'
}
comm -12 <(cf_members "$CF_STAGING_ACCOUNT_ID" | sort) \
         <(cf_members "$CF_PROD_ACCOUNT_ID" | sort)
# Should only show platform team members, not general dev team
```

---

## Related Articles

- `zero-trust-network-access.md` — general ZTNA/VPN replacement strategy
- `cloudflare-account-organization-team-access.md` — account role design
- `cloudflare-workers-multi-account-failover.md` — multi-account DR uses same account topology
- `vault-dynamic-secrets-cloudflare-workers.md` — secrets scoping to environments
- `wrangler-toml-multi-environment-config.md` — env-specific wrangler configuration

---

## Sources

- Cloudflare Access documentation: https://developers.cloudflare.com/cloudflare-one/policies/access/
- Cloudflare Gateway HTTP policies: https://developers.cloudflare.com/cloudflare-one/policies/gateway/http-policies/
- Service Bindings documentation: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Checkov Terraform custom checks: https://www.checkov.io/3.Custom%20Policies/Python%20Custom%20Policies.html
- Cloudflare Access service tokens: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
