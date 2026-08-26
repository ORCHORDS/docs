# elasticsearch-index-management

**Issue:** Managing Elasticsearch index lifecycle, shard sizing, and rollover to prevent cluster instability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Clusters become unstable when indices have too many small shards, too few large ones, or when old indices are never deleted. Search performance degrades on indices with millions of documents split unevenly across shards.

## Pattern / Solution
Use Index Lifecycle Management (ILM) for time-series data and explicit shard count guidance for search indices.

**Shard sizing rules of thumb:**
- Target 10–50 GB per shard
- Aim for shard count ≤ 20 × number of data nodes
- Small shards (< 1 GB) waste overhead; consolidate with force-merge or shrink API

**ILM policy for log indices:**
```json
PUT _ilm/policy/logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "30gb",
            "max_age": "7d"
          },
          "set_priority": { "priority": 100 }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "forcemerge": { "max_num_segments": 1 },
          "shrink": { "number_of_shards": 1 },
          "allocate": { "require": { "data": "warm" } },
          "set_priority": { "priority": 50 }
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": { "delete": {} }
      }
    }
  }
}
```

**Index template that attaches the policy:**
```json
PUT _index_template/logs-template
{
  "index_patterns": ["logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 2,
      "number_of_replicas": 1,
      "index.lifecycle.name": "logs-policy",
      "index.lifecycle.rollover_alias": "logs"
    }
  }
}
```

**Check cluster and index health:**
```bash
# Cluster health
curl -s localhost:9200/_cluster/health?pretty

# Shard allocation issues
curl -s localhost:9200/_cluster/allocation/explain?pretty

# Index stats
curl -s "localhost:9200/_cat/indices?v&s=store.size:desc"

# Shard distribution
curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,docs,store,node"
```

## Gotchas
- You cannot change `number_of_shards` after index creation; use the shrink or split API, or reindex.
- Force-merge on an active write index blocks indexing; only apply to read-only (warm/cold) indices.
- ILM rollover requires the write alias to point to the current index — bootstrap with `POST logs/_rollover` if the alias is missing.
- Red cluster status blocks all ILM progress; fix unassigned shards first.

## Related
- `kafka-consumer-group-lag.md`
- `log-aggregation-loki.md`
- `prometheus-alertmanager-config.md`
