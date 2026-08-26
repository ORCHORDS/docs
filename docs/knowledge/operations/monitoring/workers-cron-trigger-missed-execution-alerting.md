# Workers Cron Trigger Missed Execution Alerting

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers cron trigger is configured to run every 5 minutes, but a platform incident,
a Worker exception that causes the isolate to terminate before updating a heartbeat, or
a misconfigured `compatibility_date` causes silent skip. No execution fires, no error
surfaces in the dashboard, and downstream data pipelines quietly stall. You need dead-man
alerting: if the expected heartbeat does not arrive within a grace window, fire an alert.

## Context

Workers cron triggers have no built-in missed-execution notification. The reliable pattern
is a *heartbeat write* at the start of each scheduled invocation that stores a timestamp in
KV. A separate monitoring Worker (or external synthetic probe) checks the age of that
heartbeat on a faster cadence and alerts if it exceeds `expected_interval + grace_period`.

For multi-cron scripts (several `[[triggers.crons]]` entries in one Worker), store a
separate heartbeat key per cron schedule, keyed by the cron expression or a stable label.

---

## 1. Heartbeat Write in the Cron Worker

```typescript
// src/index.ts
export interface Env {
  HEARTBEATS: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

// Stable label for each schedule — matches the cron expression or a friendly name
const CRON_LABEL = 'hourly-invoice-sync';

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const startMs = Date.now();

    // Write heartbeat immediately so a timeout/exception does not block it
    await env.HEARTBEATS.put(
      `heartbeat:${CRON_LABEL}`,
      JSON.stringify({
        scheduledTime: event.scheduledTime,
        recordedAt: startMs,
        cronLabel: CRON_LABEL,
      }),
      { expirationTtl: 3600 } // 1 hour TTL — cleans up automatically
    );

    try {
      await runInvoiceSync(env);

      const durationMs = Date.now() - startMs;
      env.ANALYTICS.writeDataPoint({
        blobs: [CRON_LABEL, 'success'],
        doubles: [durationMs, event.scheduledTime],
        indexes: [CRON_LABEL],
      });
    } catch (err) {
      const durationMs = Date.now() - startMs;
      env.ANALYTICS.writeDataPoint({
        blobs: [CRON_LABEL, 'error', String(err)],
        doubles: [durationMs, event.scheduledTime],
        indexes: [CRON_LABEL],
      });
      throw err; // re-throw so Cloudflare marks invocation failed
    }
  },
};

async function runInvoiceSync(_env: Env): Promise<void> {
  // ... business logic
}
```

## 2. Heartbeat Monitor Worker (Faster Cadence)

```typescript
// monitor/heartbeat-check.ts — cron: "*/2 * * * *" (every 2 minutes)
export interface Env {
  HEARTBEATS: KVNamespace;
  ALERT_WEBHOOK: string;
  ANALYTICS: AnalyticsEngineDataset;
}

interface CronConfig {
  label: string;
  expectedIntervalSeconds: number;
  gracePeriodSeconds: number;
}

const WATCHED_CRONS: CronConfig[] = [
  { label: 'hourly-invoice-sync',     expectedIntervalSeconds: 3600,  gracePeriodSeconds: 300 },
  { label: 'five-min-metrics-flush',  expectedIntervalSeconds: 300,   gracePeriodSeconds: 120 },
  { label: 'daily-report-generation', expectedIntervalSeconds: 86400, gracePeriodSeconds: 600 },
];

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const now = Date.now();

    for (const config of WATCHED_CRONS) {
      const raw = await env.HEARTBEATS.get(`heartbeat:${config.label}`);
      const maxAgeMs = (config.expectedIntervalSeconds + config.gracePeriodSeconds) * 1000;

      let isMissed = false;
      let ageMs = 0;

      if (!raw) {
        isMissed = true; // Key missing = never ran or TTL expired
        ageMs = maxAgeMs + 1;
      } else {
        const hb = JSON.parse(raw) as { recordedAt: number };
        ageMs = now - hb.recordedAt;
        isMissed = ageMs > maxAgeMs;
      }

      env.ANALYTICS.writeDataPoint({
        blobs: [config.label, isMissed ? 'missed' : 'ok'],
        doubles: [ageMs, isMissed ? 1 : 0],
        indexes: [config.label],
      });

      if (isMissed) {
        ctx.waitUntil(
          sendAlert(env.ALERT_WEBHOOK, config.label, ageMs, config.expectedIntervalSeconds)
        );
      }
    }
  },
};

async function sendAlert(
  webhook: string,
  label: string,
  ageMs: number,
  expectedS: number
): Promise<void> {
  await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `[missed-cron] ${label} last ran ${Math.round(ageMs / 1000)}s ago (expected every ${expectedS}s)`,
    }),
  });
}
```

## 3. Alert De-duplication with KV

