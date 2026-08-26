# cdn-origin-shield-patterns

**Issue:** Using CDN origin shield to reduce origin load and improve cache hit rates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
High origin traffic despite CDN in front of it. Each CDN edge PoP sends its own cache miss to origin, resulting in N×misses for N edges during cold start or low-traffic periods.

## Pattern / Solution
Origin Shield sits between CDN edges and origin, acting as an additional cache tier:

```
User → CDN Edge (PoP, ~300 locations)
         ↓ cache miss
       Origin Shield (single regional node)
         ↓ cache miss
       Origin (ALB / S3 / app server)
```

CloudFront Origin Shield:
```hcl
resource "aws_cloudfront_distribution" "main" {
  origin {
    domain_name = "api.example.com"
    origin_id   = "api"
    origin_shield {
      enabled              = true
      origin_shield_region = "us-east-1"   # choose closest to origin
    }
  }
}
```

Cloudflare Tiered Cache (equivalent concept):
```bash
# Enable via API
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/cache/tiered_cache_smart_topology_enable" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"value":"on"}'
```

When origin shield helps most:
- Objects with TTL > 60 s (shield can satisfy subsequent edge misses)
- Many CDN edge PoPs (global audience) with low per-PoP traffic
- Origin with low concurrency capacity

When it hurts:
- Very short TTL (<5 s) — shield adds latency without cache benefit
- All traffic from one region — no collapse benefit

## Gotchas
- Origin Shield incurs an additional HTTP request charge in CloudFront ($0.0075/10K requests)
- Choose origin shield region closest to your origin datacenter, not your users
- Origin Shield is not a WAF — malicious requests still pass through to it
- Caching on origin shield requires proper Cache-Control headers from origin

## Related
- `aws-cloudfront-patterns.md`
- `global-load-balancing-anycast.md`
- `cache-invalidation-strategies.md`
