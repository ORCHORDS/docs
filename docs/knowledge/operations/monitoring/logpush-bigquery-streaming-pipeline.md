# Logpush to BigQuery Streaming Pipeline

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Teams need to run ad-hoc analytical SQL over millions of Cloudflare request logs without managing Athena catalogs or S3 partitions. Logpush's native BigQuery destination delivers rows in near-real-time using the BigQuery Storage Write API.

## Context
Cloudflare Logpush supports a BigQuery destination that writes to a dataset table directly via the BigQuery JSON streaming endpoint. The destination requires a service-account JSON key stored as a Logpush credential; rows land in BigQuery with a short lag (typically under 60 s). Field selection and filter expressions trim volume before bytes leave Cloudflare's edge.

## BigQuery Dataset and Table Setup

Create a dataset and a table whose schema matches the Logpush fields you intend to push. The table can use `DATE`-based partitioning on the `Timestamp` column to keep query costs manageable.

```sql
-- run in BigQuery console or via bq CLI
CREATE TABLE IF NOT EXISTS `my-project.cf_logs.worker_requests`
(
  Timestamp         TIMESTAMP,
  RequestID         STRING,
  Outcome           STRING,
  CPUTime           INT64,
  WallTimeUs        INT64,
  Exceptions        JSON,
  ScriptName        STRING,
  Status            INT64,
  ClientCountry     STRING
)
PARTITION BY DATE(Timestamp)
OPTIONS (
  require_partition_filter = false,
  partition_expiration_days = 90
);
```

Grant the service account `bigquery.dataEditor` on the dataset and `bigquery.jobUser` on the project before creating the Logpush job.

## Logpush Job Configuration

Use the Cloudflare API to create the job. The `destination_conf` URI format for BigQuery is:
`bigquery://<project>/<dataset>/<table>?apiKey=<redacted-secret>

```typescript
// scripts/create-logpush-bigquery.ts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;

const serviceAccountB64 = Buffer.from(
  JSON.stringify(require('./sa-key.json'))
).toString('base64url');

const destination =
  `bigquery://my-project/cf_logs/worker_requests` +
  `?apiKey=<redacted-secret>

const body = {
  name: 'worker-requests-to-bq',
  dataset: 'workers_trace_events',
  enabled: true,
  logpull_options:
    'fields=Timestamp,RequestID,Outcome,CPUTime,WallTimeUs,' +
    'Exceptions,ScriptName,Status,ClientCountry' +
    '&timestamps=rfc3339',
  filter: JSON.stringify({
    where: {
      and: [
        { key: 'Outcome', operator: 'neq', value: 'ok' },   // errors only
        // OR remove this block to capture all requests
      ]
    }
  }),
  destination_conf: destination,
  output_type: 'ndjson',
};

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs`,
  {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  }
);
const json = await res.json();
console.log('Job created:', json.result?.id);
```

## Querying in BigQuery

Standard SQL lets you join request logs with custom Analytics Engine exports or with application tables in the same project.

```sql
-- P99 CPU time per script in the last hour
SELECT
  ScriptName,
  APPROX_QUANTILES(CPUTime, 100)[OFFSET(99)] AS p99_cpu_us,
  COUNT(*)                                    AS requests,
  COUNTIF(Status >= 500) / COUNT(*)           AS error_rate
FROM `my-project.cf_logs.worker_requests`
WHERE Timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY ScriptName
ORDER BY p99_cpu_us DESC
LIMIT 20;
```

## Scheduled Freshness Check via a Worker Cron

A Cron Trigger Worker can alert if BigQuery rows stop arriving — a sign the Logpush job is stalled.

```typescript
// src/bq-freshness-check.ts
export default {
  async scheduled(_ctrl: ScheduledController, env: Env): Promise<void> {
    const token = await getAccessToken(env.GCP_SA_JSON);

    const query = `
      SELECT MAX(Timestamp) AS latest
      FROM \`my-project.cf_logs.worker_requests\`
      WHERE Timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 10 MINUTE)
    `;

    const resp = await fetch(
      'https://bigquery.googleapis.com/bigquery/v2/projects/my-project/queries',
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, useLegacySql: false, timeoutMs: 10_000 }),
      }
    );
    const data: any = await resp.json();
    const latest = data.rows?.[0]?.f?.[0]?.v as string | undefined;

    if (!latest) {
      await notifySlack(env.SLACK_WEBHOOK, 'BigQuery Logpush: no rows in last 10 min');
    }
  },
} satisfies ExportedHandler<Env>;

async function getAccessToken(saJson: string): Promise<string> {
  // Use the Workers crypto API to sign a JWT for GCP OAuth2
  // Full implementation: https://developers.cloudflare.com/workers/examples/signing-requests/
  const { access_token } = await fetchGcpToken(saJson);
  return access_token;
}
```

## Anti-patterns
- Pushing all fields to BigQuery — costs scale with bytes; select only the fields you query
- Skipping partition filters in queries — full table scans on large tables are expensive
- Storing the service-account key in plaintext in wrangler.toml — use a Workers Secret
- Using the Legacy SQL dialect in BigQuery queries — Standard SQL supports JSON functions needed for the `Exceptions` column

## Gotchas
- BigQuery streaming inserts have a 10 MB/row and 100 MB/request limit; Logpush batches are well within limits but very long exception stacks can approach the per-row cap
- The `Exceptions` field arrives as a JSON string; cast with `JSON_VALUE` / `JSON_QUERY` in BigQuery Standard SQL
- Logpush jobs do not retry failed batches — enable BigQuery table expiry monitoring to detect partial day gaps
- Service-account credentials embedded in `destination_conf` are visible in the Logpush job response; rotate keys and update the job via PATCH regularly

## Verification
1. Enable the job and wait 2–5 minutes for the first batch to arrive
2. Run `SELECT COUNT(*) FROM cf_logs.worker_requests WHERE DATE(Timestamp) = CURRENT_DATE()` — count should grow each minute
3. Check the Logpush job status endpoint: `GET /accounts/{id}/logpush/jobs/{job_id}` — `last_complete` should be within the last 5 minutes
4. Trigger an intentional 500 from a staging Worker; verify the row appears in BigQuery within 90 s

## Related
- [cloudflare-logpush-r2-partitioned-athena.md](cloudflare-logpush-r2-partitioned-athena.md)
- [cloudflare-logpush-setup.md](cloudflare-logpush-setup.md)
- [logpush-filter-expressions-cost-control.md](logpush-filter-expressions-cost-control.md)
- [workers-logpush-observability-pipeline.md](workers-logpush-observability-pipeline.md)

## Sources
- https://developers.cloudflare.com/logs/get-started/enable-destinations/bigquery/
- https://cloud.google.com/bigquery/docs/streaming-data-into-bigquery
- https://developers.cloudflare.com/logs/reference/log-fields/account/workers-trace-events/
