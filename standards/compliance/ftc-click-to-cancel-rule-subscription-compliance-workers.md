# FTC Click-to-Cancel Rule — Subscription Compliance via Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Meeting 16 CFR Part 425 Without Breaking Subscription Funnels

The FTC's "click-to-cancel" rule (16 CFR Part 425, effective 2024) requires that cancelling a recurring subscription be at least as easy as signing up. Violations carry civil penalties up to $51,744 per occurrence. The rule imposes four concrete obligations: (1) same-channel cancellation, (2) single-step cancellation path with no more than one save offer permitted, (3) annual reminder notices for free-to-paid or trial conversions, and (4) immediate cancellation upon request. Workers are ideally positioned to enforce these obligations at the edge because every subscription state transition passes through the API layer.

Subscription platforms commonly gate the cancel button behind multiple confirmation modals, route users to phone-only support, or inject aggressive save flows. All of these patterns are now unlawful. The compliance challenge is architectural: the cancel path must be discoverable from whichever channel the customer used to subscribe — web, mobile, in-app purchase, or direct API — and must complete in a single authenticated POST with no mandatory deflection screens.

D1 is used to store subscription state, cancellation timestamps, save-offer presentation records, and annual reminder dispatch logs. Every edge that modifies subscription state writes an immutable audit row so that enforcement evidence is available without querying a remote database under subpoena pressure.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Database: D1 (SQLite at edge)
- Queue: Cloudflare Queues for async reminder dispatch
- Auth: JWT validated in Worker middleware
- Regulation: 16 CFR Part 425 (FTC Negative Option Rule / Click-to-Cancel)

## Same-Channel Cancellation Enforcement

Every subscription record stores its `acquisition_channel`. The cancel endpoint validates that the inbound request channel matches; if it does not, the Worker still honours the cancellation (the rule requires parity, not exclusivity) but logs the cross-channel event for analytics.

