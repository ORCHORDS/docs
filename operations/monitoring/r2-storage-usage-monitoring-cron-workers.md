# Monitoring R2 Bucket Storage Usage with a Cron Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

R2 bills on stored gigabytes and you need early warning before you cross a billing tier boundary or an internally defined storage budget. Without automated monitoring you only discover overages on the monthly invoice. You want trend data so you can project when the bucket will reach a threshold and receive a Slack alert with enough lead time to act.

---

## Context

Cloudflare exposes an R2 bucket usage endpoint at `GET /client/v4/accounts/{accountId}/r2/buckets/{bucketName}/usage` that returns current byte count and object count. A Cron Trigger Worker calls this endpoint on a schedule, writes the sample to a D1 `r2_usage` table, computes a 30-day linear growth projection, and posts a Slack alert when projected or current usage is within 20% of a configurable billing tier limit. The Worker uses the Cloudflare REST API rather than an R2 binding because the usage endpoint is not exposed through the Workers R2 binding.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "r2-usage-monitor"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[triggers]
crons = ["0 * * * *"]  # Every hour

[[d1_databases]]
binding = "DB"
database_name = "monitoring"
database_id = "<your-d1-database-id>"

[vars]
CF_ACCOUNT_ID     = "<your-cloudflare-account-id>"
R2_BUCKET_NAME    = "my-production-bucket"
# 10 GB free tier; set to your plan limit in bytes
STORAGE_LIMIT_BYTES = "10737418240"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
```

```sql
-- D1 migration: 0002_create_r2_usage.sql
CREATE TABLE IF NOT EXISTS r2_usage (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  bucket_name TEXT    NOT NULL,
  bytes_used  INTEGER NOT NULL,
  object_count INTEGER NOT NULL,
  sampled_at  INTEGER NOT NULL  -- Unix epoch seconds
);

CREATE INDEX IF NOT EXISTS idx_r2_usage_sampled_at
  ON r2_usage (bucket_name, sampled_at);
```

---

## Section 2 — Worker implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  CF_ACCOUNT_ID: string;
  R2_BUCKET_NAME: string;
  STORAGE_LIMIT_BYTES: string;
  SLACK_WEBHOOK_URL: string;
  CF_API_TOKEN: string; // Set via wrangler secret put CF_API_TOKEN
}

interface R2UsageResult {
  result: {
    bucketName: string;
    payloadSize: number;   // bytes stored
    objectCount: number;
  };
  success: boolean;
  errors: { message: string }[];
}

async function fetchR2Usage(env: Env): Promise<{ bytes: number; objects: number }> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/r2/buckets/${env.R2_BUCKET_NAME}/usage`;

  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`R2 usage API returned ${response.status}: ${await response.text()}`);
  }

  const data = await response.json<R2UsageResult>();
  if (!data.success) {
    throw new Error(`R2 usage API error: ${data.errors.map((e) => e.message).join(", ")}`);
  }

  return {
    bytes: data.result.payloadSize,
    objects: data.result.objectCount,
  };
}

async function recordUsage(
  db: D1Database,
  bucketName: string,
  bytes: number,
  objects: number
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO r2_usage (bucket_name, bytes_used, object_count, sampled_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(bucketName, bytes, objects, Math.floor(Date.now() / 1000))
    .run();
}

interface UsageSample {
  bytes_used: number;
  sampled_at: number;
}

async function computeGrowthProjection(
  db: D1Database,
  bucketName: string
): Promise<{ currentBytes: number; projectedBytes30d: number } | null> {
  const thirtyDaysAgo = Math.floor(Date.now() / 1000) - 30 * 24 * 60 * 60;

  const result = await db
    .prepare(
      `SELECT bytes_used, sampled_at
       FROM r2_usage
       WHERE bucket_name = ? AND sampled_at >= ?
       ORDER BY sampled_at ASC`
    )
    .bind(bucketName, thirtyDaysAgo)
    .all<UsageSample>();

  if (!result.results || result.results.length < 2) {
    // Not enough history for a meaningful projection
    return null;
  }

  const samples = result.results;
  const oldest = samples[0];
  const newest = samples[samples.length - 1];

  const elapsedSeconds = newest.sampled_at - oldest.sampled_at;
  const bytesDelta = newest.bytes_used - oldest.bytes_used;

  if (elapsedSeconds <= 0) return null;

  // bytes per second growth rate
  const growthRatePerSecond = bytesDelta / elapsedSeconds;
  const secondsIn30Days = 30 * 24 * 60 * 60;
  const projectedBytes30d = newest.bytes_used + growthRatePerSecond * secondsIn30Days;

  return { currentBytes: newest.bytes_used, projectedBytes30d };
}

function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  return `${value.toFixed(2)} ${units[unitIndex]}`;
}

