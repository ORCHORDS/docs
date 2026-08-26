# aws-elasticache-redis

**Issue:** Running ElastiCache for Redis in production with proper HA and eviction config
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ElastiCache Redis clusters fail over slowly, evict wrong keys, or hit memory limits because default configs are optimised for demos not production.

## Pattern / Solution
```hcl
resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "prod-redis"
  description          = "Production cache"
  node_type            = "cache.r7g.xlarge"
  num_cache_clusters   = 3          # 1 primary + 2 replicas
  automatic_failover_enabled = true
  multi_az_enabled           = true
  engine_version             = "7.2"
  port                       = 6379

  parameter_group_name = aws_elasticache_parameter_group.redis7.name

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

resource "aws_elasticache_parameter_group" "redis7" {
  name   = "prod-redis7-params"
  family = "redis7"

  parameter { name = "maxmemory-policy"    value = "allkeys-lru" }
  parameter { name = "activerehashing"     value = "yes" }
  parameter { name = "lazyfree-lazy-eviction" value = "yes" }
  parameter { name = "tcp-keepalive"       value = "60" }
}
```

For cluster mode (sharding across 6 shards):
```hcl
  num_node_groups         = 6
  replicas_per_node_group = 1
```

## Gotchas
- Cluster mode changes key slot ownership — client must support Redis Cluster protocol (ioredis, redis-py cluster)
- `maxmemory-policy = noeviction` causes OOM errors under load; `allkeys-lru` is safer for cache workloads
- Replication lag during heavy write bursts can cause replica reads to return stale data
- ElastiCache does not support `KEYS` command in production — use `SCAN` instead

## Related
- `redis-eviction-policies.md`
- `redis-sentinel-vs-cluster.md`
- `cache-invalidation-strategies.md`
