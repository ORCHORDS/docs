# Workers Analytics and Billing Monitoring

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Cloudflare Workers bills silently spike when a new deployment increases CPU time,
a cron trigger runs at unexpectedly high frequency, or a background queue
consumer loops on errors. Teams discover the overage on the monthly invoice,
not during the incident. This article shows how to surface Workers billing
signals in near-real-time and connect them to per-service attribution.

## Context

Cloudflare's billing model for Workers (as of 2026) charges for:
- **Requests**: included in plan, then per-million beyond the limit
- **CPU time (duration)**: billed per million GB-ms of actual CPU consumed
- **Durable Objects**: storage GiB-month + WebSocket forwarding GiB
- **Queues**: per-million operations
- **R2**: storage, Class A (write), and Class B (read) operations

The Cloudflare Analytics API (GraphQL) exposes `workersInvocationsAdaptive`
and `workersSubrequestsAdaptive` datasets with 1-minute granularity.
Account-level GraphQL is available at `https://api.cloudflare.com/client/v4/graphql`.

Billing data lags by ~5 minutes but is far more actionable than waiting for
the Cloudflare dashboard email digest.

---

## Section 1: GraphQL Billing Query via Scheduled Worker

Create a scheduled Worker that polls the Analytics Engine GraphQL API every
5 minutes and writes derived metrics to Workers Analytics Engine.

```toml
# wrangler.toml
name = "billing-monitor"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[vars]
CF_ACCOUNT_ID = "abc123"

[[analytics_engine_datasets]]
binding = "BILLING_AE"
dataset = "billing_metrics"

[triggers]
crons = ["*/5 * * * *"]
```

```typescript
// src/index.ts
export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string; // bound as secret via `wrangler secret put`
  BILLING_AE: AnalyticsEngineDataset;
  ALERT_WEBHOOK: string;
}

const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";

async function queryWorkerMetrics(
  accountId: string,
  token: string,
  sinceMinutes = 5
): Promise<WorkerMetricRow[]> {
  const since = new Date(Date.now() - sinceMinutes * 60_000).toISOString();
  const query = `{
    viewer {
      accounts(filter: { accountTag: "${accountId}" }) {
        workersInvocationsAdaptive(
          limit: 10000
          filter: { datetimeHour_geq: "${since}" }
          orderBy: [datetimeMinute_ASC]
        ) {
          dimensions { scriptName datetimeMinute }
          sum { requests errors subrequests wallTime cpuTime }
          quantiles { cpuTimeP99 }
        }
      }
    }
  }`;

  const resp = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  if (!resp.ok) throw new Error(`GraphQL ${resp.status}`);
  const json: any = await resp.json();
  return (
    json.data?.viewer?.accounts?.[0]?.workersInvocationsAdaptive ?? []
  );
}

interface WorkerMetricRow {
  dimensions: { scriptName: string; datetimeMinute: string };
  sum: {
    requests: number;
    errors: number;
    subrequests: number;
    wallTime: number;
    cpuTime: number;
  };
  quantiles: { cpuTimeP99: number };
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const rows = await queryWorkerMetrics(env.CF_ACCOUNT_ID, env.CF_API_TOKEN);

    for (const row of rows) {
      const { scriptName } = row.dimensions;
      const cpuGbMs = row.sum.cpuTime / 1_000; // µs -> ms
      // Estimated cost: $0.02 per million GB-ms (Standard tier)
      const estimatedCostUsd = (cpuGbMs / 1_000_000) * 0.02;

      env.BILLING_AE.writeDataPoint({
        blobs: [scriptName],
        doubles: [
          row.sum.requests,
          row.sum.errors,
          row.sum.cpuTime,
          row.quantiles.cpuTimeP99,
          estimatedCostUsd,
        ],
        indexes: [scriptName],
      });

      // Alert if estimated cost per 5-min window exceeds $0.50
      if (estimatedCostUsd > 0.5) {
        await fetch(env.ALERT_WEBHOOK, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: `⚠️ Worker \`${scriptName}\` cost $${estimatedCostUsd.toFixed(4)} in the last 5 min`,
          }),
        });
      }
    }
  },
};
```

---

## Section 2: Grafana Dashboard via Analytics Engine SQL API

Analytics Engine supports a SQL API compatible with Grafana's Infinity plugin.
Configure a data source pointing at:

```
https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql
```

Example SQL queries for dashboard panels:

```sql
-- Panel: CPU cost by Worker (last 1 hour)
SELECT
  blob1 AS worker,
  SUM(double3) / 1e9 AS cpu_seconds,
  SUM(double5) AS estimated_usd
FROM billing_metrics
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY worker
ORDER BY estimated_usd DESC
LIMIT 20
```

```sql
-- Panel: Error rate spike detection
SELECT
  toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS minute,
  blob1 AS worker,
  SUM(double2) / SUM(double1) AS error_rate
FROM billing_metrics
WHERE timestamp > NOW() - INTERVAL '30' MINUTE
GROUP BY minute, worker
HAVING error_rate > 0.05
ORDER BY minute DESC
```

```sql
-- Panel: Hourly spend forecast
SELECT
  toStartOfInterval(timestamp, INTERVAL '1' HOUR) AS hour,
  SUM(double5) * 12 AS projected_hourly_usd   -- 5-min windows × 12
