---
title: Redis Version Governance (Community, Open Source, Stack 7.x, Stack 8.x)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Redis Open Source (https://redis.io/docs/), Redis Stack 7.x / 8.x; Redis Enterprise; Redis Modules documentation
---

# Redis Version Governance (Community, Open Source, Stack 7.x, Stack 8.x)

## Scope

This card governs how `orchords-docs` evaluates Redis and Redis Stack versions. It is the reference input for any reference card that cites an in-memory cache, key-value store, session store, pub/sub, or streaming aggregation.

## Why this card exists

Redis ships frequent minor releases (every few months) and major releases with breaking changes. Redis Stack adds modules (RedisJSON, RediSearch, RedisTimeSeries, RedisGraph-deprecated, RedisBloom, RedisGears-deprecated). License changes (Redis 7.4 → SSPL; Valkey fork) materially affect adoption. A KB card that cites "Redis" without binding to the version, license, and module matrix produces a configuration that breaks on first dependency update.

## Version support matrix

| Version | First release | License | Notes |
|---|---|---|---|
| 6.2.x | August 2021 | BSD-3 | legacy LTS |
| 6.4 (Stack) | 2023 | BSD-3 (Redis Stack) | Stack predecessor |
| 7.0.x | April 2023 | BSD-3 | ACL improvements, client-side caching |
| 7.2.x | August 2023 | BSD-3 | Redis Stack 7.2 |
| 7.4.x | July 2024 | SSPL + RSAL | license change |
| 8.0.x | May 2025 | SSPL + RSAL | Redis Stack 8.x |
| Valkey 7.2.x | March 2024 | BSD-3 | Linux Foundation fork |
| Valkey 8.0.x | September 2024 | BSD-3 | active development |

References: `https://redis.io/docs/about/`, `https://github.com/valkey-io/valkey`.

## License policy

The project supports both Redis (under SSPL) and Valkey (under BSD-3). The license decision is made per reference card. Default: Valkey (BSD-3) preferred for new deployments to preserve open-source licensing.

## Redis Stack modules

| Module | Purpose |
|---|---|
| RediSearch | full-text search, secondary indexes |
| RedisJSON | JSON document storage |
| RedisTimeSeries | time-series data |
| RedisBloom | probabilistic data structures (Bloom, Cuckoo, Count-min) |
| RedisGears (deprecated) | server-side functions |

## Persistence modes

| Mode | Description |
|---|---|
| RDB | point-in-time snapshots |
| AOF | append-only file |
| RDB + AOF | both (default) |
| No persistence | ephemeral cache only |

Policy:

- Production: `RDB + AOF` is default.
- Cache-only: `RDB` is acceptable.
- Disable persistence only for ephemeral use cases.

## Replication

| Mode | Description |
|---|---|
| Master-replica | async, single-master |
| Sentinel | HA orchestration |
| Cluster | sharded, multi-master |

Policy:

- Sentinel for HA on standalone Redis.
- Cluster for sharding.
- Replication factor ≥ 3 for production.

## Sentinel and Cluster

- **Sentinel**: monitors Redis masters and replicas; automatic failover.
- **Cluster**: 16384 hash slots; data sharded across masters; ≥ 6 nodes (3 masters + 3 replicas) recommended.

## Memory policy

| Policy | Description |
|---|---|
| `noeviction` | return errors when memory limit reached |
| `allkeys-lru` | evict any key, LRU |
| `volatile-lru` | evict keys with TTL, LRU |
| `allkeys-lfu` | evict any key, LFU |
| `volatile-lfu` | evict keys with TTL, LFU |
| `allkeys-random` | evict any key, random |
| `volatile-random` | evict keys with TTL, random |
| `volatile-ttl` | evict keys with TTL, soonest first |

Policy:

- `volatile-lru` or `volatile-lfu` for cache workloads (only evicts keys with TTL).
- `noeviction` for non-cache workloads (let the application decide).

## Mandatory pre-flight (before adopting a new Redis deployment)

1. The version is within the support matrix.
2. The license is documented (BSD-3 vs SSPL).
3. Modules in use are documented.
4. Persistence is configured per policy.
5. Replication and HA are configured.
6. Memory policy is configured.
7. Authentication and TLS are configured.
8. Monitoring is wired.

## Security

| Setting | Required |
|---|---|
| `requirepass` (Redis 6.x) or `user` + ACL | required |
| `protected-mode yes` | required |
| TLS 1.2+ (stunnel or native) | required |
| `rename-command` for dangerous commands | required (`FLUSHDB`, `FLUSHALL`, `KEYS`, `CONFIG`) |
| `bind` to internal interface only | required |

## Observability

- `redis_memory_used_bytes` (gauge).
- `redis_memory_used_ratio` (gauge).
- `redis_connected_clients` (gauge).
- `redis_commands_total` (counter, by command).
- `redis_keyspace_hits` / `redis_keyspace_misses` (counter).
- `redis_replication_lag` (gauge).
- `redis_pubsub_channels` (gauge).
- `redis_sentinel_known_servers` (gauge).

## Sources

- Redis Open Source: `https://redis.io/docs/`
- Redis Stack: `https://redis.io/docs/stack/`
- Valkey: `https://github.com/valkey-io/valkey`
- Redis license FAQ: `https://redis.io/docs/about/redis-open-source-license/`
- Redis Sentinel: `https://redis.io/docs/management/sentinel/`
- Redis Cluster: `https://redis.io/docs/management/scaling/`
