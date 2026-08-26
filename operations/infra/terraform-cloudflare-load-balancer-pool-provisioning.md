# Terraform Cloudflare Load Balancer Pool Provisioning

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to provision Cloudflare Load Balancer pools, origins, health monitors, and the load balancer resource itself through IaC so that origin failover configuration is version-controlled, reviewable in PRs, and replicable across environments — rather than hand-configured in the dashboard.

## Context

Cloudflare Load Balancer (CLB) is composed of four Terraform resources that build on each other: `cloudflare_load_balancer_monitor` defines how origins are probed, `cloudflare_load_balancer_pool` groups origins and references the monitor, `cloudflare_load_balancer` places the balancer on a DNS hostname, and optionally `cloudflare_load_balancer_pool` includes geographic steering for latency-based routing. All resources live in the `cloudflare/cloudflare` Terraform provider v4+.

---

## Health Monitor Definition

```hcl
resource "cloudflare_load_balancer_monitor" "http_check" {
  account_id     = var.account_id
  type           = "http"
  method         = "GET"
  path           = "/health"
  expected_codes = "2xx"
  interval       = 60    # seconds between probes
  retries        = 2
  timeout        = 5
  consecutive_up   = 2   # healthy after 2 consecutive passes
  consecutive_down = 2   # unhealthy after 2 consecutive failures

  header {
    header = "Host"
    values = ["api.example.com"]
  }

  description = "HTTP health check for API origins"
}
```

## Origin Pool with Multiple Regions

```hcl
resource "cloudflare_load_balancer_pool" "primary" {
  account_id         = var.account_id
  name               = "primary-pool"
  monitor            = cloudflare_load_balancer_monitor.http_check.id
  notification_email = "ops@example.com"
  minimum_origins    = 1

  origin {
    name    = "us-east-1"
    address = "10.0.1.50"
    weight  = 1
    enabled = true
    header {
      header = "Host"
      values = ["api.example.com"]
    }
  }

  origin {
    name    = "us-west-2"
    address = "10.0.2.50"
    weight  = 1
    enabled = true
    header {
      header = "Host"
      values = ["api.example.com"]
    }
  }

  load_shedding {
    default_policy    = "random"
    default_threshold = 0
    session_policy    = "hash"
    session_threshold = 0
  }

  origin_steering {
    policy = "random"   # or "hash" for session affinity
  }
}

resource "cloudflare_load_balancer_pool" "fallback" {
  account_id      = var.account_id
  name            = "fallback-pool"
  monitor         = cloudflare_load_balancer_monitor.http_check.id
  minimum_origins = 1

  origin {
    name    = "eu-west-1"
    address = "10.1.0.50"
    weight  = 1
    enabled = true
  }
}
```

## Load Balancer Resource with Geo Steering

```hcl
resource "cloudflare_load_balancer" "api" {
  zone_id          = var.zone_id
  name             = "api.example.com"
  fallback_pool_id = cloudflare_load_balancer_pool.fallback.id
  default_pool_ids = [cloudflare_load_balancer_pool.primary.id]

  proxied     = true
  ttl         = 30    # ignored when proxied = true
  steering_policy = "geo"

  region_pools {
    region   = "WNAM"   # Western North America
    pool_ids = [cloudflare_load_balancer_pool.primary.id]
  }

  region_pools {
    region   = "ENAM"   # Eastern North America
    pool_ids = [cloudflare_load_balancer_pool.primary.id]
  }

  region_pools {
    region   = "WEU"    # Western Europe
    pool_ids = [cloudflare_load_balancer_pool.fallback.id]
  }

  adaptive_routing {
    failover_across_pools = true
  }

  session_affinity = "none"

  rules {
    name      = "bypass-healthcheck-for-internal"
    condition = "http.request.uri.path matches \"^/internal/\""
    overrides {
      steering_policy  = "off"
      default_pool_ids = [cloudflare_load_balancer_pool.primary.id]
    }
  }
}
```