FROM billing_metrics
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY hour
ORDER BY hour ASC
```

Grafana alert rule — attach to the error-rate panel with threshold > 0.1 for
5 consecutive minutes before firing.

---

## Section 3: Durable Objects and Queue Billing Signals

DO storage growth and Queue throughput require separate GraphQL datasets:

```typescript
// Add to billing-monitor Worker
async function queryDurableObjectMetrics(
  accountId: string,
  token: string
): Promise<void> {
  const query = `{
    viewer {
      accounts(filter: { accountTag: "${accountId}" }) {
        durableObjectsInvocationsAdaptive(limit: 1000) {
          dimensions { namespace }
          sum { requests wallTime storageReadUnits storageWriteUnits }
        }
        durableObjectsStorageAdaptive(limit: 1000) {
          dimensions { namespace }
          max { storedBytes }
        }
      }
    }
  }`;

  const resp = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });
  const json: any = await resp.json();
  const invocations =
    json.data?.viewer?.accounts?.[0]?.durableObjectsInvocationsAdaptive ?? [];
  const storage =
    json.data?.viewer?.accounts?.[0]?.durableObjectsStorageAdaptive ?? [];

  console.log(
    `DO namespaces active: ${invocations.length}, storage entries: ${storage.length}`
  );
  // Write to Analytics Engine with same pattern as Worker metrics
}
```

For Queues:

```graphql
# GraphQL query fragment for queue operations
queuesAdaptive(limit: 1000) {
  dimensions { queueName }
  sum { messagesProduced messagesConsumed messagesRetried messagesDead }
}
```

Cost formula for Queues: `(messagesProduced + messagesConsumed) / 1_000_000 * $0.40`.
Dead-letter messages indicate retry loops that multiply cost without value.

---

## Anti-patterns

- **Polling the dashboard manually**: The Cloudflare UI updates every 15–30 minutes;
  by the time a spike is visible you may have burned thousands of GiB-ms.
- **Treating wall time as billing time**: Cloudflare bills on *CPU time*, not wall
  clock. A Worker that awaits fetch() for 900 ms but uses 5 ms of CPU costs far
  less than assumed. Monitor `cpuTime` specifically.
- **Single global alert threshold**: A Worker handling low-traffic admin tasks and
  one handling payment webhooks need separate thresholds. Parameterize by script name.
- **Ignoring `subrequests`**: Each outbound `fetch()` from a Worker counts as a
  subrequest. Plans cap subrequests per invocation; exceeding them throws silently
  in some plan tiers.
- **Forgetting DO egress**: Data transferred out of Durable Objects over WebSocket
  is billed separately. Track `storageReadUnits` not just `storedBytes`.

---

## Gotchas

- The GraphQL API returns data with up to 5-minute lag. Do not compare real-time
  traffic to billing data expecting exact alignment.
- `workersInvocationsAdaptive` aggregates sub-1-minute data into 1-minute buckets
  server-side; querying at finer granularity than 1 minute returns nothing.
- Analytics Engine `writeDataPoint` is fire-and-forget. If the monitor Worker itself
  errors, data points for that window are lost. Add a secondary log via `console.log`
  captured by Logpush as a fallback.
- The GraphQL `limit` for `workersInvocationsAdaptive` is 10,000 rows. Accounts
  with >10,000 script×minute combinations in a window will lose tail rows. Shard the
  query by time range when this ceiling is approached.
- Secrets bound with `wrangler secret put` do not appear in `wrangler.toml` and
  are not included in `wrangler dev` local mode by default. Use a `.dev.vars` file
  for local testing.

---

## Verification

```bash
# Confirm the scheduled Worker is deploying and running
wrangler deployments list --name billing-monitor

# Tail live logs to see scheduled invocations
wrangler tail billing-monitor --format pretty

# Query Analytics Engine directly to verify data points are arriving
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1, SUM(double5) as cost FROM billing_metrics WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR GROUP BY blob1 ORDER BY cost DESC LIMIT 10"}'

# Verify alert webhook fires (dry run using curl)
curl -X POST "$ALERT_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text":"Test billing alert from billing-monitor"}'
```

Expected: the SQL query returns rows with worker names and non-zero cost values
within 10 minutes of deploying the monitor Worker.

---

## Related

- `/documentation/categories/infra/cloudflare-cost-attribution-tagging.md`
- `/documentation/categories/infra/cloudflare-workers-limits-resource-planning.md`
- `/documentation/categories/infra/finops-real-time-cost-anomaly-detection.md`
- `/documentation/categories/infra/keda-cloudflare-queue-consumers.md`
- `/documentation/categories/infra/opentelemetry-collector-config.md`

---

## Sources

- Cloudflare Analytics GraphQL API reference (2026): https://developers.cloudflare.com/analytics/graphql-api/
- Workers Pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Durable Objects billing: https://developers.cloudflare.com/durable-objects/platform/pricing/
- Queues pricing: https://developers.cloudflare.com/queues/platform/pricing/
