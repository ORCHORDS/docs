# multi-region-write-patterns

**Issue:** The service is deployed to several regions for latency and availability, and the hardest question is not where reads come from but where writes go. Single-writer designs make every distant user pay a cross-region round trip on the most sensitive operation; multi-writer designs invite conflicting concurrent updates to the same record that must then be resolved. AWS's DynamoDB global tables documentation captures the full spectrum — asynchronous multi-region eventual consistency with per-item "last writer wins" resolution on one end, and multi-region strong consistency with synchronous replication, three-region topology, and write-conflict exceptions on the other. Choosing a write pattern is really choosing which consistency violations and latency bills the product can tolerate, per data category, before a single region is provisioned.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Principles

1. **The write path defines the consistency contract.** Reads can be served from replicas, caches, or CDN edges; only writes determine what the truth is and when. Select the write pattern per entity or table, not per system — profile data, counters, and financial ledgers have wildly different tolerances.
2. **Every multi-writer system has a conflict story; make it explicit.** DynamoDB MREC resolves concurrent writes to the same item with the latest internal timestamp per item ("last writer wins") and converges all replicas to the last write. That is a deliberate choice: simple and convergent, but capable of silently discarding a concurrent update. Systems that cannot tolerate that discard need a different pattern.
3. **Strong cross-region consistency is synchronous and constrained.** DynamoDB MRSC replicates "to at least one other Region before the write operation returns," requires exactly three regions (two replicas plus an optional witness), and fails overlapping writes with a retryable `ReplicatedWriteConflictException`. Global correctness is bought with write latency and a fixed topology.
4. **RPO is the deciding metric between the modes.** MREC's recovery point equals replication delay between replicas (typically under a second, per AWS); MRSC delivers RPO zero at the cost of higher write and strongly consistent read latencies. Write the RPO requirement down before choosing.
5. **Conditional writes evaluate where you write.** In MREC, conditional writes "evaluate the condition expression against the version of the item in the Region" receiving the write — not globally. Validation logic that assumes a global view of state is wrong by construction in an async multi-writer system.
6. **Replication lag is observable; budget for it.** ReplicationLatency metrics exist per region pair, depend on distance between regions, and rising values are the signal to shift traffic. Monitoring lag is part of the write pattern, not an ops afterthought.

## Implementation Approaches

1. **Home-region pinning (single writer per entity).** Route each user's or tenant's writes to their designated home region; all other regions serve reads from replication. Local writes stay fast, conflicts are structurally impossible, and residency falls out for free; the costs are routing infrastructure and failover when a home region is impaired.
2. **Write forwarding.** Accept writes at the nearest edge and synchronously forward them to the authoritative region, returning the confirmation from there. Users get one logical endpoint; distant users still pay the round trip but the application never has to know which region owns the data.
3. **Asynchronous multi-writer with LWW (MREC-style).** Every region accepts writes and replicates asynchronously (typically sub-second), converging via last-writer-wins per item. Best for conflict-tolerant data — presence, preferences, idempotent upserts — and for workloads that prioritize low write latency and can tolerate RPO > 0.
4. **Synchronous multi-region quorum (MRSC/Spanner-style).** Writes commit only after synchronous replication to at least one other region (or a consensus quorum); strongly consistent reads return the latest version anywhere. Use when correctness across regions outranks write latency and the topology constraints (region sets, no TTL, restricted transactions) are acceptable.
5. **CRDT-based convergence for mergeable data.** Model values as conflict-free replicated types — counters, OR-sets, LWW-registers — so concurrent multi-region writes merge deterministically instead of one silently winning. Combine with per-property granularity (as Figma does at the application layer) so collisions stay rare and comprehensible.
6. **Entity-ownership split.** Partition the schema by write pattern: a global strongly consistent ledger for money movements, home-region-pinned rows for profiles, CRDT counters for engagement metrics. Most real systems are a composite, chosen per entity with the reason recorded in an ADR.

## Gotchas and Failure Modes

1. **Transactions do not survive replication.** In MREC, transaction operations are atomic only within the invoking region; "only some of the writes in a transaction may be returned by read operations in other replicas at a given point in time," and MRSC rejects transactions outright. Multi-item invariants across regions need idempotent sagas or single-writer routing for those items.
2. **LWW silently drops data.** Last-writer-wins resolves by internal timestamp, not business logic; two legitimate concurrent updates (e.g., different fields updated during a partition) can lose one. For fields where loss matters, use per-field merge, CRDTs, or route writes to a single owner.
3. **Strongly consistent reads still return stale data in MREC.** A consistent read returns the latest version only if the item was last updated in the read's region; cross-region updates may be stale until replication lands. Teams read the "strongly consistent" label and assume global currency — it is regional.
4. **Mode changes are one-way doors.** A global table's consistency mode cannot be changed after creation, and converting a populated table to MRSC is unsupported (the table must be empty). Provisioning order and mode choice are architectural decisions with real migration cost.
5. **Replication consumes write capacity.** Every replicated write consumes write capacity on all other replicas; provisioned-capacity tables throttle when application writes plus replication writes exceed provision, and TTL delete replication is billed on the remote side. Capacity plans must include replication fan-out.
6. **Caches lie during regional failover.** When you shift traffic to another region on impair or rising replication latency, caches in front of the new region may hold pre-failover state (DynamoDB's own DAX caches only refresh on TTL because replicated writes bypass them). Include cache purge in the failover runbook.
7. **Region-set topology locks you in.** MRSC supports fixed region sets (US, EU, AP) that cannot span each other, and replicas cannot be added later — a future "add a fourth region" roadmap item invalidates the original choice. Check the two-year plan before committing to a synchronous topology.

## When (Not) To Apply

1. **Apply multi-region writes only when the latency data demands it.** If write p99 from distant users is acceptable through write forwarding, single-writer plus global reads is simpler and conflict-free; multi-writer machinery is a cost you pay only for user-visible write latency or region autonomy.
2. **Apply synchronous quorum for money and inventory.** Anything with a hard invariant (balances never negative, no double-sell) belongs in the strongly consistent tier or behind a single owner, with async tiers for everything else.
3. **Skip multi-writer for conflict-intolerant collaborative records.** Documents, records with business-meaningful field interplay, and anything with audit requirements should be single-owner or CRDT-modeled; naive LWW will eventually eat an edit at the worst time.
4. **Skip region-spanning writes entirely when residency partitions the data anyway.** If EU data must stay in the EU, you are running separate single-region domains by law — invest in routing and identity, not in cross-region conflict resolution.
