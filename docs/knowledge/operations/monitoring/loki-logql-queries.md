# loki-logql-queries

**Issue:** Writing effective LogQL queries for log filtering and metric extraction
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers struggle to find relevant logs or extract metrics from log streams in Loki.

## Pattern / Solution
```logql
# Filter by label then parse JSON
{service="api", env="prod"} | json | status_code >= 500

# Regex filter
{service="worker"} |~ "ERROR|FATAL"

# Extract metric: request rate by endpoint
sum by (path) (rate({service="api"} | json | unwrap duration_ms [5m]))

# Top slow endpoints
topk(5,
  sum by (path) (
    rate({service="api"} | json | unwrap duration_ms [5m])
  )
)

# Count errors per service
sum by (service) (
  count_over_time({env="prod"} | json | level="error" [5m])
)

# Pattern matching
{service="api"} | pattern `<_> status=<status> path=<path> <_>`
| status = "500"
```

## Gotchas
- `rate()` requires `unwrap` for numeric values; `count_over_time` counts log lines
- Without label selectors, full-scan queries will time out
- `|=` is faster than `|~` (regex); use for exact string matching

## Related
- `loki-log-labels.md`
- `loki-log-parsing.md`
- `grafana-loki-integration.md`
