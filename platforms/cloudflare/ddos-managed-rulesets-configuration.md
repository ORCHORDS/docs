# DDoS Managed Rulesets Configuration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Legitimate traffic is being blocked during a volumetric attack because the HTTP DDoS managed ruleset sensitivity is set too high. Alternatively, a slow-rate application-layer attack slips through because a specific ruleset rule is set to `log` instead of `block`. You need to tune individual rules, override sensitivity levels per path, and validate changes without affecting production before a live incident.

## Context

Cloudflare's DDoS protection is built around managed rulesets that run in the Cloudflare network data plane — before the request reaches WAF or origin. There are three main rulesets:

| Ruleset | Layer | Zone requirement |
|---|---|---|
| `cloudflare_http_attacks` | L7 HTTP | Free and above |
| `cloudflare_http_ratelimit` | L7 rate limiting | Pro and above |
| `cloudflare_network_l3_l4_attacks` | L3/L4 | Magic Transit only |

Each ruleset contains dozens to hundreds of individual rules (identified by rule ID) that detect specific attack signatures. You can:
- Override the **action** (`block`, `challenge`, `managed_challenge`, `js_challenge`, `log`, `drop`)
- Override the **sensitivity level** (`high`, `medium`, `low`, `eoff` — essentially off)
- Scope overrides to a subset of traffic using a Filter expression
- Apply overrides at the ruleset level (affects all rules) or per-rule

## Viewing Current Rulesets

```bash
# List all phase entry-point rulesets for your zone
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | select(.phase == "ddos_l7") | {id, name, phase}'

# Get the full HTTP DDoS ruleset with all rules
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result.rules[].action_parameters.overrides.rules[]? | {id, action, sensitivity_level}'
```

## Zone-Level Override: Reduce Global Sensitivity

Apply a zone-wide override to drop the entire HTTP DDoS managed ruleset to `medium` sensitivity — useful when your API sends high-volume legitimate bursts that trigger `high` sensitivity rules:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "action": "execute",
        "expression": "true",
        "action_parameters": {
          "id": "4d21379b4f9f4bb088e0729962c8b3cf",
          "overrides": {
            "sensitivity_level": "medium"
          }
        }
      }
    ]
  }'
```

The `id` value `4d21379b4f9f4bb088e0729962c8b3cf` is Cloudflare's canonical HTTP DDoS ruleset ID (account-level managed ruleset).

## Per-Rule Override: Block a Specific Attack Pattern

Override a single rule (e.g., HTTP Flood rule ID `fdfdac75430c4c47a959592f0aa5f68c`) to `block` with `high` sensitivity while keeping the rest at default:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "action": "execute",
        "expression": "true",
        "action_parameters": {
          "id": "4d21379b4f9f4bb088e0729962c8b3cf",
          "overrides": {
            "rules": [
              {
                "id": "fdfdac75430c4c47a959592f0aa5f68c",
                "action": "block",
                "sensitivity_level": "high"
              }
            ]
          }
        }
      }
    ]
  }'
```

## Scoped Override: Bypass DDoS on Known API Paths

Legitimate high-throughput internal services hitting `/internal/health` or `/webhooks/stripe` should not be challenged. Use a Filter expression scoped to those paths:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "action": "execute",
        "expression": "(http.request.uri.path matches \"^/internal/\" or http.request.uri.path matches \"^/webhooks/\")",
        "action_parameters": {
          "id": "4d21379b4f9f4bb088e0729962c8b3cf",
          "overrides": {
            "sensitivity_level": "eoff"
          }
        }
      },
      {
        "action": "execute",
        "expression": "true",
        "action_parameters": {
          "id": "4d21379b4f9f4bb088e0729962c8b3cf"
        }
      }
    ]
  }'
```

Rules are evaluated in order; the first matching rule wins. The bypass rule must come before the default execution rule.

## Terraform: Managed Ruleset Override

```hcl
resource "cloudflare_ruleset" "ddos_l7_override" {
  zone_id = var.zone_id
  name    = "DDoS L7 zone overrides"
  kind    = "zone"
  phase   = "ddos_l7"

  rules {
    action      = "execute"
    expression  = "(http.request.uri.path matches \"^/api/batch\")"
    description = "Lower sensitivity for batch API endpoints"

    action_parameters {
      id = "4d21379b4f9f4bb088e0729962c8b3cf"

      overrides {
        sensitivity_level = "low"
      }
    }
  }

  rules {
    action      = "execute"
    expression  = "true"
    description = "Default HTTP DDoS ruleset"

    action_parameters {
      id = "4d21379b4f9f4bb088e0729962c8b3cf"

      overrides {
        sensitivity_level = "high"

        rules {
          id                = "fdfdac75430c4c47a959592f0aa5f68c"
          action            = "block"
          sensitivity_level = "high"
        }
      }
    }
  }
}
```

## Enabling DDoS Log Mode for Tuning

Before switching any rule to `block`, enable `log` mode to see what would be blocked without actually dropping traffic. This is critical before a ruleset hardening during an incident:

```bash
# Set action override to "log" for the entire ruleset
curl -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "action": "execute",
        "expression": "true",
        "action_parameters": {
          "id": "4d21379b4f9f4bb088e0729962c8b3cf",
          "overrides": {
            "action": "log"
          }
        }
      }
    ]
  }'
