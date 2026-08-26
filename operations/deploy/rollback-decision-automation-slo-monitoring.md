# Rollback Decision Automation with SLO Monitoring

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

After a deployment, on-call engineers manually check dashboards for 15–30 minutes before declaring a deploy healthy. This creates two failure modes: (1) a bad deploy is detected late because no one is actively watching, and (2) engineers are burned out by mandatory post-deploy babysitting. The goal is a system that evaluates SLO health automatically after every deployment and triggers rollback without human intervention when error-budget burn exceeds a threshold — without generating false positives from normal traffic variation.

---

## Context

SLO-based rollback automation couples two disciplines: SLO burn-rate alerting (from the Google SRE workbook) and deployment lifecycle management. The standard multi-window burn-rate alert fires within 5 minutes for fast burns and 1 hour for slow burns. Deployment automation uses a tighter observation window — typically 2–10 minutes — because the goal is catching a clearly bad deploy, not a gradual degradation.

The critical design question is: **what signal is reliable enough to automate an irreversible (or hard-to-reverse) action?**

The recommended threshold for automated rollback is a burn rate ≥ 14.4× (the rate that exhausts a 30-day error budget in 50 minutes) sustained for at least 2 minutes. This is a narrow, high-confidence signal. Anything subtler should trigger an alert to humans rather than an automatic rollback.

Cloudflare-specific signals available for SLO evaluation:

- **Cloudflare Analytics Engine** — sub-minute custom metric ingestion from Workers; most appropriate for application-level SLOs.
- **Workers invocation errors** — available via the Cloudflare API (`/accounts/{id}/workers/analytics`); tracks 5xx responses from the Worker runtime.
- **R2 / D1 error rates** — available via the respective API analytics endpoints.
- **Workers Logpush** — JSON structured logs streamed to R2 or a third-party SIEM; useful for enriched failure analysis but adds latency relative to Analytics Engine.

---

## Component 1 — SLO Instrumentation in the Application Worker

Every request records its outcome in Analytics Engine. Keep instrumentation outside the critical path using `waitUntil`.

```typescript
// src/instrumented-handler.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  DEPLOY_VERSION: string;  // injected at deploy time via wrangler vars
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let statusCode = 200;
    let errorType = "";

    try {
      const response = await handleRequest(request, env);
      statusCode = response.status;
      return response;
    } catch (err) {
      statusCode = 500;
      errorType = (err as Error).message.slice(0, 64);
      return new Response("Internal Server Error", { status: 500 });
    } finally {
      const latencyMs = Date.now() - start;
      ctx.waitUntil(
        recordSLOEvent(env.ANALYTICS, {
          statusCode,
          latencyMs,
          errorType,
          deployVersion: env.DEPLOY_VERSION,
          path: new URL(request.url).pathname,
        }),
      );
    }
  },
};

async function recordSLOEvent(
  dataset: AnalyticsEngineDataset,
  data: {
    statusCode: number;
    latencyMs: number;
    errorType: string;
    deployVersion: string;
    path: string;
  },
): Promise<void> {
  dataset.writeDataPoint({
    blobs: [data.deployVersion, data.path, data.errorType],
    doubles: [data.statusCode, data.latencyMs, data.statusCode >= 500 ? 1 : 0],
    indexes: [data.deployVersion],
  });
}

async function handleRequest(_request: Request, _env: Env): Promise<Response> {
  // Application logic here
  return new Response("OK");
}
```

---

## Component 2 — SLO Evaluator Worker (Cron Trigger)

A dedicated Worker runs on a 1-minute cron, queries Analytics Engine for the current error rate, computes the burn rate against the SLO target, and triggers rollback if the threshold is exceeded.

