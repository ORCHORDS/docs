# Subscription Lifecycle Management with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Managing subscription state across Stripe webhooks, renewal attempts, grace periods, and upgrade/downgrade events with stateless Workers leads to race conditions and split-brain state. A single `past_due → active` transition can be triggered simultaneously by a webhook delivery and a manual admin action, corrupting subscription records. You need strongly consistent, per-subscription orchestration with alarm-driven renewal attempts and a clear state machine.

## Context

Cloudflare Durable Objects (DOs) provide a single-threaded, strongly consistent execution environment per object instance. Each subscription gets its own DO instance, identified by its Stripe subscription ID. The DO:

- Maintains the canonical subscription state machine in its transactional storage.
- Schedules its own renewal alarm.
- Implements dunning logic (grace period + retry schedule).
- Writes the authoritative record to D1 after each transition for queryability.
- Handles proration calculations for mid-cycle plan changes.

## Solution

```typescript
import Stripe from 'stripe';
import { DurableObject } from 'cloudflare:workers';
import { Env } from './types';

// ── State machine ─────────────────────────────────────────────────────────────

type SubscriptionStatus =
  | 'trial'
  | 'active'
  | 'past_due'
  | 'in_grace'
  | 'canceled'
  | 'paused';

type SubscriptionState = {
  subscriptionId: string;
  customerId: string;
  planId: string;
  status: SubscriptionStatus;
  currentPeriodEnd: number; // Unix seconds
  trialEnd: number | null;
  graceDeadline: number | null; // Unix seconds — end of grace period
  dunningAttempt: number; // 0 = not in dunning
  pricePerUnit: number; // cents
  quantity: number;
  cancelAtPeriodEnd: boolean;
  history: Array<{ from: SubscriptionStatus; to: SubscriptionStatus; at: number; reason: string }>;
};

const GRACE_PERIOD_SECONDS = 60 * 60 * 24 * 7; // 7 days
const DUNNING_INTERVALS_SECONDS = [0, 86400, 259200, 604800]; // immediate, 1d, 3d, 7d

// ── Durable Object ────────────────────────────────────────────────────────────

export class SubscriptionDO extends DurableObject {
  private stripe: Stripe;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
  }

  private async getState(): Promise<SubscriptionState | null> {
    return (await this.ctx.storage.get<SubscriptionState>('state')) ?? null;
  }

  private async setState(state: SubscriptionState): Promise<void> {
    await this.ctx.storage.put('state', state);
    // Mirror to D1 for querying outside the DO.
    await this.syncToD1(state);
  }

  private async transition(
    state: SubscriptionState,
    to: SubscriptionStatus,
    reason: string,
  ): Promise<SubscriptionState> {
    const updated: SubscriptionState = {
      ...state,
      status: to,
      history: [
        ...state.history,
        { from: state.status, to, at: Math.floor(Date.now() / 1000), reason },
      ],
    };
    await this.setState(updated);
    return updated;
  }

  private async syncToD1(state: SubscriptionState): Promise<void> {
    const env = this.env as Env;
    await env.DB.prepare(
      `INSERT INTO subscriptions
         (stripe_subscription_id, customer_id, plan_id, status,
          current_period_end, grace_deadline, dunning_attempt, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())
       ON CONFLICT (stripe_subscription_id) DO UPDATE SET
         status            = excluded.status,
         current_period_end = excluded.current_period_end,
         grace_deadline    = excluded.grace_deadline,
         dunning_attempt   = excluded.dunning_attempt,
         updated_at        = excluded.updated_at`,
    )
      .bind(
        state.subscriptionId,
        state.customerId,
        state.planId,
        state.status,
        state.currentPeriodEnd,
        state.graceDeadline ?? null,
        state.dunningAttempt,
      )
      .run();
  }

  // ── Alarm handler ────────────────────────────────────────────────────────

  async alarm(): Promise<void> {
    const state = await this.getState();
    if (!state) return;

    const now = Math.floor(Date.now() / 1000);

    if (state.status === 'trial' && state.trialEnd && now >= state.trialEnd) {
      await this.handleTrialEnd(state);
      return;
    }

    if (state.status === 'active' && now >= state.currentPeriodEnd) {
      await this.handleRenewal(state);
      return;
    }

    if (state.status === 'in_grace') {
      await this.handleDunning(state);
      return;
    }
  }

  private async handleTrialEnd(state: SubscriptionState): Promise<void> {
    // Attempt first charge immediately on trial end.
    await this.handleRenewal(await this.transition(state, 'active', 'trial_ended'));
  }

  private async handleRenewal(state: SubscriptionState): Promise<void> {
    try {
      const invoice = await this.stripe.invoices.create({
        customer: state.customerId,
        subscription: state.subscriptionId,
        auto_advance: true,
      });
      await this.stripe.invoices.finalizeInvoice(invoice.id);
      await this.stripe.invoices.pay(invoice.id, {
        // idempotency key scoped to billing period
        idempotencyKey: `renew-${state.subscriptionId}-${state.currentPeriodEnd}`,
      } as Parameters<typeof this.stripe.invoices.pay>[1]);

      const next = await this.stripe.subscriptions.retrieve(state.subscriptionId);
      const updated = await this.transition(state, 'active', 'renewal_paid');
      await this.setState({
        ...updated,
        currentPeriodEnd: next.current_period_end,
        dunningAttempt: 0,
        graceDeadline: null,
      });

      // Schedule next renewal alarm.
      await this.ctx.storage.setAlarm(
        new Date((next.current_period_end + 60) * 1000), // 60s after period end
      );
    } catch (err) {
      console.error(`[DO] Renewal failed for ${state.subscriptionId}:`, err);
      const grace = await this.transition(state, 'in_grace', 'renewal_payment_failed');
      await this.setState({
        ...grace,
        graceDeadline: Math.floor(Date.now() / 1000) + GRACE_PERIOD_SECONDS,
        dunningAttempt: 0,
      });
      // Start dunning immediately.
      await this.ctx.storage.setAlarm(new Date(Date.now() + 1_000));
    }
  }

  private async handleDunning(state: SubscriptionState): Promise<void> {
    const now = Math.floor(Date.now() / 1000);

    if (state.graceDeadline && now > state.graceDeadline) {
      await this.transition(state, 'canceled', 'grace_period_expired');
      await this.stripe.subscriptions.cancel(state.subscriptionId);
      return;
    }

    try {
      await this.stripe.invoices.pay(
        (await this.stripe.invoices.list({ subscription: state.subscriptionId, limit: 1 })).data[0].id,
        { idempotencyKey: `dunning-${state.subscriptionId}-attempt-${state.dunningAttempt}` } as Parameters<typeof this.stripe.invoices.pay>[1],
      );
      const recovered = await this.transition(state, 'active', 'dunning_payment_succeeded');
      const next = await this.stripe.subscriptions.retrieve(state.subscriptionId);
      await this.setState({
        ...recovered,
        currentPeriodEnd: next.current_period_end,
        dunningAttempt: 0,
        graceDeadline: null,
      });
      await this.ctx.storage.setAlarm(new Date((next.current_period_end + 60) * 1000));
    } catch {
      const nextAttempt = state.dunningAttempt + 1;
      if (nextAttempt >= DUNNING_INTERVALS_SECONDS.length) {
        // Exhausted dunning schedule — wait out the rest of the grace period.
        return;
      }
      const nextRunMs = Date.now() + DUNNING_INTERVALS_SECONDS[nextAttempt] * 1000;
      await this.setState({ ...state, dunningAttempt: nextAttempt });
      await this.ctx.storage.setAlarm(new Date(nextRunMs));
    }
  }

  // ── Proration for mid-cycle upgrade/downgrade ─────────────────────────────

  private calcProration(
    state: SubscriptionState,
    newPricePerUnit: number,
    newQuantity: number,
  ): number {
    const now = Math.floor(Date.now() / 1000);
    const periodLength = state.currentPeriodEnd - (state.currentPeriodEnd - 30 * 24 * 3600); // approx
    const remaining = Math.max(state.currentPeriodEnd - now, 0);
    const fraction = remaining / (30 * 24 * 3600);

    const currentCharge = state.pricePerUnit * state.quantity;
    const newCharge = newPricePerUnit * newQuantity;
    const credit = currentCharge * fraction;
    const debit = newCharge * fraction;
    return Math.round(debit - credit); // positive = customer owes more
  }

  // ── HTTP interface ────────────────────────────────────────────────────────

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/init') {
      const body = await request.json<Omit<SubscriptionState, 'history' | 'dunningAttempt' | 'graceDeadline'>>();
      const state: SubscriptionState = {
        ...body,
        dunningAttempt: 0,
        graceDeadline: null,
        history: [{ from: 'trial', to: body.status, at: Math.floor(Date.now() / 1000), reason: 'initialized' }],
      };
      await this.setState(state);

      const alarmTime = state.trialEnd
        ? new Date(state.trialEnd * 1000)
        : new Date((state.currentPeriodEnd + 60) * 1000);
      await this.ctx.storage.setAlarm(alarmTime);

      return Response.json({ ok: true });
    }

    if (request.method === 'GET' && url.pathname === '/state') {
      const state = await this.getState();
      return Response.json(state);
    }

    if (request.method === 'POST' && url.pathname === '/upgrade') {
      const { newPlanId, newPricePerUnit, newQuantity } = await request.json<{
        newPlanId: string;
        newPricePerUnit: number;
        newQuantity: number;
      }>();
      const state = await this.getState();
      if (!state) return new Response('Not found', { status: 404 });

      const proration = this.calcProration(state, newPricePerUnit, newQuantity);
      await this.setState({
        ...state,
        planId: newPlanId,
        pricePerUnit: newPricePerUnit,
        quantity: newQuantity,
      });

      return Response.json({ proration, newPlanId });
    }

    return new Response('Not Found', { status: 404 });
  }
}

// ── Worker router ─────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const subId = url.searchParams.get('subscriptionId');
    if (!subId) return new Response('Missing subscriptionId', { status: 400 });

    const id = env.SUBSCRIPTION_DO.idFromName(subId);
    const stub = env.SUBSCRIPTION_DO.get(id);
    return stub.fetch(request);
  },
};
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE subscriptions (
  stripe_subscription_id TEXT PRIMARY KEY,
  customer_id            TEXT NOT NULL,
  plan_id                TEXT NOT NULL,
  status                 TEXT NOT NULL,
  current_period_end     INTEGER,
  grace_deadline         INTEGER,
  dunning_attempt        INTEGER NOT NULL DEFAULT 0,
  updated_at             INTEGER NOT NULL
);
```

