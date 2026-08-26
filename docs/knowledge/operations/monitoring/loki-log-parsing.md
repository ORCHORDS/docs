# loki-log-parsing

**Issue:** Parsing structured and unstructured logs in Loki pipeline stages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Logs are ingested as raw strings and cannot be filtered by fields like `level`, `user_id`, or `duration`.

## Pattern / Solution
```yaml
# Promtail pipeline for JSON logs
pipeline_stages:
  - json:
      expressions:
        level: level
        msg: message
        duration: duration_ms
        trace_id: trace_id
  - labels:
      level:
  - structured_metadata:
      trace_id:
  - output:
      source: msg

# Promtail pipeline for logfmt logs
# time=2026-08-11T10:00:00Z level=info msg="request complete" duration=42ms
pipeline_stages:
  - logfmt:
      mapping:
        level: level
        duration: duration
  - labels:
      level:

# Regex parsing for unstructured logs
pipeline_stages:
  - regex:
      expression: '^(?P<ts>\S+) \[(?P<level>\w+)\] (?P<msg>.+)$'
  - labels:
      level:
  - timestamp:
      source: ts
      format: RFC3339
```

## Gotchas
- `json` stage silently drops lines that are not valid JSON
- Timestamp stage must come after extraction to avoid ordering issues
- `output` stage changes what Loki stores as the log line body

## Related
- `loki-log-labels.md`
- `loki-logql-queries.md`
- `log-structured-logging.md`
