# durable-objects-alarms

**Issue:** Using Durable Object alarms for deferred and scheduled work
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Durable Object alarms let a DO schedule a callback to itself at a specific time. Unlike cron triggers (which are global), alarms are per-DO instance and survive hibernation — ideal for per-user timers, delayed jobs, and timeouts.

## Pattern / Solution

```typescript
import { DurableObject } from 'cloudflare:workers';

export class SessionManager extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/start-session') {
      const { userId } = await request.json() as { userId: string };

      // Persist session
      await this.ctx.storage.put('session', { userId, startedAt: Date.now() });

      // Set alarm to expire session in 1 hour
      await this.ctx.storage.setAlarm(Date.now() + 60 * 60 * 1000);

      return Response.json({ ok: true, expiresIn: '1h' });
    }

    if (url.pathname === '/extend') {
      // Clear existing alarm and set a new one
      await this.ctx.storage.deleteAlarm();
      await this.ctx.storage.setAlarm(Date.now() + 60 * 60 * 1000);
      return Response.json({ ok: true, extended: true });
    }

    if (url.pathname === '/status') {
      const alarm = await this.ctx.storage.getAlarm();
      const session = await this.ctx.storage.get('session');
      return Response.json({
        session,
        expiresAt: alarm ? new Date(alarm).toISOString() : null,
      });
    }

    return new Response('Not Found', { status: 404 });
  }

  // Called by the runtime when the alarm fires
  async alarm(): Promise<void> {
    const session = await this.ctx.storage.get<{ userId: string }>('session');
    if (!session) return;

    console.log(`Session expired for user: ${session.userId}`);

    // Clean up
    await this.ctx.storage.deleteAll();

    // Notify downstream (e.g., push to a Queue)
    // await this.env.EVENTS_QUEUE.send({ type: 'session_expired', userId: session.userId });
  }
}
```

**Patterns:**
```typescript
// Retry with exponential backoff using alarms
async alarm(): Promise<void> {
  const attempt = (await this.ctx.storage.get<number>('attempt')) ?? 0;
  try {
    await doWork(this.env);
    await this.ctx.storage.deleteAll();
  } catch {
    if (attempt < 5) {
      await this.ctx.storage.put('attempt', attempt + 1);
      const delay = Math.pow(2, attempt) * 1000; // 1s, 2s, 4s, 8s, 16s
      await this.ctx.storage.setAlarm(Date.now() + delay);
    } else {
      // Give up — notify DLQ
      await this.ctx.storage.deleteAll();
    }
  }
}
```

## Gotchas
- Only **one alarm** can be set per DO instance at a time; calling `setAlarm()` again replaces the existing one.
- Alarms have a **10-second CPU budget** (same as a regular Worker request).
- If the `alarm()` method throws, the alarm is retried after ~30 seconds automatically (up to platform limits).
- `setAlarm()` accepts a `Date` or milliseconds since epoch.
- Alarms are durable — they survive DO eviction, Worker redeployments, and even brief platform outages.
- `deleteAlarm()` cancels the pending alarm; `getAlarm()` returns its scheduled time or `null`.
- The alarm fires on the specific DO instance — routing must send the cancel/extend request to the same instance.

## Related
- `durable-objects-hibernation.md`
- `durable-objects-patterns.md`
- `workers-scheduled-events.md`