```

Then use **Security → Events** (or Logpush to your SIEM) to review which rules would have triggered, and tune sensitivity or expressions accordingly before switching back to `block`.

## Adaptive DDoS Protection

For Business and Enterprise zones, Adaptive DDoS Protection automatically learns your traffic baseline and tunes rule sensitivity dynamically. It is enabled per-zone:

```bash
# Check if Adaptive DDoS is enabled
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | select(.id == "advanced_ddos")'
```

Adaptive DDoS can still be supplemented with manual overrides; manual overrides take precedence over automatic sensitivity adjustments for the specific rules/paths you override.

## Anti-patterns

- **Setting zone-wide sensitivity to `eoff`** — eliminates all automatic DDoS protection; scope bypasses narrowly by IP prefix or path.
- **Applying `block` action without testing in `log` mode first** — legitimate clients (CI runners, mobile apps behind CGNAT) may share IPs with attackers and get blocked.
- **Forgetting the rule order in the entrypoint ruleset** — a `PUT` to the entrypoint replaces the entire rule list; the first matching rule wins. Always include all desired rules in the payload.
- **Treating HTTP DDoS and WAF rate limiting as substitutes** — they are complementary. DDoS managed rules detect volumetric patterns; WAF rate limiting enforces per-entity thresholds. Both are needed.
- **Not separating admin/webhook paths from public paths in overrides** — a single zone-wide sensitivity downgrade protects attackers' traffic too.

## Gotchas

- The HTTP DDoS managed ruleset ID (`4d21379b4f9f4bb088e0729962c8b3cf`) is the same across all accounts but differs from the network (L3/L4) ruleset ID — do not mix them.
- Overrides survive ruleset version upgrades by Cloudflare. When Cloudflare adds new rules to the managed ruleset, they inherit the sensitivity from your ruleset-level override (not `eoff` for individual rule overrides).
- The `ddos_l7` phase is only configurable at the zone level. There is no account-level `ddos_l7` phase entry-point unless you are using Cloudflare for SaaS.
- The Terraform `cloudflare_ruleset` resource manages the entire ruleset as a unit; partial updates via `terraform apply` replace all rules. Maintain the full desired state in Terraform.
- `sensitivity_level = "eoff"` is not the same as deleting the rule override. Setting `eoff` explicitly means "this rule fires but takes no action." A missing override means the rule uses its default.

## Verification

```bash
# Confirm the current override is in effect
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/phases/ddos_l7/entrypoint" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result.rules[].action_parameters.overrides'

# Generate test traffic and check Security Events for "DDoS" events
# Dashboard: Security → Events → filter by "DDoS Managed Rule"

# Check analytics for blocked requests by DDoS ruleset
curl -s "https://api.cloudflare.com/client/v4/graphql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ viewer { zones(filter: {zoneTag: \"'${ZONE_ID}'\"}) { httpRequestsAdaptiveGroups(limit: 10, filter: {datetime_gt: \"2026-08-21T00:00:00Z\", source: \"firewall_managed\"}) { count dimensions { clientCountryName action } } } } }"
  }' | jq '.data.viewer.zones[0].httpRequestsAdaptiveGroups'
```

## Related

- `waf-managed-rules-exception-order-and-future-rule-drift.md` — WAF rule exceptions vs. DDoS overrides
- `under-attack-mode-ddos-runbook.md` — incident response when a DDoS is in progress
- `rate-limiting-v2-vs-workers-side.md` — WAF rate limiting vs. Workers-side throttling
- `cloudflare-terraform-provider-iac.md` — managing all Cloudflare resources via Terraform

## Sources

- https://developers.cloudflare.com/ddos-protection/managed-rulesets/
- https://developers.cloudflare.com/ddos-protection/managed-rulesets/http/configure-api/
- https://developers.cloudflare.com/ddos-protection/managed-rulesets/http/override-parameters/
- https://developers.cloudflare.com/ddos-protection/adaptive-protection/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
