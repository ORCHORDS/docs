# Cloudflare Logpush D1 Log Aggregation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) Workers produce high-volume request logs that need
to be queryable for mobile request correlation, error investigation,
and SLO reporting. Streaming all logs into a third-party logging SaaS
is cost-prohibitive at scale. The team wants to push logs to R2,
convert them to a queryable format, and maintain a hot-log D1 table
for recent queries without building a full data warehouse.

## Context

Cloudflare Logpush delivers structured logs from Workers, HTTP
requests, and Firewall events to destinations including R2, S3,
Datadog, Splunk, and HTTP endpoints. R2 is the natural first
destination for cost efficiency — R2 storage is $0.015/GB/month
with no egress fees. Logpush delivers logs in 5-second batches in
either JSON Lines (NDJSON) or Parquet format. Parquet files are
smaller and faster to scan with columnar tools (DuckDB, Athena)
but require a Worker or scheduled job to convert them for D1
insertion. The hot-log D1 pattern keeps only the last 7 days of
logs in D1 for sub-second SQL queries from Grafana; older logs
stay in R2.

## Logpush job configuration

```bash
# Create Logpush job: Workers Trace Events to R2
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name":         "example project-workers-r2",
    "dataset":      "workers_trace_events",
    "destination_conf": "r2://${R2_BUCKET_NAME}/workers-logs/{DATE}?account-id=${CF_ACCOUNT_ID}&access-key-id=${R2_ACCESS_KEY}&secret-access-key=${R2_SECRET_KEY}",
    "output_options": {
      "field_names": [
        "EventTimestampMs",
        "Outcome",
        "ScriptName",
        "RequestMethod",
        "RequestUrl",
        "ResponseStatus",
        "Exceptions",
        "Logs",
        "CPUTimeMs"
      ],
      "timestamp_format": "unixnano",
      "batch_size":       100000,
      "sample_rate":      1.0
    },
    "logpull_options": "fields=EventTimestampMs,Outcome,ScriptName,RequestMethod,RequestUrl,ResponseStatus,Exceptions,CPUTimeMs&timestamps=unixnano",
    "enabled": true
  }'
```

Available output formats and trade-offs:

| Format   | Size vs JSON | Columnar | D1 insert path    | Query tool        |
|----------|-------------|----------|-------------------|-------------------|
| NDJSON   | 1x          | No       | Direct parse      | jq, grep, D1      |
| Parquet  | ~0.2x       | Yes      | Requires convert  | DuckDB, Athena    |

Use NDJSON for the hot-log pipeline (lower conversion overhead).
Use Parquet for the cold archive R2 prefix queried by DuckDB.

## R2 bucket layout

```
r2://example project-logs/
  workers-logs/
    2026-08-22/
      2026-08-22T14:00:00Z--2026-08-22T14:05:00Z.ndjson.gz
      2026-08-22T14:05:00Z--2026-08-22T14:10:00Z.ndjson.gz
    ...
  workers-logs-parquet/
    date=2026-08-22/
      part-0001.parquet
```

Logpush names files using the `{DATE}` path template variable.
Add a prefix per format to keep archives separate.

## D1 hot-log schema

```sql
-- Run once: wrangler d1 execute example project-hot-logs --file=schema.sql
CREATE TABLE IF NOT EXISTS hot_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms           INTEGER NOT NULL,   -- Unix ms from EventTimestampMs / 1e6
  outcome         TEXT    NOT NULL,   -- 'ok' | 'exception' | 'exceeded*'
  script_name     TEXT    NOT NULL,
  method          TEXT    NOT NULL,
  url_path        TEXT    NOT NULL,   -- pathname only — strip query & host
  status          INTEGER NOT NULL,
  has_exception   INTEGER NOT NULL,   -- 0 | 1
  cpu_time_ms     INTEGER NOT NULL,
  mobile          INTEGER NOT NULL,   -- 0 | 1, derived from User-Agent
  inserted_at     TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hot_log_ts
  ON hot_log (ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_hot_log_script_ts
  ON hot_log (script_name, ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_hot_log_mobile_ts
  ON hot_log (mobile, ts_ms DESC);
```

## R2-to-D1 ingestion Worker

