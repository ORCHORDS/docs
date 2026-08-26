# Cloudflare Logpush to R2 with Partitioned Storage and Athena Queries

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project generates 50–200 million HTTP request log lines per day across
mobile and desktop clients. Cloudflare's native dashboard retains logs
for only 72 hours. Debugging a reported issue from a mobile user that
occurred five days ago requires log access beyond that window. The team
also needs ad-hoc analytics over raw logs — referrer chains, bot traffic
breakdown, regional error clustering — without paying per-query SaaS
pricing.

The required architecture:
- Continuous delivery of Cloudflare logs to R2 (Cloudflare's S3-
  compatible object store) for cost-effective long-term retention.
- Hive-style prefix partitioning (year/month/day/hour/device_type)
  so Athena prunes partitions and scans only the data needed.
- An AWS Glue table and Athena workgroup configured to query logs
  without full-bucket scans.

---

## Context

Cloudflare Logpush delivers log batches to R2 in gzip-compressed
newline-delimited JSON (NDJSON) every 30 seconds. The delivery format
cannot be changed, but the **key prefix** controls how files land in R2.
Athena reads R2 via its S3-compatible endpoint and uses partition
projection to resolve `WHERE dt = '2026-08-22'` into a specific key
prefix without a `MSCK REPAIR TABLE` step.

R2 has no per-GB retrieval fee (unlike S3 Standard), making it ideal
for log archival queried infrequently.

Mobile and desktop logs are NOT separated at ingestion time by Logpush —
separation happens at query time via the `ClientDeviceType` field in
the log schema. However, for high-value operational queries, writing a
separate Athena view per device type avoids repetitive filtering.

---

## Section 1: R2 Bucket and Logpush Job Setup

```bash
# Create the R2 bucket for log archival
wrangler r2 bucket create example project-logs-archive

# Verify bucket exists
wrangler r2 bucket list | grep example project-logs-archive
```

Create the Logpush job via the Cloudflare API. The `destination_conf`
uses the R2-specific format with a prefix template that embeds date/hour
components from the log timestamp.

```bash
# Create Logpush job — HTTP requests dataset to R2
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "example project-http-logs-r2",
    "logpull_options": "fields=ClientIP,ClientRequestHost,ClientRequestMethod,ClientRequestURI,ClientRequestUserAgent,ClientDeviceType,EdgeResponseStatus,EdgeResponseBytes,EdgeStartTimestamp,RayID,WorkerStatus,WorkerSubrequestCount,ClientCountry",
    "destination_conf": "r2://example project-logs-archive/http_requests/{DATE}/{HOUR}?account-id='"$CF_ACCOUNT_ID"'&access-key-id='"$R2_ACCESS_KEY_ID"'&secret-access-key='"$R2_SECRET_ACCESS_KEY"'",
    "dataset": "http_requests",
    "enabled": true,
    "filter": "{\"where\":{\"and\":[{\"key\":\"EdgeResponseStatus\",\"operator\":\"!eq\",\"value\":\"0\"}]}}"
  }'
```

The `{DATE}` and `{HOUR}` template variables are resolved by Logpush to
`YYYY-MM-DD` and `HH` respectively. This produces keys like:

```
http_requests/2026-08-22/14/20260822140000-20260822140030-xyz.log.gz
```

For full Hive-style partitioning Athena expects (and that enables
partition pruning), re-key the files with a Lambda or Workers Cron job
into the format:

```
http_requests/dt=2026-08-22/hr=14/20260822140000-xyz.log.gz
```

---

## Section 2: Re-keying Worker (Cron-based R2 → R2 Transform)

A Cloudflare Worker running on a cron trigger reads the flat Logpush
output, renames keys to the Hive-compatible format, and optionally
extracts a `device_type=mobile|desktop` sub-partition for high-traffic
datasets.

