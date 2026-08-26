# global-load-balancing-anycast

**Issue:** Routing users to the nearest region using anycast or GeoDNS for latency reduction
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
All users routed to a single region regardless of location. Global users in Asia/Europe experience 200+ ms latency to US-only infrastructure.

## Pattern / Solution
AWS Global Accelerator (anycast, TCP/UDP):
```hcl
resource "aws_globalaccelerator_accelerator" "main" {
  name            = "prod-ga"
  ip_address_type = "IPV4"
  enabled         = true
}

resource "aws_globalaccelerator_listener" "https" {
  accelerator_arn = aws_globalaccelerator_accelerator.main.id
  protocol        = "TCP"
  port_range { from_port = 443; to_port = 443 }
}

resource "aws_globalaccelerator_endpoint_group" "us" {
  listener_arn                  = aws_globalaccelerator_listener.https.id
  endpoint_group_region         = "us-east-1"
  traffic_dial_percentage       = 100
  health_check_path             = "/health"
  health_check_interval_seconds = 10

  endpoint_configuration {
    endpoint_id = aws_lb.us_east.arn
    weight      = 100
  }
}

resource "aws_globalaccelerator_endpoint_group" "eu" {
  listener_arn            = aws_globalaccelerator_listener.https.id
  endpoint_group_region   = "eu-west-1"
  traffic_dial_percentage = 100

  endpoint_configuration {
    endpoint_id = aws_lb.eu_west.arn
    weight      = 100
  }
}
```

GeoDNS with Route 53 (DNS-based, not anycast):
```hcl
resource "aws_route53_record" "api_latency" {
  zone_id = var.zone_id
  name    = "api.example.com"
  type    = "A"

  latency_routing_policy {
    region = "us-east-1"
  }

  alias {
    name                   = aws_lb.us_east.dns_name
    zone_id                = aws_lb.us_east.zone_id
    evaluate_target_health = true
  }
  set_identifier = "us-east-1"
}
```

Tradeoffs:
```
Anycast (Global Accelerator):
  + Instant failover (seconds, not DNS TTL minutes)
  + Works for TCP/UDP (not just HTTP)
  + 20–60ms latency improvement for cross-region users
  - $0.025/GB data transfer + $0.015/accelerator-hour

GeoDNS (Route 53 Latency):
  + Cheaper
  + Works well for HTTP (clients retry on failure)
  - Failover limited by DNS TTL (60–300s)
  - GSLB must handle stale DNS caches
```

## Gotchas
- Global Accelerator does not cache — it routes; still need CDN for content
- Route 53 health checks must be in the same region as the endpoint for latency routing
- TCP keepalive to Global Accelerator PoPs improves reuse — disable Nagle's algorithm for small messages

## Related
- `cdn-origin-shield-patterns.md`
- `bgp-routing-basics.md`
- `dns-ttl-strategy.md`
