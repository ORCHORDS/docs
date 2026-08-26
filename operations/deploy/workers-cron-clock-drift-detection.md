# Workers Cron Trigger Clock Drift Detection

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A scheduled Worker is configured with `crons = ["*/5 * * * *"]` (every 5 minutes)
but Cloudflare Analytics Engine shows gaps of 8–12 minutes between invocations.
The gap is non-deterministic and does not consistently map to any deployment event.
Alerting thresholds built on "missed run = 0 events in 5 min window" fire too
frequently and lose signal, while "missed run = 0 events in 10 min window" misses
real failures.

A second variant: a batch job that processes time-windowed data using
`Date.now()` to compute its window start/end drifts over weeks because each
invocation is slightly late, causing the window to creep and occasionally double-
or triple-count events near boundaries.

## Context

Cloudflare cron triggers are **best-effort**, not hard-real-time. The platform
guarantees that a cron trigger will eventually fire, but it does not guarantee it
will fire at exactly the scheduled instant. Under normal conditions jitter is
< 30 seconds. Under platform maintenance, high global load, or after a Worker
deployment (which briefly suspends the trigger), jitter can exceed several minutes.

example project uses cron Workers for:
- Hourly billing aggregation (`0 * * * *`)
- 5-minute metric rollup (`*/5 * * * *`)
- Daily D1 vacuum and stats collection (`0 2 * * *`)

Drift detection must distinguish between:
1. **Acceptable jitter** — trigger fired late but within tolerance
2. **Skipped invocation** — trigger missed entirely and should not fire again until
   the next scheduled slot
3. **Clock drift accumulation** — each invocation is a few seconds late and the
   cumulative error compounds over days

---

## Section 1 — Measuring Invocation Skew with KV Timestamps

```typescript
// workers/cron-drift-detector.ts
import type { Env } from '../types';

const CRON_SCHEDULES: Record<string, number> = {
  'billing-aggregator': 3600,       // every 3600s
  'metric-rollup': 300,             // every 300s
  'db-vacuum': 86400,               // every 86400s
};

export async function recordInvocationAndMeasureDrift(
  cronName: string,
  env: Env,
): Promise<{ skewMs: number; skippedSlots: number }> {
  const now = Date.now();
  const key = `cron:last-invocation:${cronName}`;
  const raw = await env.CRON_STATE.get(key);

  let skewMs = 0;
  let skippedSlots = 0;

  if (raw !== null) {
    const last = parseInt(raw, 10);
    const intervalMs = CRON_SCHEDULES[cronName] * 1_000;
    const elapsed = now - last;
    skippedSlots = Math.max(0, Math.floor(elapsed / intervalMs) - 1);
    // Skew is the delta from the nearest expected fire time
    const expectedFire = last + intervalMs * (skippedSlots + 1);
    skewMs = now - expectedFire;
  }

  await env.CRON_STATE.put(key, String(now), { expirationTtl: 604800 });
  return { skewMs, skippedSlots };
}
```

## Section 2 — Emitting Drift Metrics to Analytics Engine

```typescript
// workers/scheduled-handler.ts
import type { Env, ExecutionContext } from '../types';
import { recordInvocationAndMeasureDrift } from './cron-drift-detector';

export default {
  async scheduled(
    event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    const cronName = resolveCronName(event.cron);
    const { skewMs, skippedSlots } = await recordInvocationAndMeasureDrift(
      cronName,
      env,
    );

    // Write to Analytics Engine for dashboards and alerting
    env.ANALYTICS.writeDataPoint({
      blobs: [cronName, event.cron],
      doubles: [skewMs, skippedSlots],
      indexes: [cronName],
    });

    if (skippedSlots > 0) {
      console.error(
        `[DRIFT] ${cronName} skipped ${skippedSlots} slot(s). Skew: ${skewMs}ms`,
      );
    } else if (Math.abs(skewMs) > 60_000) {
      console.warn(
        `[DRIFT] ${cronName} jitter ${skewMs}ms exceeds 60s threshold`,
      );
    }

    // Skip processing if we are too late and the next slot is imminent
    const intervalMs = getIntervalMs(cronName);
    if (intervalMs > 0 && skewMs > intervalMs * 0.8) {
      console.warn(`[DRIFT] ${cronName} skipping work — arrived too close to next slot`);
      return;
    }

    await runCronWork(cronName, env, ctx);
  },
};

function resolveCronName(cron: string): string {
  const map: Record<string, string> = {
    '0 * * * *': 'billing-aggregator',
    '*/5 * * * *': 'metric-rollup',
    '0 2 * * *': 'db-vacuum',
  };
  return map[cron] ?? 'unknown';
}

function getIntervalMs(cronName: string): number {
  const intervals: Record<string, number> = {
    'billing-aggregator': 3_600_000,
    'metric-rollup': 300_000,
    'db-vacuum': 86_400_000,
  };
  return intervals[cronName] ?? 0;
}

async function runCronWork(
  cronName: string,
  env: Env,
  ctx: ExecutionContext,
): Promise<void> {
  // dispatch to the actual handler — omitted for brevity
}
```

## Section 3 — Anchored Time Windows to Prevent Drift Accumulation

Instead of computing windows relative to `Date.now()`, anchor them to the
scheduled cron slot. The `event.scheduledTime` property contains the intended fire
time (Unix ms), which is stable and does not drift.

