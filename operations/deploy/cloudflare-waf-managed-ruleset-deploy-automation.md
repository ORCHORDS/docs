# Cloudflare WAF Managed Ruleset Deploy Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare WAF configuration (managed rulesets, custom rules, rate limiting rules,
and override exceptions) is currently managed manually per zone in the dashboard. Security
exceptions added for one application silently never reach staging; production zones
accumulate undocumented overrides. The goal is to manage all WAF rule configuration as
code, reviewed in pull requests, and deployed consistently across environments.

---

## Context

Cloudflare WAF operates at three levels:

1. **Managed Rulesets** — Cloudflare-maintained rule collections (OWASP Core, Cloudflare
   Managed, DDoS, etc.). You enable/disable them and can override individual rule actions
   at zone or account level.
2. **Custom Rules** — Zone-specific expression-based rules in the `http_request_firewall_custom`
   phase. Allow/block/challenge decisions.
3. **Rate Limiting Rules** — Zone-level rules in the `http_ratelimit` phase.

Managed rulesets are applied via **rulesets** — versioned collections of rules assigned to
a zone's execution phase. Overrides are applied on top of managed rulesets without modifying
the ruleset itself.

Terraform's Cloudflare provider exposes `cloudflare_ruleset` for all of these.

---

## Terraform: WAF Managed Ruleset with Overrides

```hcl
# terraform/waf.tf

# Enable Cloudflare Managed Ruleset on a zone
resource "cloudflare_ruleset" "zone_managed_waf" {
  zone_id     = var.cloudflare_zone_id
  name        = "Zone WAF - ${var.environment}"
  description = "Managed WAF rules for ${var.environment}"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action = "execute"
    action_parameters {
      id = "efb7b8c949ac4650a09736fc376e9aee"   # Cloudflare Managed Ruleset ID

      overrides {
        # Set default action to log instead of block (useful during initial rollout)
        action  = "log"
        enabled = true

        # Re-enable blocking for specific high-confidence rules
        rules {
          id     = "100015"   # SQLi detection
          action = "block"
          enabled = true
        }
        rules {
          id     = "100016"   # XSS detection
          action = "block"
          enabled = true
        }

        # Disable a rule causing false positives on your API
        rules {
          id      = "100035"   # Body size limit rule
          enabled = false
        }

        # Override by tag: set all rules tagged "wordpress" to managed_challenge
        categories {
          category = "wordpress"
          action   = "managed_challenge"
          enabled  = true
        }
      }
    }

    expression  = "true"
    description = "Execute Cloudflare Managed Ruleset"
    enabled     = true
  }
}

# Enable OWASP Core Ruleset
resource "cloudflare_ruleset" "zone_owasp" {
  zone_id     = var.cloudflare_zone_id
  name        = "Zone OWASP - ${var.environment}"
  description = "OWASP Core ruleset for ${var.environment}"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action = "execute"
    action_parameters {
      id = "4814384a9e5d4991b9815dcfc25d2f1f"   # Cloudflare OWASP Core Ruleset

      overrides {
        # Set paranoia level and score threshold
        rules {
          id      = "6179ae15870a4bb7b2d480d4843b323c"   # OWASP PL1
          action  = "block"
          enabled = true
          score_threshold = 60
        }
      }
    }

    expression  = "true"
    description = "Execute OWASP Core Ruleset"
    enabled     = true
  }
}
```

---

## Custom WAF Rules as Code

```hcl
# terraform/waf-custom-rules.tf

resource "cloudflare_ruleset" "zone_custom_waf" {
  zone_id     = var.cloudflare_zone_id
  name        = "Zone Custom WAF - ${var.environment}"
  description = "Custom WAF rules for ${var.environment}"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  # Rule 1: Block known bad IPs from a KV-backed dynamic list
  rules {
    action      = "block"
    expression  = "(ip.src in $cf.open_proxies) or (http.request.uri.path contains \"/.env\")"
    description = "Block open proxies and .env probes"
    enabled     = true
  }

  # Rule 2: Challenge aggressive bots on login endpoint
  rules {
    action     = "managed_challenge"
    expression = <<-EOT
      (http.request.uri.path eq "/api/auth/login")
      and (http.request.method eq "POST")
      and (not cf.bot_management.verified_bot)
      and (cf.bot_management.score lt 30)
    EOT
    description = "Challenge suspicious login attempts"
    enabled     = true
  }

  # Rule 3: Skip WAF for internal health checks
  rules {
    action     = "skip"
    action_parameters {
      ruleset = "current"
    }
    expression  = "(http.request.uri.path eq \"/health\") and (ip.src in {10.0.0.0/8 172.16.0.0/12})"
    description = "Skip WAF for internal health checks"
    enabled     = true
  }

  # Rule 4: Rate-limit aggressive scrapers per IP
  rules {
    action     = "block"
    expression = "(http.request.uri.path matches \"^/api/\") and (rate(http.request.uri.path, 60) > 1000)"
    description = "Block high-rate API abuse (>1000 req/min per path)"
    enabled     = var.environment == "production"  # Production only
  }
}
```

