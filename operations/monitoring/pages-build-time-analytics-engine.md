# Cloudflare Pages Build Time Tracking with Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Build pipelines on Cloudflare Pages drift in duration over time as codebases grow,
but no built-in dashboard tracks p95 build times per branch or shows which commit
introduced a spike. Teams notice slowdowns only after deploy delays accumulate.
You need structured, queryable build-time telemetry persisted beyond the 24-hour
Pages build log retention window.

---

## Context

Cloudflare Pages exposes a Deploy Hook — an HTTP endpoint you `POST` to trigger
a build — but the inverse (a hook that Pages calls on completion) is the
**Deploy Hook outbound webhook** (set under Settings → Deploy Hooks). Pair that
with a small Worker that receives the webhook, extracts duration from the Pages
REST API, and writes a row to Analytics Engine. All data then lives in a
`workers_analytics_engine_datasets` namespace queryable via the SQL API.

Analytics Engine rows are append-only, cheap (~$0.25 / million writes), and
survive for 90 days by default. This makes them ideal for build-time trending
across long periods without pulling Pages API on every dashboard refresh.

---

## 1. Create the Analytics Engine Dataset Binding

```toml
# wrangler.toml
name = "pages-build-metrics"
compatibility_date = "2025-01-01"

[[analytics_engine_datasets]]
binding = "BUILD_METRICS"
dataset = "pages_build_times"
```

---

## 2. Pages Deploy Webhook Receiver Worker

```typescript
// src/index.ts
import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

interface Env {
  BUILD_METRICS: AnalyticsEngineDataset;
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  PAGES_PROJECT_NAME: string;
  WEBHOOK_SECRET: string;
}

interface PagesDeployment {
  id: string;
  url: string;
  environment: string;
  deployment_trigger: { metadata: { branch: string; commit_hash: string } };
  created_on: string;
  build_config: { build_command: string };
  stages: Array<{ name: string; started_on: string; ended_on: string; status: string }>;
}

async function fetchDeployment(env: Env, deploymentId: string): Promise<PagesDeployment> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/pages/projects/${env.PAGES_PROJECT_NAME}/deployments/${deploymentId}`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
  );
  const json = await res.json<{ result: PagesDeployment }>();
  return json.result;
}

function extractBuildDurationMs(deployment: PagesDeployment): number {
  const buildStage = deployment.stages.find((s) => s.name === "build");
  if (!buildStage?.started_on || !buildStage?.ended_on) return 0;
  return new Date(buildStage.ended_on).getTime() - new Date(buildStage.started_on).getTime();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Validate shared secret passed as ?secret= query param
    const url = new URL(request.url);
    if (url.searchParams.get("secret") !== env.WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const payload = await request.json<{ deployment?: { id: string } }>();
    const deploymentId = payload?.deployment?.id;
    if (!deploymentId) {
      return new Response("Missing deployment id", { status: 400 });
    }

    const deployment = await fetchDeployment(env, deploymentId);
    const buildMs = extractBuildDurationMs(deployment);
    const buildStage = deployment.stages.find((s) => s.name === "build");
    const success = buildStage?.status === "success" ? 1 : 0;

    env.BUILD_METRICS.writeDataPoint({
      blobs: [
        deployment.deployment_trigger.metadata.branch,    // index 1: branch
        deployment.environment,                            // index 2: environment
        deployment.deployment_trigger.metadata.commit_hash.slice(0, 8), // index 3: short sha
        buildStage?.status ?? "unknown",                   // index 4: status
      ],
      doubles: [
        buildMs,  // index 1: build_duration_ms
        success,  // index 2: success (1|0)
      ],
      indexes: [deployment.deployment_trigger.metadata.branch],
    });

    return new Response("OK");
  },
};
```

---

## 3. Query Build Time Percentiles via SQL API

```bash
# p50 / p95 / p99 build durations by branch, last 30 days
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "
      SELECT
        blob1                                   AS branch,
        count()                                 AS builds,
        quantileExact(0.50)(double1)            AS p50_ms,
        quantileExact(0.95)(double1)            AS p95_ms,
        quantileExact(0.99)(double1)            AS p99_ms,
        avg(double2)                            AS success_rate
      FROM pages_build_times
      WHERE timestamp >= now() - INTERVAL 30 DAY
        AND double1 > 0
      GROUP BY branch
      ORDER BY p95_ms DESC
    "
  }'
