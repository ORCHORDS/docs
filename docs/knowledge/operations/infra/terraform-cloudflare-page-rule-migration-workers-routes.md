# Terraform Cloudflare Page Rule Migration to Workers Routes

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare deprecated Page Rules in favour of the Rules suite (Redirect Rules, Cache Rules, Configuration Rules) and Workers Routes. Existing `cloudflare_page_rule` Terraform resources need to be migrated to their modern equivalents without downtime, with state managed cleanly so old resources are removed and new ones are introduced in the same `terraform apply`.

## Context

Page Rules were Cloudflare's original per-URL configuration system. Cloudflare announced their deprecation in 2024 and began removing the UI in 2025. The replacement set is:
- **Redirect Rules** (`cloudflare_ruleset` with `http_request_redirect` action) for URL forwarding
- **Cache Rules** (`cloudflare_ruleset` with `set_cache_settings` action) for cache TTL and bypass
- **Configuration Rules** (`cloudflare_ruleset` with `set_config` action) for security level, SSL mode etc.
- **Workers Routes** (`cloudflare_worker_route`) for routing requests to a Worker script

All of these are zone-level resources in the Cloudflare Terraform provider. Migration is non-trivial because Page Rules evaluated as a priority-ordered list, whereas the new rules pipeline has explicit phases with separate resources.

## 1. Inventory Existing Page Rules

Before writing Terraform, audit what exists:

```bash
# List all page rules for a zone
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/pagerules?status=active&order=priority&direction=asc" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq '.result[] | {priority: .priority, url: .targets[0].constraint.value, actions: [.actions[].id]}'
```

Group page rules by action type to plan the migration target:
- `forwarding_url` → Redirect Rule
- `cache_level`, `edge_cache_ttl`, `bypass_cache_on_cookie` → Cache Rule
- `ssl`, `security_level`, `minify` → Configuration Rule
- Route to Worker → Workers Route

## 2. Migrating URL Forwarding Page Rules to Redirect Rules

**Before (deprecated Page Rule):**

```hcl
resource "cloudflare_page_rule" "www_redirect" {
  zone_id  = var.cloudflare_zone_id
  target   = "www.example.com/*"
  priority = 1
  status   = "active"

  actions {
    forwarding_url {
      url         = "https://example.com/$1"
      status_code = 301
    }
  }
}
```

**After (Redirect Rule via cloudflare_ruleset):**

```hcl
resource "cloudflare_ruleset" "redirect_rules" {
  zone_id     = var.cloudflare_zone_id
  name        = "Redirect Rules"
  description = "Replaces Page Rule URL forwarding"
  kind        = "zone"
  phase       = "http_request_redirect"

  rules {
    action      = "redirect"
    description = "Redirect www to apex"
    enabled     = true
    expression  = "(http.host eq \"www.example.com\")"

    action_parameters {
      from_value {
        status_code = 301
        target_url {
          expression = "concat(\"https://example.com\", http.request.uri.path)"
        }
        preserve_query_string = true
      }
    }
  }
}
```

## 3. Migrating Cache Page Rules to Cache Rules

**Before:**

```hcl
resource "cloudflare_page_rule" "api_cache_bypass" {
  zone_id  = var.cloudflare_zone_id
  target   = "example.com/api/*"
  priority = 2

  actions {
    cache_level = "bypass"
  }
}
```

**After:**

```hcl
resource "cloudflare_ruleset" "cache_rules" {
  zone_id     = var.cloudflare_zone_id
  name        = "Cache Rules"
  description = "Replaces Page Rule cache settings"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  rules {
    action      = "set_cache_settings"
    description = "Bypass cache for API routes"
    enabled     = true
    expression  = "(starts_with(http.request.uri.path, \"/api/\"))"

    action_parameters {
      cache = false
    }
  }

  rules {
    action      = "set_cache_settings"
    description = "Cache static assets 30 days"
    enabled     = true
    expression  = "(http.request.uri.path.extension matches \"(css|js|png|jpg|svg|woff2)\")"

    action_parameters {
      cache = true
      edge_ttl {
        mode    = "override_origin"
        default = 2592000  # 30 days in seconds
      }
      browser_ttl {
        mode    = "override_origin"
        default = 86400    # 1 day
      }
    }
  }
}
```

## 4. Migrating Worker Route Page Rules

**Before:**

```hcl
resource "cloudflare_page_rule" "worker_route_pagerule" {
  zone_id  = var.cloudflare_zone_id
  target   = "example.com/app/*"
  priority = 3

  actions {
    waf          = "on"
    rocket_loader = "off"
  }
}
```

For routing to a Worker, `cloudflare_worker_route` replaces zone-based Worker routing. Note: Workers Routes are independent of Page Rules — this is for cases where routing itself was managed as a page rule:

```hcl
resource "cloudflare_worker_route" "app_route" {
  zone_id     = var.cloudflare_zone_id
  pattern     = "example.com/app/*"
  script_name = cloudflare_worker_script.app_worker.name
}
```

For the WAF/rocket-loader settings that were bundled in the page rule, use a Configuration Rule:

