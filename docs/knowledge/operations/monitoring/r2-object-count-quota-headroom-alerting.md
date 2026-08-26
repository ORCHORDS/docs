# R2 Object Count Quota Headroom Alerting

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

An R2 bucket used for user-uploaded assets grows steadily. Storage in GB stays well within budget, but the bucket approaches Cloudflare's per-bucket object count limits and eventually PUTs start failing with `R2 bucket exceeds object limit`. Because the standard Cloudflare dashboard surfaces only byte usage, the object count headroom goes unmonitored until upload failures hit production.

## Context

R2 enforces limits at the object count level independently of byte usage. A bucket receiving many small files (thumbnails, webhook payloads, log shards) can exhaust the object count long before storage bytes become a concern. Cloudflare does not currently send automatic notifications for object count headroom. Workers can query R2 bucket metadata via the `list()` API to count objects, write the count to Analytics Engine, and fire alerts when headroom falls below a threshold. This pattern runs as a scheduled Worker (cron trigger) to avoid adding latency to hot paths.

---

## 1. Object Count Probe Worker

```typescript
// src/r2-count-probe.ts
export interface Env {
  BUCKET: R2Bucket;
  AE_DATASET: AnalyticsEngineDataset;
  BUCKET_NAME: string;
  OBJECT_LIMIT: string;   // e.g. "1000000000" — set in wrangler.toml vars
}

async function countAllObjects(bucket: R2Bucket): Promise<number> {
  let total = 0;
  let cursor: string | undefined;

  do {
    const page = await bucket.list({
      limit: 1000,
      cursor,
      include: [],   // skip metadata — count only
    });

    total += page.objects.length;
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);

  return total;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const objectLimit = parseInt(env.OBJECT_LIMIT, 10);
    const objectCount = await countAllObjects(env.BUCKET);
    const headroomPct = ((objectLimit - objectCount) / objectLimit) * 100;

    env.AE_DATASET.writeDataPoint({
      indexes: [env.BUCKET_NAME],
      blobs: ['object-count-probe'],
      doubles: [
        objectCount,
        objectLimit,
        headroomPct,
        objectCount / objectLimit, // fill ratio 0..1
      ],
    });
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml excerpt
[[triggers.crons]]
crons = ["0 * * * *"]   # hourly

[vars]
BUCKET_NAME   = "user-assets"
OBJECT_LIMIT  = "1000000000"
```

---

## 2. Prefix-Level Object Count Breakdown

When a bucket uses prefix namespacing (one prefix per tenant), breaking down counts by prefix lets you identify a single tenant exhausting the bucket.

```typescript
// src/r2-prefix-count.ts
export async function countByPrefix(
  bucket: R2Bucket,
  prefixes: string[],
  ae: AnalyticsEngineDataset,
  bucketName: string
): Promise<void> {
  await Promise.all(
    prefixes.map(async prefix => {
      let count = 0;
      let cursor: string | undefined;

      do {
        const page = await bucket.list({ prefix, limit: 1000, cursor, include: [] });
        count += page.objects.length;
        cursor = page.truncated ? page.cursor : undefined;
      } while (cursor);

      ae.writeDataPoint({
        indexes: [`${bucketName}/${prefix}`],
        blobs: ['prefix-count'],
        doubles: [count, 0, 100, 0],
      });
    })
  );
}
```

---

## 3. Analytics Engine SQL Queries

```sql
-- Latest object count per bucket
SELECT
  index1                         AS bucket,
  LAST(double1)                  AS object_count,
  LAST(double2)                  AS object_limit,
  LAST(double3)                  AS headroom_pct,
  LAST(double4)                  AS fill_ratio
FROM r2_object_count
WHERE timestamp > NOW() - INTERVAL '2' HOUR
GROUP BY bucket
ORDER BY fill_ratio DESC;

-- Object count growth rate — objects added per hour over the last 7 days
SELECT
  toStartOfHour(timestamp)            AS hour,
  index1                              AS bucket,
  LAST(double1) - FIRST(double1)      AS objects_delta
FROM r2_object_count
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY hour, bucket
ORDER BY hour DESC, objects_delta DESC;

-- Days until object limit at current growth rate (linear projection)
WITH daily AS (
  SELECT
    index1                                    AS bucket,
    toStartOfDay(timestamp)                   AS day,
    AVG(double1)                              AS avg_count
  FROM r2_object_count
  WHERE timestamp > NOW() - INTERVAL '14' DAY
  GROUP BY bucket, day
)
SELECT
  bucket,
  LAST(avg_count)                             AS current_count,
  (LAST(avg_count) - FIRST(avg_count)) / 14   AS daily_growth_rate,
  (1000000000 - LAST(avg_count)) /
    NULLIF((LAST(avg_count) - FIRST(avg_count)) / 14, 0)  AS days_to_limit
FROM daily
GROUP BY bucket
ORDER BY days_to_limit ASC
LIMIT 10;
```

