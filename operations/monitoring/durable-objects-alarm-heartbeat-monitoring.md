# Durable Objects Alarm-Based Heartbeat Monitoring

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A background job inside a Durable Object stops making progress silently — no error surfaces, no exception is thrown, and the regular HTTP health-check endpoint never fires because there is no incoming request to trigger it. The DO is alive at the platform level but functionally dead. You need a dead-man's switch that fires an alert whenever the object fails to renew its own heartbeat within a known SLO window.

---

## Context

Durable Objects expose a single-alarm primitive: `this.ctx.storage.setAlarm(timestampMs)`. Only one alarm can be queued per object at a time; setting a new one replaces the previous. When the scheduled time elapses, the runtime calls `alarm()` on the object's class. If the object crashes or its alarm handler throws, the platform retries with exponential back-off up to a platform-defined ceiling before giving up.

The alarm primitive is commonly used for timeouts and scheduling. A lesser-known pattern is to treat it as a heartbeat lease: the object sets an alarm `N` seconds in the future at the end of each successful work cycle. If work stops for any reason — runaway await, infinite loop, eviction without reconnect — the next alarm fires and the handler can emit a metric, write to Analytics Engine, or call an external webhook signalling the stall.

Alarm handler execution is billed like any other DO request. A 60-second heartbeat on an idle object costs roughly $0.0000002 per invocation at current pricing — negligible.

---

## Section 1: Basic Heartbeat DO Pattern

```typescript
// heartbeat-do.ts
import { DurableObject } from "cloudflare:workers";

export interface Env {
  HEARTBEAT_DO: DurableObjectNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

const HEARTBEAT_INTERVAL_MS = 60_000; // 1 minute
const STALE_THRESHOLD_MS   = 90_000; // alert if > 1.5× interval missed

export class HeartbeatDO extends DurableObject {
  private lastBeat: number = 0;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Restore persisted lastBeat across evictions
    this.ctx.blockConcurrencyWhile(async () => {
      this.lastBeat = (await this.ctx.storage.get<number>("lastBeat")) ?? 0;
    });
  }

  // Called by the Worker to start or renew heartbeat monitoring
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/start") {
      await this.renewLease();
      return new Response("started", { status: 200 });
    }
    if (url.pathname === "/status") {
      const age = Date.now() - this.lastBeat;
      return Response.json({ lastBeat: this.lastBeat, ageMs: age });
    }
    return new Response("not found", { status: 404 });
  }

  // Called by the actual work loop at the end of each cycle
  async beat(): Promise<void> {
    this.lastBeat = Date.now();
    await this.ctx.storage.put("lastBeat", this.lastBeat);
    await this.renewLease();
  }

  // Alarm fires if beat() is not called within HEARTBEAT_INTERVAL_MS
  async alarm(): Promise<void> {
    const age = Date.now() - this.lastBeat;
    if (age >= STALE_THRESHOLD_MS) {
      await this.emitStaleAlert(age);
    }
    // Re-arm the alarm so alerts continue until the heartbeat resumes
    await this.renewLease();
  }

  private async renewLease(): Promise<void> {
    await this.ctx.storage.setAlarm(Date.now() + HEARTBEAT_INTERVAL_MS);
  }

  private async emitStaleAlert(ageMs: number): Promise<void> {
    const env = this.env as Env;
    env.ANALYTICS.writeDataPoint({
      blobs:   ["heartbeat_stale", this.ctx.id.toString()],
      doubles: [ageMs],
      indexes: ["heartbeat_stale"],
    });
    console.error(JSON.stringify({
      event:   "heartbeat_stale",
      doId:    this.ctx.id.toString(),
      ageMs,
      ts:      new Date().toISOString(),
    }));
  }
}
```

---

## Section 2: Registering a Named Heartbeat per Job

For long-running pipeline stages, use a named DO per job so alerts carry a meaningful identifier.

```typescript
// worker-entrypoint.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const jobId = new URL(request.url).searchParams.get("job") ?? "default";

    // Stable DO identity per job name
    const id   = env.HEARTBEAT_DO.idFromName(jobId);
    const stub = env.HEARTBEAT_DO.get(id);

    // Start monitoring on first call; subsequent calls just renew
    await stub.fetch("https://internal/start");
    return new Response(`Heartbeat armed for job=${jobId}`);
  },
};
```

From inside the job DO, signal successful cycles:

```typescript
// Inside the actual job Durable Object
async runCycle(): Promise<void> {
  await this.doWork();  // your business logic

  // Notify the heartbeat DO that we are alive
  const hbId   = this.env.HEARTBEAT_DO.idFromName(this.jobName);
  const hbStub = this.env.HEARTBEAT_DO.get(hbId);
  // Use RPC if available; fall back to fetch
  await hbStub.fetch("https://internal/beat", { method: "POST" });
}
```

---

## Section 3: Wiring the Alarm Alert to an External Webhook

The `emitStaleAlert` method in Section 1 writes to Analytics Engine. For immediate PagerDuty/Slack notification, add a `fetch` call inside the alarm handler.

```typescript
private async emitStaleAlert(ageMs: number): Promise<void> {
  const env = this.env as Env & { ALERT_WEBHOOK_URL: string };

  // Fire-and-forget; if this fetch fails the platform will retry alarm()
  await fetch(env.ALERT_WEBHOOK_URL, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      summary:  `Heartbeat stale for DO ${this.ctx.id.toString()}`,
      severity: "critical",
      ageMs,
      timestamp: new Date().toISOString(),
    }),
  });
}
```