```hcl
resource "cloudflare_ruleset" "config_rules" {
  zone_id     = var.cloudflare_zone_id
  name        = "Configuration Rules"
  description = "Replaces Page Rule configuration actions"
  kind        = "zone"
  phase       = "http_config_settings"

  rules {
    action      = "set_config"
    description = "Disable Rocket Loader on app paths"
    enabled     = true
    expression  = "(starts_with(http.request.uri.path, \"/app/\"))"

    action_parameters {
      rocket_loader = false
    }
  }
}
```

## 5. State Migration — Remove Old, Add New Atomically

To avoid a gap where neither old nor new rules are active, use Terraform's built-in dependency ordering:

```hcl
# Explicitly state that new rules should be created before old are destroyed
resource "cloudflare_ruleset" "redirect_rules" {
  # ... as above
  depends_on = []  # no dependency needed; new resource is independent
}

# Terraform will create new rulesets, then destroy old page rules in same apply
# because cloudflare_page_rule removal has no depends_on the new resources.
# Order: create redirect_rules -> create cache_rules -> destroy page_rules
```

For rules where the old and new would conflict (same URL, same action), use `create_before_destroy`:

```hcl
resource "cloudflare_ruleset" "redirect_rules" {
  zone_id = var.cloudflare_zone_id
  # ...

  lifecycle {
    create_before_destroy = true
  }
}
```

If removing `cloudflare_page_rule` resources from state while keeping them active during cut-over:

```bash
# Step 1: Import new resources into state
terraform import cloudflare_ruleset.redirect_rules <zone_id>/<ruleset_id>

# Step 2: Remove old page rule from state without deleting in API
terraform state rm cloudflare_page_rule.www_redirect

# Step 3: Manually delete via API after verification
curl -X DELETE "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/pagerules/$PAGE_RULE_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN"
```

## 6. Verification Post-Migration

```bash
# Confirm no active page rules remain
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/pagerules?status=active" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result | length'
# Expected: 0

# Confirm redirect rule fires correctly
curl -sI "https://www.example.com/path?q=1" | grep -E "^location:|^HTTP/"

# Confirm cache bypass on API
curl -sI "https://example.com/api/users" | grep -i "cf-cache-status"
# Expected: cf-cache-status: BYPASS

# Confirm Worker route is active
curl -s "https://example.com/app/dashboard" | grep "X-Worker:"

# Terraform plan shows no diff
terraform plan -detailed-exitcode
```

## Anti-patterns

- **Migrating page rules one by one in separate applies** — creates a window where both old and new rules fire simultaneously, potentially doubling redirects or conflicting on cache settings. Migrate all rules for a given action type in one apply.
- **Mapping page rule priority to ruleset rule order without re-evaluating logic** — ruleset rules within a phase are evaluated top-to-bottom with a `continue` or `stop` semantic that differs from page rule priority. Review each rule's `action` to confirm `execute` vs `stop` behavior.
- **Using `cloudflare_page_rule` for new infrastructure** — Cloudflare's API will eventually reject new page rule creation. Write all new routing as Redirect/Cache/Configuration Rules from the start.
- **Forgetting that `cloudflare_ruleset` is zone-global per phase** — there can only be one ruleset per phase per zone in Terraform state. If multiple modules each define `cloudflare_ruleset` for the same phase, they conflict. Centralize all rules for a phase in one resource.
- **Deleting page rules before the new ruleset is applied and verified** — causes a traffic gap for critical redirects (SEO impact) or cache misses.

## Gotchas

- One `cloudflare_ruleset` resource per `phase` per zone. The Cloudflare API enforces this; Terraform apply will 409 if a second resource for the same phase is created.
- `http_request_redirect` phase evaluates before `http_request_cache_settings`. Requests that match a redirect rule never reach cache rules.
- Expressions in Redirect Rules use the Wireup language; Page Rule `*` wildcards do not translate directly. `example.com/*` becomes `(http.host eq "example.com")` plus a path expression.
- `concat()` in `target_url.expression` requires the URL to be a full absolute URL including scheme; missing `https://` causes a 500 from the ruleset engine.
- Workers Routes (`cloudflare_worker_route`) and the `http_request_redirect` ruleset can both match the same path. Routes take precedence — the Worker runs, redirect rule is skipped.

## Related

- `cloudflare-waf-custom-ruleset-terraform.md` — WAF rulesets using the same `cloudflare_ruleset` resource
- `cloudflare-snippets-terraform-edge-js.md` — lightweight edge JS as alternative to Configuration Rules
- `terraform-cloudflare-pages-deployment.md` — Cloudflare Pages routing vs Workers routes
- `wrangler-toml-multi-environment-config.md` — Worker script deployment referenced by routes

## Sources

- https://developers.cloudflare.com/rules/reference/page-rules-migration/
- https://developers.cloudflare.com/rules/redirect-rules/
- https://developers.cloudflare.com/cache/how-to/cache-rules/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_route
- https://developers.cloudflare.com/ruleset-engine/rules-language/expressions/
