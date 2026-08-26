# Automated Email IP Warm-up Scheduling with Workers Cron Triggers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Manually adjusting daily send volume during an IP warm-up is error-prone and easy to skip on weekends. You want a Cloudflare Worker on a daily Cron Trigger to look up what day of the warm-up you are on, compute the allowed volume for that day, enqueue a volume-capped batch job to your ESP, and record progress in D1 so the ramp can be paused and resumed safely.

## Context

IP warm-up requires a geometric volume ramp — typically doubling every 1–3 days — while staying under thresholds that ISPs use to flag new senders. The ramp schedule and current position are stored in a D1 database so they survive Worker restarts and can be modified without a code deploy. A KV flag provides a circuit-breaker: if complaint rate spikes, an operator sets `warmup:paused=true` and the Cron Worker no-ops until it is cleared. The actual email dispatch uses the ESP's API (e.g., Resend or SendGrid) with a `daily_limit` parameter to cap sends.

## D1 Schema and Ramp Table

```typescript
// migrations/0001_warmup.sql (run via wrangler d1 execute)
// CREATE TABLE warmup_schedules (
//   id TEXT PRIMARY KEY,
//   domain TEXT NOT NULL,
//   esp TEXT NOT NULL,
//   start_date TEXT NOT NULL,          -- ISO date of day 1
//   current_day INTEGER NOT NULL DEFAULT 1,
//   paused INTEGER NOT NULL DEFAULT 0, -- 0 or 1
//   completed INTEGER NOT NULL DEFAULT 0
// );
//
// CREATE TABLE warmup_ramp (
//   schedule_id TEXT NOT NULL,
//   day INTEGER NOT NULL,
//   max_volume INTEGER NOT NULL,
//   PRIMARY KEY (schedule_id, day)
// );

// src/schedule.ts
export interface Env {
  DB: D1Database;
  WARMUP_KV: KVNamespace;
  ESP_API_KEY: string;
  ESP_BASE_URL: string; // e.g. https://api.resend.com
}

interface WarmupSchedule {
  id: string;
  domain: string;
  esp: string;
  current_day: number;
  paused: number;
  completed: number;
}

export async function getActiveSchedules(env: Env): Promise<WarmupSchedule[]> {
  const { results } = await env.DB.prepare(
    `SELECT id, domain, esp, current_day, paused, completed
     FROM warmup_schedules
     WHERE completed = 0 AND paused = 0`
  ).all<WarmupSchedule>();
  return results;
}

export async function getTodayVolume(
  env: Env,
  scheduleId: string,
  day: number
): Promise<number | null> {
  const row = await env.DB.prepare(
    `SELECT max_volume FROM warmup_ramp WHERE schedule_id = ? AND day = ?`
  ).bind(scheduleId, day).first<{ max_volume: number }>();
  return row?.max_volume ?? null;
}

export async function advanceDay(env: Env, scheduleId: string, nextDay: number): Promise<void> {
  const maxDay = await env.DB.prepare(
    `SELECT MAX(day) AS max_day FROM warmup_ramp WHERE schedule_id = ?`
  ).bind(scheduleId).first<{ max_day: number }>();

  if (nextDay > (maxDay?.max_day ?? 0)) {
    await env.DB.prepare(
      `UPDATE warmup_schedules SET completed = 1 WHERE id = ?`
    ).bind(scheduleId).run();
    console.log(`Warm-up complete for schedule ${scheduleId}`);
  } else {
    await env.DB.prepare(
      `UPDATE warmup_schedules SET current_day = ? WHERE id = ?`
    ).bind(nextDay, scheduleId).run();
  }
}
```

## Dispatching Volume-Capped Batches via ESP API

