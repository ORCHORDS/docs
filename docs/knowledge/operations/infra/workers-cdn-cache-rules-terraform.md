# Managing Cloudflare Cache Rules with Terraform

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need fine-grained control over what Cloudflare caches, for how long, and under what conditions. Default caching based on file extension is insufficient: API routes must never be cached, static assets should be cached aggressively at the edge, and some pages need stale-while-revalidate semantics to maintain performance during origin slowdowns. Managing these rules via the dashboard causes drift and is not reproducible across zones.

## Context

Cloudflare replaced the legacy Page Rules system (deprecated 2024) with the **Ruleset Engine** for cache configuration. The `cloudflare_ruleset` Terraform resource targets the `http_request_cache_settings` phase and supports rich expressions using the Cloudflare Expression Language. Rules are evaluated top-down and the first matching rule wins unless `continue` is set.

Key concepts:
- **Edge TTL** — how long Cloudflare's cache holds an object (overrides `Cache-Control: s-maxage`).
- **Browser TTL** — how long the end-user browser caches the response.
- **Cache key normalization** — strips irrelevant query params to improve cache hit ratio.
- **Stale-while-revalidate** — serves stale content while fetching a fresh copy in the background.
- **Cache bypass** — instructs Cloudflare to always forward to origin without caching.

## Solution

```hcl
# variables.tf
variable "zone_id" {
  type        = string
  description = "Cloudflare Zone ID"
}

variable "api_hostname" {
  type    = string
  default = "api.example.com"
}

variable "static_hostname" {
  type    = string
  default = "static.example.com"
}

variable "edge_ttl_static_seconds" {
  type    = number
  default = 31536000 # 1 year
}

variable "edge_ttl_page_seconds" {
  type    = number
  default = 300 # 5 minutes
}

variable "browser_ttl_static_seconds" {
  type    = number
  default = 604800 # 1 week
}
```

```hcl
# cache_rules.tf
resource "cloudflare_ruleset" "cache_rules" {
  zone_id     = var.zone_id
  name        = "orchords-cache-rules"
  description = "Cache configuration ruleset — managed by Terraform"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  # Rule 1 — bypass cache for all API paths
  rules {
    ref         = "bypass-api"
    description = "Never cache API responses"
    enabled     = true
    expression  = "(http.host eq \"${var.api_hostname}\") or (http.request.uri.path matches \"^/api/\")"

    action = "set_cache_settings"
    action_parameters {
      cache = false

      # Ensure downstream caches also skip storage
      browser_ttl {
        mode = "bypass"
      }
    }
  }

  # Rule 2 — bypass cache for authenticated requests
  rules {
    ref         = "bypass-authenticated"
    description = "Do not cache requests carrying a session cookie"
    enabled     = true
    expression  = "(http.cookie contains \"session_id=\") or (http.request.headers[\"Authorization\"] ne \"\")"

    action = "set_cache_settings"
    action_parameters {
      cache = false

      browser_ttl {
        mode = "bypass"
      }
    }
  }

  # Rule 3 — aggressive caching for versioned static assets
  rules {
    ref         = "static-assets-immutable"
    description = "Cache fingerprinted static assets for 1 year"
    enabled     = true
    # Matches /static/<hash>.<ext> or assets served from CDN subdomain
    expression  = "(http.host eq \"${var.static_hostname}\") or (http.request.uri.path matches \"^/static/[a-f0-9]{8,}/\")"

    action = "set_cache_settings"
    action_parameters {
      cache = true

      edge_ttl {
        mode    = "override_origin"
        default = var.edge_ttl_static_seconds
      }

      browser_ttl {
        mode    = "override_origin"
        default = var.browser_ttl_static_seconds
      }

      # Respect cache-control headers from origin when stronger
      respect_strong_etags = true
    }
  }

  # Rule 4 — stale-while-revalidate for HTML pages
  rules {
    ref         = "page-cache-swr"
    description = "Short edge TTL with SWR for HTML responses"
    enabled     = true
    expression  = "(http.request.uri.path matches \"\\.(html?)$\") or (http.request.uri.path eq \"/\")"

    action = "set_cache_settings"
    action_parameters {
      cache = true

      edge_ttl {
        mode    = "override_origin"
        default = var.edge_ttl_page_seconds
      }

      browser_ttl {
        mode    = "override_origin"
        default = 60
      }

      # Serve stale while fetching fresh copy (up to 60s background revalidation)
      serve_stale {
        disable_stale_while_updating = false
      }
    }
  }

  # Rule 5 — cache key normalization
  rules {
    ref         = "cache-key-normalization"
    description = "Strip irrelevant query parameters and normalize cache key"
    enabled     = true
    expression  = "true"

    action = "set_cache_settings"
    action_parameters {
      cache = true

      cache_key {
        ignore_query_strings_order = true

        custom_key {
          query_string {
            # Only include these params in the cache key — all others ignored
            include {
              list = ["page", "per_page", "sort", "filter", "locale"]
            }
          }

          header {
            include        = ["Accept-Language"]
            check_presence = ["Authorization"]
          }
        }
      }
    }
  }
}
```

