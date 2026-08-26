# Terraform Cloudflare Workers Routes and Zone Configuration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to route specific URL patterns on an existing zone to a Cloudflare Worker
without migrating the entire hostname to a custom domain. This is typical for
augmenting a legacy origin — intercepting `/api/*` with a Worker while letting
`/static/*` pass through to S3. Managing routes manually through the dashboard
creates drift between environments. You also need to configure zone-level settings
(compression, TLS version, cache behaviour) alongside the routes in the same Terraform
plan.

---

## Context

Workers Routes attach a Worker script to a URL pattern on a zone. Unlike Custom
Domains (which own the entire hostname), routes coexist with other zone features:
Cache Rules, Page Rules, Firewall, and origin pass-through all apply after the Worker
executes or invokes `fetch()`.

Key resources:

| Resource | Purpose |
|----------|---------|
| `cloudflare_worker_route` | Binds a URL pattern on a zone to a Worker script |
| `cloudflare_zone_setting` | Controls per-zone settings (TLS, compression, always-HTTPS) |
| `cloudflare_worker_script` | The Worker code itself |
| `cloudflare_ruleset` | Zone-level rulesets (Cache Rules, Transform Rules, etc.) |

This article does **not** cover Custom Domains (`cloudflare_workers_domain`); see
`terraform-cloudflare-workers-custom-domain-routing.md` for that pattern.

---

## 1. Variables and Provider

```hcl
# variables.tf
variable "cloudflare_api_token" {
  type      = string
  sensitive = true
  description = "Token with Zone:Edit + Workers Routes:Edit + Workers Scripts:Edit"
}

variable "account_id" { type = string }
variable "zone_id"    { type = string }
variable "zone_name"  { type = string }   # e.g. "example.com"

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

---

## 2. Worker Script

```hcl
# worker.tf
resource "cloudflare_worker_script" "api" {
  account_id         = var.account_id
  name               = "zone-api-handler"
  content            = file("${path.module}/dist/worker.js")
  compatibility_date = "2024-09-23"

  kv_namespace_binding {
    name         = "CACHE"
    namespace_id = cloudflare_workers_kv_namespace.cache.id
  }
}

resource "cloudflare_workers_kv_namespace" "cache" {
  account_id = var.account_id
  title      = "zone-api-handler-cache"
}
```

---

## 3. Workers Routes

```hcl
# routes.tf
locals {
  routes = {
    api     = "${var.zone_name}/api/*"
    graphql = "${var.zone_name}/graphql"
    webhook = "${var.zone_name}/webhooks/*"
  }
}

resource "cloudflare_worker_route" "routes" {
  for_each = local.routes

  zone_id = var.zone_id
  pattern = each.value
  script_name = cloudflare_worker_script.api.name

  depends_on = [cloudflare_worker_script.api]
}
```

Route patterns support `*` as a wildcard (matching zero or more characters) but not
`**`. Patterns are matched against the full URL path including the leading slash.

To disable a route without deleting it (useful for emergency rollback), set
`script_name = ""`:

```hcl
# Rollback: comment out the script_name and uncomment the line below
# script_name = ""
```

---

## 4. Zone Settings

```hcl
# zone-settings.tf

# Enforce TLS 1.2 minimum
resource "cloudflare_zone_setting" "min_tls" {
  zone_id  = var.zone_id
  setting_id = "min_tls_version"
  value    = "1.2"
}

# Enable Brotli compression
resource "cloudflare_zone_setting" "brotli" {
  zone_id    = var.zone_id
  setting_id = "brotli"
  value      = "on"
}

# Force HTTPS redirect at the zone level
resource "cloudflare_zone_setting" "always_https" {
  zone_id    = var.zone_id
  setting_id = "always_use_https"
  value      = "on"
}

# Enable HTTP/2
resource "cloudflare_zone_setting" "http2" {
  zone_id    = var.zone_id
  setting_id = "http2"
  value      = "on"
}

# Cache level — aggressive caching for static assets
resource "cloudflare_zone_setting" "cache_level" {
  zone_id    = var.zone_id
  setting_id = "cache_level"
  value      = "aggressive"
}
```

Zone settings are account-wide defaults overridable per-request by Workers via the
`cf` fetch option or by Cache Rules. Keep them in the same Terraform module as routes
so the plan shows the full zone configuration in one diff.

---

## 5. Cache Rules for Worker Bypass

When a Worker issues `fetch(request, { cf: { cacheEverything: true } })`, you may
want to ensure the zone's Cache Rules do not conflict. Declare cache rules explicitly:

```hcl
# cache-rules.tf
resource "cloudflare_ruleset" "cache_rules" {
  zone_id     = var.zone_id
  name        = "Cache Rules"
  description = "Zone-level cache configuration"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  rules {
    action      = "set_cache_settings"
    description = "Cache static assets for 24h"
    expression  = "(http.request.uri.path matches \"^/static/\")"
    enabled     = true

    action_parameters {
      cache = true
      edge_ttl {
        mode    = "override_origin"
        default = 86400
      }
      browser_ttl {
        mode    = "override_origin"
        default = 3600
      }
    }
  }

  rules {
    action      = "set_cache_settings"
    description = "Bypass cache for API routes (Worker handles caching)"
    expression  = "(http.request.uri.path matches \"^/api/\")"
    enabled     = true

    action_parameters {
      cache = false
    }
  }
}
```

---

## 6. TypeScript Worker Using the Route Context

```typescript
// src/index.ts
export interface Env {
  CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const cacheKey = url.pathname;

