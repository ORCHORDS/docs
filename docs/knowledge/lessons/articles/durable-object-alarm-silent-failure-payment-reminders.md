# On-Call Lesson: Durable Object Alarm Silently Failing Caused Missed Payment Reminders

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production
- **Category:** On-call lesson / incident retrospective

---

## Symptom

Over a 72-hour period, the platform failed to send 1,847 subscription renewal reminder emails. Users were charged without receiving the 3-day advance notice the Terms of Service promised. Customer support received 214 inbound contacts from confused users. No alert fired during the outage. The failure was discovered when a customer support agent escalated a pattern of complaints to the engineering team.

---

## Context

The platform uses Cloudflare Durable Objects to implement per-user scheduled work. Each user account has a `UserScheduler` Durable Object responsible for scheduling and executing time-sensitive operations including: subscription renewal reminders, trial expiry warnings, and weekly digest emails. The `UserScheduler` uses the Durable Objects Alarms API to schedule future work — each Durable Object schedules its own alarm by calling `this.storage.setAlarm(timestamp)`. When the alarm fires, the runtime calls the `alarm()` method on the Durable Object.

The failure occurred because a code deployment introduced a runtime error in the `alarm()` method. The Durable Objects runtime retried the alarm repeatedly with exponential backoff, but the error persisted across all retries. After the maximum retry count was exhausted, the alarm was silently abandoned. No exception reached the Workers error logging pipeline. No metric changed visibly. The alarms simply stopped firing.

---

## Timeline

| UTC | Event |
|---|---|
| 2026-08-13 09:14 | Deployment containing `UserScheduler` refactor rolls out |
| 2026-08-13 09:18 | First alarm failures begin (backoff hides them initially) |
| 2026-08-13 ~10:00 | Alarms exhausting retry budget begin silently failing |
| 2026-08-13 – 2026-08-16 | 1,847 reminders silently dropped over 72 hours |
| 2026-08-16 11:42 | Customer support agent escalates pattern of complaints |
| 2026-08-16 12:05 | Engineer identifies deployment correlation |
| 2026-08-16 12:31 | Root cause confirmed: null dereference in `alarm()` method |
| 2026-08-16 12:48 | Hotfix deployed; new alarms begin firing correctly |
| 2026-08-16 13:30 | Manual replay of missed alarms completes |

---

## Root Cause Analysis

### Primary: Null Dereference in alarm() Method

The refactor changed the internal structure of `UserScheduler`'s stored state. The `alarm()` method read a field (`this.userData.subscriptionPlan`) that existed in the old state format but was absent in state objects created before the migration ran. When the alarm fired for users whose state had not yet been migrated, `this.userData.subscriptionPlan` was `undefined`, and subsequent code called `.renewalDays` on `undefined`, throwing a `TypeError`.

```ts
// Vulnerable code after refactor
async alarm() {
  const renewalDays = this.userData.subscriptionPlan.renewalDays; // TypeError if subscriptionPlan is undefined
  // ...
}
```

The fix was a null-safe access with a fallback default:

```ts
async alarm() {
  const renewalDays = this.userData.subscriptionPlan?.renewalDays ?? 3;
  // ...
}
```

### Contributing: Durable Object Alarms Fail Silently After Retry Exhaustion

The Durable Objects Alarms API retries a failed `alarm()` method with exponential backoff. If the method continues to throw after all retries are exhausted, the alarm is abandoned. This is the correct behaviour for preventing infinite retry loops, but it has a critical consequence: **there is no error surface visible to the application**. The alarm disappears without a trace in Workers logs, metrics, or error tracking.

This is fundamentally different from Cloudflare Queues messages, which move to a dead-letter queue on retry exhaustion. Alarms have no DLQ equivalent.

### Contributing: No Heartbeat or Liveness Check for Alarms

The platform had no mechanism to verify that scheduled alarms were executing. There was no metric tracking "alarms fired per hour" or "reminders sent per hour." If such a metric had existed, it would have dropped to near-zero within minutes of the deployment and triggered an alert.

### Contributing: State Migration Not Completed Before Code Deployment

The refactor required a data migration to update stored state for existing Durable Objects. The deployment shipped the new code before the migration completed (or in fact before it was written). This is a classic "blue/green mismatch" — new code ran against old data.

