# Cloudflare WAF and Firewall Rules via Terraform

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The example.com API receives bot traffic, credential stuffing attempts from specific countries, and high-frequency scraping. You need WAF managed rule sets enabled, custom country-block rules, rate limiting for unauthenticated endpoints, and a bot-score threshold rule — all reproducible via Terraform, tested in log-only mode before enforcement.

## Context

Cloudflare's Ruleset Engine handles both the WAF and custom firewall rules. All rules live in `cloudflare_ruleset` resources targeting specific phases:

- **`http_request_firewall_managed`** — WAF managed rule sets (OWASP, Cloudflare Managed Rules)
- **`http_request_firewall_custom`** — custom firewall rules (country block, IP block, header matching)
- **`http_ratelimit`** — rate limiting rules

Actions: `block`, `challenge`, `js_challenge`, `managed_challenge`, `log`, `skip`.

Rule priority is set by order within the `rules` block array. Lower index = higher priority.

## Solution

```hcl
# waf_managed.tf — Cloudflare Managed Rules and OWASP
resource "cloudflare_ruleset" "waf_managed" {
  zone_id     = var.zone_id
  name        = "orchords-waf-managed"
  description = "WAF managed rule sets — Terraform managed"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  # Deploy Cloudflare Managed Rules
  rules {
    ref         = "cf-managed-rules"
    description = "Cloudflare Managed Ruleset"
    enabled     = true
    expression  = "true"
    action      = "execute"

    action_parameters {
      id = "efb7b8c949ac4650a09736fc376e9aee" # Cloudflare Managed Rules
      version = "latest"

      overrides {
        # Global sensitivity — paranoia level 2 is recommended for APIs
        sensitivity_level = "medium"

        # Override specific rules that cause false positives on our API
        rules {
          id      = "6179ae15870a4bb7b2d480d4843b323c" # SQLi rule
          enabled = true
          action  = "block"
        }

        # Downgrade a noisy rule to log-only while we tune it
        rules {
          id      = "5de7edfa648c4d6891dc3e7f84534ffa"
          enabled = true
          action  = "log"
        }

        # Whitelist a known-good IP range from rule evaluation
        categories {
          category = "wordpress"
          enabled  = false # Not a WordPress site — disable entire category
        }
      }
    }
  }

  # Deploy Cloudflare OWASP Core Ruleset
  rules {
    ref         = "owasp-core"
    description = "OWASP Core Ruleset"
    enabled     = true
    expression  = "true"
    action      = "execute"

    action_parameters {
      id      = "4814384a9e5d4991b9815dcfc25d2f1f" # OWASP
      version = "latest"

      overrides {
        sensitivity_level = "low" # Reduce false positive rate for API traffic
      }
    }
  }
}
```

```hcl
# firewall_custom.tf — Custom rules: country block, bot score, IP allowlist skip
resource "cloudflare_ruleset" "firewall_custom" {
  zone_id     = var.zone_id
  name        = "orchords-firewall-custom"
  description = "Custom firewall rules — Terraform managed"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  # Rule 1 — skip rules for verified internal IPs (highest priority)
  rules {
    ref         = "skip-internal-ips"
    description = "Skip all firewall checks for trusted office IPs"
    enabled     = true
    expression  = "(ip.src in {${join(" ", formatlist("%s", var.trusted_ip_cidrs))}})"
    action      = "skip"

    action_parameters {
      ruleset = "current"
    }

    logging {
      enabled = true # Still log skipped requests for audit
    }
  }

  # Rule 2 — block high-risk countries for admin endpoints
  rules {
    ref         = "block-country-admin"
    description = "Block high-risk geos from admin paths"
    enabled     = true
    expression  = "(http.request.uri.path matches \"^/admin/\") and (ip.geoip.country in {\"CN\" \"RU\" \"KP\" \"IR\"})"
    action      = "block"
  }

  # Rule 3 — managed challenge for bot score below threshold
  rules {
    ref         = "challenge-bots"
    description = "Managed challenge for low bot score on non-API paths"
    enabled     = true
    # Bot score 1-29 = almost certainly a bot; 30-99 = likely automated
    expression  = "(cf.bot_management.score lt 30) and not (http.request.uri.path matches \"^/api/webhooks/\")"
    action      = "managed_challenge"
  }

  # Rule 4 — JS challenge for suspicious user-agent patterns
  rules {
    ref         = "challenge-suspicious-ua"
    description = "JS challenge for missing or bot-like user agents"
    enabled     = true
    expression  = "(not http.user_agent matches \"Mozilla|curl|HTTPie\") and (http.request.uri.path matches \"^/api/\")"
    action      = "js_challenge"
  }

  # Rule 5 — block known bad ASNs
  rules {
    ref         = "block-bad-asns"
    description = "Block requests from known hosting/proxy ASNs abusing the API"
    enabled     = var.enable_asn_blocking
    expression  = "ip.geoip.asnum in {${join(" ", var.blocked_asns)}}"
    action      = "block"
  }
}

variable "trusted_ip_cidrs" {
  type    = list(string)
  default = ["203.0.113.0/24", "198.51.100.10"]
}

variable "blocked_asns" {
  type    = list(number)
  default = [14061, 16509, 15169] # DigitalOcean, AWS, Google Cloud — adjust as needed
}

variable "enable_asn_blocking" {
  type    = bool
  default = false # Enable only after testing in log-only mode
}
```

