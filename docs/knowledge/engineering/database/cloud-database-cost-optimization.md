# Cloud Database Cost Optimization

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your cloud-managed database bill (RDS, Aurora, Cloud SQL, AlloyDB, Neon) is
growing faster than your traffic. You are paying for over-provisioned
instances, unoptimized storage, excessive I/O, and cross-AZ data transfer
without understanding where the cost comes from.

## Context

Cloud-managed databases charge across multiple dimensions: compute (instance
hours), storage (GB-months), I/O (read/write operations), backups (snapshot
storage), data transfer (cross-AZ, cross-region, internet egress), and
features (Performance Insights, Enhanced Monitoring). Cost optimization
requires understanding which dimensions dominate your bill and targeting
them specifically.

## Cost optimization strategies

### 1. Right-size compute

- **Start small, scale up** — begin with the smallest instance class that
  meets your latency SLO. Monitor CPU, memory, and connection count.
- **Reserved Instances / Savings Plans** — for stable workloads, 1-year
  reserved instances save 30-40%; 3-year saves 50-60% vs. on-demand.
- **Aurora Serverless v2** — for variable workloads, scales between 0.5 and
  128 ACUs. Eliminates over-provisioning but costs more per ACU-hour than
  provisioned at steady state.
- **Stop dev/staging databases** — schedule non-production databases to stop
  outside business hours. Aurora supports stop/start (up to 7 days).

### 2. Optimize storage

- **GP3 over GP2** — GP3 provides baseline 3,000 IOPS and 125 MB/s
  throughput regardless of volume size. GP2 scales IOPS with size, forcing
  you to over-provision storage to get IOPS.
- **Aurora I/O-Optimized** — for I/O-heavy workloads (> 25% of DB cost is
  I/O), Aurora I/O-Optimized eliminates per-I/O charges for a 30% compute
  premium. Break-even is typically around 25-30% I/O cost ratio.
- **Clean up old snapshots** — automated snapshots are retained per your
  retention period, but manual snapshots persist until deleted. Audit and
  delete unused manual snapshots.
- **Storage auto-scaling** — enable for RDS to avoid over-provisioning
  storage upfront. Set a reasonable maximum.

### 3. Reduce I/O

- **Connection pooling** — use PgBouncer or RDS Proxy to reduce connection
  overhead. Each idle connection consumes memory.
- **Query optimization** — the single highest-impact cost lever. One
  unindexed query scanning a full table generates millions of I/O
  operations. Use `EXPLAIN ANALYZE` and add targeted indexes.
- **Read replicas for read-heavy workloads** — route read queries to
  replicas. This offloads the primary and can use smaller instance classes.
- **Caching** — put Redis/ElastiCache in front of frequently-read, rarely-
  changing data. Cache invalidation strategy must match your consistency
  requirements.

### 4. Reduce data transfer

- **Same-AZ placement** — place your application and database in the same
  AZ to eliminate cross-AZ data transfer charges (~$0.01/GB each way).
- **VPC endpoints** — use VPC endpoints for S3, DynamoDB, etc. to avoid NAT
  Gateway data processing charges.
- **Compress backups** — cross-region backup replication incurs data
  transfer charges. Compress where possible.

## Serverless cost traps

- **Aurora Serverless v2 minimum ACU** — the minimum is 0.5 ACU, not zero.
  You pay for 0.5 ACU even when idle. For databases that are truly idle for
  hours, a small provisioned instance with stop/start scheduling is cheaper.
- **Neon branching storage** — Neon charges for storage across all branches.
  Delete unused preview branches promptly.
- **DynamoDB on-demand vs. provisioned** — on-demand pricing is 6-7x more
  expensive per request than provisioned capacity. For predictable workloads,
  provisioned with auto-scaling is significantly cheaper.

## Anti-patterns

- **Over-provisioning "just in case"** — a db.r6g.2xlarge running at 15%
  CPU is wasting 85% of compute cost. Right-size based on actual metrics.
- **Ignoring I/O costs** — on standard Aurora, I/O charges can exceed
  compute costs. Monitor `ReadIOPS` and `WriteIOPS` CloudWatch metrics.
- **Multi-AZ for dev/staging** — Multi-AZ doubles compute cost. Use
  single-AZ for non-production environments.
- **Default backup retention** — the default 7-day retention for RDS
  automated backups is often sufficient. Longer retention increases
  snapshot storage costs.

## Gotchas

- **Reserved Instance coverage monitoring** — track RI utilization in AWS
  Cost Explorer. Unused RIs are wasted spend. Set alerts for < 80%
  utilization.
- **Aurora storage is append-only** — deleting rows does not immediately
  reclaim storage. Storage is reclaimed asynchronously. Large deletes may
  not show immediate cost reduction.
- **RDS Proxy pricing** — RDS Proxy charges per vCPU per hour of the
  associated database instance. For small instances, the proxy can cost
  more than the database itself.
- **Performance Insights free tier** — 7-day retention is free; longer
  retention costs extra. The free tier is usually sufficient.

## Verification

- Enable AWS Cost Explorer database-level cost allocation tags.
- Set up monthly cost anomaly detection alerts (> 20% increase).
- Review `PerformanceInsights` for top SQL by I/O and CPU.
- Track cost-per-query for the top 10 most expensive queries.
- Compare reserved vs. on-demand spend monthly.

## Related

- `documentation/docs/policies/database/connection-pool-sizing.md`
- `documentation/docs/policies/database/query-plan-optimization.md`
- `documentation/docs/policies/database/read-replicas-routing.md`
- `documentation/docs/policies/database/autovacuum-tuning.md`
- `documentation/docs/policies/monitoring/cost-monitoring-dashboards.md`

## Source URLs (verified 2026-08-16)

- AWS RDS pricing — https://aws.amazon.com/rds/pricing/
- Aurora I/O-Optimized — https://aws.amazon.com/rds/aurora/pricing/
- Aurora Serverless v2 — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html
