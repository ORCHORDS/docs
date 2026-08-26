# Log Drain Configuration Archiving Cloudflare Logs to R2

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Cloudflare edge logs (HTTP requests, Workers invocations, Firewall events) are ephemeral by default. You need long-term retention in a queryable store — R2 bucket — for compliance, debugging, and analytics (Athena or similar). Logpush must be configured programmatically so it can be reproduced across accounts and environments without dashboard clicks.

## Context

Cloudflare **Logpush** streams logs from the Cloudflare network to a destination in near-real time. R2 is a first-class Logpush destination (no egress cost). Logs arrive as newline-delimited JSON (NDJSON) or, optionally, Parquet.

Key concepts:
- **Dataset** — the log type: `http_requests`, `workers_trace_events`, `firewall_events`, `dns_logs`, etc.
- **Logpush Job** — configuration binding a dataset to a destination and field list.
- **R2 key prefix** — determines how files land in the bucket (affects Athena partition discovery).

Logpush is available on Pro+ plans for zone-scoped datasets; some datasets are account-scoped.

## Solution

### 1. R2 bucket preparation

```typescript
// Ensure bucket exists (idempotent via Pulumi or wrangler)
// wrangler r2 bucket create example project-logs

// Bucket CORS and lifecycle policies are set via the R2 API or Pulumi:
const logBucket = new cloudflare.R2Bucket("log-bucket", {
  accountId,
  name: "example project-logs",
});
```

### 2. Logpush job creation via API

```typescript
const CF_API = "https://api.cloudflare.com/client/v4";

interface LogpushJob {
  id: number;
  name: string;
  enabled: boolean;
  dataset: string;
  destination_conf: string;
  logpull_options: string;
  frequency: "high" | "low";  // high = ~30 s batches; low = ~5 min
  filter?: string;            // JSON-encoded filter expression
}

async function createLogpushJob(
  token: string,
  zoneId: string,            // or accountId for account-level datasets
  r2AccountId: string,
  bucketName: string,
): Promise<LogpushJob> {
  // R2 destination format:
  // r2://<bucket>/<path-prefix>?account-id=<r2-account-id>&access-key-id=<id>&secret-access-key=<key>
  // Use R2 API tokens (not the main CF token) for the r2 credentials.
  const destination = [
    `r2://${bucketName}/http_requests`,
    `?account-id=${r2AccountId}`,
    `&access-key-id=${R2_ACCESS_KEY_ID}`,
    `&secret-access-key=${R2_SECRET_ACCESS_KEY}`,
  ].join("");

  const res = await fetch(`${CF_API}/zones/${zoneId}/logpush/jobs`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type":  "application/json",
    },
    body: JSON.stringify({
      name:            "example project-http-to-r2",
      enabled:         true,
      dataset:         "http_requests",
      frequency:       "high",
      destination_conf: destination,
      logpull_options: buildLogpullOptions(),
      filter:          buildFilter(),
    }),
  });

  const json = await res.json<{ result: LogpushJob; success: boolean; errors: unknown[] }>();
  if (!json.success) throw new Error(JSON.stringify(json.errors));
  return json.result;
}
```

### 3. Log field selection

```typescript
function buildLogpullOptions(): string {
  // Fields are passed as a comma-separated query-string value.
  // Only request the fields you need — fewer fields = smaller files.
  const fields = [
    "ClientIP",
    "ClientRequestHost",
    "ClientRequestMethod",
    "ClientRequestURI",
    "ClientRequestUserAgent",
    "EdgeResponseStatus",
    "EdgeResponseBytes",
    "EdgeStartTimestamp",
    "RayID",
    "CacheCacheStatus",
    "OriginResponseStatus",
    "WorkerStatus",
    "WorkerSubrequest",
    "ClientCountry",
    "ClientASN",
  ].join(",");

  // timestamps=rfc3339 outputs ISO-8601 instead of unix nanoseconds
  return `fields=${fields}&timestamps=rfc3339`;
}
```

### 4. Filtering by status code

```typescript
function buildFilter(): string {
  // Logpush filter is a JSON string, not a URL query param.
  // Filter syntax: { "where": { "and": [ { "key": ..., "operator": ..., "value": ... } ] } }
  const filter = {
    where: {
      and: [
        // Exclude 1xx, 2xx, 3xx — log only 4xx and 5xx
        {
          key:      "EdgeResponseStatus",
          operator: "geq",
          value:    400,
        },
      ],
    },
  };
  return JSON.stringify(filter);
}