```hcl
# rate_limiting.tf — Rate limiting rules
resource "cloudflare_ruleset" "rate_limiting" {
  zone_id     = var.zone_id
  name        = "orchords-rate-limits"
  description = "Rate limiting rules — Terraform managed"
  kind        = "zone"
  phase       = "http_ratelimit"

  # Rule 1 — strict rate limit on authentication endpoints
  rules {
    ref         = "ratelimit-auth"
    description = "10 requests per minute per IP on /auth/ paths"
    enabled     = true
    expression  = "(http.request.uri.path matches \"^/api/auth/\") or (http.request.uri.path matches \"^/api/v1/login\")"
    action      = "block"

    ratelimit {
      characteristics = ["ip.src", "http.request.headers[\"CF-Connecting-IP\"]"] # Deduplicate by real IP
      period          = 60     # 1-minute window
      requests_per_period = 10
      mitigation_timeout  = 300 # Block for 5 minutes after threshold
      counting_expression = "" # Count all requests matching the rule expression
    }
  }

  # Rule 2 — general API rate limit
  rules {
    ref         = "ratelimit-api-general"
    description = "500 requests per minute per IP on /api/ paths"
    enabled     = true
    expression  = "http.request.uri.path matches \"^/api/\""
    action      = "managed_challenge" # Challenge rather than hard block for legitimate spikes

    ratelimit {
      characteristics         = ["ip.src"]
      period                  = 60
      requests_per_period     = 500
      mitigation_timeout      = 60
    }
  }

  # Rule 3 — rate limit by session token to catch distributed attacks
  rules {
    ref         = "ratelimit-per-token"
    description = "200 requests per minute per API token"
    enabled     = true
    expression  = "(http.request.uri.path matches \"^/api/\") and (http.request.headers[\"Authorization\"] ne \"\")"
    action      = "block"

    ratelimit {
      characteristics     = ["http.request.headers[\"Authorization\"]"]
      period              = 60
      requests_per_period = 200
      mitigation_timeout  = 60
    }
  }
}
```