Configure `ALERT_WEBHOOK_URL` as a secret in `wrangler.toml`:

```toml
[vars]
# non-secret placeholder — override with `wrangler secret put`

[[durable_objects.bindings]]
name    = "HEARTBEAT_DO"
class_name = "HeartbeatDO"
```

```bash
wrangler secret put ALERT_WEBHOOK_URL
```

---

## Section 4: Analytics Engine Query for Stale Heartbeats

Query all stale events in the last hour using the Analytics Engine SQL API:

```sql
SELECT
  blob1                          AS event_type,
  blob2                          AS do_id,
  double1                        AS age_ms,
  toDateTime(timestamp)          AS fired_at
FROM   ANALYTICS_ENGINE_DATASET
WHERE  index1 = 'heartbeat_stale'
  AND  timestamp > now() - INTERVAL '1' HOUR
ORDER  BY fired_at DESC
LIMIT  50
```

Call via the REST endpoint:

```typescript
const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
  {
    method:  "POST",
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query: SQL }),
  }
);
const { data } = await res.json();
```

---

## Section 5: Grafana Panel for Heartbeat Health

In Grafana, point the Cloudflare Analytics Engine data source at the query above and configure a **Stat** panel showing the count of stale events in the last 5 minutes. Threshold: `0 = green`, `≥1 = red`. Attach a Grafana alert rule with no-data state `OK` (silence when the job is intentionally stopped) and fire-when-non-zero state `Alerting`.

```yaml
# grafana/provisioning/alerts/heartbeat.yaml
apiVersion: 1
groups:
  - name: heartbeat
    folder: Workers
    interval: 1m
    rules:
      - uid: do-heartbeat-stale
        title: "DO Heartbeat Stale"
        condition: C
        data:
          - refId: A
            datasourceUid: cloudflare-ae
            model:
              rawSql: |
                SELECT count() AS cnt
                FROM   ANALYTICS_ENGINE_DATASET
                WHERE  index1 = 'heartbeat_stale'
                  AND  timestamp > now() - INTERVAL '5' MINUTE
          - refId: C
            datasourceUid: __expr__
            model:
              type: threshold
              conditions:
                - evaluator: { type: gt, params: [0] }
                  query:     { params: [A] }
        noDataState: OK
        execErrState: Alerting
```

---

## Section 6: Cancelling the Heartbeat Cleanly

When a job finishes intentionally, cancel the alarm to avoid spurious alerts:

```typescript
async stop(): Promise<void> {
  await this.ctx.storage.deleteAlarm();
  await this.ctx.storage.delete("lastBeat");
  console.log(JSON.stringify({ event: "heartbeat_stopped", doId: this.ctx.id.toString() }));
}
```

Expose this via a `/stop` route on the HeartbeatDO and call it from the job's teardown path.

---

## Anti-patterns

- **Setting the alarm inside `alarm()` before emitting the alert** — if the alert fetch throws, the alarm is already re-armed with no retry on the alert itself. Emit first, then re-arm.
- **Using wall-clock Date.now() for the threshold without accounting for DO eviction time** — a DO evicted for inactivity reloads `lastBeat` from storage correctly only if `blockConcurrencyWhile` is used in the constructor. Without it, `lastBeat` can reset to 0 on cold start, generating false stale alerts.
- **Single global DO for all jobs** — contention on the single-alarm slot means the last `setAlarm` call wins. Use one DO per logical job.
- **Expecting sub-second alarm precision** — the platform guarantees delivery within seconds of the scheduled time but not exactly on it. Design thresholds with at least 1.5× the nominal interval.

---

## Gotchas

- `deleteAlarm()` is a no-op if no alarm is set; it does not throw.
- If `alarm()` throws and the platform retries, your alert webhook may fire multiple times for a single stale event. Make the webhook handler idempotent (deduplicate by DO ID + time window).
- Alarm retries use exponential back-off; after repeated failures the platform silently stops retrying. Monitor `alarm()` errors via Tail Workers to detect this case.
- `ctx.storage.setAlarm()` inside a transaction (`ctx.storage.transaction()`) is supported but the alarm is only registered if the transaction commits.

---

## Verification

1. Deploy the `HeartbeatDO` and arm it for a test job.
2. Confirm the alarm is set: `wrangler d1 execute` is not applicable here — use `wrangler tail` and watch for the `heartbeat_stale` log within `HEARTBEAT_INTERVAL_MS + STALE_THRESHOLD_MS`.
3. Stop calling `beat()` and wait; the alarm should fire and emit the stale event.
4. Call `/stop` on the DO and confirm no further stale events appear.
5. Query Analytics Engine SQL API and verify the `heartbeat_stale` rows are present with correct `age_ms`.

---

## Related

- `durable-objects-capacity-planning.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-notifications-pagerduty-webhook.md`
- `workers-tail-real-time-log-streaming.md`
- `cron-job-monitoring.md`

---

## Sources

- Cloudflare Durable Objects Alarms docs: https://developers.cloudflare.com/durable-objects/api/alarms/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Workers Pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Grafana Provisioning Alerting: https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/
