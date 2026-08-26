# Terraform Cloudflare Rate Limiting Rules
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Teams protecting Workers APIs with rate limiting configure rules via dashboard or the
deprecated `cloudflare_rate_limit` Terraform resource, which targets the legacy Rate
Limiting product. When the account migrates to the new Ruleset engine (mandatory for
zones on new plans) existing `cloudflare_rate_limit` resources stop applying and the
dashboard shows them as inactive. The Ruleset-based approach (`cloudflare_ruleset` with
`action = "block"` and a `ratelimit` block) is the current method and supports
characteristics, counting expressions, and mitigation periods unavailable in the legacy
product.

## Context

Cloudflare's new rate limiting lives inside the Ruleset engine under the
`http_ratelimit` phase. Each rule in the ruleset can define:

- **Expression** – what requests to count (Wirespeed filter expression)
- **Action** – `block`, `challenge`, `js_challenge`, `managed_challenge`, or `log`
- **Characteristics** – what identifies a unique client (IP, header, cookie, JA3, ASN)
- **Period** – counting window in seconds (10, 60, 600, 3600)
- **Requests per period** – threshold before action fires
- **Mitigation timeout** – how long to keep blocking after threshold exceeded
- **Counting expression** – optional filter to count only a subset of matching requests

The `cloudflare_ruleset` resource with `kind = "zone"` and
`phase = "http_ratelimit"` manages these rules. One ruleset per phase per zone.

## Basic Rate Limiting Ruleset

```hcl
# terraform/modules/rate-limiting/variables.tf
variable "zone_id"    { type = string }
variable "account_id" { type = string }

# terraform/modules/rate-limiting/main.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

resource "cloudflare_ruleset" "rate_limiting" {
  zone_id     = var.zone_id
  name        = "Rate Limiting Rules"
  description = "Managed by Terraform — do not edit in dashboard"
  kind        = "zone"
  phase       = "http_ratelimit"

  # Rule 1: global API rate limit by IP
  rules {
    ref         = "global-api-limit"
    description = "Limit all /api/* requests to 100 req/min per IP"
    expression  = "(http.request.uri.path matches \"^/api/\")"
    action      = "block"
    enabled     = true

    action_parameters {}

    ratelimit {
      characteristics       = ["cf.colo.id", "ip.src"]
      period                = 60
      requests_per_period   = 100
      mitigation_timeout    = 120
      requests_to_origin    = false   # count at edge, do not forward to origin
    }
  }
}
```

## Per-Endpoint Rate Limiting with Counting Expression

A counting expression lets you rate-limit on one expression while only counting a
subset (e.g. count only failed auth responses to detect credential stuffing):

```hcl
resource "cloudflare_ruleset" "rate_limiting" {
  zone_id     = var.zone_id
  name        = "Rate Limiting Rules"
  description = "Managed by Terraform"
  kind        = "zone"
  phase       = "http_ratelimit"

  # Rule 1: login brute-force protection – count only 401/403 responses
  rules {
    ref         = "login-bruteforce"
    description = "Block IPs that trigger 10 auth failures in 60s"
    expression  = "(http.request.uri.path eq \"/api/auth/login\")"
    action      = "block"
    enabled     = true

    action_parameters {}

    ratelimit {
      characteristics      = ["ip.src"]
      period               = 60
      requests_per_period  = 10
      mitigation_timeout   = 600   # 10-minute block after threshold
      counting_expression  = "(http.response.code in {401 403})"
    }
  }

  # Rule 2: registration rate limit by IP + fingerprint
  rules {
    ref         = "registration-limit"
    description = "Limit /api/auth/register to 5 req/10min per IP+JA3"
    expression  = "(http.request.uri.path eq \"/api/auth/register\")"
    action      = "managed_challenge"
    enabled     = true

    action_parameters {}

    ratelimit {
      characteristics      = ["ip.src", "cf.unique_client_id"]
      period               = 600
      requests_per_period  = 5
      mitigation_timeout   = 3600
    }
  }

  # Rule 3: search API – challenge rather than block
  rules {
    ref         = "search-challenge"
    description = "JS challenge on /api/search above 30 req/10min"
    expression  = "(http.request.uri.path starts_with \"/api/search\")"
    action      = "js_challenge"
    enabled     = true

    action_parameters {}

    ratelimit {
      characteristics      = ["ip.src"]
      period               = 600
      requests_per_period  = 30
      mitigation_timeout   = 300
    }
  }

  # Rule 4: catch-all API logging for analysis (log-only, no block)
  rules {
    ref         = "api-log-rate"
    description = "Log high-volume API clients for analysis"
    expression  = "(http.request.uri.path matches \"^/api/\")"
    action      = "log"
    enabled     = true

    action_parameters {}

    ratelimit {
      characteristics      = ["ip.src"]
      period               = 60
      requests_per_period  = 200
      mitigation_timeout   = 0   # log action ignores mitigation_timeout
    }
  }
}
```

Rules within the same ruleset are evaluated in declaration order. Place more specific
rules before general ones; a request matches the first rule whose expression and
ratelimit threshold is met.

## Account-Level Rate Limiting (Workers Routes)

For accounts using zone-less Workers (workers.dev or custom domains without WAF),
apply the ruleset at account level using `kind = "root"` and `phase = "http_ratelimit"`:

```hcl
resource "cloudflare_ruleset" "account_rate_limiting" {
  account_id  = var.account_id
  name        = "Account Rate Limiting"
  description = "Managed by Terraform"
  kind        = "root"
  phase       = "http_ratelimit"

  rules {
    ref         = "workers-api-limit"
    description = "Limit Workers API endpoints to 500 req/min per IP"
    expression  = "(http.request.uri.path matches \"^/api/\")"
    action      = "block"
    enabled     = true

    action_parameters {}

    ratelimit {
      characteristics      = ["ip.src"]
      period               = 60
      requests_per_period  = 500
      mitigation_timeout   = 60
    }
  }
}
```

## Custom Block Response with Action Parameters

Return a JSON error body instead of Cloudflare's default block page:

```hcl
  rules {
    ref         = "api-block-json"
    description = "Block with JSON response body"
    expression  = "(http.request.uri.path matches \"^/api/\")"
    action      = "block"
    enabled     = true

    action_parameters {
      response {
        status_code  = 429
        content_type = "application/json"
        content      = "{\"error\":\"rate_limit_exceeded\",\"retry_after\":60}"
      }
    }

    ratelimit {
      characteristics      = ["ip.src"]
      period               = 60
      requests_per_period  = 100
      mitigation_timeout   = 60
    }
  }
```

## Environment-Specific Rate Limits via Variables

Production gets strict limits; staging is relaxed to allow load tests:

```hcl
# terraform/environments/production/rate-limiting.tf
module "rate_limiting" {
  source  = "../../modules/rate-limiting"
  zone_id = var.zone_id

  api_requests_per_minute = 100
  login_failures_per_minute = 10
  mitigation_timeout_seconds = 600
}

# terraform/environments/staging/rate-limiting.tf
module "rate_limiting" {
  source  = "../../modules/rate-limiting"
  zone_id = var.staging_zone_id

  api_requests_per_minute = 10000
  login_failures_per_minute = 1000
  mitigation_timeout_seconds = 10
}
```

```hcl
# terraform/modules/rate-limiting/variables.tf
variable "api_requests_per_minute"     { type = number; default = 100 }
variable "login_failures_per_minute"   { type = number; default = 10 }
variable "mitigation_timeout_seconds"  { type = number; default = 120 }

# Use variables in the ruleset
ratelimit {
  characteristics      = ["ip.src"]
  period               = 60
  requests_per_period  = var.api_requests_per_minute
  mitigation_timeout   = var.mitigation_timeout_seconds
}
```

## Anti-patterns

- **Using `cloudflare_rate_limit` (legacy resource)** on accounts/zones on new WAF
  plans – rules are silently inactive. Migrate to `cloudflare_ruleset` with
  `phase = "http_ratelimit"`.
- **Creating multiple `cloudflare_ruleset` resources for the same zone+phase** –
  Cloudflare enforces one ruleset per phase per zone. The second `apply` will error.
  Use a single resource with multiple `rules {}` blocks.
- **Setting `mitigation_timeout = 0` with `action = "block"`** – a zero timeout means
  "block forever until the rate limit period resets"; this is rarely the intent. Use a
  positive timeout unless intentional.
- **Omitting `enabled = true`** on rules – rules default to `false` (disabled) if the
  attribute is omitted in some provider versions; always set explicitly.

## Gotchas

- The `cloudflare_ruleset` resource for `http_ratelimit` cannot be imported via
  `terraform import` on zones that have existing dashboard rate limit rules; the import
  ID must be the ruleset UUID found via:
  `GET /zones/{zone_id}/rulesets?phase=http_ratelimit`.
- `cf.unique_client_id` is a JA3-based fingerprint; it requires the zone to have Bot
  Management or Advanced Rate Limiting enabled. Using it without the entitlement causes
  a provider error on apply.
- `counting_expression` must be a valid Wirespeed expression referencing response
  fields (e.g. `http.response.code`). Request-field-only expressions are invalid in
  `counting_expression`.
- Rate limit rules in `http_ratelimit` phase run before `http_request_firewall_custom`.
  A blocked request at rate limit stage does not reach WAF rules.

## Verification

```bash
# List rulesets for the zone – confirm http_ratelimit phase exists
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | select(.phase == "http_ratelimit") | {id, name, rules: (.rules | length)}'

# Get the full ruleset content
RULESET_ID=$(curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq -r '.result[] | select(.phase == "http_ratelimit") | .id')

curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/$RULESET_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.rules[] | {ref, description, enabled}'

# Smoke test: trigger rate limit with ab
ab -n 200 -c 10 "https://example.com/api/data"
# Expect 429 responses after 100 requests within 60s
```

## Related

- `cloudflare-waf-custom-ruleset-terraform.md` – WAF custom rules in the same Ruleset engine
- `cloudflare-network-analytics-ddos-forensics.md` – analyzing rate limit events in Analytics
- `cloudflare-workers-api-token-scoping.md` – least-privilege token for ruleset management
- `cloudflare-zero-trust-staging-prod-isolation.md` – isolating rate limit scopes per env
- `workers-analytics-billing-monitoring.md` – monitoring rate limit event costs

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
- https://developers.cloudflare.com/waf/rate-limiting-rules/
- https://developers.cloudflare.com/ruleset-engine/rules-language/
- https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- https://developers.cloudflare.com/waf/rate-limiting-rules/create-via-api/