// To log ALL status codes, omit the filter field from the job creation payload.
```

### 5. Compression

Cloudflare Logpush compresses batches automatically with **gzip** when you append `&compression=gzip` to the destination URL:

```typescript
const destination = [
  `r2://${bucketName}/http_requests`,
  `?account-id=${r2AccountId}`,
  `&access-key-id=${R2_ACCESS_KEY_ID}`,
  `&secret-access-key=${R2_SECRET_ACCESS_KEY}`,
  `&compression=gzip`,
].join("");
// Files land as: http_requests/20241015T153000Z_20241015T153030Z_<hash>.log.gz
```

For Parquet output (requires Cloudflare Workers for Platforms or Enterprise agreement with schema upload), use `&format=parquet` instead of `&compression=gzip`.

### 6. Partitioned R2 key structure (Athena-compatible)

Athena requires `key=value` Hive-style partition paths. Use the `{DATE}` and `{HOUR}` template placeholders in the prefix:

```typescript
// Prefix template (Cloudflare evaluates placeholders at write time)
const prefix = `http_requests/year={DATE:Y}/month={DATE:M}/day={DATE:D}/hour={HOUR}`;

const destination = [
  `r2://${bucketName}/${prefix}`,
  `?account-id=${r2AccountId}`,
  `&access-key-id=${R2_ACCESS_KEY_ID}`,
  `&secret-access-key=${R2_SECRET_ACCESS_KEY}`,
  `&compression=gzip`,
].join("");

// Resulting R2 keys:
// http_requests/year=2024/month=10/day=15/hour=15/<batch>.log.gz
```

Athena DDL:
```sql
CREATE EXTERNAL TABLE cf_http_requests (
  ClientIP             STRING,
  ClientRequestHost    STRING,
  ClientRequestMethod  STRING,
  ClientRequestURI     STRING,
  EdgeResponseStatus   INT,
  EdgeResponseBytes    BIGINT,
  EdgeStartTimestamp   STRING,
  RayID                STRING,
  CacheCacheStatus     STRING,
  ClientCountry        STRING
)
PARTITIONED BY (year STRING, month STRING, day STRING, hour STRING)
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
LOCATION 's3://example project-logs/http_requests/'
TBLPROPERTIES ('compressionType'='gzip');

-- Add partitions after new data arrives
MSCK REPAIR TABLE cf_http_requests;
```

### 7. Worker to enable/disable job on deploy

```typescript
async function toggleLogpushJob(
  token: string,
  zoneId: string,
  jobId: number,
  enabled: boolean,
): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/logpush/jobs/${jobId}`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    },
  );
  if (!res.ok) throw new Error(`Toggle failed: ${await res.text()}`);
}
```

## Implementation Details

- Logpush jobs write batches on `frequency: "high"` approximately every 30 seconds; `"low"` is every 5 minutes. High frequency produces many small files — consider a compaction Worker that merges them daily.
- R2 access key and secret must be **R2 API tokens** created in the R2 section of the dashboard (not a general CF API token). The R2 token needs `Object:Write` permission on the target bucket.
- The `{DATE}` placeholder uses UTC. Athena partition pruning works correctly when queries include `WHERE year='2024' AND month='10'`.
- Workers Trace Events dataset is account-scoped — use `/accounts/{account_id}/logpush/jobs` instead of the zone path.
- Logpush guarantees **at-least-once** delivery. Downstream queries must tolerate duplicate RayIDs.

## Anti-patterns

- Do not use the global Cloudflare API token for the R2 destination credentials — scope a dedicated R2 token.
- Do not request all available fields — the full `http_requests` schema has 80+ fields; unused fields waste storage and slow Athena queries.
- Do not use a flat prefix (no date partitioning) — listing a bucket with millions of files is slow and Athena scans increase cost.
- Do not enable `frequency: "high"` if your downstream pipeline (Athena, DuckDB) cannot handle many small files — use `"low"` or add a compaction step.
- Do not store R2 credentials in Workers environment variables as plain text; use `wrangler secret put`.

## Gotchas

- Logpush jobs must be **validated** before they start sending. The API sends a test file to the destination and the job remains in `pending` state until validation succeeds.
- If the R2 bucket is in a different Cloudflare account than the zone, the `account-id` in the destination URL must be the R2 bucket's account, not the zone's account.
- `timestamps=rfc3339` outputs nanosecond precision ISO-8601 strings. Athena's `TIMESTAMP` type handles microseconds — cast with `CAST(from_iso8601_timestamp(EdgeStartTimestamp) AS TIMESTAMP)`.
- Gzip-compressed NDJSON and Parquet are mutually exclusive; choose one format per job.
- Logpush is not available on Cloudflare Free plan.

## Verification

```bash
# List existing jobs
curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/logpush/jobs" \
  | jq '.result[] | {id, name, enabled, dataset}'

# Check job status / last error
curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/logpush/jobs/$JOB_ID" \
  | jq '.result | {enabled, last_complete, last_error}'

# List R2 files after a batch lands (~30 s)
wrangler r2 object list example project-logs --prefix http_requests/year=2024
```

## Related

- `documentation/docs/policies/infra/workers-pulumi-cloudflare-iac.md`
- `documentation/docs/policies/infra/workers-waf-custom-ruleset-api.md`

## Sources

- https://developers.cloudflare.com/logs/get-started/
- https://developers.cloudflare.com/logs/reference/log-fields/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
- https://developers.cloudflare.com/logs/reference/filters/