```

---

## 4. Detect Build Time Regressions Over Rolling Windows

```typescript
// Scheduled Worker: compare last-24h p95 vs previous-24h p95 per branch
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const sql = async (q: string) => {
      const res = await fetch(
        `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.CF_API_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ query: q }),
        }
      );
      return res.json<{ data: Record<string, unknown>[] }>();
    };

    const result = await sql(`
      SELECT
        blob1 AS branch,
        quantileExactIf(0.95)(double1, timestamp >= now() - INTERVAL 1 DAY) AS p95_current,
        quantileExactIf(0.95)(double1,
          timestamp >= now() - INTERVAL 2 DAY AND timestamp < now() - INTERVAL 1 DAY
        ) AS p95_previous
      FROM pages_build_times
      WHERE timestamp >= now() - INTERVAL 2 DAY AND double1 > 0
      GROUP BY branch
    `);

    for (const row of result.data) {
      const ratio = Number(row.p95_current) / (Number(row.p95_previous) || 1);
      if (ratio > 1.3) {
        console.log(JSON.stringify({
          level: "warn",
          branch: row.branch,
          p95_current_ms: row.p95_current,
          p95_previous_ms: row.p95_previous,
          ratio: ratio.toFixed(2),
          msg: "Build time p95 regressed >30% vs prior 24h",
        }));
      }
    }
  },
};
```

---

## 5. Grafana Panel — Build Duration Trend

Connect Grafana to the Analytics Engine via the Cloudflare datasource plugin and
use this SQL for a time-series panel grouped by branch:

```sql
SELECT
  toStartOfHour(timestamp) AS time,
  blob1                    AS branch,
  quantileExact(0.95)(double1) AS p95_build_ms
FROM pages_build_times
WHERE
  timestamp BETWEEN $__fromTime AND $__toTime
  AND double1 > 0
  AND blob1 IN ($branch)
GROUP BY time, branch
ORDER BY time
```

Set **visualization** to Time series, **legend** to `{{branch}}`.

---

## Anti-patterns

- **Polling the Pages API on every Grafana load** — the API has rate limits and adds
  latency. Write once on deploy, read from Analytics Engine.
- **Writing build duration in the webhook payload only** — Pages webhooks do not
  include stage-level timing; always re-fetch the deployment object from the REST API.
- **Using a single blob for all metadata** — split branch, environment, and status
  into separate blob slots so you can `GROUP BY` them independently in SQL.
- **Ignoring failed builds in percentile calculations** — include `double2 = 1`
  filter or track failed builds separately; mixing zeros from aborted builds skews p95.

---

## Gotchas

- Pages outbound webhooks fire **after the deployment status is set**, but the
  stages array may briefly show `null` for `ended_on` if you hit the API within
  milliseconds. Add a 2-second `setTimeout` or retry once.
- Analytics Engine `writeDataPoint` is fire-and-forget; it does not throw on
  failure. Wrap in `ctx.waitUntil` so the Worker does not terminate before the
  write flushes.
- The `indexes` array in `writeDataPoint` accepts exactly **one** element. Use the
  branch name as the index for fast single-branch lookups.
- `quantileExact` in Analytics Engine SQL is computed client-side from raw rows —
  for datasets > 1 million rows prefer `quantile` (approximate) to stay under the
  query timeout.

---

## Verification

```bash
# Confirm rows are arriving (should show recent timestamps)
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT max(timestamp), count() FROM pages_build_times"}'

# Trigger a manual webhook delivery in Pages dashboard → Settings → Deploy Hooks
# then re-run the query to see count increment
```

---

## Related

- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-analytics-engine-grafana-dashboard.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `cloudflare-logpush-setup.md`
- `deployment-event-tracking.md`

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/pages/configuration/deploy-hooks/
- https://developers.cloudflare.com/api/operations/pages-deployment-get-deployment-info
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
