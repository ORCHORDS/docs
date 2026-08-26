# Cloudflare Logpush — Workers Observability Pipeline

Date:   2026-08-22
Author: example.com
Status: active

---

## Symptom

After a mobile-traffic spike on example project, engineering needs to replay
48 hours of Worker invocation logs to identify which device classes
and geographic regions triggered elevated D1 query latency. Cloudflare
Analytics Dashboard retains only 24 hours of raw event data, and the
built-in filters do not support high-cardinality field grouping like
`(device_type, country, status_code)` simultaneously.

---

## Context

Cloudflare Logpush exports structured Worker invocation logs
continuously to an external destination: R2, S3, Datadog, Splunk,
New Relic, Google Cloud Storage, Azure Blob, or an HTTP endpoint.
Once enabled, logs arrive within ~30 seconds of the event. Fields
include the full `cf` object (device type, country, colo, ASN), HTTP
status, CPU time, and any custom log lines emitted with `console.log`.

For example project, mobile traffic constitutes ~70 % of requests. A
structured Logpush pipeline lets the team partition stored logs by
`device_type` and run cost-efficient analytical queries without paying
per-query Analytics Engine rates.

---

## Logpush Job Configuration

Jobs are created via the Cloudflare API or dashboard. The `dataset`
for Workers is `workers_trace_events`.

```bash
# Create a Logpush job targeting R2
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name":        "example project-workers-r2",
    "dataset":     "workers_trace_events",
    "destination_conf": "r2://${R2_BUCKET}/workers/{date}?account-id=${CF_ACCOUNT_ID}",
    "output_options": {
      "field_names": [
        "ScriptName","Outcome","CPUTimeMs","WallTimeMs",
        "FetchStatusCode","Exceptions","Logs",
        "EventTimestampMs","RequestUrl","RequestMethod",
        "RequestHeaders","ClientIP","ClientCountry",
        "ClientDeviceType","ClientASN","ColoId"
      ],
      "timestamp_format": "rfc3339",
      "sample_rate": 1.0
    },
    "filter": "{\"where\":{\"key\":\"ScriptName\",\"operator\":\"eq\",\"value\":\"example project-api\"}}",
    "enabled": true
  }'
```

Field availability varies by dataset version. Always request only the
fields you will query — unused fields inflate storage cost with no
observability benefit.

---

## Log Structure for Mobile vs Desktop Analysis

Recommended JSON schema emitted by the Worker before Logpush picks
it up:

```typescript
interface WaspLog {
  ts:          string;    // ISO-8601
  script:      string;    // Worker name
  device:      "mobile" | "desktop" | "tablet" | "unknown";
  country:     string;    // CF-IPCountry
  colo:        string;    // nearest CF PoP
  method:      string;
  path:        string;    // no query string (PII risk)
  status:      number;
  cpu_ms:      number;
  wall_ms:     number;
  d1_queries:  number;    // count of D1 calls this invocation
  d1_ms:       number;    // total D1 wall time
  cache_hit:   boolean;
  error_name?: string;
}
```

Emit with `console.log(JSON.stringify(record))` — Logpush captures
stdout lines from the Worker runtime and embeds them in the `Logs`
array of the trace event.

---

## High-Cardinality Field Strategy

Logpush exports to files; downstream queries run in Athena/BigQuery/
DuckDB. Design fields so that the most frequent query dimensions are
lowest-cardinality.

| Field             | Cardinality   | Index in Parquet | Notes                    |
|-------------------|---------------|------------------|--------------------------|
| `device`          | 4             | partition col    | mobile / desktop / …     |
| `status`          | ~20           | sort col         | HTTP status codes        |
| `country`         | ~240          | clustering col   | ISO-3166 alpha-2         |
| `colo`            | ~300          | —                | IATA code (e.g. LHR)     |
| `path`            | unbounded     | never partition  | strip before storage     |
| `error_name`      | ~50 distinct  | —                | filter, not partition    |

R2 path layout that enables partition pruning:

```
workers/
  date=2026-08-22/
    device=mobile/
      HH=14/
        part-0001.json.gz
    device=desktop/
      HH=14/
        part-0001.json.gz
```