A scheduled Worker (cron `*/10 * * * *`) lists the most recent R2
objects, parses NDJSON, and batch-inserts into D1:

```typescript
// src/workers/logpush-ingester.ts
import { parse as parseUrl } from 'node:url';

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(ingest(env));
  },
};

async function ingest(env: Env): Promise<void> {
  // List objects in today's prefix not yet ingested
  const prefix  = `workers-logs/${today()}/`;
  const listed   = await env.LOGS_BUCKET.list({ prefix, limit: 20 });

  for (const obj of listed.objects) {
    const alreadyDone = await env.INGEST_STATE.get(`done:${obj.key}`);
    if (alreadyDone) continue;

    const body = await (await env.LOGS_BUCKET.get(obj.key))!
      .text();

    const rows = body
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((line) => parseLogLine(line))
      .filter((r): r is LogRow => r !== null);

    if (rows.length > 0) {
      await batchInsert(rows, env);
    }
    await env.INGEST_STATE.put(`done:${obj.key}`, '1', {
      expirationTtl: 86400 * 2,   // forget after 2 days
    });
  }
}

interface LogRow {
  tsMs:       number;
  outcome:    string;
  scriptName: string;
  method:     string;
  urlPath:    string;
  status:     number;
  hasExcept:  number;
  cpuTimeMs:  number;
  mobile:     number;
}

function parseLogLine(line: string): LogRow | null {
  try {
    const e = JSON.parse(line);
    const path = new URL(e.RequestUrl).pathname;
    return {
      tsMs:       Math.floor(e.EventTimestampMs / 1_000_000),
      outcome:    e.Outcome ?? 'unknown',
      scriptName: e.ScriptName ?? '',
      method:     e.RequestMethod ?? 'GET',
      urlPath:    path,
      status:     e.ResponseStatus ?? 0,
      hasExcept:  Array.isArray(e.Exceptions) && e.Exceptions.length > 0 ? 1 : 0,
      cpuTimeMs:  Math.round(e.CPUTimeMs ?? 0),
      mobile:     isMobileUserAgent(e) ? 1 : 0,
    };
  } catch {
    return null;
  }
}

function isMobileUserAgent(e: any): boolean {
  const ua = e.RequestHeaders?.find(
    ([k]: [string, string]) => k.toLowerCase() === 'user-agent',
  )?.[1] ?? '';
  return /mobile|android|iphone|ipad/i.test(ua);
}

async function batchInsert(rows: LogRow[], env: Env): Promise<void> {
  const CHUNK = 50;   // D1 batch limit per prepare round-trip
  for (let i = 0; i < rows.length; i += CHUNK) {
    const chunk = rows.slice(i, i + CHUNK);
    const stmts = chunk.map((r) =>
      env.HOT_LOGS.prepare(
        `INSERT INTO hot_log
           (ts_ms, outcome, script_name, method, url_path,
            status, has_exception, cpu_time_ms, mobile)
         VALUES (?,?,?,?,?,?,?,?,?)`,
      ).bind(
        r.tsMs, r.outcome, r.scriptName, r.method,
        r.urlPath, r.status, r.hasExcept, r.cpuTimeMs, r.mobile,
      ),
    );
    await env.HOT_LOGS.batch(stmts);
  }
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}
```

## Mobile request correlation queries

```sql
-- Mobile error rate, last 1 hour, by script
SELECT
  script_name,
  SUM(CASE WHEN mobile = 1 AND status >= 500 THEN 1 ELSE 0 END)  AS mobile_5xx,
  SUM(CASE WHEN mobile = 1 THEN 1 ELSE 0 END)                    AS mobile_total,
  ROUND(
    SUM(CASE WHEN mobile = 1 AND status >= 500 THEN 1 ELSE 0 END)
      * 100.0
      / MAX(1, SUM(CASE WHEN mobile = 1 THEN 1 ELSE 0 END)),
    2
  )                                                               AS mobile_err_pct
FROM hot_log
WHERE ts_ms > (strftime('%s','now') - 3600) * 1000
GROUP BY script_name
ORDER BY mobile_err_pct DESC;

-- Requests per minute (mobile vs desktop), last 30 min
SELECT
  (ts_ms / 60000) * 60000    AS minute_epoch_ms,
  mobile,
  COUNT(*)                   AS requests
FROM hot_log
WHERE ts_ms > (strftime('%s','now') - 1800) * 1000
GROUP BY minute_epoch_ms, mobile
ORDER BY minute_epoch_ms ASC;
```

