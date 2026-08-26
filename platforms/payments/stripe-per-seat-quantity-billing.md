# Per-Seat Quantity-Based Subscription Billing with Stripe

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A SaaS product charges per active user seat (e.g. $12/seat/month for a team plan). When an admin invites the 6th team member the subscription quantity must jump from 5 to 6; when someone is removed it must drop. You need atomic seat tracking in D1, prorated mid-cycle billing via Stripe, and enforcement that blocks invite actions when the team is at its purchased-seat ceiling.

---

## Context

Stripe models per-seat billing through the `quantity` field on a `SubscriptionItem`. Updating quantity mid-cycle triggers automatic proration: Stripe credits unused time on the old quantity and charges for remaining time on the new quantity on the same invoice cycle. The invoice amount appears on the next invoice unless you pass `proration_behavior: 'always_invoice'` to bill immediately.

Key decisions:
- **Prorate immediately** (`always_invoice`): clean but surprising; a mid-month seat addition generates an immediate invoice.
- **Prorate at cycle end** (`create_prorations`): friendlier UX; the adjustment appears as a line item on the next regular invoice.
- **No proration** (`none`): charge the full new quantity from the next period; avoids confusing mid-cycle charges but can undercharge for the current period.

For example project/Orchords team plans the recommended approach is `create_prorations` (cycle-end credit/debit line item) with an immediate payment attempt only when crossing from a free tier to a paid tier.

---

## Section 1 — D1 Seat Tracking Schema

```sql
-- migration: 0015_seat_tracking.sql
CREATE TABLE IF NOT EXISTS team_seats (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id         TEXT    NOT NULL,
  user_id         TEXT    NOT NULL,
  role            TEXT    NOT NULL DEFAULT 'member',
  status          TEXT    NOT NULL DEFAULT 'active',  -- active | suspended | removed
  invited_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  activated_at    INTEGER,
  removed_at      INTEGER,
  UNIQUE(team_id, user_id)
);

CREATE TABLE IF NOT EXISTS team_subscriptions (
  team_id                   TEXT    PRIMARY KEY,
  stripe_subscription_id    TEXT    NOT NULL,
  stripe_subscription_item  TEXT    NOT NULL,   -- item id for the seats price
  purchased_seats           INTEGER NOT NULL DEFAULT 1,
  active_seats              INTEGER NOT NULL DEFAULT 1,
  plan_id                   TEXT    NOT NULL,
  updated_at                INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## Section 2 — Updating Stripe Quantity When Seats Change

```typescript
// workers/src/lib/seat-manager.ts
import Stripe from 'stripe';

export class SeatManager {
  constructor(
    private readonly stripe: Stripe,
    private readonly db: D1Database,
  ) {}

  /**
   * Add a seat: validates capacity, updates D1 atomically, then syncs Stripe.
   * Returns the new active seat count.
   */
  async addSeat(
    teamId: string,
    newUserId: string,
    role: 'admin' | 'member' = 'member',
  ): Promise<number> {
    // 1. Load current subscription state
    const ts = await this.db
      .prepare(
        'SELECT * FROM team_subscriptions WHERE team_id = ?1',
      )
      .bind(teamId)
      .first<{
        stripe_subscription_id: string;
        stripe_subscription_item: string;
        purchased_seats: number;
        active_seats: number;
      }>();

    if (!ts) throw new Error(`No subscription for team ${teamId}`);

    if (ts.active_seats >= ts.purchased_seats) {
      // Enforce hard ceiling — caller should have checked first
      throw Object.assign(new Error('Seat limit reached'), { code: 'SEAT_LIMIT' });
    }

    const newCount = ts.active_seats + 1;

    // 2. Insert seat record in D1 (unique constraint guards against double-add)
    await this.db
      .prepare(
        `INSERT INTO team_seats (team_id, user_id, role, activated_at)
         VALUES (?1, ?2, ?3, unixepoch())`,
      )
      .bind(teamId, newUserId, role)
      .run();

    await this.db
      .prepare(
        `UPDATE team_subscriptions
            SET active_seats = ?1, updated_at = unixepoch()
          WHERE team_id = ?2`,
      )
      .bind(newCount, teamId)
      .run();

    // 3. Sync quantity to Stripe (create proration, bill at cycle end)
    await this.stripe.subscriptionItems.update(
      ts.stripe_subscription_item,
      {
        quantity: newCount,
        proration_behavior: 'create_prorations',
      },
    );

    return newCount;
  }

