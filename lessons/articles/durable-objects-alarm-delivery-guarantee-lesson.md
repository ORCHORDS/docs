# Durable Objects Alarm Delivery Guarantee — Lesson

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A payment reminder system built on Durable Objects sent duplicate reminder emails to customers. Two identical "Your payment is due tomorrow" emails arrived 40 seconds apart. This happened for 23 customers during a transient Cloudflare infrastructure event. The engineering team had assumed alarms fire exactly once. They do not — alarms are **at least once**, and the handler must be idempotent.

---

## Context

The platform uses a Durable Object per subscription to manage payment lifecycle. When a subscription enters the `payment_due_soon` state, the DO sets an alarm for T-24h before the due date. The alarm handler sends a reminder email via a transactional email API.

**Stack:**
- Cloudflare Durable Objects (per-subscription state + alarm)
- D1 (subscription and payment records)
- Transactional email API (Resend)
- No deduplication logic in original design

**Original alarm handler:**

```typescript
// durable-objects/subscription-do.ts (BEFORE — not idempotent)
export class SubscriptionDO implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async alarm() {
    const sub = await this.state.storage.get<Subscription>('subscription');
    if (!sub || sub.status !== 'active') return;

    // Send reminder email — no deduplication
    await sendReminderEmail(sub.customerEmail, sub.dueDate, this.env);

    // Schedule next check
    await this.state.storage.setAlarm(
      Date.now() + 24 * 60 * 60 * 1000 // 24h
    );
  }

  // ... fetch handler, other methods
}
```

This design worked correctly during normal operation. Under a transient failure — specifically, the DO runtime receiving an alarm callback but encountering an internal error before acknowledging delivery — the Cloudflare platform retried the alarm delivery. The retry arrived 40 seconds later, the handler ran again, and a second email was sent.

---

## Incident Timeline

### 2026-08-11

- `03:17 UTC` — Cloudflare infrastructure event causes transient DO runtime errors in `WNAM` region. Alarms that fired during the window were retried by the platform.
- `03:17 UTC` — 23 `SubscriptionDO` alarm callbacks fire for payment reminders due on 2026-08-12.
- `03:17 UTC` — First email sent to each of the 23 customers via Resend.
- `03:17 UTC` — Cloudflare retries alarm delivery (transient runtime error during acknowledgment).
- `03:57 UTC` — Second alarm callback fires for the same 23 DOs. Second email sent to each customer.
- `04:15 UTC` — Customer complaints begin arriving in support. "Why did I get two payment reminder emails?"
- `06:02 UTC` — Engineering alerted. Cloudflare status page confirms infrastructure event in `WNAM` at 03:10–03:25 UTC.
- `06:45 UTC` — Root cause confirmed: alarm at-least-once delivery + non-idempotent handler.
- `08:30 UTC` — Fix deployed (idempotency key in D1).

---

## Root Cause

Cloudflare's documentation states:

> Alarms will be retried if the alarm handler throws an exception or if the Durable Object is evicted before the handler completes. **Alarms are delivered at least once.**

The original handler design assumed exactly-once delivery. This assumption is incorrect and is explicitly contradicted by the documentation. Under normal conditions (no infrastructure events, no handler exceptions), alarms fire once and the behavior appears correct. Under transient failure, the platform retries, and a non-idempotent handler produces duplicate side effects.

Sending an email is a non-idempotent operation — sending the same email twice causes a duplicate.

---

## Fix — Idempotency Key with D1 `INSERT OR IGNORE`

The fix introduces an idempotency key for each alarm firing, stored in D1. Before sending the email, the handler attempts to insert the idempotency key. If the insert is ignored (key already exists), the email was already sent and the handler exits without sending again.

```typescript
// durable-objects/subscription-do.ts (AFTER — idempotent)
export class SubscriptionDO implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async alarm() {
    const sub = await this.state.storage.get<Subscription>('subscription');
    if (!sub || sub.status !== 'active') return;

    // Generate a deterministic idempotency key for this alarm firing
    // Key is scoped to subscription ID + due date to allow future alarms
    const idempotencyKey = `reminder:${sub.id}:${sub.dueDate}`;

    // Attempt to claim the key — INSERT OR IGNORE is atomic in SQLite/D1
    const result = await this.env.DB.prepare(`
      INSERT OR IGNORE INTO sent_notifications (idempotency_key, sent_at)
      VALUES (?, ?)
    `).bind(idempotencyKey, new Date().toISOString()).run();

    if (result.meta.changes === 0) {
      // Key already existed — this is a duplicate delivery, skip send
      console.log(`Duplicate alarm for ${idempotencyKey}, skipping email.`);
      return;
    }

    // Key was new — proceed with email send
    await sendReminderEmail(sub.customerEmail, sub.dueDate, this.env);

    // Schedule next alarm (e.g., 7 days before due date, then 1 day before)
    await this.state.storage.setAlarm(
      Date.now() + 24 * 60 * 60 * 1000
    );
  }
}
```

**D1 schema for idempotency table:**