```typescript
// src/dispatch.ts
interface DispatchResult {
  scheduleId: string;
  domain: string;
  day: number;
  allowed: number;
  sent: number;
  skipped: boolean;
}

export async function dispatchWarmupBatch(
  env: Env,
  schedule: WarmupSchedule
): Promise<DispatchResult> {
  // Circuit-breaker: check KV pause flag per domain
  const pauseFlag = await env.WARMUP_KV.get(`warmup:${schedule.domain}:paused`);
  if (pauseFlag === 'true') {
    return { scheduleId: schedule.id, domain: schedule.domain,
      day: schedule.current_day, allowed: 0, sent: 0, skipped: true };
  }

  const maxVolume = await getTodayVolume(env, schedule.id, schedule.current_day);
  if (maxVolume === null) {
    console.error(`No ramp entry for ${schedule.id} day ${schedule.current_day}`);
    return { scheduleId: schedule.id, domain: schedule.domain,
      day: schedule.current_day, allowed: 0, sent: 0, skipped: true };
  }

  // Trigger ESP campaign with a daily cap; actual queuing is ESP-side
  const res = await fetch(`${env.ESP_BASE_URL}/campaigns/trigger`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.ESP_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      domain: schedule.domain,
      daily_limit: maxVolume,
      warmup_day: schedule.current_day,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`ESP trigger failed for ${schedule.domain}: ${err}`);
  }
  const { sent } = await res.json<{ sent: number }>();

  await advanceDay(env, schedule.id, schedule.current_day + 1);
  return { scheduleId: schedule.id, domain: schedule.domain,
    day: schedule.current_day, allowed: maxVolume, sent, skipped: false };
}
```

## Scheduled Handler and Cron Wiring

```typescript
// src/worker.ts
import { getActiveSchedules, type Env } from './schedule';
import { dispatchWarmupBatch } from './dispatch';

export const scheduled: ExportedHandlerScheduledHandler<Env> = async (_event, env) => {
  const schedules = await getActiveSchedules(env);
  if (schedules.length === 0) {
    console.log('No active warm-up schedules today');
    return;
  }

  const results = await Promise.allSettled(
    schedules.map((s) => dispatchWarmupBatch(env, s))
  );

  for (const r of results) {
    if (r.status === 'rejected') {
      console.error('Warm-up dispatch error:', r.reason);
    } else {
      const { domain, day, allowed, sent, skipped } = r.value;
      console.log(
        skipped
          ? `Skipped ${domain} (paused or missing ramp entry)`
          : `${domain} day ${day}: allowed=${allowed}, sent=${sent}`
      );
    }
  }
};

// wrangler.toml cron: [triggers] crons = ["0 7 * * *"]
export default { scheduled } satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Hardcoding the ramp volume table in Worker source — store it in D1 so you can adjust the schedule without a new deployment.
- Advancing the day counter before confirming the ESP dispatch succeeded — always advance only after a successful API response.
- No pause mechanism — without a KV circuit-breaker, a reputation event forces a code deploy to stop sends.

## Gotchas

- The `[triggers]` cron in `wrangler.toml` fires in UTC; if your ESP enforces sending windows in local time, offset your cron accordingly.
- Cloudflare does not guarantee cron fires within seconds of the scheduled minute — add idempotency using the stored `current_day` so a double-fire on the same day is a no-op.

## Verification

```bash
# Seed a 7-day schedule in D1
wrangler d1 execute EMAIL_DB --command \
  "INSERT INTO warmup_schedules VALUES ('wm1','example.com','resend','2026-08-23',1,0,0)"
wrangler d1 execute EMAIL_DB --command \
  "INSERT INTO warmup_ramp VALUES ('wm1',1,500),('wm1',2,1000),('wm1',3,2000),
   ('wm1',4,4000),('wm1',5,8000),('wm1',6,16000),('wm1',7,30000)"

# Trigger cron manually in local dev
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+7+*+*+*"

# Pause via KV circuit-breaker
wrangler kv key put --namespace-id <NS_ID> "warmup:example.com:paused" "true"
```

## Related

- `email/ip-warming-strategy.md`
- `email/domain-warming-strategy.md`
- `email/bulk-email-warming-new-domain-strategy.md`
- `email/email-reputation-monitoring.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://developers.cloudflare.com/d1/get-started/
- https://sendgrid.com/docs/api-reference/
