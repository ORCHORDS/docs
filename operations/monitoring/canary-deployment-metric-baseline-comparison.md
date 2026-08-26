# Canary Deployment Monitoring: Comparing Metric Baselines Between Versions

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use Case

You deploy a new version of your Cloudflare Worker or Pages project to a small fraction of traffic (5–10%) before promoting it to 100%. You need to automatically compare the canary version's metrics against the stable baseline: error rate, P50/P95/P99 latency, cache hit rate, and business KPIs (conversion events, API call success rate). If the canary diverges beyond a configured threshold, you want an automated rollback or at minimum an immediate alert before the bad code reaches all users.

---

## Context

Cloudflare Workers supports traffic splitting natively via **Worker Routes with weights** (using Cloudflare's Traffic Routing rules, or via a custom dispatch Worker) or through **Gradual Rollouts** in the Cloudflare dashboard for Workers. For Pages deployments, you can use **Branch deployments** and direct a fraction of traffic to the branch URL.

The key challenge in canary monitoring is **baseline comparison**: the canary sees only 5–10% of traffic, so raw counts are not comparable to the stable version's counts. You must normalise metrics to _rates_ (errors per request, latency per percentile) rather than _totals_.

**Analytics Engine** is the natural storage layer: write version-tagged metric rows from within both the stable and canary Workers, then query the Analytics Engine SQL API to compute comparative statistics per version. A cron Worker runs the comparison on a schedule and decides whether to escalate.

---

## Architecture

```
User Traffic
    │
    ├──── 95% ──► Stable Worker (v1.2.3) ──► Analytics Engine (version=v1.2.3)
    │
    └──── 5%  ──► Canary Worker (v1.3.0) ──► Analytics Engine (version=v1.3.0)
                                                         │
                                          ┌──────────────┘
                                          ▼
                                  Cron Worker (every 1 min)
                                  Queries Analytics Engine
                                  Compares v1.3.0 vs v1.2.3
                                  ──► OK: continue canary
                                  ──► DEGRADED: alert + auto-rollback
```

---

## Instrumenting the Worker with Version Tags

```typescript
// src/analytics.ts

interface Env {
  METRICS: AnalyticsEngineDataset;
  VERSION: string; // injected via [vars] in wrangler.toml, e.g. "v1.3.0"
}

export function recordRequest(
  env: Env,
  method: string,
  path: string,
  status: number,
  durationMs: number,
  cacheHit: boolean
): void {
  const isError = status >= 500;
  const isClientError = status >= 400 && status < 500;

  env.METRICS.writeDataPoint({
    blobs: [
      env.VERSION,   // index 1: version
      method,        // index 2: HTTP method
      path,          // index 3: route path (normalised, no IDs)
      String(status), // index 4: status code
    ],
    doubles: [
      durationMs,              // index 1: wall time ms
      isError ? 1 : 0,         // index 2: server error flag
      isClientError ? 1 : 0,   // index 3: client error flag
      cacheHit ? 1 : 0,        // index 4: cache hit flag
      1,                        // index 5: request count (always 1, for sum aggregation)
    ],
    indexes: [env.VERSION],    // primary dimension for fast filtering
  });
}
```

```typescript
// src/index.ts

import { recordRequest } from "./analytics";

interface Env {
  METRICS: AnalyticsEngineDataset;
  VERSION: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let response: Response;
    let cacheHit = false;

    try {
      // Cache check
      const cache = caches.default;
      const cached = await cache.match(request);
      if (cached) {
        cacheHit = true;
        response = cached;
      } else {
        response = await handleRequest(request, env);
      }
    } catch (err) {
      response = new Response("Internal Server Error", { status: 500 });
    }

    const duration = Date.now() - start;
    const url = new URL(request.url);

    ctx.waitUntil(
      Promise.resolve(
        recordRequest(
          env,
          request.method,
          normalizePath(url.pathname),
          response.status,
          duration,
          cacheHit
        )
      )
    );

    return response;
  },
};

function normalizePath(pathname: string): string {
  // Replace UUIDs and numeric IDs to reduce cardinality
  return pathname
    .replace(/\/[0-9a-f-]{36}/gi, "/:id")
    .replace(/\/\d+/g, "/:id");
}
```

```toml
# wrangler.toml (stable version)
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
VERSION = "v1.2.3"

[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "worker_request_metrics"

# wrangler.toml (canary version — separate wrangler config or override)
name = "api-worker-canary"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
VERSION = "v1.3.0"

[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "worker_request_metrics"  # Same dataset, different VERSION tag
```

---

## Canary Analysis Worker

```typescript
// canary-monitor/src/index.ts

interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;  // Analytics Engine read token
  STABLE_VERSION: string;   // e.g. "v1.2.3"
  CANARY_VERSION: string;   // e.g. "v1.3.0"
  ALERT_WEBHOOK: string;    // Slack / PagerDuty webhook
  // Thresholds
  ERROR_RATE_RELATIVE_THRESHOLD: string;  // e.g. "0.5" = canary error rate > 1.5x baseline triggers alert
  P95_RELATIVE_THRESHOLD: string;         // e.g. "0.3" = canary P95 > 1.3x baseline triggers alert
  MIN_CANARY_REQUESTS: string;            // e.g. "100" = need at least 100 canary requests before comparing
}

interface VersionMetrics {
  requestCount: number;
  errorRate: number;         // errors / requests
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
  cacheHitRate: number;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runComparison(env));
  },
};

async function queryMetrics(
  env: Env,
  version: string,
  windowMinutes: number = 10
): Promise<VersionMetrics> {
  const sql = `
    SELECT
      SUM(_sample_interval * double5) AS request_count,
      SUM(_sample_interval * double2) / SUM(_sample_interval * double5) AS error_rate,
      quantileWeighted(0.50)(double1, _sample_interval) AS p50,
      quantileWeighted(0.95)(double1, _sample_interval) AS p95,
      quantileWeighted(0.99)(double1, _sample_interval) AS p99,
      SUM(_sample_interval * double4) / SUM(_sample_interval * double5) AS cache_hit_rate
    FROM worker_request_metrics
    WHERE
      blob1 = '${version}'
      AND timestamp >= NOW() - INTERVAL '${windowMinutes}' MINUTE
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!resp.ok) {
    throw new Error(`Analytics Engine query failed: ${resp.status}`);
  }

  const result = await resp.json<{ data: Record<string, number | null>[] }>();
  const row = result.data[0] ?? {};

  return {
    requestCount: Number(row.request_count ?? 0),
    errorRate: Number(row.error_rate ?? 0),
    p50Ms: Number(row.p50 ?? 0),
    p95Ms: Number(row.p95 ?? 0),
    p99Ms: Number(row.p99 ?? 0),
    cacheHitRate: Number(row.cache_hit_rate ?? 0),
  };
}