---

## Rate Limiting Rules

```hcl
# terraform/waf-rate-limiting.tf

resource "cloudflare_ruleset" "zone_rate_limit" {
  zone_id     = var.cloudflare_zone_id
  name        = "Zone Rate Limiting - ${var.environment}"
  description = "Rate limiting rules for ${var.environment}"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = "{\"error\":\"rate_limit_exceeded\",\"retry_after\":60}"
      }
    }
    ratelimit {
      characteristics     = ["ip.src", "http.request.headers[\"cf-ray\"]"]
      period              = 60
      requests_per_period = 500
      mitigation_timeout  = 60
      requests_to_origin  = false
    }
    expression  = "(http.request.uri.path matches \"^/api/\")"
    description = "Rate limit API endpoints: 500 req/min per IP"
    enabled     = true
  }
}
```

---

## CI/CD Pipeline: WAF Rules Deploy

```yaml
# .github/workflows/deploy-waf.yml
name: Deploy WAF Rules

on:
  push:
    branches: [main]
    paths:
      - "terraform/waf*.tf"
  pull_request:
    paths:
      - "terraform/waf*.tf"

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Plan
        run: |
          terraform plan \
            -var="environment=${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}" \
            -var="cloudflare_zone_id=${{ secrets.CF_ZONE_ID }}" \
            -out=waf.plan
        working-directory: terraform
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Post plan to PR
        if: github.event_name == 'pull_request'
        run: terraform show -no-color waf.plan >> "$GITHUB_STEP_SUMMARY"
        working-directory: terraform

  apply:
    needs: plan
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Apply
        run: |
          terraform apply -auto-approve \
            -target=cloudflare_ruleset.zone_managed_waf \
            -target=cloudflare_ruleset.zone_owasp \
            -target=cloudflare_ruleset.zone_custom_waf \
            -target=cloudflare_ruleset.zone_rate_limit \
            -var="environment=production" \
            -var="cloudflare_zone_id=${{ secrets.CF_ZONE_ID }}"
        working-directory: terraform
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  verify:
    needs: apply
    runs-on: ubuntu-latest
    steps:
      - name: Verify rulesets are deployed
        run: |
          RULESET_COUNT=$(curl -s \
            "https://api.cloudflare.com/client/v4/zones/${{ secrets.CF_ZONE_ID }}/rulesets" \
            -H "Authorization: Bearer ${{ secrets.CF_API_TOKEN }}" | \
            jq '[.result[] | select(.phase | startswith("http_request_firewall"))] | length')
          echo "Active WAF rulesets: $RULESET_COUNT"
          [ "$RULESET_COUNT" -ge 2 ] || { echo "Expected at least 2 WAF rulesets"; exit 1; }

      - name: Smoke test: blocked path returns 403
        run: |
          HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}" \
            "https://${{ secrets.ZONE_HOSTNAME }}/.env")
          [ "$HTTP_CODE" = "403" ] || \
            { echo "Expected 403 for .env probe, got $HTTP_CODE"; exit 1; }
```

---

## Audit: Listing Active Overrides