```typescript
// src/middleware/waf-bypass-check.ts
// Worker middleware to validate that WAF rules are working as expected
// Call this endpoint in staging after deploying new WAF rules

export interface Env {
  WAF_TEST_SECRET: string;
}

const WAF_TEST_PATHS = [
  '/api/auth/login',
  '/admin/dashboard',
  '/api/users',
] as const;

export async function handleWafTest(
  request: Request,
  env: Env
): Promise<Response> {
  const secret = <redacted-secret>'X-Waf-Test-Secret');
  if (secret !== env.WAF_TEST_SECRET) {
    return new Response('Unauthorized', { status: 401 });
  }

  const results: Record<string, unknown> = {};

  for (const path of WAF_TEST_PATHS) {
    const testReq = new Request(`https://api.example.com${path}`, {
      method: 'GET',
      headers: {
        'User-Agent': 'python-requests/2.28.0', // Commonly blocked UA
        'X-Forwarded-For': '185.220.101.1', // Known Tor exit node IP
      },
    });

    try {
      const res = await fetch(testReq);
      results[path] = {
        status: res.status,
        cfCacheStatus: res.headers.get('cf-cache-status'),
        cfRay: res.headers.get('cf-ray'),
      };
    } catch (err) {
      results[path] = { error: String(err) };
    }
  }

  return Response.json({ timestamp: new Date().toISOString(), results });
}
```

## Implementation Details

**Log-only mode before enforcement.** When adding a new blocking rule, first deploy it with `action = "log"`. Monitor the Cloudflare Firewall Events dashboard (or Analytics Engine) for 24–48 hours to ensure it does not match legitimate traffic. Then change to `action = "block"` and re-apply.

**Rule override mechanics.** The `overrides.rules` block inside `action_parameters` targets individual WAF rule IDs. Find the rule ID in `Security > WAF > Managed Rules` in the dashboard or via API:

```bash
curl "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.phase == "http_request_firewall_managed")'
```

**Priority ordering.** The `skip` action (for trusted IPs) must be the first rule in the custom firewall ruleset. If it appears after a blocking rule, legitimate office IPs will be blocked before the skip rule is evaluated.

**Rate limit `characteristics`.** Using `http.request.headers["Authorization"]` as a characteristic allows per-token limits that catch distributed attacks from many IPs using the same stolen token. Always combine with `ip.src` for unauthenticated endpoints.

## Anti-patterns

- **Blocking entire countries at the zone level.** Geo-blocking without path scoping will block legitimate users (e.g., employees traveling, VPN users). Scope blocks to sensitive paths only.
- **Using `block` action on WAF managed rules without testing.** Managed rules have false positives. Always start with `log` or `challenge`.
- **Putting the skip rule after blocking rules.** The first matching rule wins. Skip rules must be highest priority.
- **Rate limiting by `ip.src` alone for authenticated APIs.** A CDN or corporate NAT can have many users behind one IP. Use `Authorization` header or user ID as the characteristic for authenticated endpoints.
- **Leaving ASN blocking enabled for major cloud providers globally.** Legitimate users access your API from cloud-hosted environments (CI/CD, Lambda functions). Scope ASN blocks to specific paths.

## Gotchas

- WAF managed ruleset IDs are global constants, not zone-specific. The IDs in this document are stable but verify them against the [Cloudflare docs](https://developers.cloudflare.com/waf/managed-rules/) when the provider updates.
- `managed_challenge` is preferred over `js_challenge` for modern browsers. `js_challenge` may fail on headless clients that are legitimate (monitoring bots, RSS readers).
- Ratelimit `characteristics` using request headers are case-sensitive in the expression engine.
- The `ratelimit` block requires the zone to be on a paid plan (Pro or above). Free plans only get the basic rate limiting without custom expressions.
- Terraform plan will fail if you reference a WAF rule ID that doesn't exist in the managed ruleset. Validate rule IDs via the API before hardcoding them.
- Custom firewall rules and WAF managed rules are in **different phases** and require separate `cloudflare_ruleset` resources. You cannot mix `http_request_firewall_custom` and `http_request_firewall_managed` phases in one resource.

## Verification

```bash
# List all active firewall rulesets on the zone
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {name, phase, rules_count: (.rules | length)}'

# Tail firewall events (last 100) to see recent blocks
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/security/events?limit=100" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {action, rule_id, country: .meta.country, path: .request.uri}'

# Test bot score rule (use a known bot IP)
curl -sI https://api.example.com/api/health \
  --header 'User-Agent: Googlebot/2.1 (+http://www.google.com/bot.html)' \
  | grep -E 'HTTP|cf-ray|x-cf-challenge'

# Confirm rate limit triggers on auth endpoint (run 15 times in 60s)
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://api.example.com/api/auth/login \
    -H 'Content-Type: application/json' -d '{"email":"test@test.com","password":"wrong"}'
done
```

## Related

- `documentation/docs/policies/infra/workers-cdn-cache-rules-terraform.md`
- `documentation/docs/policies/infra/workers-zone-lockdown-ip-allowlist.md`
- `documentation/docs/policies/infra/workers-cost-monitoring-budget-alerts.md`
- Cloudflare WAF documentation: https://developers.cloudflare.com/waf/
- Cloudflare Ruleset Engine: https://developers.cloudflare.com/ruleset-engine/

## Sources

- Cloudflare Terraform Provider v4 — cloudflare_ruleset
- Cloudflare WAF Managed Rules documentation (2025)
- Cloudflare Rate Limiting with the Ruleset Engine
- Internal example.com security runbook v4