```sql
CREATE TABLE IF NOT EXISTS sent_notifications (
  idempotency_key TEXT PRIMARY KEY,
  sent_at         TEXT NOT NULL
);

-- TTL cleanup: a Cron Worker purges keys older than 30 days
-- to prevent unbounded table growth
```

---

## Why `INSERT OR IGNORE` Is the Right Primitive

`INSERT OR IGNORE` in SQLite (and D1) is atomic. If the row already exists (PRIMARY KEY conflict), the insert is silently ignored and `result.meta.changes` returns `0`. This gives us:

- **Atomicity**: No race condition between check and insert — the operation is a single atomic write.
- **Idempotency**: Multiple concurrent or sequential alarm deliveries produce exactly one row insert and exactly one email send.
- **Auditability**: The `sent_notifications` table is a durable log of every notification sent, queryable for debugging.

An alternative is D1's `INSERT ... ON CONFLICT DO NOTHING` syntax, which is equivalent.

---

## Anti-patterns / What Went Wrong

1. **Assuming DO alarms are exactly-once.** The Cloudflare documentation is explicit: alarms are at-least-once. Any alarm handler that performs side effects (email, SMS, Stripe charge, webhook delivery) must be idempotent.

2. **No deduplication metrics in the original design.** There was no counter for "alarm fired" vs "email sent". If those two numbers had been emitted and compared, the divergence during the incident would have been immediately visible.

3. **No integration test for duplicate alarm delivery.** The test suite called `alarm()` once and asserted one email was sent. No test called `alarm()` twice and asserted one email was sent.

4. **Confusing "typically fires once" with "guaranteed to fire once".** Under normal load, alarms behave as if exactly-once. This creates a false sense of security. The at-least-once behavior only manifests under failure conditions — precisely when correctness matters most.

---

## Gotchas

- **All DO alarm handlers that cause side effects must be idempotent.** Payments, emails, webhooks, third-party API calls — if the operation is not safe to run twice, you need deduplication.
- **`setAlarm` is also idempotent by default** — calling it multiple times with different times replaces the previous alarm. There is at most one pending alarm per DO instance. This is helpful: you can safely call `setAlarm` in both the alarm handler and the `fetch` handler without creating duplicate alarms.
- **Idempotency keys must encode the alarm's semantic identity**, not just a random UUID. A key like `reminder:{sub.id}:{dueDate}` ensures that a re-run of the same logical alarm is deduplicated, while a future alarm (different `dueDate`) generates a new key and is not incorrectly suppressed.
- **D1 `INSERT OR IGNORE` requires a PRIMARY KEY or UNIQUE constraint.** Without it, every insert succeeds and the deduplication does not work.
- **Clean up old idempotency keys.** A Cron Worker that deletes `sent_notifications` rows older than N days prevents unbounded table growth.
- **The at-least-once guarantee also applies to `fetch` handlers under certain eviction scenarios.** For critical state mutations in `fetch`, consider similar idempotency patterns.

---

## Monitoring Gap Addressed

Post-incident, two Analytics Engine data points were added to the alarm handler:

```typescript
async alarm() {
  // ... idempotency check ...

  // Metric: alarm fired (including duplicates)
  this.env.AE.writeDataPoint({
    indexes: ['subscription_alarm_fired'],
    blobs: [sub.id],
  });

  if (result.meta.changes === 0) {
    // Metric: duplicate detected
    this.env.AE.writeDataPoint({
      indexes: ['subscription_alarm_duplicate'],
      blobs: [sub.id],
    });
    return;
  }

  // Metric: email sent
  this.env.AE.writeDataPoint({
    indexes: ['subscription_alarm_email_sent'],
    blobs: [sub.id],
  });

  await sendReminderEmail(sub.customerEmail, sub.dueDate, this.env);
}
```

An alert fires if `subscription_alarm_duplicate` count exceeds 0 in a 10-minute window, indicating a platform-level retry event.

---

## Verification

- Post-fix: 0 duplicate emails in the 60 days following remediation (verified via Resend send log).
- `sent_notifications` table audited: single row per `reminder:{id}:{date}` key.
- Integration test added: `alarm()` called twice in sequence, asserts exactly one email sent and one DB row inserted.
- Monitoring: `subscription_alarm_duplicate` counter at zero in Analytics Engine for 60 days post-deploy.

---

## Related

- `kv-eventual-consistency-cache-poisoning-incident.md`
- `r2-lifecycle-rule-accidental-deletion-incident.md`
- Cloudflare Durable Objects: [Alarms](https://developers.cloudflare.com/durable-objects/api/alarms/)
- Cloudflare D1: [INSERT OR IGNORE](https://www.sqlite.org/lang_insert.html)

---

## Sources

- Internal incident report `INC-2026-0811`
- Cloudflare status page event `2026-08-11 WNAM infrastructure event`
- Customer support tickets `SUP-2026-8301` through `SUP-2026-8323`
- Durable Objects alarms documentation (at-least-once delivery guarantee)
