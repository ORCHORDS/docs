# Durable Object Heartbeat & Platform Liveness Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project's moderation pipeline silently fails: the Queues consumer stops draining, the Workers AI classifier returns 503s, or the D1 database enters a read-only degraded state — but no external alert fires because the Workers runtime itself is healthy enough to serve 200 OK on the public edge. The platform appears live from the outside while the trust & safety layer is completely down. This article covers a Durable Object heartbeat design that detects internal subsystem failures independent of external uptime probes.

## Context

Cloudflare's external status page (cloudflarestatus.com) does not reflect Worker-specific or binding-specific failures. A Durable Object alarm is the only mechanism in the Workers runtime that can self-schedule a probe at a guaranteed future time without relying on incoming traffic. Combined with Analytics Engine for time-series emission and an external dead-man's-switch webhook, this pattern provides genuine liveness detection for example project's internal critical path.

The alarm fires even when there is zero user traffic — a key property for detecting silent failures in off-peak hours when abuse pipelines are most likely to be sabotaged or stuck.

## 1. Heartbeat Durable Object

```typescript
// src/do/platform-heartbeat.ts
import type { Env } from "../types";

export class PlatformHeartbeat implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env   = env;
    // Ensure the alarm is always armed on cold start
    this.state.blockConcurrencyWhile(async () => {
      const existing = await this.state.storage.getAlarm();
      if (!existing) {
        await this.state.storage.setAlarm(Date.now() + 60_000);
      }
    });
  }

  async alarm(): Promise<void> {
    const checks = await Promise.allSettled([
      this.checkD1(),
      this.checkQueues(),
      this.checkWorkersAI(),
      this.checkR2(),
    ]);

    const results = checks.map((c, i) => ({
      subsystem: ["d1", "queues", "workers_ai", "r2"][i],
      ok: c.status === "fulfilled" && c.value,
      error: c.status === "rejected" ? String(c.reason) : undefined,
    }));

    const allOk = results.every(r => r.ok);

    // Emit to Analytics Engine for time-series dashboards
    this.env.AE_DATASET.writeDataPoint({
      blobs: [allOk ? "healthy" : "degraded"],
      indexes: ["platform_liveness"],
      doubles: results.map(r => r.ok ? 1 : 0),
    });

    if (!allOk) {
      await this.fireDeadManAlert(results);
    }

    // Re-arm for next tick (60 s)
    await this.state.storage.setAlarm(Date.now() + 60_000);
  }

  private async checkD1(): Promise<boolean> {
    const r = await this.env.DB.prepare("SELECT 1 AS ok").first<{ ok: number }>();
    return r?.ok === 1;
  }

  private async checkQueues(): Promise<boolean> {
    // Write a sentinel message; the consumer must echo it back via DO storage
    const sentinel = `hb-${Date.now()}`;
    await this.env.MODERATION_QUEUE.send({ type: "heartbeat", sentinel });
    // Optimistic: queue.send() not throwing means the binding is alive
    return true;
  }

  private async checkWorkersAI(): Promise<boolean> {
    const resp = await this.env.AI.run("@cf/baai/bge-small-en-v1.5", {
      text: ["heartbeat"],
    }) as { data: number[][] };
    return Array.isArray(resp.data) && resp.data.length > 0;
  }

  private async checkR2(): Promise<boolean> {
    const sentinel = await this.env.CONTENT_BUCKET.head("_heartbeat");
    // Returns null if object doesn't exist — binding is still reachable
    return sentinel !== undefined;
  }

  private async fireDeadManAlert(
    results: Array<{ subsystem: string; ok: boolean; error?: string }>
  ): Promise<void> {
    const failing = results.filter(r => !r.ok).map(r => r.subsystem).join(", ");
    await fetch(this.env.ALERT_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `[example project LIVENESS] Subsystems DEGRADED: ${failing}`,
        details: results,
        ts: new Date().toISOString(),
      }),
    });
  }

  async fetch(_request: Request): Promise<Response> {
    // Allow manual re-arm or status probe
    const status = await this.state.storage.getAlarm();
    return Response.json({ next_alarm_at: status, ok: true });
  }
}
```

## 2. Bootstrap: Arm the Heartbeat on Deploy

```typescript
// src/workers/heartbeat-init.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Ensure exactly one singleton Durable Object is armed
    const id = env.PLATFORM_HEARTBEAT.idFromName("singleton");
    const stub = env.PLATFORM_HEARTBEAT.get(id);
    await stub.fetch("https://internal/status");
  },
};
```

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "PLATFORM_HEARTBEAT"
class_name = "PlatformHeartbeat"

[[migrations]]
tag = "v1"
new_classes = ["PlatformHeartbeat"]