    // Only handle paths this route covers
    if (!url.pathname.startsWith("/api/")) {
      // Pass through to origin for non-matched patterns
      return fetch(request);
    }

    // Check KV cache first
    const cached = await env.CACHE.get(cacheKey, "text");
    if (cached) {
      return new Response(cached, {
        headers: {
          "Content-Type": "application/json",
          "X-Cache": "HIT",
        },
      });
    }

    // Fetch from origin and cache the response
    const origin = await fetch(request);
    if (origin.ok) {
      const body = await origin.text();
      ctx.waitUntil(env.CACHE.put(cacheKey, body, { expirationTtl: 300 }));
      return new Response(body, {
        headers: {
          ...Object.fromEntries(origin.headers),
          "X-Cache": "MISS",
        },
      });
    }

    return origin;
  },
} satisfies ExportedHandler<Env>;
```

---

## 7. Route Ordering and Conflict Detection

Multiple routes can match the same URL. Cloudflare evaluates routes in order of
specificity (longest matching pattern wins). Document the intended precedence in code:

```hcl
# routes.tf (extended)
locals {
  # More specific patterns must be declared — Cloudflare resolves by longest match,
  # but Terraform does not enforce ordering. Document it here.
  # /api/v2/* is more specific than /api/* — both are valid simultaneously.
  routes = {
    api_v2  = "${var.zone_name}/api/v2/*"   # Handled by v2-worker
    api_v1  = "${var.zone_name}/api/*"      # Handled by api-worker (fallback)
  }
}
```

Use `terraform plan` to detect accidental duplicate patterns — the Cloudflare API
returns an error for exact duplicate patterns on the same zone.

---

## Anti-patterns

- **Wildcard-only route `example.com/*`** — This captures all traffic on the zone,
  including assets and the apex domain. A broken Worker will take the entire site down.
  Use narrow patterns and test in staging first.
- **Managing routes without managing the Worker script** — If the script is deployed
  out-of-band (e.g. via `wrangler deploy`), Terraform state diverges and the next
  `terraform apply` may destroy and recreate the route.
- **Mixing zone settings between Terraform and dashboard** — Zone settings not declared
  in Terraform are treated as out-of-band and will not be reverted by `terraform apply`.
  Import existing settings with `terraform import`.
- **Setting `cache_level = "bypass"` zone-wide** — This defeats CDN caching for all
  assets. Use Cache Rules to bypass only specific paths.

---

## Gotchas

- `cloudflare_worker_route` `pattern` must include the scheme-less hostname (e.g.
  `example.com/api/*`, not `/api/*`). A missing hostname causes a 400 from the API.
- Deleting a `cloudflare_worker_route` resource does not delete the Worker script.
  Traffic to the former pattern falls through to the next matching route or origin.
- Zone settings like `http2` or `http3` are plan-level features. The Cloudflare
  provider may return an error if the zone's plan does not support the setting.
- `for_each` on routes requires stable keys. If a route's key changes (e.g.
  renaming `api` to `api_v1`), Terraform deletes the old route and creates a new one,
  causing a brief gap in routing.

---

## Verification

```bash
# List all routes for a zone
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/workers/routes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[] | {id, pattern, script}]'

# Check zone settings
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[] | select(.id == "min_tls_version" or .id == "brotli")]'

# Verify route is active by hitting a matched URL
curl -sv "https://example.com/api/health" 2>&1 | grep -E "cf-ray|server|x-cache"

# Terraform refresh to detect drift
terraform apply -refresh-only
```

---

## Related

- `terraform-cloudflare-workers-custom-domain-routing.md`
- `terraform-cloudflare-page-rule-migration-workers-routes.md`
- `terraform-cloudflare-rate-limiting-rules.md`
- `cloudflare-waf-custom-ruleset-terraform.md`
- `wrangler-toml-multi-environment-config.md`

---

## Sources

- Cloudflare Workers Routes docs: https://developers.cloudflare.com/workers/configuration/routing/routes/
- Terraform `cloudflare_worker_route`: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_route
- Terraform `cloudflare_zone_setting`: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zone_setting
- Cloudflare Cache Rules: https://developers.cloudflare.com/cache/how-to/cache-rules/
