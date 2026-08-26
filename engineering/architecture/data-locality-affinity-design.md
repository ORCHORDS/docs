# data-locality-affinity-design

**Issue:** A distributed workload moves large volumes of data across racks, availability zones, or regions to reach the compute that processes it. Cross-zone and cross-region transfer is both the slowest hop in the system and one of the most expensive line items on the cloud bill, and in cloud provider pricing inter-AZ/inter-region egress is billed while same-AZ traffic often is not. Teams routinely shard their data for scale, then schedule processing, caches, and services with no awareness of where each shard physically lives, paying the latency and cost penalty on every request. The system needs an explicit data-locality and affinity design that decides what moves to the data, what data moves to the compute, and how placement is enforced as the fleet scales.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Principles

1. **Moving computation is cheaper than moving data.** The HDFS design doc states this as the guiding rule: running computation close to the data reduces network congestion and raises throughput, and the platform should expose interfaces that let applications relocate themselves nearer their data. For any dataset measured in gigabytes per request, scheduling the job to the data beats streaming the data to the job.
2. **Placement is a reliability decision, not just a performance one.** HDFS treats replica placement as "critical to reliability and performance": with replication factor three, one replica goes to the writer's rack, and two go to a different rack, cutting inter-rack write traffic while surviving rack loss. Locality decisions must be co-designed with the failure-domain model, or you optimize latency into a blast radius.
3. **Prefer the closest replica on reads.** HDFS serves reads from the replica nearest the reader — same rack first, local data center for multi-DC clusters. Read locality is the cheap half of the pattern: if data is already replicated, route the request instead of moving bytes.
4. **Affinity is a scheduling contract.** Kubernetes node affinity, pod anti-affinity, and topology spread constraints let you declare "this service must sit near that dataset" and "these replicas must not share a rack" so placement survives rescheduling, node failure, and autoscaling without human intervention.
5. **Data gravity dictates architecture tiers.** Hot working sets belong co-located with compute (local NVMe, memory), warm data in the same zone, cold data in object storage in one home region. Design the tier boundaries around access frequency, not around storage convenience.
6. **Measure locality, do not assume it.** Export per-request metrics tagged with the zone of the client, the zone of the server, and the bytes transferred. Aggregate cross-zone ratio and make it a tracked SLO-style indicator; refactors that silently break affinity show up here first.

## Implementation Approaches

1. **Topology-aware partition assignment.** Assign Kafka partitions, cache slots, or shards to specific zones and pin the consumers to the same zones (Kubernetes topology-aware hints or node affinity on the consumer deployment). Cross-zone traffic then only occurs during rebalances and failover, not steady state.
2. **Rack/zone-aware replication.** Follow the HDFS-derived rule of thumb: keep a majority of replicas inside one failure domain for fast local quorum writes, and place at least one replica outside it for durability. Most distributed stores (Ceph, Kafka with rack awareness, Consul network segments) support a rack/zone hint — configure it rather than accepting random placement.
3. **Region pinning for residency and cost.** Pin each tenant's or entity's data to a home region and route writes there (see multi-region-write-patterns); serve cross-region reads from CDN/cache layers where legally permitted. This keeps steady-state egress near zero and satisfies data-residency policy in one mechanism.
4. **Compute-to-data dispatch for batch.** For Spark/Hadoop-style pipelines, use delayed scheduling: wait a short window for a slot on a node holding the input split before accepting a rack-local or off-rack slot. A few seconds of scheduler patience eliminates most cross-rack shuffles.
5. **Colocated cache tiers.** Put per-shard caches (Redis with hash-slot pinning, or local process caches keyed by shard) in the same zone as the primary shard, and treat cache misses that cross zones as a signal of affinity drift.
6. **Locality-aware load balancing.** Extend the service mesh or LB to prefer same-zone backends (zone-aware routing) and only spill to remote zones when local capacity is exhausted, so failover remains automatic but is not the default path.

## Gotchas and Failure Modes

1. **Affinity couples you to topology.** If stateless services are hard-pinned to zones containing their data, a zone outage takes out compute that could otherwise have failed over. Prefer soft (preferred) affinity with a documented failover path, and test zone drain regularly.
2. **Rebalancing destroys locality silently.** Kafka rebalances, cache resharding, and database failover all reshuffle placement; after any such event, re-verify locality metrics before assuming the old performance profile still holds.
3. **Autoscaling ignores data unless told.** New nodes come up in whatever zone has spare capacity. Without topology spread constraints and topology-aware hints, an elastic fleet gradually drifts away from its data.
4. **Locality vs skew conflicts.** A hot partition plus strict co-location can overload the single zone holding it. Design for the hot-key path to spill over (read replicas in a second zone) instead of hard-failing on locality.
5. **Egress cost asymmetry.** Inter-AZ transfer is billed in both directions on some providers and replication amplifies it (three replicas = multiple billed hops per write). Model replication fan-out cost before choosing replication factors across zones.
6. **Data residency overrides performance.** In regulated workloads, legal constraints on where data may live outrank latency optimization; design locality as a policy engine (allowed zones per data class) with performance tuning inside the allowed set.

## When (Not) To Apply

1. **Apply when payloads are large relative to processing.** Media transcoding, ML feature preparation, log analytics, and full-table scans are the canonical cases — the ratio of bytes moved to CPU spent justifies placement work.
2. **Apply in multi-region SaaS.** Tenant home-region pinning plus zone-aware internal routing is usually the single largest latency and egress win available.
3. **Skip for small, chatty request/response systems.** If payloads are kilobytes and p99 is dominated by queueing or GC, placement work is premature; fix the service-level issues first.
4. **Skip when the storage layer already enforces locality.** Distributed databases with built-in zone-aware placement (consensus-based stores that keep quorums zone-local) already implement this for you; duplicating it at the application layer adds coupling without benefit.
