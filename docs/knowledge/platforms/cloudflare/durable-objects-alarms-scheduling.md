# Durable Objects Alarms — Per-Entity Scheduling and Timer Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You need per-user or per-entity scheduled tasks on Cloudflare Workers
— sending reminder emails, expiring sessions, retrying failed
webhooks, or scheduling delayed state transitions. Cron Triggers run
globally on a schedule but cannot target individual Durable Object
instances. You want each entity (user, order, session) to have its own
timer that fires reliably even if the Worker restarts.

## Context

Durable Objects Alarms allow scheduling a Durable Object to wake up at
a specific time in the future. When the alarm fires, the object's
`alarm()` handler is called with guaranteed at-least-once execution —
if the handler throws an exception, it automatically retries with
exponential backoff (up to 6 retries). In 2026, alarms are the
standard pattern for per-entity scheduling on Cloudflare, replacing
external cron services or polling loops. The key constraint is one
alarm per Durable Object at a time — for multiple scheduled tasks
within one object, maintain a schedule table and set the alarm to the
nearest upcoming task.

## Alarm basics

```typescript
export class TimerObject extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/schedule') {
      const { delayMs } = await request.json();
      const triggerAt = Date.now() + delayMs;

      await this.ctx.storage.setAlarm(triggerAt);
      await this.ctx.storage.put('scheduledAction', 'send_reminder');

      return new Response(JSON.stringify({ scheduledFor: triggerAt }));
    }

    return new Response('Not found', { status: 404 });
  }

  async alarm(): Promise<void> {
    const action = await this.ctx.storage.get('scheduledAction');

    switch (action) {
      case 'send_reminder':
        await this.sendReminder();
        break;
      case 'expire_session':
        await this.expireSession();
        break;
    }

    await this.ctx.storage.delete('scheduledAction');
  }
}
```

## Multiple schedules per object

```typescript
export class MultiScheduler extends DurableObject {
  async scheduleTask(taskId: string, runAt: number, payload: any) {
    const schedules = (await this.ctx.storage.get('schedules')) || {};
    schedules[taskId] = { runAt, payload };
    await this.ctx.storage.put('schedules', schedules);

    await this.setNextAlarm(schedules);
  }

  async cancelTask(taskId: string) {
    const schedules = (await this.ctx.storage.get('schedules')) || {};
    delete schedules[taskId];
    await this.ctx.storage.put('schedules', schedules);

    if (Object.keys(schedules).length > 0) {
      await this.setNextAlarm(schedules);
    } else {
      await this.ctx.storage.deleteAlarm();
    }
  }

  private async setNextAlarm(schedules: Record<string, any>) {
    const nextRun = Math.min(
      ...Object.values(schedules).map((s: any) => s.runAt)
    );
    await this.ctx.storage.setAlarm(nextRun);
  }

  async alarm(): Promise<void> {
    const schedules = (await this.ctx.storage.get('schedules')) || {};
    const now = Date.now();

    for (const [taskId, schedule] of Object.entries(schedules)) {
      if ((schedule as any).runAt <= now) {
        await this.executeTask(taskId, (schedule as any).payload);
        delete schedules[taskId];
      }
    }

    await this.ctx.storage.put('schedules', schedules);

    if (Object.keys(schedules).length > 0) {
      await this.setNextAlarm(schedules);
    }
  }

  private async executeTask(taskId: string, payload: any) {
    // Process the scheduled task
  }
}
```

## Common patterns

```
Session expiration:
  → Set alarm to session TTL (e.g., 30 min from last activity)
  → alarm() deletes session data and notifies client
  → Reset alarm on each user interaction

Retry with backoff:
  → On failure, schedule alarm at delay * 2^attempt
  → Store attempt count in Durable Object storage
  → Cap at max retries, then move to dead letter

Delayed state transitions:
  → Order placed → alarm at 30min → check payment status
  → If unpaid → cancel order and release inventory
  → If paid → proceed to fulfillment

Recurring tasks:
  → alarm() executes task, then sets next alarm
  → Store interval in storage
  → Self-perpetuating schedule within one DO
```

## Anti-patterns

- **Polling instead of alarms** — using `setInterval` or repeated
  `fetch` calls to check if it is time to execute a task. Durable
  Objects may be evicted between requests. Alarms are persisted
  and guaranteed to fire.
- **One alarm per task via separate DOs** — creating a new Durable
  Object for each scheduled task. This works but is expensive at
  scale. Use a schedule table within a single DO per entity.
- **Short-interval alarms on many objects** — scheduling every
  Durable Object to wake every 5 seconds. Each alarm invocation
  has cost. Use event-driven patterns instead of polling patterns.
- **Not making alarm() idempotent** — alarms guarantee at-least-once
  execution, meaning `alarm()` may run more than once. Check state
  before acting and use idempotency keys for external calls.

## Gotchas

- **One alarm per object** — calling `setAlarm()` overwrites any
  existing alarm. To manage multiple schedules, maintain a sorted
  schedule list and set the alarm to the earliest entry.
- **Alarm precision** — alarms fire at approximately the scheduled
  time but are not millisecond-precise. Expect up to a few seconds
  of jitter. Do not rely on alarms for sub-second timing.
- **Eviction and cold starts** — the Durable Object may be evicted
  between scheduling and firing. When the alarm fires, the object
  is instantiated fresh. All state must be in durable storage, not
  in-memory variables.
- **Alarm cost** — each alarm invocation counts as a Durable Object
  request for billing purposes. High-frequency alarms across many
  objects can become expensive. Batch work where possible.

## Verification

- Alarms fire reliably after the scheduled time.
- `alarm()` handler is idempotent (safe to execute multiple times).
- Multiple schedules within one DO resolve correctly to the nearest.
- Failed alarms retry automatically with exponential backoff.
- Alarm state survives Durable Object eviction and restart.

## Related

- `documentation/docs/policies/cloudflare/durable-objects-real-time-collaboration.md`
- `documentation/docs/policies/cloudflare/workers-cron-triggers.md`
- `documentation/docs/policies/cloudflare/queues-batch-processing.md`

## Source URLs (verified 2026-08-16)

- Durable Objects Alarms API — https://developers.cloudflare.com/durable-objects/api/alarms/
- Durable Objects Alarms: A Wake-Up Call for Your Applications — https://blog.cloudflare.com/durable-objects-alarms/
- Building a Scheduling System with Workers and Durable Objects — https://blog.cloudflare.com/building-scheduling-system-with-workers-and-durable-objects/
- Rules of Durable Objects — https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/