  /**
   * Remove a seat: marks removed in D1, decrements active count, syncs Stripe.
   */
  async removeSeat(teamId: string, userId: string): Promise<number> {
    const ts = await this.db
      .prepare('SELECT * FROM team_subscriptions WHERE team_id = ?1')
      .bind(teamId)
      .first<{
        stripe_subscription_item: string;
        active_seats: number;
        purchased_seats: number;
      }>();

    if (!ts) throw new Error(`No subscription for team ${teamId}`);

    const newCount = Math.max(1, ts.active_seats - 1); // floor at 1 seat (owner)

    await this.db
      .prepare(
        `UPDATE team_seats
            SET status = 'removed', removed_at = unixepoch()
          WHERE team_id = ?1 AND user_id = ?2`,
      )
      .bind(teamId, userId)
      .run();

    await this.db
      .prepare(
        `UPDATE team_subscriptions
            SET active_seats = ?1, updated_at = unixepoch()
          WHERE team_id = ?2`,
      )
      .bind(newCount, teamId)
      .run();

    await this.stripe.subscriptionItems.update(
      ts.stripe_subscription_item,
      {
        quantity: newCount,
        proration_behavior: 'create_prorations',
      },
    );

    return newCount;
  }

  /**
   * Purchase additional seats without adding users yet (pre-purchase).
   */
  async purchaseSeats(teamId: string, totalSeats: number): Promise<void> {
    const ts = await this.db
      .prepare('SELECT * FROM team_subscriptions WHERE team_id = ?1')
      .bind(teamId)
      .first<{
        stripe_subscription_item: string;
        active_seats: number;
      }>();

    if (!ts) throw new Error(`No subscription for team ${teamId}`);

    // Bill immediately when expanding purchased seats (upgrade behaviour)
    await this.stripe.subscriptionItems.update(
      ts.stripe_subscription_item,
      {
        quantity: totalSeats,
        proration_behavior: 'always_invoice',
        payment_behavior: 'pending_if_incomplete',
      },
    );

    await this.db
      .prepare(
        `UPDATE team_subscriptions
            SET purchased_seats = ?1, updated_at = unixepoch()
          WHERE team_id = ?2`,
      )
      .bind(totalSeats, teamId)
      .run();
  }
}
```

---

## Section 3 — Seat Ceiling Guard Middleware

```typescript
// workers/src/middleware/seat-guard.ts
import type { MiddlewareHandler } from 'hono';

/**
 * Blocks team invite actions when active seats equal purchased seats.
 * Mount before invite and role-change routes.
 */
export const seatGuard: MiddlewareHandler = async (c, next) => {
  const teamId: string = c.get('teamId');

  const ts = await c.env.DB.prepare(
    `SELECT purchased_seats, active_seats FROM team_subscriptions WHERE team_id = ?1`,
  )
    .bind(teamId)
    .first<{ purchased_seats: number; active_seats: number }>();

  if (!ts) return c.json({ error: 'no_team_subscription' }, 402);

  c.set('seatMeta', ts);

  if (ts.active_seats >= ts.purchased_seats) {
    return c.json(
      {
        error: 'seat_limit_reached',
        purchased_seats: ts.purchased_seats,
        active_seats: ts.active_seats,
        upgrade_url: '/settings/billing?action=add-seats',
      },
      402,
    );
  }

  await next();
};
```

---

## Section 4 — Reconciling Stripe Webhook with D1 Seat Count

Stripe's `customer.subscription.updated` fires when quantity changes (e.g. via the Customer Portal or admin override). Always reconcile your D1 state from the webhook to stay in sync.

```typescript
// workers/src/webhooks/seat-reconciler.ts
import Stripe from 'stripe';