---

## Cost vs Retention Trade-offs

| Destination    | Cost model          | Retention  | Query latency   |
|----------------|---------------------|------------|-----------------|
| R2             | $0.015/GB stored    | unlimited  | Batch (Athena)  |
| Datadog Logs   | ~$1.27/GB ingest    | 15 days    | Near-real-time  |
| Splunk HEC     | licence-dependent   | configurable | Near-real-time |
| HTTP endpoint  | self-managed        | self-managed | varies         |

example project recommendation: primary sink to R2 with 90-day lifecycle
rule; secondary live-tail sink to Datadog for the past 24 hours only.
Dual-sink is configured by creating two Logpush jobs pointing to
different destinations with the same filter.

```bash
# Datadog secondary job — last 24 h live tail
-d '{
  "dataset": "workers_trace_events",
  "destination_conf": "datadog://?header_DD-API-KEY=${DD_KEY}&ddsource=cloudflare",
  "output_options": { "sample_rate": 0.05 },
  "enabled": true
}'
```

Use 5 % sampling to Datadog for cost control; use 100 % to R2 for
audit completeness.

---

## Parsing R2 Logs with DuckDB

```sql
-- Mobile vs desktop error rate by country, last 7 days
SELECT
  json_extract_string(line, '$.country')          AS country,
  json_extract_string(line, '$.device')           AS device,
  COUNT(*)                                         AS total,
  SUM(CASE WHEN CAST(json_extract(line,'$.status')
               AS INTEGER) >= 500 THEN 1 ELSE 0 END) AS errors,
  ROUND(errors * 100.0 / total, 2)                AS error_pct
FROM read_ndjson_auto('s3://example project-logs/workers/date=2026-08-*/device=*/*.json.gz')
GROUP BY country, device
ORDER BY errors DESC
LIMIT 50;
```

---

## Anti-Patterns

- Logging PII (email, user ID, session token) in `console.log` output.
  These values propagate into Logpush and any downstream systems.
  Hash or omit before logging.
- Setting `sample_rate` below 1.0 on the R2 job. You lose audit
  completeness for incident reconstruction. Sample at the query layer
  instead.
- Including the full query string in the `path` field. Query strings
  often contain auth tokens and search terms.
- Creating a single Logpush job for all Workers. Separate jobs per
  script let you apply different filters and sample rates per service.

---

## Gotchas

- Logpush delivery is at-least-once. Duplicate events are possible
  during Cloudflare PoP restarts. Add a dedup key using
  `cf-ray` header + `EventTimestampMs`.
- R2 destination paths use `{date}` as a macro, not the JS
  template literal `${date}`. Using `${}` syntax in the destination
  string is interpreted literally.
- The `workers_trace_events` dataset only becomes available after
  enabling Workers Trace Events in the Logpush wizard — it is not
  on by default even with a paid plan.
- `console.log` calls inside a Tail Worker are NOT captured by
  Logpush — Logpush only covers the producing Worker.

---

## Verification

```bash
# List active Logpush jobs
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].name'

# Validate a job is delivering by checking R2 for today's files
wrangler r2 object list example project-logs --prefix "workers/date=$(date +%F)/"

# Count events in last hour
wrangler r2 object get example project-logs \
  --key "workers/date=$(date +%F)/device=mobile/HH=$(date +%H)/part-0001.json.gz" \
  | zcat | wc -l
```

---

## Related

- documentation/docs/policies/monitoring/cloudflare-workers-tail-debugging.md
- documentation/docs/policies/monitoring/cloudflare-logpush-setup.md
- documentation/docs/policies/monitoring/cloudflare-logpush-no-backfill-loss-and-health-slo.md
- documentation/docs/policies/monitoring/log-retention-policies.md
- documentation/docs/policies/monitoring/observability-cost-control.md

---

## Source URLs

- https://developers.cloudflare.com/logs/about/
- https://developers.cloudflare.com/logs/get-started/api-configuration/
- https://developers.cloudflare.com/logs/reference/log-fields/zone/workers_trace_events/
- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://duckdb.org/docs/data/json/overview.html
