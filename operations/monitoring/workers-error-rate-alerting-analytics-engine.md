# Real-Time Error Rate Alerting via Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to detect when a Worker's HTTP error rate spikes above an acceptable threshold and receive a PagerDuty alert within minutes — not on the next day's dashboard review. You also need the alert to auto-resolve when the error rate returns to normal, preventing stale incidents from cluttering the on-call queue.

---

## Context

Every Worker response writes a data point to Analytics Engine with `double1` set to `1` for error responses (status >= 500) and `0` for success. A separate Cron Trigger Worker queries the Analytics Engine SQL API every five minutes, computing the average of `double1` over the trailing five-minute window — which equals the error rate as a fraction. The threshold is stored in KV so it can be updated without a Worker redeploy. When the error rate exceeds the threshold the Worker fires a PagerDuty Events API v2 trigger and stores the open incident key in KV; when the rate drops below threshold it resolves the incident by sending a resolve event using the stored key.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "error-rate-alerter"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[triggers]
crons = ["*/5 * * * *"]  # Every 5 minutes

[[analytics_engine_datasets]]
binding = "METRICS"
dataset = "worker_metrics"

[[kv_namespaces]]
binding = "CONFIG"
id = "<your-kv-namespace-id>"

[vars]
CF_ACCOUNT_ID       = "<your-cloudflare-account-id>"
MONITORED_WORKER    = "my-api-worker"
# PagerDuty routing key — store as a secret in production
PAGERDUTY_ROUTING_KEY = "<your-pd-routing-key>"
```

```
# KV keys used at runtime (set via wrangler kv:key put or API)
# CONFIG:error_rate_threshold  →  "0.05"   (5% error rate)
# CONFIG:pd_incident_key       →  ""        (cleared when no open incident)
# CONFIG:cf_api_token          →  "<token>" (Analytics Engine read token)
```

---

## Section 2 — Worker implementation (metrics writer + alert checker)

```typescript
// src/index.ts
export interface Env {
  METRICS: AnalyticsEngineDataset;
  CONFIG: KVNamespace;
  CF_ACCOUNT_ID: string;
  MONITORED_WORKER: string;
  PAGERDUTY_ROUTING_KEY: string;
}

// --- Metrics writer: call from your primary API worker ---
// Import and instantiate in the API worker that you want to monitor:
//
// import { recordMetric } from "./metrics";
// recordMetric(env.METRICS, request, response);
//
// This function is included here for reference; in a real setup it lives
// in the monitored Worker, not in the alerter Worker.
export function recordMetric(
  dataset: AnalyticsEngineDataset,
  request: Request,
  response: Response
): void {
  const isError = response.status >= 500 ? 1 : 0;
  const path = new URL(request.url).pathname;

  dataset.writeDataPoint({
    blobs: [
      path,                    // blob1 — URL path for per-route breakdown
      request.method,          // blob2
      String(response.status), // blob3 — status as string for grouping
    ],
    doubles: [
      isError,                 // double1 — 1=error, 0=success
      response.status,         // double2 — numeric status
    ],
    indexes: [path],           // shard by path for efficient per-route queries
  });
}

// --- Alert checker: runs on cron ---