## Dynamic Pool Creation from a Variable Map

```hcl
variable "origin_regions" {
  type = map(object({
    address = string
    weight  = number
  }))
  default = {
    "us-east-1" = { address = "10.0.1.50", weight = 2 }
    "us-west-2" = { address = "10.0.2.50", weight = 1 }
  }
}

resource "cloudflare_load_balancer_pool" "dynamic" {
  account_id      = var.account_id
  name            = "dynamic-pool"
  monitor         = cloudflare_load_balancer_monitor.http_check.id
  minimum_origins = 1

  dynamic "origin" {
    for_each = var.origin_regions
    content {
      name    = origin.key
      address = origin.value.address
      weight  = origin.value.weight
      enabled = true
    }
  }
}
```

## Outputs and Notification Policy

```hcl
output "lb_hostname" {
  value = cloudflare_load_balancer.api.name
}

output "primary_pool_id" {
  value = cloudflare_load_balancer_pool.primary.id
}

# Wire a Cloudflare notification for pool health events
resource "cloudflare_notification_policy" "pool_health" {
  account_id  = var.account_id
  name        = "lb-pool-health-alert"
  enabled     = true
  alert_type  = "load_balancing_pool_enablement_alert"

  email_integration {
    id = "ops@example.com"
  }

  filters {
    pool_id = [cloudflare_load_balancer_pool.primary.id]
  }
}
```

## Anti-patterns

- Setting `proxied = false` on the load balancer DNS record — this exposes origin IPs and bypasses Cloudflare DDoS protection; LBs should always be proxied.
- Using `minimum_origins = 0` — the pool will never be marked unhealthy regardless of how many origins fail, silently routing to down origins.
- Hardcoding origin IPs in Terraform source — use `var` or read from a data source / SSM parameter to keep IPs out of version control.
- Omitting `consecutive_up`/`consecutive_down` on the monitor — defaults are 1/1, which can cause flapping on transient probe failures.
- Pointing `fallback_pool_id` to the same pool as `default_pool_ids` — if the default pool is fully down, the fallback is also down and CLB will return 503 with no useful failover.

## Gotchas

- `cloudflare_load_balancer_monitor` is an account-level resource (not zone-level) and can be shared across multiple pools and zones.
- Changing `origin.address` for an existing origin requires Terraform to destroy and recreate the pool because the origin name is the key; rename the origin or add a new one first.
- `steering_policy = "geo"` requires at least one `region_pools` or `country_pools` block; omitting them causes the policy to fall back to `"off"` silently.
- CLB is a paid Cloudflare add-on; `terraform plan` will succeed but `apply` will fail with a 403 if the account does not have Load Balancing enabled.
- Health checks run from Cloudflare's edge — origins must be reachable from Cloudflare IPs, not just your internal network. Use Cloudflare Tunnel if origins are private.

## Verification

```bash
# Check pool health via API
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/load_balancers/pools" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | \
  jq '.result[] | {name, healthy, origins: [.origins[] | {name, address, healthy: .health.healthy}]}'

# Trigger a manual pool check
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/load_balancers/pools/${POOL_ID}/health" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .

# Verify DNS resolution goes through CLB
dig +short api.example.com          # returns Cloudflare anycast IP
curl -sv https://api.example.com/health 2>&1 | grep "cf-ray"

# Confirm Terraform state matches live config
terraform state show cloudflare_load_balancer.api
```

## Related

- `cloudflare-load-balancer-health-check-workers.md`
- `terraform-cloudflare-notification-policy.md`
- `cloudflare-tunnel-terraform-private-network.md`
- `terraform-cloudflare-dns-zone-record-management.md`
- `global-load-balancing-anycast.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/load_balancer
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/load_balancer_pool
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/load_balancer_monitor
- https://developers.cloudflare.com/load-balancing/understand-basics/load-balancing-components/
- https://developers.cloudflare.com/load-balancing/understand-basics/health-details/