async function maybeAlert(
  env: Env,
  currentBytes: number,
  projectedBytes30d: number,
  limitBytes: number
): Promise<void> {
  const currentRatio = currentBytes / limitBytes;
  const projectedRatio = projectedBytes30d / limitBytes;

  // Alert when current usage OR 30-day projection exceeds 80% of limit
  const shouldAlert = currentRatio >= 0.8 || projectedRatio >= 0.8;
  if (!shouldAlert) return;

  const blocks = [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: [
          `:warning: *R2 Storage Alert* — \`${env.R2_BUCKET_NAME}\``,
          `Current usage: *${formatBytes(currentBytes)}* (${(currentRatio * 100).toFixed(1)}% of limit)`,
          `Limit: *${formatBytes(limitBytes)}*`,
          `30-day projection: *${formatBytes(projectedBytes30d)}* (${(projectedRatio * 100).toFixed(1)}% of limit)`,
        ].join("\n"),
      },
    },
  ];

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const limitBytes = parseInt(env.STORAGE_LIMIT_BYTES, 10);

    // 1. Fetch current usage from Cloudflare API
    const { bytes, objects } = await fetchR2Usage(env);

    // 2. Persist the sample to D1
    await recordUsage(env.DB, env.R2_BUCKET_NAME, bytes, objects);

    // 3. Compute growth projection from D1 history
    const projection = await computeGrowthProjection(env.DB, env.R2_BUCKET_NAME);

    // 4. Alert if needed
    if (projection) {
      await maybeAlert(
        env,
        projection.currentBytes,
        projection.projectedBytes30d,
        limitBytes
      );
    }

    console.log(`R2 usage recorded: ${formatBytes(bytes)}, ${objects} objects`);
  },
};
```

---

## Section 3 — Pruning old samples

```typescript
// Add to scheduled handler to prevent unbounded D1 table growth
async function pruneOldSamples(db: D1Database, bucketName: string): Promise<void> {
  // Keep 90 days of hourly samples — 90 * 24 = 2160 rows max per bucket
  const ninetyDaysAgo = Math.floor(Date.now() / 1000) - 90 * 24 * 60 * 60;
  await db
    .prepare(`DELETE FROM r2_usage WHERE bucket_name = ? AND sampled_at < ?`)
    .bind(bucketName, ninetyDaysAgo)
    .run();
}

// Call from scheduled handler:
// await pruneOldSamples(env.DB, env.R2_BUCKET_NAME);
```

---

## Anti-patterns

- **Storing the API token in `[vars]`** — `[vars]` values appear in plaintext in `wrangler.toml` and in the dashboard. Always store `CF_API_TOKEN` with `wrangler secret put CF_API_TOKEN`.
- **Using a global API token** — Create a scoped API token with only `Account R2 Storage:Read` permissions for this monitoring Worker. A compromised monitoring Worker should not be able to write or delete R2 objects.
- **Projecting growth from fewer than two samples** — A single data point yields a division-by-zero or meaningless projection. Guard with a sample count check and skip projection on first run.
- **Alerting on every cron execution above threshold** — This floods Slack every hour once the threshold is crossed. Add a `last_alerted_at` value in KV with a minimum alert interval of 24 hours.

---

## Gotchas

- The `/r2/buckets/{name}/usage` endpoint reflects usage as of the previous billing period snapshot, not real-time byte counts. Expect up to a few minutes of lag.
- Linear growth projection is accurate only for steady ingestion patterns. Bursty uploads (batch migrations, backups) will cause false-positive alerts; consider switching to a 7-day window for more responsive projection.
- D1 row limits per database are large (500 MB), but hourly samples for many buckets can accumulate quickly. Prune regularly.
- `wrangler secret put` values are available in the Workers environment but are not visible in `wrangler.toml` or the Cloudflare dashboard after creation. Rotate them with `wrangler secret put` again.

---

## Verification

```bash
# 1. Add the API token as a secret
npx wrangler secret put CF_API_TOKEN

# 2. Apply D1 migration
npx wrangler d1 execute monitoring --file=migrations/0002_create_r2_usage.sql

# 3. Deploy the cron worker
npx wrangler deploy

# 4. Manually trigger the cron to confirm it runs without errors
npx wrangler trigger scheduled --name r2-usage-monitor --cron "0 * * * *"

# 5. Verify the sample was written to D1
npx wrangler d1 execute monitoring \
  --command "SELECT * FROM r2_usage ORDER BY sampled_at DESC LIMIT 5"

# 6. Check the Cloudflare dashboard → Workers & Pages → r2-usage-monitor → Logs
# to confirm the 'R2 usage recorded' log line appears
```

---

## Related

- `workers-error-rate-alerting-analytics-engine.md`
- `queue-consumer-lag-monitoring-d1-workers.md`

---

## Sources

- Cloudflare R2 REST API — https://developers.cloudflare.com/api/resources/r2/subresources/buckets/
- Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- D1 Worker API — https://developers.cloudflare.com/d1/worker-api/
