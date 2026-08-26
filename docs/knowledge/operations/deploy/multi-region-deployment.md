# multi-region-deployment

**Issue:** Deploying services across multiple cloud regions for HA and latency reduction
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single-region deployments have unacceptable blast radius for global services. Multi-region introduces complexity around data consistency, traffic routing, and deployment sequencing.

## Pattern / Solution
Rolling region deployment order:
```
1. Canary region (e.g. us-east-1, lowest traffic)
2. Observe 15 min (error rate, p99 latency)
3. Roll to secondary regions (eu-west-1, ap-southeast-1) in parallel
4. Roll to primary traffic region last
```

Terraform multi-region with provider aliases:
```hcl
provider "aws" {
  alias  = "us_east"
  region = "us-east-1"
}

provider "aws" {
  alias  = "eu_west"
  region = "eu-west-1"
}

module "app_us" {
  source    = "./modules/app"
  providers = { aws = aws.us_east }
  image_tag = var.image_tag
}

module "app_eu" {
  source    = "./modules/app"
  providers = { aws = aws.eu_west }
  image_tag = var.image_tag
}
```

Global traffic routing with Route53 latency records:
```hcl
resource "aws_route53_record" "api" {
  for_each = {
    us-east-1    = aws_lb.us.dns_name
    eu-west-1    = aws_lb.eu.dns_name
  }
  zone_id        = data.aws_route53_zone.main.zone_id
  name           = "api.example.com"
  type           = "A"
  set_identifier = each.key

  latency_routing_policy {
    region = each.key
  }

  alias {
    name                   = each.value
    zone_id                = aws_lb.us.zone_id
    evaluate_target_health = true
  }
}
```

Database replication considerations:
- **Read replicas**: acceptable for eventually consistent reads; primary writes still single-region
- **Multi-region active-active**: requires CRDTs or conflict resolution (DynamoDB Global Tables, CockroachDB, Spanner)
- **Active-passive**: simpler; failover requires DNS TTL flip + promotion

## Gotchas
- DNS TTL must be low (60s) before a planned failover; changing TTL during an incident is too slow
- Session affinity (sticky sessions) breaks when traffic shifts regions; use stateless auth (JWT) instead
- Clock skew between regions causes timestamp ordering bugs; use logical clocks or global clock services
- Deployment to N regions takes N times as long; parallelize where possible but observe each region before proceeding
- Costs roughly double for full active-active; confirm the business requirement before committing

## Related
- `disaster-recovery-failover.md`
- `gitops-argocd-patterns.md`
- `deployment-window-management.md`