```typescript
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // Use scheduledTime, NOT Date.now(), for window computation
    const windowEndMs = event.scheduledTime;
    const intervalMs = 5 * 60 * 1_000; // for */5 cron
    const windowStartMs = windowEndMs - intervalMs;

    // This window is always exactly [T-5min, T] for the nominal schedule —
    // it does not drift even if the Worker fires 90 seconds late.
    const { results } = await env.DB.prepare(
      `SELECT * FROM events
        WHERE created_at >= ? AND created_at < ?`,
    )
      .bind(
        Math.floor(windowStartMs / 1_000),
        Math.floor(windowEndMs / 1_000),
      )
      .all();

    await processEvents(results, env);
  },
};
```

## Section 4 — GitHub Actions Drift Audit

Periodically query the Analytics Engine from CI to detect chronic drift.

```typescript
// scripts/audit-cron-drift.ts
import { execSync } from 'child_process';

interface DriftRow {
  double0: number; // skewMs
  double1: number; // skippedSlots
  blob0: string;   // cronName
}

async function auditDrift(): Promise<void> {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const apiToken = process.env.CF_API_TOKEN!;
  const now = Date.now();
  const oneDayAgo = now - 86_400_000;

  const query = `
    SELECT blob0 AS cron_name,
           AVG(double0) AS avg_skew_ms,
           MAX(double0) AS max_skew_ms,
           SUM(double1) AS total_skipped
      FROM cron_drift_metrics
     WHERE timestamp > toDateTime(${Math.floor(oneDayAgo / 1000)})
     GROUP BY cron_name
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    },
  );

  const data = (await res.json()) as { data: DriftRow[] };
  let failed = false;

  for (const row of data.data) {
    const avgSkewSec = Math.abs(row.double0) / 1_000;
    console.log(
      `${row.blob0}: avg_skew=${avgSkewSec.toFixed(1)}s  ` +
      `max_skew=${(row.double0 / 1000).toFixed(1)}s  ` +
      `skipped=${row.double1}`,
    );
    if (avgSkewSec > 120) {
      console.error(`FAIL: ${row.blob0} average drift exceeds 120s threshold`);
      failed = true;
    }
    if (row.double1 > 5) {
      console.error(`FAIL: ${row.blob0} skipped more than 5 invocations in 24h`);
      failed = true;
    }
  }

  if (failed) process.exit(1);
}

auditDrift().catch((err) => { console.error(err); process.exit(1); });
```

## Section 5 — Wrangler Configuration for Cron Triggers

```toml
# wrangler.toml
[[triggers]]
crons = ["*/5 * * * *", "0 * * * *", "0 2 * * *"]

# KV namespace for storing last-invocation timestamps
[[kv_namespaces]]
binding = "CRON_STATE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Analytics Engine dataset for drift metrics
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "cron_drift_metrics"
```

## Anti-patterns

- **Using `Date.now()` as the window anchor** — causes drift accumulation where
  late invocations shift the window, double-counting or missing events near
  boundaries.
- **Alerting on a fixed absolute window** — `"no events in 5 min"` fires during
  acceptable platform jitter. Use `skippedSlots > 0` (derived from the expected
  schedule interval) as the alert signal instead.
- **Re-running skipped slot work** — when a slot is skipped, doing double work in
  the next invocation (to catch up) often causes contention on D1 and
  downstream services. Mark the slot as skipped and let the next cycle handle its
  own window only.
- **Setting a very short KV TTL for invocation state** — if the KV record expires
  before the next invocation, the skew measurement resets silently, hiding chronic
  drift.

## Gotchas

- `event.scheduledTime` is available in the `scheduled` handler but **not** in
  `fetch` — you cannot access it from an HTTP trigger shim used for local testing.
  Use `Date.now()` as a fallback in development.
- Cloudflare guarantees that `scheduledTime` reflects the *intended* fire time, not
  actual. If a deployment causes a 10-minute delay, `scheduledTime` still shows
  when it *should* have fired.
- Workers deployed via `wrangler deploy` temporarily suspend cron triggers while
  the new version propagates. This is expected and typically causes a single late
  invocation — not a bug.
- Analytics Engine data points have eventual consistency with a typical delay of
  ~60 seconds before they appear in SQL queries. Do not use AE for real-time
  alerting; use it for retrospective drift audits.
- The `CRON_STATE` KV namespace should use a separate namespace from production
  data KV to avoid accidental eviction by TTL-heavy workloads.

## Verification

```bash
# List recent cron invocations from the Cloudflare API
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/example project-cron/schedules" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result'

# Tail live cron logs with wrangler
npx wrangler tail example project-cron --env production --format pretty

# Query Analytics Engine for drift summary (last 24h)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT blob0, AVG(double0) AS avg_skew FROM cron_drift_metrics WHERE timestamp > now() - INTERVAL '\''1'\'' DAY GROUP BY blob0"}' \
  | jq '.data'
```

## Related

- `workers-cron-trigger-deployment-management.md`
- `wrangler-tail-logs-deployment-verification.md`
- `deployment-health-gates-automated-rollback.md`
- `slo-alerting-thresholds.md`
- `post-deploy-monitoring-checklist.md`

## Sources

- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- ScheduledEvent API: https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare KV: https://developers.cloudflare.com/kv/