export async function reconcileSeats(
  db: D1Database,
  sub: Stripe.Subscription,
): Promise<void> {
  // Find the seat-based subscription item (filter by price metadata or known price id)
  const seatItem = sub.items.data.find(
    (item) =>
      item.price.metadata?.type === 'per_seat' ||
      item.price.id === (globalThis as unknown as { SEAT_PRICE_ID: string })
        .SEAT_PRICE_ID,
  );

  if (!seatItem) return;

  const stripePurchasedSeats = seatItem.quantity ?? 1;

  const ts = await db
    .prepare('SELECT team_id, active_seats FROM team_subscriptions WHERE stripe_subscription_id = ?1')
    .bind(sub.id)
    .first<{ team_id: string; active_seats: number }>();

  if (!ts) return;

  // Purchased seats drifted — update the ceiling
  if (stripePurchasedSeats !== undefined) {
    await db
      .prepare(
        `UPDATE team_subscriptions
            SET purchased_seats = ?1, updated_at = unixepoch()
          WHERE stripe_subscription_id = ?2`,
      )
      .bind(stripePurchasedSeats, sub.id)
      .run();
  }

  // If Stripe quantity is now below active seats, mark excess seats suspended
  if (stripePurchasedSeats < ts.active_seats) {
    // Suspend most-recently-added seats first
    await db
      .prepare(
        `UPDATE team_seats
            SET status = 'suspended'
          WHERE team_id = ?1
            AND status = 'active'
            AND user_id NOT IN (
              SELECT user_id FROM team_seats
               WHERE team_id = ?1 AND status = 'active'
               ORDER BY activated_at ASC
               LIMIT ?2
            )`,
      )
      .bind(ts.team_id, stripePurchasedSeats)
      .run();
  }
}
```

---

## Anti-patterns

- **Updating Stripe quantity and D1 non-atomically without compensation**: if the Stripe call succeeds but D1 update fails (or vice versa), your seat counts diverge. Use a try/catch that rolls back D1 or queues a reconciliation job.
- **Billing `always_invoice` for seat removals (downgrades)**: Stripe will try to collect a negative invoice immediately, which often fails. Generate credit notes instead, or let prorations apply at cycle end.
- **Setting quantity to 0**: Stripe interprets 0-quantity items as free but keeps the subscription active. Floor at 1.
- **Not filtering subscription items by price ID**: if a subscription has multiple items (base plan + seats add-on), updating the wrong item changes the wrong price.
- **Trusting only D1 for seat counts**: always treat the Stripe webhook as the source of truth for `purchased_seats` and reconcile on every `customer.subscription.updated`.

---

## Gotchas

- **Proration timing**: `create_prorations` does not trigger an immediate payment. The line item appears on the next invoice. If you need users to pay immediately for the added seat, use `always_invoice`.
- **`payment_behavior: 'pending_if_incomplete'`** vs `'error_if_incomplete'`: use `pending_if_incomplete` so a failed card does not block the seat from being provisioned — then rely on dunning to collect.
- **Trial periods and quantity**: if the subscription is in a trial, updating quantity does not bill. The new quantity takes effect when the trial ends.
- **Seat count in the Customer Portal**: Stripe's self-serve portal lets customers change quantity directly. Always handle `customer.subscription.updated` to sync back.
- **Downgrade below active seats**: Stripe does not automatically suspend users. Your webhook handler must decide which users to suspend when purchased seats drop below active seats.

---

## Verification

```bash
# 1. Check current subscription item quantity in Stripe
stripe subscription_items retrieve si_xxx | jq '.quantity'

# 2. Invite a new user (should increment quantity)
curl -X POST https://api.yourapp.com/teams/$TEAM_ID/invite \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -d '{"email":"newmember@example.com"}'

# 3. Confirm Stripe quantity updated
stripe subscription_items retrieve si_xxx | jq '.quantity'

# 4. Confirm D1 mirrors the change
wrangler d1 execute DB --command \
  "SELECT purchased_seats, active_seats FROM team_subscriptions WHERE team_id='$TEAM_ID';"

# 5. Hit the seat ceiling and confirm 402 response
# (invite one more than purchased_seats)
curl -X POST https://api.yourapp.com/teams/$TEAM_ID/invite \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -d '{"email":"overflow@example.com"}'
# Expected: 402 { "error": "seat_limit_reached" }

# 6. Check proration line items on next upcoming invoice
stripe invoices upcoming --customer cus_xxx | jq '.lines.data[] | select(.type=="invoiceitem")'
```

---

## Related

- `stripe-upgrade-downgrade.md` — proration mechanics in detail
- `stripe-proration-logic.md` — Stripe proration edge cases
- `stripe-subscription-lifecycle.md` — full subscription state machine
- `subscription-proration-edge-cases.md` — cycle-boundary edge cases
- `stripe-dunning-management.md` — recovering failed seat-expansion payments

---

## Sources

- Stripe Docs — Set quantities: https://stripe.com/docs/billing/subscriptions/quantities
- Stripe API — Update subscription item: https://stripe.com/docs/api/subscription_items/update
- Stripe Proration reference: https://stripe.com/docs/billing/subscriptions/prorations
- Cloudflare D1: https://developers.cloudflare.com/d1/
