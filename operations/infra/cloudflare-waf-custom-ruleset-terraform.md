# Cloudflare WAF Custom Ruleset Terraform Management

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

WAF rules are added manually through the dashboard, accumulate over time with no audit trail, and differ between staging and production. A rule change that blocks legitimate traffic requires emergency rollback with no diff to reference. You need WAF rulesets managed as code with PR review, plan preview, and safe rollback.

---

## Context

Cloudflare WAF uses a layered ruleset model. There are Cloudflare-managed rulesets (OWASP, managed rules) and custom rulesets that you author. Custom rulesets are attached to a phase (`http_request_firewall_custom`) at the zone or account level. Each ruleset contains ordered rules using Wireshark-inspired filter expressions. Terraform's `cloudflare` provider (v4+) exposes `cloudflare_ruleset` to manage both the ruleset container and its ordered rules in a single resource.

Key concepts:
- **Phase**: the pipeline stage where rules execute (`http_request_firewall_custom`, `http_ratelimit`, `http_request_transform`, etc.)
- **Action**: `block`, `challenge`, `js_challenge`, `managed_challenge`, `log`, `skip`
- **Expression**: Cloudflare Ruleset Language (Wireshark filter syntax extended with CF fields)
- **Score-based blocking**: combine with Managed Ruleset score fields for layered defence

---

## Base Zone Ruleset Structure

```hcl
# terraform/waf.tf

variable "zone_id" {
  type = string
}

resource "cloudflare_ruleset" "zone_custom_firewall" {
  zone_id     = var.zone_id
  name        = "Custom Firewall Rules"
  description = "Managed by Terraform — do not edit in dashboard"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  # Rules execute in listed order; first matching rule wins unless action is log
  rules {
    ref         = "block-known-bad-bots"
    description = "Block known malicious user agents"
    enabled     = true
    action      = "block"
    expression  = "(cf.client.bot) and not (cf.verified_bot_category in {\"Search Engine Crawler\" \"Monitoring & Analytics\"})"
  }

  rules {
    ref         = "challenge-high-threat-score"
    description = "Challenge requests with high threat score"
    enabled     = true
    action      = "managed_challenge"
    expression  = "(cf.threat_score ge 20)"
  }

  rules {
    ref         = "skip-trusted-ips"
    description = "Allow known office and CI egress IPs without further inspection"
    enabled     = true
    action      = "skip"
    action_parameters {
      ruleset = "current"
    }
    expression = "(ip.src in {192.0.2.0/24 198.51.100.10})"
  }

  rules {
    ref         = "block-sqli-attempts"
    description = "Block SQL injection patterns not caught by managed rules"
    enabled     = true
    action      = "block"
    expression  = "(http.request.uri.query contains \"UNION SELECT\" or http.request.uri.query contains \"1=1--\")"
    logging {
      enabled = true
    }
  }
}
```

---

## Rate Limiting Ruleset

Rate limiting lives in its own phase and requires a separate ruleset resource.

```hcl
resource "cloudflare_ruleset" "zone_rate_limit" {
  zone_id     = var.zone_id
  name        = "Rate Limiting Rules"
  description = "Managed by Terraform"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    ref         = "api-global-rate-limit"
    description = "Rate limit unauthenticated API requests"
    enabled     = true
    action      = "block"
    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = jsonencode({ error = "rate_limit_exceeded", retry_after = 60 })
      }
    }
    ratelimit {
      characteristics        = ["ip.src", "http.request.headers[\"cf-connecting-ip\"]"]
      period                 = 60
      requests_per_period    = 100
      mitigation_timeout     = 60
      requests_to_origin     = false
    }
    expression = "(http.request.uri.path starts_with \"/api/\")"
  }
}
```

---

## Managed Ruleset Override (OWASP)

Enable the Cloudflare OWASP ruleset and tune the paranoia level with overrides:

```hcl
resource "cloudflare_ruleset" "managed_owasp" {
  zone_id     = var.zone_id
  name        = "Managed OWASP Rules"
  description = "Managed by Terraform"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    ref         = "owasp-core"
    description = "Cloudflare OWASP Core Ruleset"
    enabled     = true
    action      = "execute"
    action_parameters {
      id = "4814384a9e5d4991b9815dcfc25d2f1f"  # Cloudflare OWASP Core Ruleset ID
      overrides {
        sensitivity_level = "medium"
        action            = "block"
        # Override specific noisy rule to log-only
        rules {
          id      = "6179ae15870a4bb7b2d480d4843b323c"
          enabled = true
          action  = "log"
        }
      }
    }
    expression = "true"
  }
}
```

