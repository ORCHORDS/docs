# Cloudflare Logpush → R2 → Workers Tail Structured Event Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need real-time structured log processing for Cloudflare Workers traffic: filter requests by HTTP status code or response duration, enrich events, and forward matching records to Analytics Engine for querying. Raw Logpush to S3/R2 alone gives you files but not a streaming processing layer.

## Context

- Cloudflare Logpush → R2 bucket (JSON-newline compressed files, ~30s batches)
- Workers Tail consumer reads R2 objects via R2 event notifications
- Analytics Engine receives filtered, enriched data points
- Stack: Workers (TypeScript), R2, Analytics Engine, Wrangler 3.x

---

## Step 1 — Configure Logpush to R2

```bash
# Create the destination R2 bucket
wrangler r2 bucket create prod-logpush

# Create Logpush job via API
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "workers-requests-r2",
    "destination_conf": "r2://prod-logpush/logs/{DATE}/{HOUR}_{INDEX}.json.gz?account-id='$CF_ACCOUNT_ID'&access-key-id='$R2_KEY_ID'&secret-access-key='$R2_SECRET'",
    "dataset": "workers",
    "fields": "Timestamp,DispatchNamespace,ScriptName,Outcome,CPUTimeMs,WallTimeMs,Status,Exceptions,Logs",
    "enabled": true,
    "frequency": "low"
  }'
```

## Step 2 — R2 Event Notification → Queue → Worker

```toml
# wrangler.toml
name = "logpush-tail-consumer"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[r2_buckets]]
binding = "LOGPUSH_BUCKET"
bucket_name = "prod-logpush"

[[queues.consumers]]
queue = "logpush-events"
max_batch_size = 10
max_batch_timeout = 5

[[analytics_engine_datasets]]
binding = "AE_WORKERS"
dataset = "workers_requests"
```

```bash
# Attach R2 event notifications to the queue
wrangler r2 bucket notification create prod-logpush \
  --event-type object-create \
  --queue logpush-events
```

## Step 3 — Worker: Decompress, Parse, Filter, Forward

```typescript
// src/index.ts
import { gunzipSync } from 'node:zlib';

interface Env {
  LOGPUSH_BUCKET: R2Bucket;
  AE_WORKERS: AnalyticsEngineDataset;
  STATUS_FILTER: string;   // e.g. "500,502,503"
  DURATION_THRESHOLD_MS: string; // e.g. "2000"
}

interface WorkersLogRecord {
  Timestamp: number;       // Unix nanoseconds
  ScriptName: string;
  DispatchNamespace: string;
  Outcome: string;
  CPUTimeMs: number;
  WallTimeMs: number;
  Status: number;
  Exceptions: { name: string; message: string }[];
  Logs: { level: string; message: string[] }[];
}

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    const statusFilter = new Set(
      env.STATUS_FILTER.split(',').map(s => parseInt(s, 10))
    );
    const durationThreshold = parseInt(env.DURATION_THRESHOLD_MS, 10);

    for (const message of batch.messages) {
      const notification = message.body as {
        object: { key: string; size: number };
        bucket: string;
      };

      const obj = await env.LOGPUSH_BUCKET.get(notification.object.key);
      if (!obj) {
        message.ack();
        continue;
      }

      const compressed = await obj.arrayBuffer();
      const raw = gunzipSync(new Uint8Array(compressed));
      const text = new TextDecoder().decode(raw);
      const lines = text.trim().split('\n').filter(Boolean);

      for (const line of lines) {
        let record: WorkersLogRecord;
        try {
          record = JSON.parse(line);
        } catch {
          continue;
        }

        // Filter: only alert-worthy records
        const isStatusMatch = statusFilter.has(record.Status);
        const isSlowRequest  = record.WallTimeMs >= durationThreshold;
        if (!isStatusMatch && !isSlowRequest) continue;

        const tsSeconds = Math.floor(record.Timestamp / 1_000_000_000);

        env.AE_WORKERS.writeDataPoint({
          blobs: [
            record.ScriptName,
            record.Outcome,
            record.Exceptions.map(e => e.message).join(';').slice(0, 255),
            isStatusMatch ? 'status_error' : 'slow_request',
          ],
          doubles: [
            record.Status,
            record.WallTimeMs,
            record.CPUTimeMs,
            record.Exceptions.length,
          ],
          indexes: [record.ScriptName],
        });
      }

      message.ack();
    }
  },
};
```

## Step 4 — Query Analytics Engine

```typescript
// query-ae.ts  (run with: npx ts-node query-ae.ts)
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;

async function queryAE(sql: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'text/plain' },
      body: sql,
    }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// Top slow scripts in last hour
const result = await queryAE(`
  SELECT blob1 AS script, avg(double2) AS avg_wall_ms, count() AS requests
  FROM workers_requests
  WHERE timestamp > NOW() - INTERVAL '1' HOUR
    AND double1 NOT IN (200, 201, 204)
  GROUP BY script
  ORDER BY avg_wall_ms DESC
  LIMIT 20
`);
console.log(JSON.stringify(result, null, 2));
```

## Anti-patterns

- Parsing compressed logs synchronously in fetch handler — use Queue consumer to avoid 30s CPU limits
- Sending every record to AE regardless of interest — AE has a 25M datapoints/day free tier; filter aggressively
- Storing full log lines as AE blobs — AE blob fields are capped at 1024 bytes; truncate exception messages
- Pulling from R2 inside a Durable Object alarm — prefer Queue consumer for fan-out resilience

## Gotchas

- Logpush `frequency: "low"` means ~30s batches; `"high"` is ~5s but costs more egress
- R2 event notifications require the queue to be in the same account as the bucket
- `gunzipSync` from `node:zlib` works in Workers with `nodejs_compat` flag; add `compatibility_flags = ["nodejs_compat"]` to wrangler.toml
- AE `writeDataPoint` is best-effort; if the Worker throws after writing, points are not rolled back
- Logpush timestamps are nanoseconds (Unix); divide by 1e9 for seconds

## Verification

```bash
# Confirm Logpush job is enabled and receiving data
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, enabled, last_complete}'

# Check R2 for recent log files
wrangler r2 object list prod-logpush --prefix "logs/$(date +%Y-%m-%d)/"

# Verify AE is receiving points
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: text/plain" \
  -d "SELECT count() FROM workers_requests WHERE timestamp > NOW() - INTERVAL '5' MINUTE"

# Tail the consumer Worker logs in real time
wrangler tail logpush-tail-consumer --format json | jq '.logs[].message[]'
```

## Related

- `documentation/docs/policies/monitoring/workers-anomaly-detection-analytics-engine.md`
- `documentation/docs/policies/monitoring/workers-slo-error-budget-burn-rate-analytics.md`

## Sources

- https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