---

## 4. Alert Worker — Headroom Threshold

```typescript
// alert-worker/r2-headroom-alert.ts
// Cron: 0 * * * *  (hourly, matches probe cadence)

const WARN_THRESHOLD_PCT  = 20;  // alert when < 20% headroom
const CRIT_THRESHOLD_PCT  = 5;   // page when < 5% headroom

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT index1 AS bucket,
             LAST(double3) AS headroom_pct,
             LAST(double1) AS object_count
      FROM r2_object_count
      WHERE timestamp > NOW() - INTERVAL '2' HOUR
      GROUP BY bucket
      HAVING headroom_pct < ${WARN_THRESHOLD_PCT}
      ORDER BY headroom_pct ASC
    `;

    const rows = await cfAeQuery<{ bucket: string; headroom_pct: number; object_count: number }>(env, sql);

    for (const row of rows) {
      const level = row.headroom_pct < CRIT_THRESHOLD_PCT ? 'CRITICAL' : 'WARNING';
      await sendSlackAlert(env.SLACK_WEBHOOK, {
        text: `[${level}] R2 bucket "${row.bucket}" has only ${row.headroom_pct.toFixed(1)}% object headroom (${row.object_count.toLocaleString()} objects).`,
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. Lifecycle Cleanup Worker — Preventing Quota Exhaustion

```typescript
// src/r2-lifecycle-cleanup.ts
// Deletes objects older than a retention window to reclaim object count quota.

export async function purgeOlderThan(
  bucket: R2Bucket,
  prefix: string,
  retentionDays: number,
  ae: AnalyticsEngineDataset
): Promise<void> {
  const cutoff = new Date(Date.now() - retentionDays * 86_400_000);
  let deleted = 0;
  let cursor: string | undefined;

  do {
    const page = await bucket.list({ prefix, limit: 1000, cursor, include: ['httpMetadata'] });

    const toDelete = page.objects.filter(
      o => o.uploaded < cutoff
    );

    if (toDelete.length > 0) {
      await bucket.delete(toDelete.map(o => o.key));
      deleted += toDelete.length;
    }

    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);

  ae.writeDataPoint({
    indexes: [`${prefix}-lifecycle`],
    blobs: ['purge'],
    doubles: [deleted, retentionDays, 0, 0],
  });
}
```

---

## Anti-patterns

- **Relying solely on byte-based billing alerts** — object count and byte usage are independent axes; an object-dense bucket can hit count limits at <1 GB of data.
- **Listing without pagination** — `bucket.list()` returns at most 1,000 keys per call; a single un-paginated call silently undercounts.
- **Running the count probe on the hot request path** — full bucket enumeration is O(n) and can be slow; always run in a cron-triggered Worker.
- **Using object count as a primary SLI** — object count is an operational resource metric, not a user-facing SLI. Keep it in the capacity monitoring tier.

## Gotchas

- Counting a bucket with millions of objects can take several seconds and consume significant CPU time on the probe Worker; budget for this in the cron Worker's CPU limit.
- `bucket.list()` returns `deleted` marker objects in versioned buckets — filter by `customMetadata` or key prefix if your bucket uses soft deletes to avoid overcounting.
- The object count limit varies by plan; verify against Cloudflare's current limits page, as it changed in 2025.
- Analytics Engine data points have a ~30-second ingestion delay; real-time dashboards should account for this lag.

## Verification

```bash
# Count objects manually for a small bucket and compare to AE value
npx wrangler r2 object list user-assets --remote 2>/dev/null | wc -l

# Query AE for the most recent count
curl -s "$CF_AE_SQL_URL" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query":"SELECT index1, LAST(double1), LAST(double3) FROM r2_object_count WHERE timestamp > NOW() - INTERVAL '\''2'\'' HOUR GROUP BY index1"}' \
  | jq '.data'
```

## Related

- `r2-storage-usage-analytics-engine-cost-monitoring.md`
- `r2-bandwidth-usage-analytics-engine.md`
- `r2-multipart-upload-monitoring.md`
- `capacity-planning-metrics.md`
- `cloudflare-billing-cost-anomaly-detection.md`

## Sources

- R2 limits: https://developers.cloudflare.com/r2/reference/limits/
- R2 Workers API — list: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Analytics Engine write API: https://developers.cloudflare.com/analytics/analytics-engine/get-started/
- Cloudflare cron triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