```hcl
# outputs.tf
output "cache_ruleset_id" {
  value       = cloudflare_ruleset.cache_rules.id
  description = "ID of the deployed cache ruleset"
}
```

## Implementation Details

**Rule ordering matters.** Cloudflare evaluates rules sequentially. Place bypass rules (API, authenticated) before permissive caching rules. If the API bypass rule is listed after the static-asset rule the expression for static assets might inadvertently match an API path that ends in `.js`.

**`override_origin` vs `respect_origin`.** Using `override_origin` on `edge_ttl` means Cloudflare will ignore `Cache-Control: max-age` or `s-maxage` headers from your origin and apply the value in Terraform instead. Use this only for static assets where you control cache-busting via filename fingerprinting. For dynamic pages prefer `respect_origin` so origin can signal shorter TTLs during deployments.

**Plan-time validation.** The `cloudflare_ruleset` resource validates expression syntax at plan time via the Cloudflare API (`POST /zones/{zone_id}/rulesets/preview`). CI pipelines should run `terraform plan` with real credentials so expression errors surface before apply.

**Ruleset replacement.** Terraform replaces the entire ruleset resource when `phase` or `kind` changes. Avoid changing these after initial creation — use `lifecycle { prevent_destroy = true }` to protect against accidental deletes.

```hcl
resource "cloudflare_ruleset" "cache_rules" {
  # ...
  lifecycle {
    prevent_destroy = true
  }
}
```

**Multiple rulesets per phase.** Only one ruleset of kind `zone` per phase is allowed. Use a single resource with multiple `rules` blocks rather than separate `cloudflare_ruleset` resources for the same phase.

## Anti-patterns

- **Caching `POST` or `PUT` responses.** Cloudflare does not cache non-idempotent methods by default. Forcing cache on POST responses causes data corruption. Never set `cache = true` without restricting `http.request.method eq "GET"`.
- **Overly broad bypass expressions.** Bypassing the entire zone to avoid one problematic path defeats the purpose of the CDN. Be surgical.
- **Setting `browser_ttl` to values above 1 year.** Browsers cap `max-age` at 365 days. Values above this are silently clamped and differ from what you specified.
- **Omitting the `ref` field.** Without `ref`, Terraform cannot track rule identity and will recreate rules unnecessarily on every plan.
- **Using Page Rules alongside Ruleset cache rules.** Page Rules and Ruleset cache rules can conflict. Migrate all cache Page Rules to the Ruleset Engine before deploying this configuration.

## Gotchas

- The Cloudflare Terraform provider fetches the existing ruleset on every plan. Large rulesets can cause slow plans on rate-limited accounts.
- `serve_stale.disable_stale_while_updating = false` **enables** SWR (the field name is a double negative).
- Cache TTL of `0` means "use origin headers" not "do not cache". Use `cache = false` to bypass.
- `cache_key.custom_key.query_string.include.list` is whitelist mode. An empty list means no query params affect the cache key — every URL variation hits the same cached object. This breaks pagination unless `page` and `per_page` are listed.
- Expression syntax uses double-quotes (`"`), not single-quotes. Terraform HCL requires escaping them as `\"` inside string values.

## Verification

```bash
# Check which cache rules are active on the zone
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" | jq '.result[] | select(.phase == "http_request_cache_settings")'

# Inspect cache headers on a static asset
curl -sI https://static.example.com/static/abc123de/app.js \
  | grep -i -E 'cache-control|cf-cache-status|age|expires'

# Confirm API bypass is working (cf-cache-status should be BYPASS or DYNAMIC)
curl -sI https://api.example.com/v1/health \
  | grep -i 'cf-cache-status'

# Purge cache after a deploy
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything": true}'
```

Expected `cf-cache-status` values:
- `HIT` — served from edge cache
- `MISS` — first request, now cached
- `BYPASS` — cache bypass rule matched
- `DYNAMIC` — Cloudflare determined the response is not cacheable
- `REVALIDATED` — stale content served while background refresh occurred

## Related

- `documentation/docs/policies/infra/terraform-cloudflare.md`
- `documentation/docs/policies/infra/workers-firewall-rules-waf.md`
- `documentation/docs/policies/infra/workers-dns-records-automation.md`
- Cloudflare Ruleset Engine docs: https://developers.cloudflare.com/ruleset-engine/
- Cache Rules migration from Page Rules: https://developers.cloudflare.com/cache/how-to/cache-rules/

## Sources

- Cloudflare Terraform Provider — `cloudflare_ruleset` resource reference
- Cloudflare Cache Rules documentation (2025)
- Cloudflare Expression Language reference
- Internal example.com runbook: CDN configuration v3
