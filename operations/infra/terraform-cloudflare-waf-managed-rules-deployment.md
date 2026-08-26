# Terraform Cloudflare WAF Managed Rules Deployment

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to deploy Cloudflare's WAF Managed Rulesets — Cloudflare Managed Rules,
OWASP Core Rule Set, Cloudflare Exposed Credentials Check — across multiple zones via
Terraform, with per-rule override capability and a consistent review/approval gate in CI.
The dashboard UI does not scale past a handful of zones and manual config drifts quickly.

## Context

Cloudflare WAF Managed Rules are account-scoped rulesets that you *deploy* at the zone
level via an `execute` action ruleset. There are three distinct Terraform resource types
in play:

| Resource | Purpose |
|---|---|
| `cloudflare_ruleset` (zone phase `http_request_firewall_managed`) | Deploys managed rulesets to a zone with overrides |
| `cloudflare_ruleset` (account phase `http_request_firewall_managed`) | Deploys to all zones in an account |
| Data source: API to list available managed ruleset IDs | Discover rule IDs before writing overrides |

The primary managed ruleset IDs (account-level, stable):
- Cloudflare Managed Rules: `efb7b8c949ac4650a09736fc376e9aee`
- Cloudflare OWASP: `4814384a9e5d4991b9815dcfc25d2f1f`
- Cloudflare Exposed Credentials Check: `c2e184081120413c86c3ab7e14069605`

---

## Section 1 — Enable Managed Rules on a Zone (Basic)

```hcl
# terraform/waf_managed.tf

variable "cloudflare_zone_id" { type = string }
variable "cloudflare_account_id" { type = string }

locals {
  # Cloudflare Managed Ruleset ID (stable, account-wide)
  cf_managed_ruleset_id  = "efb7b8c949ac4650a09736fc376e9aee"
  owasp_ruleset_id       = "4814384a9e5d4991b9815dcfc25d2f1f"
}

resource "cloudflare_ruleset" "zone_waf_managed" {
  zone_id     = var.cloudflare_zone_id
  name        = "Zone WAF Managed Rules"
  description = "Deploy Cloudflare and OWASP managed rulesets with overrides"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  # Execute Cloudflare Managed Rules
  rules {
    action      = "execute"
    description = "Cloudflare Managed Ruleset"
    enabled     = true
    expression  = "true"

    action_parameters {
      id      = local.cf_managed_ruleset_id
      version = "latest"

      overrides {
        # Set a default action for all rules; individual rules can override below
        action  = "block"
        enabled = true

        # Override specific rules to log-only during initial rollout
        rules {
          id      = "efb7b8c949ac4650a09736fc376e9aee"   # placeholder; use real rule IDs
          action  = "log"
          enabled = true
        }
      }
    }
  }

  # Execute OWASP Core Rule Set
  rules {
    action      = "execute"
    description = "OWASP Core Rule Set"
    enabled     = true
    expression  = "true"

    action_parameters {
      id      = local.owasp_ruleset_id
      version = "latest"

      overrides {
        action  = "block"
        enabled = true

        # OWASP sensitivity: low / medium / high
        categories {
          category = "paranoia-level-2"
          enabled  = false   # Disable PL2+ to reduce false positives initially
        }
        categories {
          category = "paranoia-level-3"
          enabled  = false
        }
        categories {
          category = "paranoia-level-4"
          enabled  = false
        }
      }
    }
  }
}
```

---

## Section 2 — Per-Environment Rule Overrides with Locals

Use local variable maps to express per-environment overrides cleanly without duplication.

```hcl
# terraform/waf_overrides.tf

variable "environment" {
  type    = string
  default = "production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Must be 'staging' or 'production'."
  }
}

locals {
  # Rules to disable in staging only (aggressive rules that cause false positives in dev traffic)
  staging_disabled_rules = [
    "4814384a9e5d4991b9815dcfc25d2f1f",  # replace with actual rule IDs from `cf waf rules list`
  ]

  # Rules always set to 'log' in all envs during rollout phase
  log_only_rules = var.environment == "production" ? [] : local.staging_disabled_rules
}

resource "cloudflare_ruleset" "zone_waf_with_env_overrides" {
  zone_id     = var.cloudflare_zone_id
  name        = "WAF Managed Rules (${var.environment})"
  description = "Environment-specific WAF deployment"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action      = "execute"
    description = "Cloudflare Managed — ${var.environment}"
    enabled     = true
    expression  = "true"

    action_parameters {
      id      = local.cf_managed_ruleset_id
      version = "latest"

      overrides {
        action  = "block"
        enabled = true

        dynamic "rules" {
          for_each = local.log_only_rules
          content {
            id      = rules.value
            action  = "log"
            enabled = true
          }
        }
      }
    }
  }
}
```