---

## Expression Testing Workflow (TypeScript)

Validate expressions against live traffic samples before deploying:

```typescript
// scripts/test-waf-expression.ts
const ZONE_ID   = process.env.CF_ZONE_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

interface ExpressionTestResult {
  result: { matched: boolean; error?: string };
}

async function testExpression(expression: string, sampleRequest: Record<string, unknown>): Promise<boolean> {
  const url = `https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/http_request_firewall_custom/entrypoint/rules/test`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ expression, sample: sampleRequest }),
  });
  const data = (await res.json()) as ExpressionTestResult;
  if (data.result.error) throw new Error(data.result.error);
  return data.result.matched;
}

// Usage in CI before terraform apply
const matched = await testExpression(
  '(http.request.uri.query contains "UNION SELECT")',
  { uri: { query: "id=1 UNION SELECT * FROM users--" } }
);
console.log("Expression matched test payload:", matched); // should be true
```

---

## CI/CD Plan Diff Review

```yaml
# .github/workflows/waf-plan.yml
name: WAF Terraform Plan

on:
  pull_request:
    paths:
      - "terraform/waf.tf"

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.x"
      - name: Terraform Init
        run: terraform -chdir=terraform init
        env:
          TF_VAR_zone_id: ${{ secrets.CF_ZONE_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      - name: Terraform Plan
        run: terraform -chdir=terraform plan -var="zone_id=$CF_ZONE_ID" -out=waf.tfplan
        env:
          CF_ZONE_ID: ${{ secrets.CF_ZONE_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      - name: Show Plan Summary
        run: terraform -chdir=terraform show -no-color waf.tfplan | grep -A3 "cloudflare_ruleset"
```

---

## Anti-patterns

- **Mixing dashboard edits with Terraform**: Terraform will overwrite dashboard changes on next apply; treat the dashboard as read-only after enabling Terraform management.
- **Using `action = "block"` for new rules without first testing with `action = "log"`**: deploy in log mode for 24 hours to confirm false positive rate before switching to block.
- **Hardcoding managed ruleset IDs**: Cloudflare occasionally retires and replaces managed ruleset IDs. Fetch them dynamically with the `cloudflare_rulesets` data source or pin to known-stable IDs and watch the changelog.
- **Placing `skip` rules after block rules**: rules execute in order; a skip rule after a block rule for the same expression has no effect on already-blocked requests.
- **Not enabling logging on block rules**: without `logging { enabled = true }`, blocked requests are invisible in Firewall Analytics.

---

## Gotchas

- The `cloudflare_ruleset` resource manages the entire ruleset as one block. Adding a rule in the dashboard and then running `terraform plan` will show a diff that removes the dashboard rule.
- `kind = "zone"` rulesets are scoped to one zone. Account-level rulesets use `kind = "root"` and require `account_id` instead of `zone_id`.
- Managed ruleset IDs (`4814384a9e5d4991b9815dcfc25d2f1f` for OWASP) are Cloudflare global constants — they are the same across all accounts.
- Rate limit `period` must be one of: 10, 60, 600, 3600. Arbitrary values are rejected at apply time.
- Ruleset changes are non-transactional: if Terraform fails mid-apply (e.g. network timeout), the ruleset may be in a partial state. Always `terraform plan` before re-applying.
- Expression syntax is validated by the API — malformed expressions return a 400 during `terraform apply`, not during `plan`.

---

## Verification

```bash
# List all rulesets on a zone
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, phase}'

# Fetch the live ruleset to compare with Terraform state
RULESET_ID=$(terraform -chdir=terraform output -raw custom_firewall_ruleset_id)
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets/$RULESET_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.rules | length'

# Check Firewall Events for recent block actions
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/firewall/events" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[:5]'
```

---

## Related

- `aws-waf-rules.md`
- `cloudflare-network-analytics-ddos-forensics.md`
- `cloudflare-zero-trust-staging-prod-isolation.md`
- `iac-best-practices.md`
- `terraform-state-management-remote-backend.md`

---

## Sources

- Cloudflare Ruleset Engine: https://developers.cloudflare.com/ruleset-engine/
- Terraform cloudflare_ruleset: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
- Cloudflare WAF Custom Rules: https://developers.cloudflare.com/waf/custom-rules/
- Managed Ruleset IDs: https://developers.cloudflare.com/waf/managed-rules/reference/cloudflare-managed-ruleset/
- Rate Limiting: https://developers.cloudflare.com/waf/rate-limiting-rules/