```typescript
// src/log-rekeyer.ts
interface Env {
  LOGS_BUCKET: R2Bucket;
  REKEYED_BUCKET: R2Bucket;
}

const DATE_HOUR_RE = /http_requests\/(\d{4}-\d{2}-\d{2})\/(\d{2})\//;

export default {
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<void> {
    // Process the previous full hour to avoid partial batches
    const now = new Date();
    const prevHour = new Date(now.getTime() - 3600_000);
    const dt = prevHour.toISOString().slice(0, 10);          // 2026-08-22
    const hr = prevHour.getUTCHours().toString().padStart(2, "0"); // 14

    const prefix = `http_requests/${dt}/${hr}/`;
    let cursor: string | undefined;

    do {
      const listed = await env.LOGS_BUCKET.list({ prefix, cursor, limit: 100 });

      for (const obj of listed.objects) {
        const newKey = obj.key
          .replace(
            DATE_HOUR_RE,
            (_m, date, hour) => `http_requests/dt=${date}/hr=${hour}/`,
          );

        // Copy to rekeyed bucket
        const body = await env.LOGS_BUCKET.get(obj.key);
        if (body) {
          await env.REKEYED_BUCKET.put(newKey, body.body, {
            httpMetadata: { contentEncoding: "gzip", contentType: "application/x-ndjson" },
          });
        }
      }

      cursor = listed.truncated ? listed.cursor : undefined;
    } while (cursor);
  },
};
```

```toml
# wrangler.toml for the re-keyer
name = "example project-log-rekeyer"
main = "src/log-rekeyer.ts"
compatibility_date = "2025-09-01"

[triggers]
crons = ["5 * * * *"]   # 5 minutes past every hour

[[r2_buckets]]
binding = "LOGS_BUCKET"
bucket_name = "example project-logs-archive"

[[r2_buckets]]
binding = "REKEYED_BUCKET"
bucket_name = "example project-logs-partitioned"
```

---

## Section 3: Glue Table with Partition Projection

Partition projection lets Athena resolve partition values from the key
path without registering partitions in the Glue metastore. The table
definition references the R2 bucket via its S3-compatible endpoint.

```sql
-- Run in Athena query editor
CREATE EXTERNAL TABLE example project_http_logs (
  ClientIP              string,
  ClientRequestHost     string,
  ClientRequestMethod   string,
  ClientRequestURI      string,
  ClientRequestUserAgent string,
  ClientDeviceType      string,
  EdgeResponseStatus    int,
  EdgeResponseBytes     bigint,
  EdgeStartTimestamp    bigint,
  RayID                 string,
  WorkerStatus          string,
  WorkerSubrequestCount int,
  ClientCountry         string
)
PARTITIONED BY (dt string, hr string)
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
STORED AS INPUTFORMAT
  'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT
  'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://example project-logs-partitioned/http_requests/'
TBLPROPERTIES (
  'projection.enabled'        = 'true',
  'projection.dt.type'        = 'date',
  'projection.dt.format'      = 'yyyy-MM-dd',
  'projection.dt.range'       = '2026-01-01,NOW',
  'projection.dt.interval'    = '1',
  'projection.dt.interval.unit' = 'DAYS',
  'projection.hr.type'        = 'integer',
  'projection.hr.range'       = '0,23',
  'projection.hr.digits'      = '2',
  'storage.location.template' = 's3://example project-logs-partitioned/http_requests/dt=${dt}/hr=${hr}/',
  'compressionType'           = 'gzip'
);
```

---

## Section 4: Athena Query Patterns

```sql
-- Mobile vs desktop error rate for a specific day
SELECT
  ClientDeviceType,
  EdgeResponseStatus,
  COUNT(*)                                              AS request_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER
    (PARTITION BY ClientDeviceType), 2)                AS pct_of_device_type
FROM  example project_http_logs
WHERE dt = '2026-08-22'
  AND EdgeResponseStatus >= 400
GROUP BY ClientDeviceType, EdgeResponseStatus
ORDER BY ClientDeviceType, request_count DESC;

-- Top error-generating URIs for mobile users on a given day/hour
SELECT
  ClientRequestURI,
  EdgeResponseStatus,
  COUNT(*) AS hits
FROM  example project_http_logs
WHERE dt    = '2026-08-22'
  AND hr    = '14'
  AND ClientDeviceType = 'mobile'
  AND EdgeResponseStatus >= 500
GROUP BY ClientRequestURI, EdgeResponseStatus
ORDER BY hits DESC
LIMIT 20;

-- Bytes served per country, mobile only, last 7 days (partition-pruned)
SELECT
  ClientCountry,
  SUM(EdgeResponseBytes) / 1e9    AS gb_served,
  COUNT(*)                        AS requests
FROM  example project_http_logs
WHERE dt BETWEEN '2026-08-15' AND '2026-08-22'
  AND ClientDeviceType = 'mobile'
GROUP BY ClientCountry
ORDER BY gb_served DESC;
```