---

## Section 3 — Account-Level Deployment Across All Zones

```hcl
# terraform/waf_account.tf
# Deploys managed rules to ALL zones in the account.
# Zone-level rulesets evaluated AFTER account-level rulesets.

resource "cloudflare_ruleset" "account_waf_managed" {
  account_id  = var.cloudflare_account_id
  name        = "Account WAF Managed Rules"
  description = "Account-wide baseline WAF coverage"
  kind        = "root"
  phase       = "http_request_firewall_managed"

  rules {
    action      = "execute"
    description = "Cloudflare Managed Ruleset (account)"
    enabled     = true
    expression  = "true"

    action_parameters {
      id      = local.cf_managed_ruleset_id
      version = "latest"

      overrides {
        action  = "managed_challenge"  # Use managed challenge as default for account-wide
        enabled = true
      }
    }
  }

  # Scope to specific zones using skip rules
  rules {
    action      = "skip"
    description = "Exclude internal tooling zone from managed rules"
    enabled     = true
    expression  = "(cf.zone.name eq \"internal-tools.example.com\")"
    action_parameters {
      ruleset = "current"
    }
    logging {
      enabled = false
    }
  }
}
```

---

## Section 4 — Exposed Credentials Check

```hcl
# terraform/waf_credentials.tf

resource "cloudflare_ruleset" "exposed_credentials" {
  zone_id     = var.cloudflare_zone_id
  name        = "Exposed Credentials Check"
  description = "Block logins using compromised credentials"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action      = "execute"
    description = "Cloudflare Exposed Credentials Check"
    enabled     = true
    # Scope only to authentication endpoints to avoid unnecessary scanning
    expression  = "(http.request.uri.path matches \"^/(login|auth|signin|api/v[0-9]+/session)\")"

    action_parameters {
      id      = "c2e184081120413c86c3ab7e14069605"
      version = "latest"

      overrides {
        action  = "managed_challenge"
        enabled = true
      }
    }
  }
}
```

---

## Section 5 — Sensitive Data Detection Skip Rule

Avoid blocking internal monitoring or health-check paths with a skip rule before the
managed ruleset fires.

```hcl
# terraform/waf_skip.tf

resource "cloudflare_ruleset" "waf_skip_internal" {
  zone_id     = var.cloudflare_zone_id
  name        = "WAF Skip — Internal Paths"
  description = "Skip managed rules for health checks and internal IPs"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  # Skip rule MUST come before the execute rule in phase ordering
  rules {
    action      = "skip"
    description = "Skip WAF for health check endpoints"
    enabled     = true
    expression  = <<-EOT
      (http.request.uri.path in {"/health" "/ping" "/__status"}) or
      (ip.src in {192.0.2.0/24 10.0.0.0/8})
    EOT

    action_parameters {
      ruleset  = "current"
      rulesets = [local.cf_managed_ruleset_id, local.owasp_ruleset_id]
    }

    logging {
      enabled = true   # Still log skipped requests for audit
    }
  }
}
```

---

## Section 6 — CI Gate: WAF Rule Drift Detection

```typescript
// scripts/waf-drift-check.ts
// Run in GitHub Actions after terraform plan to detect unexpected rule disablement.

interface WafRulesetRule {
  id: string;
  action: string;
  enabled: boolean;
  description: string;
}

async function fetchActiveWafRules(zoneId: string, token: string): Promise<WafRulesetRule[]> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/rulesets?phase=http_request_firewall_managed`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const data = (await resp.json()) as { result: Array<{ rules: WafRulesetRule[] }> };
  return data.result.flatMap(r => r.rules ?? []);
}

