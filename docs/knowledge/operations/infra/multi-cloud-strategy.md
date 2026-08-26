# multi-cloud-strategy

**Issue:** Patterns and tradeoffs for running workloads across multiple cloud providers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams choose multi-cloud for risk diversification or vendor leverage but underestimate the operational complexity and egress cost. Single workloads split across clouds create latency and consistency challenges.

## Pattern / Solution
Pragmatic multi-cloud taxonomy:
```
Active-Active (same workload on 2+ clouds):
  → Highest resilience, highest ops complexity
  → Requires: cloud-agnostic data layer, global load balancing, conflict resolution

Active-Passive (primary cloud + DR on secondary):
  → Moderate complexity, RPO/RTO depends on replication lag
  → Suitable for most enterprise DR requirements

Workload segmentation (different workloads on different clouds):
  → Most common; simplest operationally
  → e.g. ML training on GCP (TPUs), SaaS product on AWS
```

Infrastructure abstraction for portability:
```hcl
# Use Terraform modules with per-cloud implementations
module "compute" {
  source = "./modules/compute-aws"   # swap to compute-gcp, compute-azure
  instance_count = 3
  machine_type   = "medium"
}
```

Data portability:
- Use Parquet/ORC in object storage (S3/GCS/Azure Blob) — readable by any cloud's query engine
- Avoid cloud-proprietary formats: DynamoDB streams, Firestore native API without abstraction
- Replicate critical data with Kafka MirrorMaker 2 or Debezium across cloud boundaries

Egress cost awareness:
```
AWS → Internet:  ~$0.09/GB
GCP → Internet:  ~$0.08/GB
Azure → Internet: ~$0.087/GB
Cross-cloud data transfer: varies $0.02–0.09/GB depending on region pair
```

## Gotchas
- Multi-cloud does not eliminate downtime — a bad deploy affects both clouds simultaneously
- IAM/identity is not portable — each cloud has its own RBAC model
- Monitoring requires a cloud-agnostic layer (Datadog, Grafana Cloud, OpenTelemetry collector)
- Kubernetes helps with portability but storage classes, load balancers, and IAM annotations remain cloud-specific

## Related
- `cloud-cost-optimization-rightsizing.md`
- `global-load-balancing-anycast.md`
- `object-storage-replication.md`