---

## Technical Sections

### 1. Durable Object Alarm Retry Semantics

A Durable Object's `alarm()` method is called by the runtime at or after the scheduled time. If the method throws, the runtime retries with exponential backoff up to a platform-defined limit. After that limit, the alarm is dropped.

Key properties:
- Retry delays: approximately 15s, 30s, 60s, 2m, 4m, 8m, 16m (implementation may vary; do not rely on exact timings)
- After retry exhaustion: the alarm is dropped; the Durable Object's scheduled state is cleared
- No dead-letter mechanism; no automatic notification to the application

The correct posture is: **treat alarm() as a method that must never unhandledly throw.** Wrap the body in a try/catch and handle or log errors explicitly.

```ts
async alarm() {
  try {
    await this.executeScheduledWork();
  } catch (err) {
    // Log to an external sink — Logpush, Analytics Engine, or a logging Worker
    await this.logAlarmError(err);
    // Optionally reschedule: this.storage.setAlarm(Date.now() + 300_000)
    // Do NOT rethrow unless you want the runtime to retry
  }
}
```

### 2. Making Alarm Failures Visible

Because the Durable Objects runtime swallows alarm errors after retry exhaustion, the application must create its own visibility.

**Option A: Emit a metric on every alarm execution (success or failure).**

Use Workers Analytics Engine to write a data point from within `alarm()`:

```ts
async alarm() {
  const start = Date.now();
  let status = 'success';
  try {
    await this.executeScheduledWork();
  } catch (err) {
    status = 'error';
    await this.logAlarmError(err);
  } finally {
    this.env.ANALYTICS.writeDataPoint({
      blobs: [this.env.DO_NAME, status],
      doubles: [Date.now() - start],
      indexes: ['alarm_execution'],
    });
  }
}
```

Alert when `alarm_execution` event count drops below the expected rate.

**Option B: Write a "last executed" timestamp to Durable Object storage on success.**

An external health-check Worker (scheduled via Cron Triggers) queries a sample of Durable Objects for their `lastAlarmExecuted` timestamp and alerts if any are overdue:

```ts
// In alarm()
await this.storage.put('lastAlarmExecuted', Date.now());

// In health check Worker
const obj = env.USER_SCHEDULER.get(env.USER_SCHEDULER.idFromName(userId));
const last = await obj.fetch('/health');
// Alert if Date.now() - last > expectedIntervalMs * 2
```

**Option C: Track expected vs actual alarm count in D1 or KV.**

Before scheduling an alarm, write a row to D1 with status `scheduled`. After successful alarm execution, update to `completed`. A nightly reconciliation query finds rows that are still `scheduled` past their expected execution time:

```sql
SELECT * FROM alarm_audit
WHERE status = 'scheduled'
  AND scheduled_at < UNIXEPOCH() - 3600; -- 1 hour overdue
```

### 3. Safe Alarm Rescheduling Pattern

Durable Object alarms should reschedule themselves at the top of the `alarm()` method, before doing any work, to ensure the next alarm is set even if the work fails:

```ts
async alarm() {
  // Reschedule first, so if the work fails we don't lose the cadence
  const nextAlarm = Date.now() + this.getIntervalMs();
  await this.storage.setAlarm(nextAlarm);

  try {
    await this.executeScheduledWork();
  } catch (err) {
    await this.logAlarmError(err);
    // Do not rethrow — rescheduling already handled above
  }
}
```

This is the same "schedule-first, execute-second" pattern used in reliable cron implementations. It ensures that a transient failure in the work does not prevent future alarm delivery.

### 4. State Migration Protocol for Durable Objects

The root cause was unmigrated state meeting new code. The correct protocol for DO state migrations:

1. **Write new code to handle both old and new state format** (defensive reads with defaults)
2. **Deploy the backward-compatible code** first
3. **Run the migration** (either a lazy migration on next access, or a bulk backfill Worker)
4. **Verify migration completeness** (query D1 or a sentinel KV key updated by the migration)
5. **Only then remove backward-compatibility shims** in a follow-up deploy

For Durable Objects, lazy migration on next access is often the safest approach:

```ts
private async ensureMigrated(): Promise<void> {
  const version = await this.storage.get<number>('stateVersion') ?? 0;
  if (version < CURRENT_VERSION) {
    await this.migrateFrom(version);
    await this.storage.put('stateVersion', CURRENT_VERSION);
  }
}

async fetch(request: Request): Promise<Response> {
  await this.ensureMigrated();
  // ... rest of handler
}

async alarm(): Promise<void> {
  await this.ensureMigrated();
  // ... rest of alarm
}
```

### 5. Testing Alarm Paths in Wrangler / Miniflare

Durable Object alarms can be tested locally using Miniflare. The `triggerAlarm()` API allows triggering the `alarm()` method synchronously in tests without waiting for the scheduled time:

```ts
import { env } from 'cloudflare:test';
import { SELF } from 'cloudflare:test';

it('sends reminder email when alarm fires', async () => {
  const id = env.USER_SCHEDULER.newUniqueId();
  const stub = env.USER_SCHEDULER.get(id);

  // Schedule the alarm
  await stub.fetch('/schedule-reminder', { method: 'POST' });

  // Trigger the alarm immediately in tests
  await runInDurableObject(stub, async (instance) => {
    await instance.alarm();
  });

  // Assert the email was sent
  expect(emailsSent).toContainEqual(expect.objectContaining({ type: 'renewal_reminder' }));
});
```

The `alarm()` method must be covered by unit tests that exercise failure paths — null state, network errors from email provider, D1 write failures — to catch regressions before they reach production.

---

## Anti-Patterns

- **Letting alarm() throw unhandled exceptions.** Unhandled throws cause the runtime to retry and eventually drop the alarm silently. Always wrap alarm bodies in try/catch.
- **No monitoring of alarm execution rate.** If you cannot answer "how many alarms fired in the last hour," you will not detect alarm failures until users complain. Treat alarm execution rate as a key reliability metric.
- **Deploying code before state migration is complete.** New code must handle old data gracefully, or the migration must complete before new code is deployed. There is no safe middle ground.
- **Rescheduling alarms at the end of alarm().** If the work fails before the reschedule call, the alarm chain is broken. Reschedule at the start.
- **Assuming retry behaviour is a sufficient safety net.** Retries handle transient failures. They do not handle bugs that are deterministic (the same input will always throw). Test failure modes in CI.

---

## Gotchas

- Durable Object alarms fire at-least-once. If an alarm fires and the DO crashes mid-execution, it may fire again. The `alarm()` method must be idempotent.
- The alarm is associated with a specific Durable Object instance identified by its ID. If you change the ID generation scheme (e.g., switch from `idFromName(userId)` to `newUniqueId()`), existing alarms are lost because they are registered on the old ID.
- Alarms are stored in the Durable Object's own storage. They do not survive if the Durable Object is deleted. If you need alarms to survive object deletion and recreation, store the schedule in D1 and re-register the alarm on object initialisation.
- A Durable Object can only have one alarm pending at a time. If the alarm should fire multiple times (e.g., daily), it must reschedule itself from within `alarm()`.
- The `setAlarm()` call counts against the Durable Object's storage operation budget. Frequent alarm rescheduling (e.g., every second) will incur meaningful storage costs at scale.

---

## Verification

Post-incident verification:

1. `alarm()` method wrapped in try/catch; all error paths tested in unit tests.
2. Analytics Engine `alarm_execution` metric implemented; alert configured for rate dropping below 50% of 7-day average.
3. `stateVersion` migration pattern implemented; CI test added that runs `alarm()` against old-format state to catch regressions.
4. Manual replay of 1,847 missed reminders completed; 1,831 succeeded (16 users had deactivated accounts in the interim).
5. Runbook updated with alarm failure diagnosis steps and replay procedure.

---

## Related

- `write-the-runbook-before-the-incident.md`
- `alert-fatigue-masks-real-outages-2026.md`
- `idempotency-keys-for-all-payment-calls.md`
- `cloudflare-storage-primitive-selection.md`
- `queue-consumers-must-be-idempotent.md`
- `monitor-before-and-after-deploy.md`

---

## Sources

- Durable Objects Alarms API: https://developers.cloudflare.com/durable-objects/api/alarms/
- Miniflare testing guide: https://miniflare.dev/
- Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
