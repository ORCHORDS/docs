# Pulumi: Cloudflare WAF Custom Firewall Rules

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to manage Cloudflare WAF custom rules — blocking bad bots, rate-limiting specific paths, skipping managed rulesets for trusted IPs — via Pulumi so rule changes go through code review and CI before reaching production.

## Context
Cloudflare WAF custom rules live in zone-level or account-level rulesets identified by the `http_request_firewall_custom` phase. Each ruleset contains ordered rules with Wireshark-style expressions (Ruleset Engine Language). Pulumi's `@pulumi/cloudflare` exposes `cloudflare.Ruleset` to manage them declaratively. Custom rules execute before managed WAF rulesets, making them the first line of defence for application-specific threats.

## Defining a Zone-Level Custom WAF Ruleset

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const config = new pulumi.Config();
const zoneId = config.require("zoneId");
const trustedIpList = config.require("trustedIpListId"); // pre-existing IP list ID

// A single Ruleset resource manages ALL custom WAF rules for the zone.
// Do not create multiple Ruleset resources for the same zone/phase — the last
// one wins and silently deletes the others.
const wafCustomRuleset = new cloudflare.Ruleset("waf-custom-rules", {
  zoneId,
  name: "Custom WAF Rules",
  description: "Application-specific firewall rules managed by Pulumi",
  kind: "zone",
  phase: "http_request_firewall_custom",

  rules: [
    // Rule 1: Allow trusted internal IPs through all checks (skip action)
    {
      ref: "allow-trusted-ips",
      description: "Bypass WAF for trusted internal and CI egress IPs",
      expression: `(ip.src in $${trustedIpList})`,
      action: "skip",
      actionParameters: {
        ruleset: "current",  // skips the rest of this ruleset
        phases: [
          "http_ratelimit",
          "http_request_firewall_managed",
        ],
        products: ["waf", "rateLimit", "bic"],
      },
      enabled: true,
    },

    // Rule 2: Block requests with suspicious User-Agent strings
    {
      ref: "block-bad-bots",
      description: "Block known scraper and attack tool user-agents",
      expression: [
        `(http.user_agent contains "sqlmap")`,
        `(http.user_agent contains "nikto")`,
        `(http.user_agent contains "masscan")`,
        `(http.user_agent contains "zgrab")`,
        `(http.user_agent eq "")`,
      ].join(" or "),
      action: "block",
      enabled: true,
    },

    // Rule 3: Challenge requests to the admin path from non-corporate countries
    {
      ref: "challenge-admin-foreign",
      description: "JS challenge admin panel from unexpected geos",
      expression:
        `(http.request.uri.path starts_with "/admin") and ` +
        `not (ip.geoip.country in {"GB" "DE" "US" "NL"})`,
      action: "managed_challenge",
      enabled: true,
    },

    // Rule 4: Block XML-RPC abuse on WordPress endpoints
    {
      ref: "block-xmlrpc",
      description: "Drop all POST traffic to /xmlrpc.php",
      expression:
        `(http.request.uri.path eq "/xmlrpc.php") and (http.request.method eq "POST")`,
      action: "block",
      enabled: true,
    },
  ],
});

export const rulesetId = wafCustomRuleset.id;
```

## Adding Rate-Limit Rules to the Same Ruleset

```typescript
// Rate limiting for the login endpoint — extend rules array above
const loginRateRule = {
  ref: "rate-limit-login",
  description: "Limit login attempts to 10 per minute per IP",
  expression: `(http.request.uri.path eq "/auth/login") and (http.request.method eq "POST")`,
  action: "block",
  ratelimit: {
    characteristics: ["ip.src"],
    period: 60,          // seconds
    requestsPerPeriod: 10,
    mitigationTimeout: 600, // 10-minute block after threshold hit
    countingExpression: "",  // count all matching requests
  },
  enabled: true,
};

// For the Ruleset resource, add loginRateRule into the rules array.
// Rate-limit rules must be in the http_ratelimit phase, NOT http_request_firewall_custom.
const rateLimitRuleset = new cloudflare.Ruleset("waf-rate-limits", {
  zoneId,
  name: "Rate Limiting Rules",
  kind: "zone",
  phase: "http_ratelimit",
  rules: [loginRateRule],
});
```

## Deploying Custom Rules with a GitHub Actions Gate

```yaml
# .github/workflows/waf-deploy.yml
name: WAF Rules Deploy
on:
  push:
    branches: [main]
    paths: ["infra/waf/**"]
  pull_request:
    paths: ["infra/waf/**"]

jobs:
  preview:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: pulumi/actions@v6
        with:
          command: preview
          stack-name: production
          work-dir: infra/waf
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  deploy:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - uses: pulumi/actions@v6
        with:
          command: up
          stack-name: production
          work-dir: infra/waf
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Anti-patterns
- Creating multiple `cloudflare.Ruleset` resources for the same zone and phase — the API only supports one custom ruleset per phase; concurrent Pulumi resources will conflict and one will silently overwrite the other
- Using `action: "js_challenge"` for login-path rate limiting — JS challenge is appropriate for bot mitigation, not rate limiting, where a 429 block is the correct response
- Ordering rules with low-specificity blocks before high-specificity bypasses — trusted IP skip rules must come first in the `rules` array; Cloudflare evaluates rules top-down and stops at the first match
- Embedding IP addresses as literals in rule expressions — use Cloudflare IP Lists (`$list_name`) so IPs can be updated without a ruleset redeploy
- Omitting `enabled: false` on experimental rules — deploy new rules as disabled, verify via Analytics, then enable in a follow-up PR

## Gotchas
- The `skip` action's `ruleset: "current"` parameter skips the remainder of the *current* ruleset only; to skip managed WAF rulesets you must also list them in `phases`
- Pulumi performs a full ruleset replacement on every `pulumi up` that changes rule order or count; this is a single atomic API operation (no partial rule updates)
- Ruleset Engine Language is validated by the Cloudflare API at apply time, not by Pulumi validation; a bad expression surfaces as a 400 during `pulumi up`
- The `ratelimit` block is only valid when `phase` is `http_ratelimit`; mixing it into `http_request_firewall_custom` returns a validation error
- WAF custom rules count toward the zone's rule quota; Enterprise zones have higher limits than Pro/Business

## Verification
```bash
# List all rulesets on a zone
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, phase, rules: (.rules | length)}'

# Inspect a specific ruleset's rules
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets/$RULESET_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.rules[] | {ref, description, action, enabled}'

# Check WAF events in the last hour for a specific rule
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/security/events?since=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)&rule_id=<ref>" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result | length'
```

## Related
- `cloudflare-waf-custom-ruleset-terraform.md` — Terraform equivalent for WAF custom rulesets
- `terraform-cloudflare-waf-managed-rules-deployment.md` — deploying Cloudflare-managed WAF rulesets
- `cloudflare-ip-list-management-workers.md` — keeping IP lists fresh via Workers cron
- `terraform-cloudflare-rate-limiting-rules.md` — Terraform-based rate limit rule management

## Sources
- https://developers.cloudflare.com/waf/custom-rules/
- https://www.pulumi.com/registry/packages/cloudflare/api-docs/ruleset/
- https://developers.cloudflare.com/ruleset-engine/rules-language/
- https://developers.cloudflare.com/waf/rate-limiting-rules/
- https://developers.cloudflare.com/waf/custom-rules/skip/