async function assertNoCriticalRulesDisabled(zoneId: string, token: string): Promise<void> {
  const CRITICAL_RULE_IDS = new Set([
    // Populate with rule IDs that must never be disabled
    "block-sqli-001",
    "block-xss-001",
  ]);

  const rules = await fetchActiveWafRules(zoneId, token);
  const disabled = rules.filter(r => CRITICAL_RULE_IDS.has(r.id) && !r.enabled);

  if (disabled.length > 0) {
    console.error("CRITICAL: The following WAF rules are disabled:", disabled.map(r => r.id));
    process.exit(1);
  }

  console.log("WAF rule audit passed — no critical rules disabled.");
}

await assertNoCriticalRulesDisabled(
  process.env.CF_ZONE_ID!,
  process.env.CF_API_TOKEN!
);
```

---

## Anti-patterns

- **Deleting and recreating the zone ruleset phase** — Terraform treats the entire
  `cloudflare_ruleset` for a phase as a single resource. Destroying it removes ALL
  WAF protection on the zone until the next apply. Use `lifecycle { prevent_destroy = true }`.
- **Setting all rules to `log` indefinitely** — log mode is useful during rollout but
  must be time-boxed. Use a Terraform variable `waf_mode = "log" | "block"` with a CI
  gate that fails if `waf_mode = "log"` is merged to production.
- **Hardcoding rule IDs** — managed rule IDs are UUIDs that can be looked up via the
  API. Document the source and re-verify IDs after Cloudflare managed ruleset updates.
- **Omitting the OWASP paranoia level** — deploying OWASP PL4 in production on day one
  causes high false positive rates. Start with PL1, measure, then incrementally enable.

---

## Gotchas

- `cloudflare_ruleset` for a zone's WAF phase is a singleton per phase. Running
  `terraform import` on an existing zone ruleset requires the ruleset UUID — retrieve it
  with `curl https://api.cloudflare.com/client/v4/zones/<id>/rulesets`.
- Skip rules and execute rules in the same `cloudflare_ruleset` resource are ordered by
  their position in the `rules` list; skip rules must appear **before** execute rules.
- The `version = "latest"` in `action_parameters` means Cloudflare can silently update the
  ruleset content. Pin to a specific version in production to prevent unexpected behavior
  changes, then upgrade deliberately.
- Account-level and zone-level rulesets for the same phase are evaluated in sequence;
  zone-level overrides do not override account-level `block` actions — they stack.
- The Exposed Credentials Check makes outbound requests from Cloudflare's network to a
  breach database; it does not store credentials.

---

## Verification

```bash
# List current zone WAF rulesets
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets?phase=http_request_firewall_managed" \
  | jq '.result[] | {id, name, rules: [.rules[] | {id, action, enabled, description}]}'

# Import existing zone WAF ruleset into Terraform state
terraform import cloudflare_ruleset.zone_waf_managed <zone_id>/<ruleset_uuid>

# Test a blocked payload (expect 403 or managed challenge)
curl -i "https://api.example.com/search?q=<script>alert(1)</script>"

# Verify OWASP PL1 is enabled and PL2 is disabled
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/$OWASP_RULESET_ID" \
  | jq '.result.rules[] | select(.categories != null) | {categories, enabled}'
```

---

## Related

- `cloudflare-waf-custom-ruleset-terraform.md`
- `cloudflare-network-analytics-ddos-forensics.md`
- `terraform-cloudflare-rate-limiting-rules.md`
- `aws-waf-rules.md`
- `policy-as-code-opa-kyverno.md`

---

## Sources

- Cloudflare Docs — WAF Managed Rules: https://developers.cloudflare.com/waf/managed-rules/
- Cloudflare Docs — Deploy WAF Managed Rules via API: https://developers.cloudflare.com/waf/managed-rules/deploy-api/
- Terraform cloudflare_ruleset: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
- Cloudflare Docs — OWASP Paranoia Levels: https://developers.cloudflare.com/waf/managed-rules/reference/owasp-core-ruleset/
- Cloudflare Docs — Exposed Credentials Check: https://developers.cloudflare.com/waf/managed-rules/check-for-exposed-credentials/