```typescript
// Add to heartbeat-check.ts to avoid repeat alerts every 2 minutes
async function shouldAlert(env: Env, label: string): Promise<boolean> {
  const cooldownKey = `alert_sent:${label}`;
  const existing = await env.HEARTBEATS.get(cooldownKey);
  if (existing) return false; // already alerted in the last 30 minutes

  // Set cooldown for 30 minutes
  await env.HEARTBEATS.put(cooldownKey, '1', { expirationTtl: 1800 });
  return true;
}
```

## 4. Analytics Engine — Execution History Query

```sql
-- Last 24 hours of cron execution outcomes per label
SELECT
  blob1                                AS cron_label,
  blob2                                AS outcome,
  count()                              AS executions,
  quantileWeighted(0.95)(double1, _sample_interval) AS p95_duration_ms,
  MAX(double2)                         AS last_scheduled_time_ms
FROM cron_executions
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
GROUP BY blob1, blob2
ORDER BY blob1, blob2
```

```sql
-- Missed-execution events in the last 6 hours
SELECT
  blob1                AS cron_label,
  SUM(_sample_interval * double2) AS missed_count,
  MAX(double1)         AS max_age_ms
FROM cron_heartbeat_checks
WHERE timestamp >= NOW() - INTERVAL '6' HOUR
  AND double2 = 1
GROUP BY blob1
ORDER BY missed_count DESC
```

## 5. Wrangler Configuration for Multi-Cron Workers

```toml
# wrangler.toml
name = "my-cron-worker"
main = "src/index.ts"

[[triggers.crons]]
crons = ["0 * * * *", "*/5 * * * *", "0 6 * * *"]

[[kv_namespaces]]
binding = "HEARTBEATS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "cron_executions"
```

```typescript
// src/index.ts — multi-schedule variant
const CRON_LABELS: Record<string, string> = {
  '0 * * * *':  'hourly-invoice-sync',
  '*/5 * * * *': 'five-min-metrics-flush',
  '0 6 * * *':  'daily-report-generation',
};

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const label = CRON_LABELS[event.cron] ?? event.cron;
    await env.HEARTBEATS.put(
      `heartbeat:${label}`,
      JSON.stringify({ recordedAt: Date.now(), cron: event.cron }),
      { expirationTtl: 7200 }
    );
    // ... dispatch to handler
  },
};
```

## 6. External Dead-man Using Healthchecks.io (Optional)

```typescript
// For critical crons: ping an external dead-man service as a belt-and-suspenders check
// in case the monitoring Worker itself also misses its schedule during an incident.
async function pingDeadman(checkUrl: string): Promise<void> {
  try {
    await fetch(checkUrl, { method: 'HEAD', signal: AbortSignal.timeout(5000) });
  } catch {
    // Non-fatal — best effort
    console.warn('[deadman] ping failed; will retry next invocation');
  }
}
```

---

## Anti-patterns

- **Writing the heartbeat at the end of the handler**: if the business logic throws or times
  out before the heartbeat write, the monitor will fire even though the cron did execute
  (partially). Write the heartbeat first.
- **Using a single heartbeat key for all cron schedules on one Worker**: you cannot tell
  which schedule missed. Key by label or cron expression.
- **Setting the monitor cadence equal to the expected interval**: a monitor running every
  hour that checks the hourly cron will only detect a miss 1–2 hours later. Run the monitor
  at 2–5× the expected interval's resolution.
- **No alert de-duplication**: without a cooldown, a missed hourly job fires one alert per
  2-minute monitor cycle (30 alerts per hour). Use KV-backed cooldown keys.

## Gotchas

- `event.cron` returns the matching cron expression string (e.g., `"0 * * * *"`), not a
  schedule name. If two schedules share the same expression (rare), both match; use index
  position or a separate binding for disambiguation.
- KV write consistency is eventual; a heartbeat written in a Worker in one region may not
  be visible to a monitor Worker in another region for up to 60 seconds. Add at least 60s
  to the grace period to avoid false positives from replication lag.
- The 30-day minimum invocation guarantee for cron triggers only applies when the Worker
  script is actively deployed. Deploying a new version causes the schedule to resume from
  the next tick, which may appear as a missed execution during the deployment window.
- `expirationTtl` on KV must be at least 60 seconds; very short-interval crons (e.g.,
  every 1 minute) should set a TTL of at least 300s to absorb replication lag before expiry.

## Verification

```bash
# Check heartbeat freshness manually
wrangler kv:key get --namespace-id=<KV_ID> "heartbeat:hourly-invoice-sync"

# List all heartbeat keys
wrangler kv:key list --namespace-id=<KV_ID> --prefix "heartbeat:" | jq '.[].name'

# Query missed-execution count from Analytics Engine
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"SELECT blob1, SUM(_sample_interval*double2) AS missed FROM cron_heartbeat_checks WHERE timestamp >= NOW() - INTERVAL '\''1'\'' HOUR GROUP BY blob1"}'
```

## Related

- `durable-objects-alarm-heartbeat-monitoring.md`
- `durable-objects-alarm-miss-rate-monitoring.md`
- `cron-job-monitoring.md`
- `uptime-monitoring-workers-cron-synthetic.md`
- `workers-error-alerting-pagerduty-integration.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