async function runComparison(env: Env): Promise<void> {
  const [stable, canary] = await Promise.all([
    queryMetrics(env, env.STABLE_VERSION),
    queryMetrics(env, env.CANARY_VERSION),
  ]);

  const minRequests = parseInt(env.MIN_CANARY_REQUESTS ?? "100", 10);
  if (canary.requestCount < minRequests) {
    console.log(`Canary has only ${canary.requestCount} requests; skipping comparison.`);
    return;
  }

  const errorThreshold = parseFloat(env.ERROR_RATE_RELATIVE_THRESHOLD ?? "0.5");
  const p95Threshold = parseFloat(env.P95_RELATIVE_THRESHOLD ?? "0.3");

  const findings: string[] = [];

  // Compare error rates
  if (stable.errorRate > 0) {
    const errorRatioIncrease = (canary.errorRate - stable.errorRate) / stable.errorRate;
    if (errorRatioIncrease > errorThreshold) {
      findings.push(
        `ERROR RATE: canary ${(canary.errorRate * 100).toFixed(2)}% vs baseline ${(stable.errorRate * 100).toFixed(2)}% (+${(errorRatioIncrease * 100).toFixed(0)}%)`
      );
    }
  } else if (canary.errorRate > 0.01) {
    // Baseline has 0 errors, canary has non-trivial error rate
    findings.push(
      `ERROR RATE: canary ${(canary.errorRate * 100).toFixed(2)}% vs baseline 0%`
    );
  }

  // Compare P95 latency
  if (stable.p95Ms > 0) {
    const p95Increase = (canary.p95Ms - stable.p95Ms) / stable.p95Ms;
    if (p95Increase > p95Threshold) {
      findings.push(
        `P95 LATENCY: canary ${canary.p95Ms.toFixed(0)}ms vs baseline ${stable.p95Ms.toFixed(0)}ms (+${(p95Increase * 100).toFixed(0)}%)`
      );
    }
  }

  // Compare cache hit rate (regression alert only)
  if (stable.cacheHitRate > 0.1) {
    const cacheRatioDecrease = (stable.cacheHitRate - canary.cacheHitRate) / stable.cacheHitRate;
    if (cacheRatioDecrease > 0.2) {
      findings.push(
        `CACHE HIT RATE: canary ${(canary.cacheHitRate * 100).toFixed(1)}% vs baseline ${(stable.cacheHitRate * 100).toFixed(1)}% (-${(cacheRatioDecrease * 100).toFixed(0)}%)`
      );
    }
  }

  const report = {
    timestamp: new Date().toISOString(),
    stableVersion: env.STABLE_VERSION,
    canaryVersion: env.CANARY_VERSION,
    stable,
    canary,
    findings,
    status: findings.length === 0 ? "OK" : "DEGRADED",
  };

  console.log("Canary comparison result", JSON.stringify(report));

  if (findings.length > 0) {
    await sendAlert(env.ALERT_WEBHOOK, report);
  }
}
```

---

## Alert Payload and Rollback Hook

```typescript
// canary-monitor/src/alert.ts

