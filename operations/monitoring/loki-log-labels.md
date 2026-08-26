# loki-log-labels

**Issue:** Designing Loki log labels for efficient querying without over-indexing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Loki queries are slow or storage costs are high because too many labels are indexed, or queries cannot filter efficiently because labels are missing.

## Pattern / Solution
Good Loki labels (low cardinality, high selectivity):
```
env, region, service, pod, level, namespace
```

Bad labels (never index):
```
user_id, request_id, trace_id, ip_address
```

Promtail configuration:
```yaml
scrape_configs:
  - job_name: containers
    static_configs:
      - targets: [localhost]
        labels:
          env: prod
          service: api
          __path__: /var/log/api/*.log
    pipeline_stages:
      - json:
          expressions:
            level: level
            trace_id: trace_id
      - labels:
          level:          # index this
      - structured_metadata:
          trace_id:       # store but don't index
```

## Gotchas
- Each unique label combination creates a new stream; keep total streams < 100k per tenant
- `structured_metadata` (Loki 2.9+) allows storing high-cardinality values without indexing
- Changing labels requires re-ingesting old logs

## Related
- `loki-logql-queries.md`
- `loki-retention-config.md`
- `grafana-loki-integration.md`