```typescript
// scripts/waf-audit.ts
// Prints a summary of all active WAF overrides per zone

const ZONE_ID = process.env.CF_ZONE_ID!;
const TOKEN = process.env.CF_API_TOKEN!;

interface RuleOverride {
  id: string;
  action?: string;
  enabled?: boolean;
}

interface Rule {
  id: string;
  description?: string;
  action: string;
  action_parameters?: {
    id?: string;
    overrides?: {
      action?: string;
      rules?: RuleOverride[];
      categories?: Array<{ category: string; action: string; enabled: boolean }>;
    };
  };
}

async function auditOverrides(): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  const { result } = (await res.json()) as { result: Array<{ id: string; phase: string; name: string }> };

  for (const rs of result.filter((r) => r.phase.startsWith("http_request_firewall"))) {
    const detail = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${rs.id}`,
      { headers: { Authorization: `Bearer ${TOKEN}` } }
    );
    const { result: rsDetail } = (await detail.json()) as { result: { rules: Rule[] } };

    for (const rule of rsDetail.rules) {
      const overrides = rule.action_parameters?.overrides;
      if (overrides?.rules?.length || overrides?.categories?.length) {
        console.log(`\n[${rs.name}] Rule "${rule.description ?? rule.id}" has overrides:`);
        overrides.rules?.forEach((o) =>
          console.log(`  Rule ${o.id}: action=${o.action ?? "inherited"} enabled=${o.enabled ?? true}`)
        );
        overrides.categories?.forEach((c) =>
          console.log(`  Category ${c.category}: action=${c.action} enabled=${c.enabled}`)
        );
      }
    }
  }
}

auditOverrides().catch((e) => { console.error(e); process.exit(1); });
```

---

## Anti-patterns

- **Setting all managed rules to `log` mode in production indefinitely** — Log mode is
  useful during initial rollout to find false positives, but attackers are not blocked.
  Set a 2-week review window, then switch confirmed rules to `block`.
- **Disabling rules by score threshold tuning alone on OWASP** — Lowering the anomaly
  score threshold (e.g. from 60 to 25) is not a substitute for understanding which rules
  fire. Audit `firewall_events` logs first.
- **One Terraform workspace for all zones** — WAF rules are zone-scoped. Use per-environment
  Terraform workspaces or separate state files; a bad apply cannot impact all zones.
- **Not version-pinning the managed ruleset ID** — Cloudflare rotates managed ruleset IDs
  rarely, but a change breaks Terraform state. Reference IDs from Cloudflare docs and pin
  them in variables.
- **Bypassing WAF for all traffic from a load balancer IP range** — If your origin IP
  leaks, attackers bypass the WAF entirely. Use Cloudflare-signed headers
  (`CF-Connecting-IP`) for origin authentication instead.

---

## Gotchas

- Cloudflare's `cloudflare_ruleset` resource does full replacement on update (not in-place
  patch). The phase accepts only one `cloudflare_ruleset` resource per zone; attempts to
  create a second resource for the same phase/zone will error.
- The `phase = "http_request_firewall_managed"` ruleset can contain multiple `execute`
  rules (one per managed ruleset), each with independent overrides.
- WAF rule expressions use Cloudflare's Ruleset Engine expression language (Wireshark-like
  syntax), not a general scripting language. Test expressions with `cf-terraforming` or the
  dashboard expression builder before committing.
- Account-level rulesets (kind = "account") override zone-level rulesets. If your account
  has managed account-level WAF rules, they execute before zone rules and may block traffic
  that zone rules would allow.
- `terraform import` for existing `cloudflare_ruleset` resources requires the ruleset ID,
  not just the zone ID. Retrieve it with `GET /zones/:zone_id/rulesets`.

---

## Verification

```bash
# List all rulesets for a zone
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, phase, version}'

# Get details of a specific ruleset including all overrides
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets/$RULESET_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.rules[].action_parameters.overrides'

# Test rule expression syntax before applying
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/filters/validate-expr" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"expression": "(http.request.uri.path contains \"/.env\")"}'
```

---

## Related

- `custom-deploy-gates-external-api-checks.md`
- `cloudflare-access-application-deploy-automation.md`
- `deploy-gate-antipatterns.md`
- `wrangler-config-validation-pre-deploy-ci-hook.md`
- `risk-based-deployment-gating.md`

---

## Sources

- https://developers.cloudflare.com/waf/
- https://developers.cloudflare.com/ruleset-engine/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
- https://developers.cloudflare.com/waf/managed-rules/reference/cloudflare-managed-ruleset/
- https://developers.cloudflare.com/waf/rate-limiting-rules/
