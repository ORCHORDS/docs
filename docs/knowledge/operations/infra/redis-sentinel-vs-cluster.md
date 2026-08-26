# redis-sentinel-vs-cluster

**Issue:** Choosing between Redis Sentinel and Redis Cluster for high availability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A single Redis node is a SPOF. Two common HA options exist — Sentinel and Cluster — and picking the wrong one causes either operational complexity you don't need or a scale ceiling you'll hit later.

## Pattern / Solution

| Dimension | Sentinel | Cluster |
|-----------|----------|---------|
| Purpose | HA for a single dataset | Horizontal sharding + HA |
| Data distribution | Single primary, N replicas | 16384 hash slots across shards |
| Min nodes | 3 (1 primary + 1 replica + 1 sentinel) | 6 (3 primary + 3 replica) |
| Multi-key ops | Full support | Only if all keys share a hash tag `{tag}` |
| Pub/Sub | Normal | Only via individual shard |
| Failover time | 10–30 s (configurable) | ~10 s |
| Client requirement | Sentinel-aware client | Cluster-aware client |
| Best for | < 100 GB dataset, simple ops | > 100 GB or write throughput ceiling |

**Sentinel minimal config:**
```
# sentinel.conf
sentinel monitor mymaster 10.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 30000
sentinel parallel-syncs mymaster 1
```

**Cluster creation (6 nodes):**
```bash
redis-cli --cluster create \
  10.0.0.1:7000 10.0.0.2:7000 10.0.0.3:7000 \
  10.0.0.4:7000 10.0.0.5:7000 10.0.0.6:7000 \
  --cluster-replicas 1
```

**Multi-key ops in cluster — use hash tags:**
```python
# Keys in same slot (hash tag {user:123} forces same slot)
pipe.set("{user:123}:name", "Alice")
pipe.set("{user:123}:score", 99)
pipe.execute()   # all keys go to same shard — pipeline works
```

## Gotchas
- Sentinel requires an odd number of Sentinel processes for quorum; 2 Sentinels give you no quorum if one fails.
- Redis Cluster's `KEYS *` pattern scan only hits one shard; use `SCAN` on each primary separately.
- Lua scripts in Cluster mode must only access keys that map to the same slot.
- Elasticache "Cluster mode disabled" is essentially Sentinel; "Cluster mode enabled" is Redis Cluster — the naming is confusing.

## Related
- `redis-eviction-policies.md`
- `postgresql-connection-pooling-pgbouncer.md`
