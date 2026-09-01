# Mimir Blocks Storage and Retention

Mimir stores Prometheus time-series data as blocks in object storage: ingesters hold recent data in memory and ship blocks to the bucket, the compactor merges and rewrites those blocks into fewer, larger ones per tenant, and the store gateway serves reads. Retention is enforced by deleting whole blocks once their time range falls outside the retention window. Every one of those stages has a size and a cadence, and mismatches between them — a compactor window larger than the retention period, blocks too small to compact efficiently, a bucket growing past the retention horizon — surface as slow queries, storage bills, or data that refuses to disappear.

## Scope

Covers the object-storage-backed block storage path in Grafana Mimir: how blocks flow from ingesters to the bucket, what the compactor does and how its block split interval relates to retention, how retention is configured globally and per tenant, and how to size and monitor the object store. Applies to self-hosted Mimir clusters. Does not cover ingester in-memory limits, the ingest-storage architecture variant, ruler storage, or alertmanager state.

## Workflow or implementation guidance

Design storage and retention together, because the compactor's block layout determines how precisely retention can delete.

1. Choose the object store first. Mimir writes blocks, bucket indexes, and group files to an S3-compatible or GCS bucket. Configure the backend per the object storage backend guide (endpoint, bucket name, credentials, and optionally separate buckets for blocks versus ruler/alertmanager data). Throughput and request-rate limits on the bucket shape everything downstream: compaction and query performance both scale with the store's ability to serve block metadata quickly.
2. Set the compactor block split interval. Mimir's compactor uses a split-and-merge algorithm that processes blocks in fixed time windows and can split high-cardinality tenants' blocks for parallelism. The split interval (for example, one day or two days) fixes the granularity at which blocks exist. Smaller windows mean more blocks and more compaction work; larger windows mean coarser blocks.
3. Set retention deliberately. Retention is a whole-block deletion decision: a block is deleted when its entire time range is older than the retention period. This is the critical constraint — the compactor's split interval must be smaller than or equal to the retention period, or blocks will never age out cleanly, and in the worst case a misconfigured window larger than retention makes deletion unable to progress. Common pairings are a split interval of one day with retention of weeks, or two days with retention of months.
4. Apply per-tenant retention where workloads differ. A global default covers most tenants; per-tenant overrides (via runtime configuration) let high-volume tenants keep days while compliance-bound tenants keep years. Changing retention downward is safe — deletion only accelerates — but verify the tenant ID mapping before applying, because retention applies per tenant and a wrong ID silently deletes the wrong tenant's history.
5. Size the store gateway and query path against block counts. Blocks per tenant drives query fan-out: the store gateway must load block indexes, so more (smaller) blocks mean more index loads. If queries slow after retention or compaction changes, inspect the block count per tenant and the compactor's output sizes rather than immediately scaling the query frontend.
6. Monitor the deletion pipeline. The compactor applies retention as part of its work; if the compactor is down or backed up, blocks age past retention but are not deleted, and storage grows. Watch the compactor's own metrics for block deletion counts and the bucket for object counts versus the retention horizon.

## Controls

- Compactor split interval and retention declared together in configuration, with a CI validation that split interval is less than retention for every tenant override.
- Object storage backend configuration with explicit request-rate and throughput expectations documented against the provider's limits.
- Per-tenant retention overrides in runtime configuration under change review, with a tenant-to-owner mapping kept alongside.
- Bucket inventory monitoring: object count, bytes, and oldest-object age compared against the retention horizon, alerting when oldest age exceeds retention by more than one compaction cycle.
- Compactor health checks: compaction cycles completed, blocks produced and deleted, and job duration, with alerting on stalled compaction.
- Quarterly storage forecast: bytes per tenant per day trended against the retention setting to project bucket growth.

## Validation evidence

Retention work is proven by deletion evidence: a bucket inventory listing (via the provider's CLI) taken before and after a retention change, showing object counts and oldest-object timestamps converging to the retention horizon within the expected number of compaction cycles. The second artifact is a query-latency comparison across the change, showing that block layout shifts did not degrade p95 query time. For sizing claims, a load test that ingests at projected peak for several compaction windows and reports blocks-per-tenant and store-gateway index load closes the evidence set. Mimir's own monitoring dashboards (compactor and object-store dashboards) captured during these windows are the filed artifacts.

## Failure modes and correction

- Storage grows past the retention horizon: the compactor is stalled or its split interval exceeds retention. Check compactor ring health and cycle metrics first; fix the interval mismatch if present.
- Queries slow after retention shortened: block layout changed — short retention with a small split interval yields many tiny blocks. Increase the split interval or enable additional compactor splitting/parallelism settings to consolidate.
- Wrong tenant's data deleted: a per-tenant override was applied to the wrong ID. Recover from the object store's versioning if enabled, and institute the tenant-to-owner mapping review before any override merge.
- Bucket request throttling during compaction: the provider's rate limits are below the compactor's demand. Reduce compactor concurrency or request limit increases; check that the bucket index interval is not forcing excessive metadata reads.
- Deletes lag on high-cardinality tenants: their block count makes compaction cycles long. Increase compactor sharding (more instances in the ring) for those tenants or split blocks further.

## Limitations

Retention is block-granular: data disappears in whole compaction windows, so effective retention is retention plus up to one split interval, never an exact timestamp. Exact parameter names and defaults change across Mimir versions; the configuration-parameters reference for the deployed version is authoritative. Object store behavior (versioning, eventual consistency of deletes, rate limits) is provider-specific and outside Mimir's control. This article does not address the newer ingest-storage architecture, which changes some components' roles. Compactor sizing guidance is empirical and must be validated against observed cycle durations.

## Canonical sources

- Mimir metrics storage retention configuration: https://grafana.com/docs/mimir/latest/configure/configure-metrics-storage-retention/
- Mimir object storage backend configuration: https://grafana.com/docs/mimir/latest/configure/configure-object-storage-backend/
- Mimir compactor reference: https://grafana.com/docs/mimir/latest/references/architecture/components/compactor/