---

## Anti-patterns

- **Querying without partition filters** — `SELECT * FROM example project_http_logs`
  with no `WHERE dt = ...` clause scans the entire bucket. Always include
  a date range. Enable Athena's per-query data scanned limit (256 MB is
  a safe default for exploration queries) in the workgroup settings.
- **Using the Logpush flat key as the Athena table location** — Athena
  partition projection requires the Hive key pattern `partition=value`.
  The Logpush flat `YYYY-MM-DD/HH` format does NOT satisfy this without
  the re-keyer step.
- **Storing uncompressed NDJSON** — Logpush delivers gzip. Re-uploading
  as raw JSON quadruples storage cost and Athena scan cost. Keep gzip.
- **Enabling Logpush on every field** — the full HTTP request schema is
  ~80 fields. Include only what analytics actually consumes. Extraneous
  fields increase storage and Athena parse time.
- **Forgetting the R2 S3-compatible credentials in Athena** — Athena
  reaches R2 via the S3 endpoint (`https://<account-id>.r2.cloudflarestorage.com`).
  Configure a custom S3 endpoint in the Athena data source settings; the
  default AWS endpoint will fail for R2 buckets.

---

## Gotchas

- Cloudflare Logpush delivers batches every 30 seconds. Files may be
  delivered slightly out of order relative to `EdgeStartTimestamp`. When
  computing hourly metrics, always include a 5-minute buffer in the
  preceding partition.
- `ClientDeviceType` in Cloudflare logs is one of: `desktop`, `mobile`,
  `tablet`, `smartTV`, or `bot`. Map `tablet` to `mobile` or treat it
  separately depending on product context.
- R2's S3-compatible API requires a dedicated access key pair (not the
  account API token). Create it under R2 → Manage R2 API tokens in the
  Cloudflare dashboard.
- Athena partition projection `range = 'NOW'` evaluates at query time to
  the current date in UTC. Queries run near midnight may miss the last
  partition of the previous day if the re-keyer is still running.
- The Glue table JSON SerDe (`JsonSerDe`) does not handle multi-line
  JSON. NDJSON (one JSON object per line) is required — which is what
  Logpush delivers.
- R2 free tier includes 10 GB storage and 1 million Class A operations
  per month. At 50 M requests/day generating ~200 B per log line, expect
  ~10 GB/day before gzip compression (roughly 1–2 GB/day after gzip).
  Budget accordingly.

---

## Verification

```bash
# Confirm Logpush job is enabled and delivering
curl "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name, enabled, last_complete}'

# Check R2 bucket for recent files
wrangler r2 object list example project-logs-archive --prefix "http_requests/2026-08-22/14/" | head -10

# After re-keyer runs, verify partitioned bucket
wrangler r2 object list example project-logs-partitioned \
  --prefix "http_requests/dt=2026-08-22/hr=14/" | head -5

# Run a partition-pruned Athena test query (should scan < 10 MB)
# Check "Data scanned" in the Athena query results panel
```

---

## Related

- `cloudflare-logpush-setup.md`
- `cloudflare-logpush-d1-log-aggregation.md`
- `log-retention-policies.md`
- `log-aggregation-architecture-patterns.md`
- `cost-monitoring-dashboards.md`

---

## Sources

- Cloudflare Logpush documentation — https://developers.cloudflare.com/logs/logpush/
- Cloudflare R2 S3-compatible API — https://developers.cloudflare.com/r2/api/s3/
- AWS Athena partition projection — https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html
- AWS Glue Data Catalog — https://docs.aws.amazon.com/glue/latest/dg/populate-data-catalog.html
- Cloudflare HTTP request log fields — https://developers.cloudflare.com/logs/reference/log-fields/zone/http_requests/