```typescript
// src/slo-evaluator.ts
export interface EvaluatorEnv {
  ANALYTICS_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  DEPLOY_STATE: KVNamespace;   // tracks current deploy version + rollback state
  ROLLBACK_WEBHOOK: string;    // endpoint that triggers the actual rollback
  SLO_TARGET: string;          // e.g. "0.999" = 99.9% availability
  OBSERVATION_WINDOW_MIN: string;  // e.g. "5"
}

export default {
  async scheduled(_event: ScheduledEvent, env: EvaluatorEnv, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(evaluateSLO(env));
  },
};

async function evaluateSLO(env: EvaluatorEnv): Promise<void> {
  const windowMin = parseInt(env.OBSERVATION_WINDOW_MIN, 10);
  const sloTarget = parseFloat(env.SLO_TARGET);
  const errorBudgetRate = 1 - sloTarget;  // 0.001 for 99.9%

  // Check rollback guard — do not rollback again within 30 minutes
  const lastRollback = await env.DEPLOY_STATE.get("last-rollback-at");
  if (lastRollback) {
    const since = Date.now() - new Date(lastRollback).getTime();
    if (since < 30 * 60 * 1000) {
      console.log("Rollback guard active, skipping evaluation");
      return;
    }
  }

  const deployVersion = await env.DEPLOY_STATE.get("current-deploy-version");
  if (!deployVersion) return;

  const { requestCount, errorCount } = await queryAnalyticsEngine(
    env.CF_ACCOUNT_ID,
    env.ANALYTICS_API_TOKEN,
    deployVersion,
    windowMin,
  );

  if (requestCount < 100) {
    // Too few requests to make a statistically significant decision
    console.log(`Only ${requestCount} requests in window — skipping`);
    return;
  }

  const observedErrorRate = errorCount / requestCount;
  const burnRate = observedErrorRate / errorBudgetRate;

  console.log(JSON.stringify({
    deploy: deployVersion,
    window_min: windowMin,
    requests: requestCount,
    errors: errorCount,
    error_rate: observedErrorRate,
    burn_rate: burnRate,
  }));

  // Automated rollback threshold: 14.4× burn rate (exhausts 30d budget in 50 min)
  if (burnRate >= 14.4) {
    console.log(`CRITICAL burn rate ${burnRate.toFixed(1)}× — triggering automated rollback`);
    await triggerRollback(env, deployVersion, burnRate);
    return;
  }

  // Alert-only threshold: 6× burn rate (exhausts budget in 2 hours)
  if (burnRate >= 6) {
    console.log(`HIGH burn rate ${burnRate.toFixed(1)}× — alerting on-call`);
    await alertOncall(env, deployVersion, burnRate);
  }
}

async function queryAnalyticsEngine(
  accountId: string,
  apiToken: string,
  deployVersion: string,
  windowMin: number,
): Promise<{ requestCount: number; errorCount: number }> {
  const sql = `
    SELECT
      SUM(_sample_interval) AS total_requests,
      SUM(double3 * _sample_interval) AS total_errors
    FROM ANALYTICS_DATASET
    WHERE timestamp >= NOW() - INTERVAL '${windowMin}' MINUTE
      AND blob1 = '${deployVersion}'
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    },
  );

  const data = await resp.json<{ data: Array<{ total_requests: number; total_errors: number }> }>();
  const row = data.data[0];
  return {
    requestCount: row?.total_requests ?? 0,
    errorCount: row?.total_errors ?? 0,
  };
}

async function triggerRollback(
  env: EvaluatorEnv,
  deployVersion: string,
  burnRate: number,
): Promise<void> {
  // Record rollback time to prevent rapid re-rollback
  await env.DEPLOY_STATE.put("last-rollback-at", new Date().toISOString());
  await env.DEPLOY_STATE.put("rollback-reason", JSON.stringify({
    triggered_at: new Date().toISOString(),
    deploy_version: deployVersion,
    burn_rate: burnRate,
  }));

  await fetch(env.ROLLBACK_WEBHOOK, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "rollback",
      reason: `SLO burn rate ${burnRate.toFixed(1)}×`,
      deploy_version: deployVersion,
    }),
  });
}

async function alertOncall(
  env: EvaluatorEnv,
  deployVersion: string,
  burnRate: number,
): Promise<void> {
  await fetch(env.ROLLBACK_WEBHOOK, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "alert",
      severity: "high",
      message: `SLO burn rate ${burnRate.toFixed(1)}× for deploy ${deployVersion} — manual review required`,
    }),
  });
}
```

---

## Component 3 — Rollback Webhook Handler

The rollback webhook calls the Cloudflare API to redeploy the previous Worker version.

```typescript
// src/rollback-handler.ts
export interface RollbackEnv {
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  WORKER_NAME: string;
  DEPLOY_STATE: KVNamespace;
  ROLLBACK_AUTH_SECRET: string;
}

