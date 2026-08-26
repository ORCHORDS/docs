# database-sharding-patterns

**Issue:** Horizontally partitioning databases to scale beyond single-node limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Database write throughput hits single-node ceiling. Single table grows to hundreds of millions of rows causing slow queries and long vacuum cycles.

## Pattern / Solution
Sharding strategies:
```
Hash sharding:     shard = hash(shardKey) % numShards
  + Even distribution
  - Cannot do range queries across shards
  - Resharding requires data movement

Range sharding:    shard based on key range (e.g. userId 0–999 → shard-1)
  + Good for range queries
  - Hot shards if distribution is skewed

Directory sharding: lookup table maps entity to shard
  + Flexible, can rebalance without rehashing
  - Lookup table is a bottleneck/SPOF
```

PostgreSQL native sharding with Citus:
```sql
-- Convert regular table to distributed
SELECT create_distributed_table('orders', 'tenant_id');
-- Citus routes queries to correct shard transparently

-- Co-locate related tables on same shard
SELECT create_distributed_table('order_items', 'tenant_id',
  colocate_with => 'orders');
```

Application-level sharding with consistent hashing:
```python
import hashlib

SHARDS = ['db-shard-0', 'db-shard-1', 'db-shard-2', 'db-shard-3']

def get_shard(tenant_id: str) -> str:
    h = int(hashlib.md5(tenant_id.encode()).hexdigest(), 16)
    return SHARDS[h % len(SHARDS)]

def get_connection(tenant_id: str):
    shard = get_shard(tenant_id)
    return connections[shard]
```

## Gotchas
- Cross-shard transactions require distributed transaction protocol (2PC) or eventual consistency design
- JOINs across shards are expensive — denormalize or keep related data co-located
- Adding shards requires data migration — plan for resharding from day one (virtual shards help)
- Monitoring must aggregate across all shards — slow query on shard-3 is invisible without per-shard metrics

## Related
- `database-read-replicas.md`
- `connection-pooling-strategies.md`
- `azure-cosmos-db-patterns.md`