[triggers]
crons = ["* * * * *"]   # Cron to ensure DO is armed; DO alarm is the real tick
```

## 3. Dead-Man's-Switch: External Pager Integration

```typescript
// src/workers/heartbeat-external.ts
// This separate Worker is called by PlatformHeartbeat.alarm() ONLY on failure.
// A third-party dead-man's switch (e.g., Cronitor, Healthchecks.io) expects a
// ping every 90 s; silence triggers an independent alert.

export async function pingDeadManSwitch(env: Env): Promise<void> {
  if (/* all checks healthy */ true) {
    // Successful ping resets the external watchdog timer
    await fetch(`${env.HEALTHCHECKS_IO_URL}/success`, { method: "HEAD" });
  } else {
    await fetch(`${env.HEALTHCHECKS_IO_URL}/fail`, { method: "HEAD" });
  }
}
```

## 4. D1 Liveness History Table

```sql
-- migration: 0044_heartbeat_history.sql
CREATE TABLE heartbeat_log (
  id           TEXT PRIMARY KEY,
  checked_at   INTEGER NOT NULL,
  d1_ok        INTEGER NOT NULL,
  queues_ok    INTEGER NOT NULL,
  workers_ai_ok INTEGER NOT NULL,
  r2_ok        INTEGER NOT NULL,
  alert_sent   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_heartbeat_checked_at ON heartbeat_log (checked_at);
```

```typescript
// Add to PlatformHeartbeat.alarm() after the checks:
await this.env.DB.prepare(
  `INSERT INTO heartbeat_log
     (id, checked_at, d1_ok, queues_ok, workers_ai_ok, r2_ok, alert_sent)
   VALUES (?, ?, ?, ?, ?, ?, ?)`
).bind(
  crypto.randomUUID(), Date.now(),
  results[0].ok ? 1 : 0,
  results[1].ok ? 1 : 0,
  results[2].ok ? 1 : 0,
  results[3].ok ? 1 : 0,
  allOk ? 0 : 1
).run();
```

## 5. Alerting on Consecutive Failures Only

```typescript
// src/do/platform-heartbeat.ts (alarm extension)
private async shouldAlert(): Promise<boolean> {
  const recent = await this.env.DB.prepare(
    `SELECT d1_ok AND queues_ok AND workers_ai_ok AND r2_ok AS all_ok
     FROM heartbeat_log ORDER BY checked_at DESC LIMIT 3`
  ).all<{ all_ok: number }>();

  // Alert only after 3 consecutive failures to suppress transient blips
  return recent.results.length === 3 && recent.results.every(r => r.all_ok === 0);
}
```

## Anti-patterns

- **Using a Cron Trigger alone** — Cron Triggers can miss ticks if the Worker is cold-booted under heavy load; DO alarms are durable.
- **Probing only the public endpoint** — a 200 OK from the edge says nothing about D1 or Workers AI binding health.
- **Firing an alert on the first failure** — transient 503s from Workers AI are common; require 3 consecutive before paging.
- **Storing raw subsystem errors in Analytics Engine blobs** — blobs are indexed; avoid PII or internal stack traces there.

## Gotchas

- `DurableObjectState.storage.setAlarm()` overwrites any existing alarm — always call `getAlarm()` first on cold start to avoid re-arming an already-armed alarm.
- Workers AI `@cf/baai/bge-small-en-v1.5` is a lightweight model; do not use a heavy model for heartbeat probes (CPU limit applies to alarm handlers too).
- DO alarm handlers have the same CPU limit as fetch handlers (50 ms unmetered, then metered); keep probe logic fast.
- If D1 is down, the `INSERT INTO heartbeat_log` in step 4 will also fail — wrap in try/catch and emit to Analytics Engine as the fallback.

## Verification

```bash
# Confirm DO alarm is set
curl https://example project-internal.example.com/heartbeat/status | jq '.next_alarm_at'
# Should be within 60 s of now (Unix ms)

# Query recent heartbeat history
wrangler d1 execute example project-db --command \
  "SELECT checked_at, d1_ok, queues_ok, workers_ai_ok, r2_ok
   FROM heartbeat_log ORDER BY checked_at DESC LIMIT 10;"

# Verify Analytics Engine writes
wrangler analytics list  # then query via GraphQL API
```

## Related

- `platform-health-score-dashboard-analytics-engine.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `platform-wide-emergency-lockdown-circuit-breaker-workers.md`
- `worker-cpu-limit-exceeded.md`

## Sources

- Cloudflare Durable Objects alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Healthchecks.io dead-man's-switch API — https://healthchecks.io/docs/http_api/
- Workers AI model catalog — https://developers.cloudflare.com/workers-ai/models/