**`wrangler.toml`:**

```toml
[[durable_objects.bindings]]
name      = "SUBSCRIPTION_DO"
class_name = "SubscriptionDO"

[[migrations]]
tag  = "v1"
new_classes = ["SubscriptionDO"]
```

**State machine transitions:**

```
trial ──────────────────────────────► active ──────────────► canceled
  └─ trial_end payment fails ───────► in_grace ─────────────► canceled (grace expired)
                                            └── payment succeeds ► active
```

**Dunning schedule:** immediate retry → +1 day → +3 days → +7 days → cancel at grace deadline (7 days). This totals up to 4 dunning attempts before the grace period expires.

## Anti-patterns

- **Using a stateless Worker for subscription state.** Two concurrent webhook deliveries for the same subscription will race and potentially apply transitions out of order. Only the DO's single-threaded execution model prevents this.
- **Setting alarms in wallclock time without accounting for `current_period_end` drift.** Always retrieve the updated subscription from Stripe after a successful renewal to get the canonical `current_period_end` rather than computing it locally.
- **Forgetting to cancel the Stripe subscription on grace period expiry.** The DO state machine must call `stripe.subscriptions.cancel()` to stop future Stripe invoices.

## Gotchas

- DO alarms fire at most once per scheduled time. If the Worker is updated mid-alarm, the alarm may not fire. Always verify alarm state on startup (`ctx.storage.getAlarm()`).
- `DurableObject` base class requires `cloudflare:workers` import, available in Workers runtime only. Avoid importing in Node.js test environments; mock it.
- `ctx.storage.put` and `ctx.storage.setAlarm` participate in the same implicit transaction within a single DO request. Ordering within a single `fetch` call is atomic.
- Proration calculation here uses 30-day approximation. For exact proration, retrieve `current_period_start` from Stripe and compute the exact fraction.

## Verification

```bash
# Init a subscription DO:
curl -X POST 'https://your-worker.workers.dev?subscriptionId=sub_test' \
  -H 'Content-Type: application/json' \
  -d '{"subscriptionId":"sub_test","customerId":"cus_test","planId":"plan_basic","status":"trial","currentPeriodEnd":9999999999,"trialEnd":1000000,"cancelAtPeriodEnd":false,"pricePerUnit":999,"quantity":1}'

# Read state:
curl 'https://your-worker.workers.dev?subscriptionId=sub_test'

# Query D1 for all past_due subscriptions:
wrangler d1 execute payments --command \
  "SELECT stripe_subscription_id, grace_deadline FROM subscriptions WHERE status = 'in_grace';"
```

## Related

- `documentation/categories/payments/workers-stripe-webhook-idempotency.md`
- `documentation/categories/payments/workers-payment-retry-exponential-backoff.md`
- `documentation/categories/payments/workers-refund-automation-pipeline.md`

## Sources

- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare DO Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Stripe Subscription Lifecycle: https://stripe.com/docs/billing/subscriptions/overview
- Stripe Dunning: https://stripe.com/docs/billing/automatic-collection
