# Cloudflare Snippets Terraform Management Edge JS

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to deploy lightweight edge JavaScript logic (header manipulation, redirect rules, bot scoring adjustments) via Cloudflare Snippets rather than full Workers, manage them as Terraform resources, attach snippet rules to specific URL patterns, and keep the JS under version control without reaching for the dashboard.

## Context

Cloudflare Snippets are zone-level, sub-millisecond JavaScript fragments that execute within Cloudflare's request pipeline. They are lighter than Workers: no isolate startup overhead, no Cron/Queues/KV bindings, and capped at 5 ms CPU and 32 KB script size. As of 2026, the Cloudflare Terraform provider (≥ 4.36) exposes `cloudflare_snippet` and `cloudflare_snippet_rules` resources. Snippets target zones (not accounts), fire only on matched URLs, and are intended for cross-cutting header manipulation, early redirects, or A/B routing — use Workers for heavier business logic.

## 1. Provider and Zone Variable

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
  required_version = ">= 1.9"
}

variable "cloudflare_zone_id" {
  type        = string
  description = "Zone ID for the target domain"
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

## 2. Simple Snippet — Security Header Injection

```hcl
resource "cloudflare_snippet" "security_headers" {
  zone_id     = var.cloudflare_zone_id
  name        = "security-headers"
  main_module = "snippet.js"

  files {
    name    = "snippet.js"
    content = file("${path.module}/snippets/security-headers.js")
  }
}
```

```javascript
// snippets/security-headers.js
export default {
  async fetch(request, env) {
    const response = await fetch(request);
    const newHeaders = new Headers(response.headers);

    newHeaders.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload");
    newHeaders.set("X-Content-Type-Options", "nosniff");
    newHeaders.set("X-Frame-Options", "DENY");
    newHeaders.set("Referrer-Policy", "strict-origin-when-cross-origin");
    newHeaders.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
    // Remove fingerprinting headers
    newHeaders.delete("X-Powered-By");
    newHeaders.delete("Server");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: newHeaders,
    });
  },
};
```

## 3. Snippet Rule — URL Pattern Matching

```hcl
resource "cloudflare_snippet_rules" "security_headers_rule" {
  zone_id = var.cloudflare_zone_id

  rules {
    enabled     = true
    expression  = "(http.host eq \"example.com\")"
    description = "Apply security headers on all responses"
    snippet_name = cloudflare_snippet.security_headers.name
  }
}
```

Rules use the same Wireup expression language as WAF custom rules. Multiple snippets can have their own rule blocks but all rules for a zone share one `cloudflare_snippet_rules` resource — it is zone-wide, not per-snippet.

## 4. Multi-File Snippet with Shared Utilities

For snippets that share utility functions across an organization:

```hcl
resource "cloudflare_snippet" "geo_redirect" {
  zone_id     = var.cloudflare_zone_id
  name        = "geo-redirect"
  main_module = "main.js"

  files {
    name    = "main.js"
    content = file("${path.module}/snippets/geo-redirect/main.js")
  }

  files {
    name    = "utils.js"
    content = file("${path.module}/snippets/geo-redirect/utils.js")
  }
}
```

```javascript
// snippets/geo-redirect/utils.js
export function getCountry(request) {
  return request.cf?.country ?? "XX";
}

export function buildRedirectUrl(country, originalUrl) {
  const countryMap = { DE: "de", FR: "fr", JP: "jp" };
  const locale = countryMap[country];
  if (!locale) return null;
  const url = new URL(originalUrl);
  if (url.pathname.startsWith(`/${locale}/`)) return null;
  return `/${locale}${url.pathname}${url.search}`;
}
```

```javascript
// snippets/geo-redirect/main.js
import { getCountry, buildRedirectUrl } from "./utils.js";

export default {
  async fetch(request) {
    const country = getCountry(request);
    const redirect = buildRedirectUrl(country, request.url);
    if (redirect) {
      return Response.redirect(new URL(redirect, request.url).toString(), 302);
    }
    return fetch(request);
  },
};
```

## 5. Snippet Rules with Multiple Patterns

```hcl
resource "cloudflare_snippet_rules" "all_rules" {
  zone_id = var.cloudflare_zone_id

  rules {
    enabled      = true
    expression   = "(http.host eq \"example.com\" and not starts_with(http.request.uri.path, \"/api/\"))"
    description  = "Security headers — non-API paths only"
    snippet_name = cloudflare_snippet.security_headers.name
  }

  rules {
    enabled      = true
    expression   = "(http.host eq \"example.com\" and not cf.bot_management.verified_bot)"
    description  = "Geo redirect for non-bot traffic"
    snippet_name = cloudflare_snippet.geo_redirect.name
  }
}
```

Order within `cloudflare_snippet_rules` mirrors execution order. Snippets fire sequentially; if multiple snippets match a request, all run in rule order.

## 6. Outputs and Drift Detection

```hcl
output "snippet_names" {
  value = {
    security_headers = cloudflare_snippet.security_headers.name
    geo_redirect     = cloudflare_snippet.geo_redirect.name
  }
}
```

Drift detection script using the Cloudflare API:

```bash
#!/usr/bin/env bash
# scripts/check-snippet-drift.sh
set -euo pipefail

ZONE_ID="$1"
TOKEN="$CF_API_TOKEN"

API_SNIPPETS=$(curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/snippets" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.result[].name' | sort)

TF_SNIPPETS=$(terraform output -json snippet_names | jq -r 'values[]' | sort)

DIFF=$(diff <(echo "$TF_SNIPPETS") <(echo "$API_SNIPPETS"))
if [[ -n "$DIFF" ]]; then
  echo "Drift detected:"
  echo "$DIFF"
  exit 1
fi

echo "No snippet drift detected."
```

## Anti-patterns

- **Deploying business logic in Snippets** — Snippets have no KV, D1, Queue, or fetch-to-external bindings by design. Route complex logic to Workers via `fetch(request)` passthrough from the Snippet.
- **Mixing Snippet and WAF custom rule expressions without documentation** — WAF rules fire before Snippets in Cloudflare's request pipeline. A WAF `block` rule will prevent the Snippet from executing. Document the full rule execution order.
- **Putting all zone rules in one `cloudflare_snippet_rules` block without `depends_on`** — Terraform may try to update the rules block before the snippet resources exist. Use implicit references (`snippet_name = cloudflare_snippet.foo.name`) to enforce ordering.
- **Storing multi-kilobyte JS bundles in Snippets** — the 32 KB limit is a hard ceiling. Run the bundle through `wrangler build` first and verify size before Terraform apply.
- **Using Snippets for A/B tests requiring persistent assignment** — Snippets are stateless. Without KV or cookies, assignment will be random on every request. Use Workers or a cookie-based routing approach.

## Gotchas

- There is exactly one `cloudflare_snippet_rules` resource per zone. If multiple modules try to create it, Terraform will conflict. Centralize snippet rules in one root module.
- Snippet names must be unique per zone and can only contain alphanumeric characters and hyphens.
- `cloudflare_snippet` replaces the entire file set on each update — there is no partial file update. All files must be included in each `terraform apply`.
- The Cloudflare dashboard allows snippet creation without Terraform awareness. Run `terraform plan` after any manual dashboard change to detect out-of-band additions.
- Snippet changes do not trigger a zone cache purge. If the snippet modifies cache-related headers, purge explicitly after deployment.

## Verification

```bash
# Confirm snippets exist in Cloudflare
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/snippets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].name'

# Confirm snippet rules are active
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/snippets/snippet_rules" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name: .snippet_name, enabled: .enabled}'

# Live request test — check security headers are present
curl -sI "https://example.com/" | grep -E "Strict-Transport|X-Content-Type|X-Frame"

# Terraform drift check
terraform plan -detailed-exitcode
```

## Related

- `cloudflare-waf-custom-ruleset-terraform.md` — WAF rules that fire before Snippets
- `wrangler-toml-multi-environment-config.md` — building JS artifacts for Snippets and Workers
- `cloudflare-workers-ai-edge-inference.md` — when logic is too complex for Snippets
- `terraform-cloudflare-page-rule-migration-workers-routes.md` — migrating redirect rules to edge JS

## Sources

- https://developers.cloudflare.com/rules/snippets/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/snippet
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/snippet_rules
- https://developers.cloudflare.com/ruleset-engine/rules-language/expressions/
- https://developers.cloudflare.com/rules/snippets/examples/