```ts
// src/handlers/cancel.ts
import { D1Database, ExecutionContext } from '@cloudflare/workers-types';

interface Env { DB: D1Database; CANCEL_QUEUE: Queue }

export async function handleCancel(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const { subscriptionId } = await req.json<{ subscriptionId: string }>();
  const userId = (req as any).userId as string; // set by auth middleware

  const sub = await env.DB.prepare(
    'SELECT * FROM subscriptions WHERE id = ? AND user_id = ?'
  ).bind(subscriptionId, userId).first<Record<string, unknown>>();

  if (!sub) return new Response('Not found', { status: 404 });
  if (sub.status === 'cancelled') return new Response('Already cancelled', { status: 409 });

  const channel = req.headers.get('x-acquisition-channel') ?? 'web';
  const crossChannel = sub.acquisition_channel !== channel;

  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE subscriptions SET status='cancelled', cancelled_at=?, cancel_channel=? WHERE id=?`
    ).bind(now, channel, subscriptionId),
    env.DB.prepare(
      `INSERT INTO cancel_audit (sub_id, user_id, cancelled_at, channel, cross_channel, save_offer_shown)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(subscriptionId, userId, now, channel, crossChannel ? 1 : 0, (sub.save_offer_shown_at ?? null) ? 1 : 0),
  ]);

  return Response.json({ cancelled: true, effectiveDate: now });
}
```

## Save-Offer Constraint — One Offer Maximum

The rule permits a single save offer (e.g., a discount or pause). A second offer constitutes an unlawful barrier. The Worker enforces this at the API level: if `save_offer_shown_at` is already set for the subscription, any request to show another offer returns 403 and logs the attempted violation.

```ts
// src/handlers/save-offer.ts
export async function handleSaveOffer(req: Request, env: Env): Promise<Response> {
  const { subscriptionId } = await req.json<{ subscriptionId: string }>();
  const userId = (req as any).userId as string;

  const sub = await env.DB.prepare(
    'SELECT save_offer_shown_at FROM subscriptions WHERE id = ? AND user_id = ?'
  ).bind(subscriptionId, userId).first<{ save_offer_shown_at: string | null }>();

  if (!sub) return new Response('Not found', { status: 404 });

  if (sub.save_offer_shown_at) {
    // Second offer attempt — log as potential violation, deny
    await env.DB.prepare(
      `INSERT INTO compliance_violations (type, sub_id, detected_at, detail)
       VALUES ('FTC_425_MULTIPLE_SAVE_OFFERS', ?, ?, ?)`
    ).bind(subscriptionId, new Date().toISOString(), 'Second save offer attempted').run();
    return new Response('Save offer already presented', { status: 403 });
  }

  await env.DB.prepare(
    'UPDATE subscriptions SET save_offer_shown_at = ? WHERE id = ?'
  ).bind(new Date().toISOString(), subscriptionId).run();

  return Response.json({ offerToken: crypto.randomUUID() });
}
```

## Annual Reminder Dispatch via Queues

For trial-to-paid and free-to-paid conversions the rule requires an annual reminder of the recurring charge before the anniversary billing date. A scheduled Worker runs nightly, enqueues reminder jobs for subscriptions whose anniversary falls within the next 7 days, and records dispatch in D1. The Queue consumer sends the actual notification and writes a delivery receipt.

```ts
// src/scheduled/annual-reminders.ts
export async function dispatchAnnualReminders(env: Env, now: Date): Promise<void> {
  const windowStart = new Date(now); windowStart.setDate(windowStart.getDate() + 1);
  const windowEnd   = new Date(now); windowEnd.setDate(windowEnd.getDate() + 7);

  const due = await env.DB.prepare(`
    SELECT s.id, s.user_id, s.plan_amount_cents, s.plan_currency, s.conversion_date,
           u.email, u.preferred_channel
    FROM subscriptions s
    JOIN users u ON u.id = s.user_id
    WHERE s.type IN ('trial_converted','free_converted')
      AND s.status = 'active'
      AND strftime('%m-%d', s.conversion_date) BETWEEN ? AND ?
      AND NOT EXISTS (
        SELECT 1 FROM reminder_log r
        WHERE r.sub_id = s.id AND strftime('%Y', r.sent_at) = strftime('%Y', 'now')
      )
  `).bind(
    windowStart.toISOString().slice(5, 10),
    windowEnd.toISOString().slice(5, 10)
  ).all<Record<string, unknown>>();

  for (const row of due.results) {
    await env.CANCEL_QUEUE.send({
      type: 'ANNUAL_REMINDER',
      subscriptionId: row.id,
      userId: row.user_id,
      email: row.email,
      amountCents: row.plan_amount_cents,
      currency: row.plan_currency,
      channel: row.preferred_channel ?? 'email',
    });
    await env.DB.prepare(
      `INSERT INTO reminder_log (sub_id, queued_at, status) VALUES (?, ?, 'queued')`
    ).bind(row.id, new Date().toISOString()).run();
  }
}

// wrangler.toml cron: "0 6 * * *"
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    await dispatchAnnualReminders(env, new Date());
  },
};
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  acquisition_channel TEXT NOT NULL DEFAULT 'web',
  type TEXT NOT NULL DEFAULT 'paid',
  plan_amount_cents INTEGER,
  plan_currency TEXT DEFAULT 'USD',
  conversion_date TEXT,
  save_offer_shown_at TEXT,
  cancelled_at TEXT,
  cancel_channel TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cancel_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sub_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  cancelled_at TEXT NOT NULL,
  channel TEXT NOT NULL,
  cross_channel INTEGER NOT NULL DEFAULT 0,
  save_offer_shown INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reminder_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sub_id TEXT NOT NULL,
  queued_at TEXT NOT NULL,
  sent_at TEXT,
  status TEXT NOT NULL DEFAULT 'queued'
);

CREATE TABLE IF NOT EXISTS compliance_violations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  sub_id TEXT,
  detected_at TEXT NOT NULL,
  detail TEXT
);
```

## Anti-patterns

- Presenting a "are you sure?" modal that requires a second button click before calling the cancel API — this adds a step beyond what the rule allows if the first click is not the cancel submission.
- Routing mobile subscribers to a web-only cancel URL when they subscribed via in-app — same-channel means native app must have a native cancel path.
- Setting `save_offer_shown_at` only on acceptance; it must be set on presentation so repeat-offer prevention works even if the user dismissed.
- Delaying cancellation effective date to end-of-billing-period without clearly disclosing this to the consumer at the moment of cancellation.

## Gotchas

- Apple/Google in-app purchases are governed by App Store and Play Store rules respectively; the FTC rule creates a parallel obligation for your own subscription management but does not override platform rules.
- The "simple mechanism" requirement applies to each channel independently — a link in a billing email must itself lead to a one-click cancel page.
- Annual reminders must state the amount, frequency, and the cancel mechanism; boilerplate renewal notices that omit the cancel URL are non-compliant.
- Cross-channel cancellations must still be honoured; the same-channel requirement is about providing parity, not exclusivity.

## Verification

```ts
// tests/click-to-cancel.spec.ts
import { expect, test } from 'vitest';

test('second save offer is rejected', async () => {
  // seed subscription with save_offer_shown_at already set
  const res = await fetch('/api/subscriptions/save-offer', {
    method: 'POST',
    headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscriptionId: 'sub_already_offered' }),
  });
  expect(res.status).toBe(403);
});

test('cancel completes in single POST', async () => {
  const res = await fetch('/api/subscriptions/cancel', {
    method: 'POST',
    headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscriptionId: 'sub_active' }),
  });
  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.cancelled).toBe(true);
  expect(body.effectiveDate).toBeTruthy();
});
```

## Related

- [auto-renewal-click-to-cancel-laws.md](auto-renewal-click-to-cancel-laws.md)
- [can-spam-casl-email-workers-queues.md](can-spam-casl-email-workers-queues.md)
- [ccpa-consumer-rights-operations.md](ccpa-cpra-consumer-rights-operations.md)
- [data-retention-automated-deletion-workers.md](data-retention-automated-deletion-workers.md)

## Sources

- 16 CFR Part 425 — FTC Negative Option Rule (Final Rule 2024): https://www.ecfr.gov/current/title-16/part-425
- FTC "Click to Cancel" Press Release (October 2024): https://www.ftc.gov/news-events/news/press-releases/2024/10/ftc-announces-final-click-to-cancel-rule
- Cloudflare D1 Documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues Documentation: https://developers.cloudflare.com/queues/
