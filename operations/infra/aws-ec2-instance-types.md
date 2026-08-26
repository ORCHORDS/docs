# aws-ec2-instance-types

**Issue:** Choosing the right EC2 instance family for workload characteristics
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Over-provisioned or wrong-family instances cause cost waste or performance problems. Compute-optimized workloads on general-purpose instances, memory-intensive apps on compute-optimized, etc.

## Pattern / Solution
```
Family    vCPU:RAM ratio  Use case
t4g       burstable       dev/test, low-traffic web
m7i/m7g   1:4             general-purpose app servers
c7i/c7g   1:2             CPU-bound: encoding, ML inference
r7i/r7g   1:8             in-memory DBs, caches, analytics
x2idn     1:32            SAP HANA, large Redis
im4gn     NVMe local      high IOPS scratch, Elasticsearch hot tier
trn1      Trainium        ML training
inf2      Inferentia      ML inference at scale
```

Graviton (g-suffix) instances give 20–40 % cost/perf advantage for most workloads. Prefer them unless software is x86-only.

```bash
# Find cheapest on-demand price for a family in a region
aws ec2 describe-instance-types \
  --filters Name=instance-type,Values=m7g.* \
  --query 'InstanceTypes[*].[InstanceType,VCpuInfo.DefaultVCpus,MemoryInfo.SizeInMiB]' \
  --output table
```

## Gotchas
- t4g burstable instances throttle to baseline CPU when credits exhaust — use unlimited mode or move to m7g for sustained load
- ARM binaries required for Graviton; check all dependencies (especially native Node modules, JVM GC logs)
- Local NVMe on im4gn/i4i is ephemeral — data lost on stop/terminate

## Related
- `spot-instance-strategies.md`
- `auto-scaling-policies.md`
- `cloud-cost-optimization-rightsizing.md`