export default {
  async fetch(request: Request, env: RollbackEnv): Promise<Response> {
    if (request.headers.get("X-Rollback-Secret") !== env.ROLLBACK_AUTH_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const body = await request.json<{ action: string; deploy_version: string }>();
    if (body.action !== "rollback") {
      return new Response("Not a rollback action", { status: 200 });
    }

    const previousVersion = await env.DEPLOY_STATE.get("previous-deploy-version");
    if (!previousVersion) {
      return new Response("No previous version available", { status: 409 });
    }

    // Use Workers Versions API to activate the previous version with 100% traffic
    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/workers/scripts/${env.WORKER_NAME}/versions/${previousVersion}/activate`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ traffic_percentage: 100 }),
      },
    );

    const result = await resp.json();
    console.log("Rollback result:", JSON.stringify(result));
    return Response.json({ status: "rolled-back", version: previousVersion });
  },
};
```

---

## Component 4 — Deploy Lifecycle Integration

Update `DEPLOY_STATE` KV on every deploy so the evaluator knows the current version and can roll back to the previous one.

```bash
# deploy.sh — called from CI after wrangler deploy completes
PREV_VERSION=$(wrangler versions list --env production --json | jq -r '.[1].id')
CURR_VERSION=$(wrangler versions list --env production --json | jq -r '.[0].id')

# Store in KV for the SLO evaluator
wrangler kv key put "previous-deploy-version" "$PREV_VERSION" \
  --namespace-id "$KV_NAMESPACE_ID" --env production

wrangler kv key put "current-deploy-version" "$CURR_VERSION" \
  --namespace-id "$KV_NAMESPACE_ID" --env production

echo "Deployed $CURR_VERSION (previous: $PREV_VERSION)"
```

---

## Anti-patterns

- **Rolling back on a single minute of bad data**: one bad data point during a traffic spike can spike error rates transiently. Require the burn rate to be high for at least two consecutive evaluation cycles before triggering rollback.
- **Automated rollback during a known incident**: if infrastructure beneath the Worker is down (D1, R2, external API), a rollback will not help. Gate automated rollback on a Worker-level signal (5xx from the Worker), not a dependency-level signal.
- **Evaluating error rate before traffic ramps**: a new deployment receiving its first few requests will have high variance in error rate. Require a minimum request count (e.g. 100 requests) before triggering any rollback logic.
- **Using time-of-day traffic patterns without adjustment**: error *rate* is the right metric, not error *count*. A deployment at 3 AM with 10 requests and 2 errors (20% error rate) should trigger rollback; a deployment at noon with 10,000 requests and 2 errors (0.02% error rate) should not.

---

## Gotchas

- Analytics Engine has a write-to-read latency of approximately 30–60 seconds. Your observation window must be at least 2 minutes wide to include a complete picture.
- Analytics Engine SQL uses `_sample_interval` weighting for sampled datasets. Always multiply counts by `_sample_interval` to get true totals.
- The Workers Versions "activate" API endpoint requires `workers:write` scope on the API token. The SLO evaluator only needs `analytics:read` — separate the tokens by function.
- KV is eventually consistent; do not use it for strict mutual exclusion between two simultaneously firing evaluator instances. Use a Durable Object or Alarm API if you need hard guarantees on a single rollback firing.
- A rollback does not automatically fix the defect in the code — it buys time. Ensure the rollback triggers a PagerDuty/Opsgenie alert so engineers investigate the cause rather than treating the rollback as resolution.

---

## Verification

```bash
# Inject test errors to validate the burn-rate evaluator fires
# (Use a feature flag to enable an error injection path in staging)
for i in $(seq 1 200); do
  curl -sf "https://api.staging.example.com/error-inject" &
done

# Wait 2 minutes, then check evaluator logs
wrangler tail slo-evaluator --env staging --format json \
  | jq 'select(.logs[].message | contains("burn_rate"))'

# Confirm rollback handler was called
wrangler kv key get "rollback-reason" --namespace-id $KV_NS_ID --env staging | jq .
```

---

## Related

- `slo-alerting-thresholds.md`
- `progressive-canary-deployment-rollback.md`
- `rollback-runbook.md`
- `cloudflare-analytics-engine-deploy-observability.md`
- `live-revision-verification-and-rollback-evidence.md`

---

## Sources

- Google SRE Workbook — Alerting on SLOs (sre.google/workbook/alerting-on-slos)
- Cloudflare Analytics Engine — SQL API (developers.cloudflare.com/analytics/analytics-engine/sql-api)
- Cloudflare Workers Versions API — activate endpoint (developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions)
- Cloudflare Workers — Cron Triggers (developers.cloudflare.com/workers/configuration/cron-triggers)
- "The Burn Rate Alerting Paradigm" — Alex Hidalgo, Increment magazine
