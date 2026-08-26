# axiom-log-management

**Issue:** Using Axiom for cost-effective log and event storage with SQL-like queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Datadog or Elasticsearch log costs are too high and teams need a cheaper alternative with good query capability.

## Pattern / Solution
```bash
# Ship logs via Axiom CLI
axiom ingest my-dataset < logs.ndjson

# Ship from application via API
curl -X POST https://api.axiom.co/v1/datasets/production/ingest \
  -H "Authorization: Bearer $AXIOM_TOKEN" \
  -H "Content-Type: application/x-ndjson" \
  -d '{"time":"2026-08-11T10:00:00Z","level":"error","service":"api","msg":"payment failed"}'
```

Query with APL (Axiom Processing Language):
```apl
['production']
| where level == "error"
| where service == "api"
| summarize count() by bin(_time, 5m), endpoint
| order by _time desc
```

OTel Collector export to Axiom:
```yaml
exporters:
  otlphttp/axiom:
    endpoint: https://api.axiom.co/v1/traces
    headers:
      authorization: "Bearer ${AXIOM_TOKEN}"
      x-axiom-dataset: traces
```

## Gotchas
- APL is similar to KQL (Kusto); prior KQL knowledge transfers
- Free tier is 500GB/month; sufficient for most startups
- No built-in alerting; integrate with PagerDuty via webhooks

## Related
- `loki-log-management.md` (conceptual comparison)
- `datadog-log-management.md`
- `log-retention-policies.md`