interface ComparisonReport {
  timestamp: string;
  stableVersion: string;
  canaryVersion: string;
  stable: Record<string, number>;
  canary: Record<string, number>;
  findings: string[];
  status: string;
}

export async function sendAlert(webhookUrl: string, report: ComparisonReport): Promise<void> {
  const message = {
    text: `🚨 *Canary regression detected*: \`${report.canaryVersion}\` vs \`${report.stableVersion}\``,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Canary \`${report.canaryVersion}\` regression at ${report.timestamp}*\n` +
            report.findings.map((f) => `• ${f}`).join("\n"),
        },
      },
      {
        type: "section",
        fields: [
          { type: "mrkdwn", text: `*Canary requests*\n${report.canary.requestCount}` },
          { type: "mrkdwn", text: `*Canary error rate*\n${(report.canary.errorRate * 100).toFixed(2)}%` },
          { type: "mrkdwn", text: `*Canary P95*\n${report.canary.p95Ms.toFixed(0)}ms` },
          { type: "mrkdwn", text: `*Baseline P95*\n${report.stable.p95Ms.toFixed(0)}ms` },
        ],
      },
    ],
  };

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(message),
  });
}
```

```bash
# Automated rollback via Cloudflare API: remove canary route weight
# (called from a separate automation triggered by the alert)

curl -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/workers/routes/${CANARY_ROUTE_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{ "pattern": "api.example.com/canary/*", "script": null }'
```

---

## Anti-Patterns

**Comparing raw counts rather than rates.** If canary sees 5% of traffic and stable sees 95%, the canary's total error count will naturally be ~19x lower even if the canary has a higher error rate. Always normalise to rate = errors / requests.

**Starting comparison immediately after canary deployment.** With fewer than 100 requests, the canary error rate is statistically meaningless (one error = 10% if you have 10 requests). Enforce a `MIN_CANARY_REQUESTS` gate.

**Using a single metric for rollback decisions.** Error rate alone misses latency regressions. Latency alone misses correctness issues. Use a multi-signal composite decision.

**Alerting on temporary blips.** A single bad 1-minute window may be noise. Consider requiring 2 consecutive degraded windows before escalating to PagerDuty.

**Not tagging the version in Analytics Engine at ingestion time.** After the fact you cannot separate canary from stable events. Version tagging must be in the Worker from day one.

---

## Gotchas

- **Analytics Engine quantile functions (`quantileWeighted`) are approximate** (using t-digest). For P99 on small samples (< 1000 requests) the value may be unreliable. Use P95 as the primary latency signal during early canary phases.
- **`_sample_interval` weighting is mandatory** when your Worker uses Analytics Engine sampling. Forgetting it produces incorrect aggregates.
- **Analytics Engine has ~1 minute write-to-read latency.** Your cron monitor should look at data at least 2 minutes old to avoid querying a partially-written window.
- **`NOW()` in Analytics Engine SQL is UTC.** Ensure your `windowMinutes` calculation accounts for the lag above.
- **Cloudflare traffic weights for Workers** are set at the route level, not the Worker level. If you have multiple routes for the same Worker, each needs its own weight configuration.
- **Cache warming skew.** Immediately after canary deployment, the canary has a cold cache, which inflates its latency and lowers its cache hit rate. Apply a 5–10 minute warm-up window before comparing cache metrics.

---

## Verification

```bash
# 1. Generate canary traffic
for i in $(seq 1 200); do
  curl -s "https://api.example.workers.dev/test" > /dev/null
done

# 2. Query Analytics Engine to verify version tagging
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{ "query": "SELECT blob1 AS version, SUM(double5) AS requests FROM worker_request_metrics GROUP BY blob1 ORDER BY requests DESC LIMIT 10" }'
# Expect rows for both stable and canary versions

# 3. Trigger cron Worker manually
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
# Check logs for "Canary comparison result"

# 4. Inject synthetic errors to test alert path
# Temporarily set ERROR_INJECTION=true in canary env and rerun traffic
# Monitor alert webhook (Slack/PagerDuty) for degradation alert within 2 minutes
```

---

## Related

- `a-b-test-metrics.md` — statistical significance testing for feature flags
- `cloudflare-analytics-engine-custom-metrics.md` — Analytics Engine dataset design
- `cloudflare-analytics-engine-grafana-dashboard.md` — visualising version comparison in Grafana
- `deployment-event-tracking.md` — recording deploy events as metric annotations
- `slo-error-budget-workers-pages.md` — SLO context for acceptable degradation thresholds
- `feature-flag-impact-monitoring.md` — flag-level metric comparison (similar pattern)

---

## Sources

- [Cloudflare Analytics Engine SQL API](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/)
- [Cloudflare Workers Traffic Routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)
- [Google SRE Book — Canarying Releases](https://sre.google/workbook/canarying-releases/)
- [PagerDuty — Automated rollback integration](https://developer.pagerduty.com/docs/events-api-v2/trigger-events/)
