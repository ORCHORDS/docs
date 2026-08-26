# loki-retention-config

**Issue:** Configuring log retention periods in Loki to control storage costs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Log storage grows unbounded or logs are deleted too early, removing forensic data needed for post-mortems.

## Pattern / Solution
```yaml
# loki-config.yml
compactor:
  working_directory: /data/loki/compactor
  shared_store: s3
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150

limits_config:
  retention_period: 30d  # global default

# Per-tenant or per-stream overrides
ruler:
  storage:
    type: local

# Override retention per stream via per-tenant config
# In multi-tenant setup:
# tenant overrides file
overrides:
  tenant-audit:
    retention_period: 365d
  tenant-debug:
    retention_period: 7d
```

S3 lifecycle policy should match or exceed Loki retention:
```json
{"Rules": [{"ID": "loki-chunks", "Status": "Enabled",
  "Filter": {"Prefix": "loki/"},
  "Expiration": {"Days": 35}}]}
```

## Gotchas
- Retention requires the compactor component; do not skip it
- Object storage lifecycle policy is a safety net, not the primary control
- Compaction is single-threaded per table; large deployments need tuning

## Related
- `loki-log-labels.md`
- `log-retention-policies.md`
