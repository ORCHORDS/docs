# KV Namespace Storage Size and Key Count Monitoring with Cron Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have one or more KV namespaces growing over time with no visibility into how many keys exist or how much storage is consumed. Cloudflare KV enforces hard limits (1 billion keys per namespace, 25 MB per value, 1 GB total namespace storage on most plans), but provides no built-in alerting when you approach them. Teams discover the limit only when writes start failing.

## Context

Cloudflare KV exposes namespace metadata — including approximate key counts — via the Cloudflare REST API (`GET /client/v4/accounts/{accountId}/storage/kv/namespaces/{namespaceId}`). The metadata response includes `count` (number of keys) and is available without rate limits that would apply to list-cursor pagination. A Cron Trigger Worker can poll this endpoint on a schedule, write a single data point to Analytics Engine, and surface a trend over time that drives threshold alerts before limits are hit.

Key limits to monitor:
- 1 billion keys per namespace
- 1 GB maximum namespace storage (Business+) / 1 GB per namespace (Enterprise)
- 1,000 key list operations per second

## Polling KV Namespace Metadata via REST API

```typescript
// wrangler.toml
// [triggers]
// crons = ["0 * * * *"]   # every hour
// [[analytics_engine_datasets]]
// binding = "AE"
// dataset = "kv_storage_metrics"

interface Env {
  AE: AnalyticsEngineDataset;
  CF_API_TOKEN: string; // secret, scoped to Account:Workers KV Storage:Read
  CF_ACCOUNT_ID: string;
  KV_NAMESPACE_IDS: string; // comma-separated namespace IDs to monitor
}

interface KVNamespaceMeta {
  id: string;
  title: string;
  supports_url_encoding: boolean;
}

interface KVNamespaceDetail {
  result: { count: number } | null;
  success: boolean;
}
```

## Cron Handler: Fetch Count and Write to Analytics Engine

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const namespaceIds = env.KV_NAMESPACE_IDS.split(",").map((s) => s.trim());

    await Promise.all(
      namespaceIds.map((nsId) => pollAndRecord(nsId, env))
    );
  },
};

async function pollAndRecord(namespaceId: string, env: Env): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/storage/kv/namespaces/${namespaceId}`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    console.error(`KV metadata fetch failed for ${namespaceId}: ${res.status}`);
    return;
  }

  const data = (await res.json()) as KVNamespaceDetail;

  if (!data.success || !data.result) {
    console.error(`KV metadata empty for ${namespaceId}`);
    return;
  }

  const keyCount = data.result.count;
  const headroomPct = ((1_000_000_000 - keyCount) / 1_000_000_000) * 100;

  env.AE.writeDataPoint({
    blobs: [namespaceId],
    doubles: [keyCount, headroomPct],
    indexes: [namespaceId],
  });

  console.log(`kv_namespace=${namespaceId} key_count=${keyCount} headroom_pct=${headroomPct.toFixed(2)}`);
}
```

## Analytics Engine SQL Queries for Trend and Alerts

```sql
-- Key count trend for a specific namespace (last 7 days)
SELECT
  toStartOfHour(timestamp) AS hour,
  blob1 AS namespace_id,
  max(double1) AS key_count,
  min(double2) AS headroom_pct
FROM kv_storage_metrics
WHERE timestamp > NOW() - INTERVAL '7' DAY
  AND blob1 = 'your-namespace-id'
GROUP BY 1, 2
ORDER BY 1;

-- Namespaces with less than 5% headroom (critical)
SELECT
  blob1 AS namespace_id,
  max(double1) AS latest_key_count,
  min(double2) AS headroom_pct
FROM kv_storage_metrics
WHERE timestamp > NOW() - INTERVAL '2' HOUR
GROUP BY 1
HAVING headroom_pct < 5
ORDER BY headroom_pct ASC;
```

## Alerting via Workers on Headroom Threshold

```typescript
// Triggered by the same cron, after writing to AE:
async function checkAndAlert(
  namespaceId: string,
  keyCount: number,
  headroomPct: number,
  env: Env & { ALERT_WEBHOOK_URL: string }
): Promise<void> {
  const severity =
    headroomPct < 2 ? "critical" : headroomPct < 10 ? "warning" : null;

  if (!severity) return;

  await fetch(env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `[${severity.toUpperCase()}] KV namespace \`${namespaceId}\` has ${keyCount.toLocaleString()} keys — only ${headroomPct.toFixed(1)}% headroom remaining.`,
    }),
  });
}
```

## Anti-patterns

- **Relying on list-cursor pagination for counts**: `kv.list()` inside the Worker itself is throttled and counts nothing faster than iterating all keys — use the REST API endpoint instead.
- **Polling more than hourly without reason**: The key count is eventually consistent; sub-hourly polling wastes API quota and provides no additional signal.
- **Alerting only at 0% headroom**: By the time writes fail the damage is already done. Set warning at 10% and critical at 2%.
- **Monitoring only key count**: Very large values (close to 25 MB each) can exhaust storage bytes before key count becomes significant — consider tracking estimated storage separately via sampling.

## Gotchas

- The `count` field from the REST API is **approximate** and can lag by several minutes for high-write namespaces.
- The Cloudflare API token must have `Account → Workers KV Storage → Read` permission — it does not need write access.
- `KV_NAMESPACE_IDS` as a plain env var is visible in wrangler output; prefer a secret or Workers binding for anything sensitive.
- Analytics Engine has a 25 writes/second rate limit per dataset per Worker invocation — not a concern for a cron job polling a handful of namespaces.

## Verification

1. Deploy the Cron Worker and trigger it manually: `wrangler dev --test-scheduled`.
2. Check `console.error` output for any 403/404 from the REST API.
3. After the first successful run, query Analytics Engine via the SQL API:
   ```bash
   curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
     -H "Authorization: Bearer $CF_API_TOKEN" \
     --data-raw "SELECT blob1, double1, double2 FROM kv_storage_metrics LIMIT 5"
   ```
4. Confirm headroom values decrease monotonically as keys are added in staging.

## Related

- `kv-operation-rate-analytics-engine.md`
- `kv-expiration-eviction-monitoring.md`
- `kv-latency-p99-analytics-engine-tracking.md`
- `workers-cron-trigger-missed-execution-alerting.md`
- `analytics-engine-write-limits-and-backpressure.md`

## Sources

- Cloudflare KV Limits: https://developers.cloudflare.com/kv/platform/limits/
- KV REST API Reference: https://developers.cloudflare.com/api/resources/kv/subresources/namespaces/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