## Retention and cleanup

```sql
-- Scheduled cleanup: delete rows older than 7 days
-- Run via a cron Worker or wrangler d1 execute
DELETE FROM hot_log
WHERE ts_ms < (strftime('%s','now') - 7 * 86400) * 1000;
```

Cold data older than 7 days stays in R2 in Parquet format for
DuckDB queries. Use the Parquet prefix for month-level SLO
reporting.

## Anti-patterns

- **Setting `sample_rate` < 1.0 on the Logpush job for the hot-log
  pipeline** — sampled logs misrepresent error rates; keep rate at
  1.0 and reduce volume via `field_names` instead of sampling.
- **Inserting raw `RequestUrl` with query strings into D1** —
  query strings contain session tokens and search terms; store
  `pathname` only.
- **Using Parquet format for the hot-log D1 pipeline** — Parquet
  requires a columnar decode step not available in the Workers
  runtime; use NDJSON for D1 ingestion.
- **Querying hot_log without the ts_ms index** — table scans over
  millions of rows will exceed D1's 30 s query timeout; always
  include a `WHERE ts_ms >` clause.
- **Forgetting to purge the INGEST_STATE KV keys** — without TTL,
  KV accumulates one key per R2 object indefinitely; set
  `expirationTtl: 86400 * 2` to auto-expire after 2 days.

## Gotchas

- `EventTimestampMs` in Workers Trace Events is nanoseconds from
  the epoch, not milliseconds — divide by `1_000_000` to get ms.
- Logpush `{DATE}` path template uses UTC date; objects delivered
  near midnight may span two date prefixes.
- R2 `list()` returns at most 1000 objects per call; if more than
  1000 Logpush files arrive in one prefix before the ingester runs,
  pagination via `cursor` is required.
- D1 is not designed for append-only high-throughput ingestion;
  at > 500 k rows/day, consider pruning to a shorter retention
  window or moving to Analytics Engine for the hot-log role.
- The `Exceptions` field in Workers Trace Events is a JSON string
  array; parse it before checking `.length`.

## Verification

- After enabling Logpush, confirm R2 objects appear in the bucket
  within 10 min: `wrangler r2 object list example project-logs`.
- Run the ingester manually: `wrangler dev src/workers/logpush-ingester.ts`;
  check D1 row count increases.
- Mobile correlation: trigger a mobile request, wait 10 min, query
  `SELECT * FROM hot_log WHERE mobile = 1 ORDER BY ts_ms DESC LIMIT 5`.
- Confirm cleanup removes old rows:
  `SELECT MIN(ts_ms) FROM hot_log` should stay within 7 days of now.
- Verify no `RequestUrl` with query strings in D1:
  `SELECT url_path FROM hot_log WHERE url_path LIKE '%?%' LIMIT 5` returns empty.

## Related

- `documentation/categories/monitoring/cloudflare-logpush-setup.md`
- `documentation/categories/monitoring/workers-logpush-observability-pipeline.md`
- `documentation/categories/monitoring/cloudflare-logpush-no-backfill-loss-and-health-slo.md`
- `documentation/categories/monitoring/log-retention-policies.md`
- `documentation/categories/monitoring/log-aggregation-architecture-patterns.md`
- `documentation/categories/monitoring/real-user-monitoring-rum-mobile-network.md`

## Sources

- Cloudflare Logpush getting started —
  https://developers.cloudflare.com/logs/get-started/
- Logpush destination: R2 —
  https://developers.cloudflare.com/logs/get-started/destinations/r2/
- Workers Trace Events fields —
  https://developers.cloudflare.com/logs/reference/log-fields/account/workers-trace-events/
- Logpush output options (Parquet / NDJSON) —
  https://developers.cloudflare.com/logs/reference/log-output-options/
- D1 Workers API —
  https://developers.cloudflare.com/d1/worker-api/
- R2 Workers API `list()` —
  https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2bucketlist