async function queryErrorRate(
  accountId: string,
  dataset: string,
  apiToken: string,
  workerName: string,
  windowMinutes: number
): Promise<number> {
  // Analytics Engine SQL uses timestamp as a special column
  const sql = `
    SELECT AVG(double1) AS error_rate
    FROM ${dataset}
    WHERE timestamp > NOW() - INTERVAL '${windowMinutes}' MINUTE
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!response.ok) {
    throw new Error(`Analytics Engine query failed: ${response.status}`);
  }

  const data = await response.json<{ data: { error_rate: number | null }[] }>();
  return data.data[0]?.error_rate ?? 0;
}

async function triggerPagerDuty(
  routingKey: string,
  workerName: string,
  errorRate: number,
  threshold: number
): Promise<string> {
  const dedupKey = `error-rate-${workerName}`;

  const body = {
    routing_key: routingKey,
    event_action: "trigger",
    dedup_key: dedupKey,
    payload: {
      summary: `Worker ${workerName} error rate ${(errorRate * 100).toFixed(2)}% exceeds threshold ${(threshold * 100).toFixed(2)}%`,
      severity: "critical",
      source: workerName,
      custom_details: {
        error_rate: errorRate,
        threshold: threshold,
        worker: workerName,
      },
    },
  };

  const response = await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`PagerDuty trigger failed: ${response.status} ${await response.text()}`);
  }

  const data = await response.json<{ dedup_key: string }>();
  return data.dedup_key;
}

async function resolvePagerDuty(
  routingKey: string,
  incidentKey: string
): Promise<void> {
  const body = {
    routing_key: routingKey,
    event_action: "resolve",
    dedup_key: incidentKey,
  };

  const response = await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`PagerDuty resolve failed: ${response.status} ${await response.text()}`);
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Read config from KV
    const [thresholdStr, existingIncidentKey, apiToken] = await Promise.all([
      env.CONFIG.get("error_rate_threshold"),
      env.CONFIG.get("pd_incident_key"),
      env.CONFIG.get("cf_api_token"),
    ]);

    const threshold = parseFloat(thresholdStr ?? "0.05");

    if (!apiToken) {
      throw new Error("CONFIG:cf_api_token KV key not set — cannot query Analytics Engine");
    }

    const errorRate = await queryErrorRate(
      env.CF_ACCOUNT_ID,
      "worker_metrics",
      apiToken,
      env.MONITORED_WORKER,
      5 // trailing 5-minute window
    );

    console.log(`Error rate: ${(errorRate * 100).toFixed(2)}%, threshold: ${(threshold * 100).toFixed(2)}%`);

    if (errorRate >= threshold) {
      // Trigger alert (PagerDuty dedup_key prevents duplicate incidents)
      const incidentKey = await triggerPagerDuty(
        env.PAGERDUTY_ROUTING_KEY,
        env.MONITORED_WORKER,
        errorRate,
        threshold
      );
      // Persist incident key so we can resolve it later
      await env.CONFIG.put("pd_incident_key", incidentKey, {
        expirationTtl: 86400, // auto-expire after 24 h as a safety net
      });
      console.log(`PagerDuty incident triggered: ${incidentKey}`);
    } else if (existingIncidentKey) {
      // Error rate is back below threshold — auto-resolve
      await resolvePagerDuty(env.PAGERDUTY_ROUTING_KEY, existingIncidentKey);
      await env.CONFIG.delete("pd_incident_key");
      console.log(`PagerDuty incident resolved: ${existingIncidentKey}`);
    }
  },
};
```

---

## Section 3 — Updating the threshold without a redeploy

```bash
# Raise the alert threshold to 10%
npx wrangler kv:key put --binding=CONFIG error_rate_threshold "0.10"

# Lower it back to 2%
npx wrangler kv:key put --binding=CONFIG error_rate_threshold "0.02"

# Read the current value
npx wrangler kv:key get --binding=CONFIG error_rate_threshold
```

---

## Anti-patterns

- **Using `double1 = 1` for all non-2xx responses** — A 404 is typically a client error, not a service failure. Consider alerting only on 5xx status codes (`response.status >= 500`) to avoid alert fatigue from bad client requests.
- **Storing the PagerDuty routing key in `[vars]`** — It appears in plaintext in `wrangler.toml`. Store it with `wrangler secret put PAGERDUTY_ROUTING_KEY` and remove the `[vars]` entry.
- **Not using dedup_key in PagerDuty** — Without `dedup_key`, every 5-minute cron run above threshold creates a new incident. The `dedup_key` ensures all repeat triggers coalesce into the same open incident.
- **Querying Analytics Engine with a window shorter than the ingestion delay** — Analytics Engine data may be up to 60 seconds behind. A 1-minute query window can return zero rows even during active traffic. Use at least a 5-minute window.

---

## Gotchas

- The `NOW()` function in Analytics Engine SQL refers to query execution time, not ingestion time. The `timestamp` column reflects ingestion time. Use `WHERE timestamp > NOW() - INTERVAL '5' MINUTE` for a trailing window.
- PagerDuty Events API v2 `dedup_key` must be consistent between the trigger and resolve calls. Using a static string derived from the Worker name (`error-rate-{workerName}`) guarantees this.
- KV `expirationTtl` on the incident key is a safety net in case the cron Worker fails repeatedly before the error rate recovers. Without it, a stale key could block future auto-resolves.
- `AVG(double1)` returns `null` when there are no data points in the window (e.g., zero traffic). Treat `null` as `0` — no traffic means no errors.
- The Analytics Engine free tier has a query rate limit. At one query per 5 minutes this Worker uses 288 queries/day, well within typical limits.

---

## Verification

```bash
# 1. Set required KV values
npx wrangler kv:key put --binding=CONFIG error_rate_threshold "0.05"
npx wrangler kv:key put --binding=CONFIG cf_api_token "<your-read-only-ae-token>"

# 2. Deploy the worker
npx wrangler deploy

# 3. Force a spike by making your primary worker return 500s (e.g., via a feature flag)
# Wait 5 minutes for the cron to fire, then check your PagerDuty incidents.

# 4. Manually trigger the cron to test immediately
npx wrangler trigger scheduled --name error-rate-alerter --cron "*/5 * * * *"

# 5. Confirm KV stores the incident key after a trigger
npx wrangler kv:key get --binding=CONFIG pd_incident_key

# 6. Restore your primary worker to healthy state, wait/trigger another cron,
# and confirm PagerDuty resolves the incident and KV key is deleted.
npx wrangler kv:key get --binding=CONFIG pd_incident_key  # should be empty
```

---

## Related

- `workers-request-tracing-analytics-engine.md`
- `workers-cpu-time-monitoring-tail-workers.md`
- `queue-consumer-lag-monitoring-d1-workers.md`

---

## Sources

- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- PagerDuty Events API v2 — https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty
- Workers KV — https://developers.cloudflare.com/kv/api/
- Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
