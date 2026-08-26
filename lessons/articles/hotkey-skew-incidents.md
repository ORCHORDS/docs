# hotkey-skew-incidents

**Issue:** Aggregate metrics say the datastore is at 3% utilization while one shard is at 100% and melting. Hot-key (hot-partition) incidents happen when traffic or data concentrates on a tiny fraction of keys — one viral entity, one big tenant, one celebrity row — overwhelming the single node that owns that key even though total capacity is plentiful. They are brutal because every tool teams rely on to prevent outages fails in the same direction: load tests use uniform data, autoscaling adds nodes that will never own the hot key, and dashboards averaged across partitions show green while p99 for the affected key's users is dead. Documented cases include a DynamoDB table that passed load testing and then fell over on Black Friday purely due to partition-key design, and Discord's engineering writeups on a single partition receiving wildly disproportionate traffic from one hot channel.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Anatomy of the incident

1. **A load-bearing entity goes viral or giant.** A celebrity post, a huge customer's tenant row, a default config key every service reads — access concentrates on one partition key. AWS's own throttling guidance keys on exactly this signature: the same partition key appearing repeatedly in throttling data while overall consumed capacity looks trivial.
2. **The owning partition saturates first.** Per-key throughput ceilings (DynamoDB's per-partition limits, a Redis single thread, one ConsistentHash range) are hit long before cluster capacity matters. Writes throttle or queue; reads on that key spike to seconds.
3. **Retries convert skew into an outage.** Clients that can't distinguish "hot key" from "database down" retry with backoff, multiplying load on the already-saturated partition and spreading pressure to connection pools and frontends. The incident now looks like a generic database incident, which misleads responders.
4. **Scale-out makes it worse.** Adding nodes cannot help — the hot key still hashes to exactly one place. Teams waste critical minutes scaling a cluster that was never the bottleneck, which is the diagnostic signature that should immediately suggest skew.

## Why load tests never catch it

1. **Synthetic data is uniform.** Load generators write evenly distributed random keys, so no partition gets hot. Production power-law distributions (a few keys with 1000x the traffic of the median) are absent by construction.
2. **The hot key is created by the world, not the schema.** Virality, a customer migrating a monolith onto your platform, or a new feature that funnels all reads through one row — none of these exist in a pre-launch test environment.
3. **Averages hide p99-per-key.** A dashboard showing mean latency across a million keys stays flat while one key's users experience total failure. Without per-partition or per-key top-N breakdowns, the signal doesn't exist.

## Detection and diagnosis

1. **Track top-N keys by traffic, always.** Instrument the data layer to export the top keys/partitions by request rate and by throttling events. When throttling starts, the AWS playbook is literally "look for repeated partition keys in throttling data" — that should be a built-in query, not improvisation at 3am.
2. **Alert on skew ratio, not just volume.** A cheap canary metric is (max partition traffic / mean partition traffic). When it jumps an order of magnitude, skew is developing regardless of absolute load.
3. **Distinguish skew from saturation in minutes.** First triage question for any datastore degradation: is one key/partition hot, or is the whole cluster saturated? The answer completely changes the response — scale-out for saturation, application-level mitigation for skew.

## Mitigations that actually work

1. **Shard the hot key in the application.** Append a bounded suffix (key0..keyN) for write-heavy hot keys and read-modify-write across shards, or scatter-write and read-aggregate. This is the standard DynamoDB remedy and the approach Discord converged on for hot channels: spread one logical entity over many physical partitions.
2. **Put a cache in front of read-mostly hot keys.** A single in-memory cache entry can absorb read skew that no database partition could survive; the tradeoff is staleness, which must be an explicit product decision rather than an accident.
3. **Quarantine pathological tenants/entities.** Feature-flag or config-driven "hot key" lists let you degrade one entity (disable counters, serve cached snapshots) without touching the code path for everyone else.
4. **Split the entity at the data-model level.** If one row must absorb unbounded writes (counters, follower lists), redesign into write-time partitioned structures (pre-aggregated shards, time-bucketed tables) — the fix is schema work, not ops.

## Design rules going forward

1. **Ask "what's the biggest key?" at design review.** Every new table/topic/cache deserves the question: what happens when one key gets 10,000x median traffic? If the answer is "it can't," the review isn't done.
2. **Never make user-controlled identifiers the sole partition key.** IDs chosen by the outside world (usernames, tenant slugs, product SKUs) will concentrate; hash or composite them with something bounded.
3. **Rehearse skew before peak events.** Run a synthetic hot-key drill (hammer one key at 100x mean) before Black Friday-style events, so the runbook's skew triage has been executed at least once under pressure.
