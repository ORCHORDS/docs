# hot-partition-mitigation

**Issue:** Hash-partitioned systems (DynamoDB, Cassandra, Kafka, Kinesis, any consistent-hashing cluster) spread load evenly only if the partition keys are evenly distributed in *access*, not just in *cardinality*. One viral celebrity profile, one whale tenant, one trending product key, or a producer that pins every message to a single Kafka key creates a hot partition: a single shard absorbing a disproportionate share of traffic. Because per-partition throughput limits are physical and independent of total cluster capacity (DynamoDB's ~1000 WCU/3000 RCU per partition key ceiling still applies even on on-demand mode, per AWS throttling docs and Stack Overflow clarifications), the cluster can be 97 percent idle while the hot key returns THROTTLING exceptions. Kafka's mirror problem is a hot *broker* or skewed partition driving disk and network saturation while peers sit idle, and AutoMQ's 2025 engineering guide separates key skew from broker-limit saturation precisely because the fixes differ. Hot partitions are a key-design disease, so the cures are mostly schema and access-pattern redesign, applied before the incident rather than during it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Detection First

1. **Per-partition metrics, not fleet aggregates.** Fleet-average utilization hides a 60x-skewed key behind healthy averages. Instrument per-key/partition throughput: DynamoDB's CloudWatch throttling and hot-partition metrics, Cassandra's per-table read/write histograms plus tablet-level metrics in 5.x, Kafka's partition-level bytes-in and lag metrics. Alert on skew ratios (max partition / mean partition), not absolute values.
2. **Classify the skew before fixing it.** AWS's throttling guide and AutoMQ's Kafka guide converge on the same triage: a *fixed* hot key (always the same celebrity) is a data-model problem; a *moving* hotspot (currently-trending item, round-robin by hour) is a capacity/adaptive problem; *uniform overload* (everything hot) is a scaling problem that no key trick will fix. Applying salting to a uniformly overloaded table just moves the throttling.
3. **Distinguish read heat from write heat.** Hot reads and hot writes have different cures (caching vs sharding). A key that is read-hot but write-cold wants a cache; a write-hot key needs physical spread. Measure both directions per key before choosing.

## Data-Model Cures

1. **Write sharding (key salting).** Append a random or bucketed suffix to the hot partition key — userId#0..9 writes to ten partitions; reads either query all ten in parallel and merge, or track which bucket holds the item. OneUptime's 2026 DynamoDB guide and AWS docs both present this as the first-line fix. The read fan-out cost is the price of admission; keep the salt count small (single digit) so scatter-gather stays cheap.
2. **Bucket with a directory entry.** A refinement that avoids read fan-out: a directory row (or cached pointer) maps the logical item to its current bucket N; writes go to userId#N with N rotated on pressure, reads hit the directory first. Adds a hop, removes the scatter — right when items are large or fan-out dominates read latency.
3. **Split the hot item across time buckets.** For time-series-ish heat (counters, leaderboards, rolling stats), shard by sub-key like (minute-bucket, item) and aggregate at read time. Each bucket gets its own partition placement and the write rate divides by bucket cardinality.
4. **Remodel aggregates as increments spread over shards.** A global counter hammered at 10k writes/sec becomes N shard counters (shard chosen per write) summed on read — this is a PN-Counter CRDT shape (see crdt-conflict-free-data-types) and also how rate-limiter buckets and view counters survive virality.

## Infrastructure Cures

1. **Caching for read heat.** DAX (DynamoDB), Redis, or a CDN in front of read-hot keys converts per-partition read limits into cache-hit capacity. Cache the hot tail aggressively; the read-repair cost of short TTLs is usually trivial versus the throttling pain. See cache-aside-pattern and read-through-cache for placement.
2. **Adaptive capacity and warm throughput.** DynamoDB's adaptive capacity automatically isolates a persistently hot key onto dedicated capacity, and pre-provisioned warm throughput smooths known spikes (launches, cron bursts). These are cushions, not designs — adaptive capacity engages after throttling begins, so treat alerts from it as "your key design is wrong" signals.
3. **Custom partitioners / more partitions in Kafka.** For producer-pinned skew: raise partition counts so a single key's partition is small relative to broker limits, use a partitioner that hashes high-cardinality fields, or explicitly strip keys when ordering per-entity is not required (ordering lives per partition — dropping the key trades ordering for spread). For consumer skew (one slow group member), the dead-letter-queue-architecture and priority-queue-architecture patterns absorb poison messages that stall a hot consumer group.
4. **Isolate whales by design.** Multi-tenant systems should give known-heavy tenants their own keyspace/table/cell (see multi-tenant-architecture and cell-based-architecture) so one tenant's virality cannot tax shared partitions. Tenant-routing rules can direct whale traffic to dedicated shards reactively.

## Operational Playbook

1. **Pre-launch key-skew review.** Before shipping a new table/topic, list the top-10 realistic access patterns and eyeball their key concentration. This ten-minute review catches most hot partitions that later become incidents.
2. **Load test with a Zipf workload.** Uniform test data hides skew; generate traffic with a Zipf/80-20 distribution over keys to observe real partition behavior under heat before production does it for you.
3. **Have a salting migration path.** Moving an existing hot table to salted keys means dual-writing or backfilling both layouts, then flipping reads — the same expand-contract discipline as zero-downtime-schema-migrations. Write the runbook when the table is young and cold, not during the outage.
4. **Blast-radius guardrails.** Cap per-key request rates at the application layer (token bucket per entity — rate-limiter-design) so one viral entity degrades gracefully instead of consuming the table's adaptive capacity budget that other keys may need.
5. **Related articles.** consistent-hashing explains why partitions form; sharding-strategy covers key choice at design time; this article covers what to do when the choice turned out wrong.
