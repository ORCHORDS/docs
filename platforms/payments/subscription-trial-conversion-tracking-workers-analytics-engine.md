# Subscription Trial Conversion Tracking with Workers Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your free-trial funnel looks healthy in Stripe dashboards, but you cannot answer: "Which acquisition channel converts best?", "What is median days-to-convert by plan tier?", or "How many trials churned before conversion this week vs last?" Stripe's built-in reports do not capture UTM parameters, pricing page variant, or the cohort dimension you need. Cloudflare Workers Analytics Engine lets you emit structured events at the edge — with full context — and query them via the GraphQL API without a third-party analytics warehouse.

---

## Context

Cloudflare Workers Analytics Engine (AE) accepts time-series data blobs via `env.ANALYTICS.writeDataPoint()`. Each data point supports up to 20 `indexes` (filterable string dimensions) and 20 `doubles` (numeric measurements). Events are queryable via the Cloudflare GraphQL Analytics API with sub-minute latency on the write path and hourly aggregation on the read path.

The tracking strategy:

1. On trial start, emit a `trial_started` event with UTM params, plan, and pricing page variant.
2. On `customer.subscription.trial_will_end` webhook (three days before expiry), emit a `trial_ending` event.
3. On `customer.subscription.updated` webhook where `status` changes `trialing → active`, emit `trial_converted`.
4. On `customer.subscription.deleted` while still in trial or within 7 days of conversion, emit `trial_churned`.

---

## 1. Analytics Engine Binding and Type Declarations

```typescript
// src/types.ts

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
}

// Analytics Engine data point shape
export interface TrialEvent {
  // indexes: filterable string dimensions (max 20, max 64 chars each)
  indexes: [
    eventType: string,  // 'trial_started' | 'trial_ending' | 'trial_converted' | 'trial_churned'
    plan: string,       // 'starter' | 'pro' | 'enterprise'
    channel: string,    // UTM source, e.g. 'google' | 'organic' | 'referral'
    variant: string,    // A/B pricing page variant: 'control' | 'variant_a'
    currency: string,   // 'usd' | 'eur'
  ];
  doubles: [
    trialDurationDays: number,
    planAmountCents: number,
    daysToConvert: number,   // 0 on non-conversion events
  ];
}
```

---

## 2. Emitting Trial Started Events

```typescript
// src/events.ts

import { Env } from './types';

export function emitTrialStarted(
  env: Env,
  opts: {
    plan: string;
    channel: string;
    variant: string;
    currency: string;
    trialDurationDays: number;
    planAmountCents: number;
  }
): void {
  env.ANALYTICS.writeDataPoint({
    indexes: [
      'trial_started',
      opts.plan,
      opts.channel,
      opts.variant,
      opts.currency,
    ],
    doubles: [
      opts.trialDurationDays,
      opts.planAmountCents,
      0, // daysToConvert — unknown at trial start
    ],
  });
}

export function emitTrialConverted(
  env: Env,
  opts: {
    plan: string;
    channel: string;
    variant: string;
    currency: string;
    trialDurationDays: number;
    planAmountCents: number;
    daysToConvert: number;
  }
): void {
  env.ANALYTICS.writeDataPoint({
    indexes: [
      'trial_converted',
      opts.plan,
      opts.channel,
      opts.variant,
      opts.currency,
    ],
    doubles: [
      opts.trialDurationDays,
      opts.planAmountCents,
      opts.daysToConvert,
    ],
  });
}

export function emitTrialChurned(
  env: Env,
  opts: {
    plan: string;
    channel: string;
    variant: string;
    currency: string;
    trialDurationDays: number;
    planAmountCents: number;
  }
): void {
  env.ANALYTICS.writeDataPoint({
    indexes: [
      'trial_churned',
      opts.plan,
      opts.channel,
      opts.variant,
      opts.currency,
    ],
    doubles: [opts.trialDurationDays, opts.planAmountCents, 0],
  });
}
```

---

## 3. Stripe Webhook Handler

```typescript
// src/index.ts
import Stripe from 'stripe';
import { emitTrialStarted, emitTrialConverted, emitTrialChurned } from './events';
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
    const body   = await request.text();
    const sig    = request.headers.get('stripe-signature') ?? '';

    let event: Stripe.Event;
    try {
      event = await stripe.webhooks.constructEventAsync(body, sig, env.STRIPE_WEBHOOK_SECRET);
    } catch {
      return new Response('Bad signature', { status: 400 });
    }

    switch (event.type) {
      case 'customer.subscription.created': {
        const sub = event.data.object as Stripe.Subscription;
        if (sub.status !== 'trialing') break;

        const meta = sub.metadata ?? {};
        const trialEnd   = sub.trial_end ?? 0;
        const trialStart = sub.start_date ?? 0;
        const trialDays  = Math.round((trialEnd - trialStart) / 86400);

        emitTrialStarted(env, {
          plan:             meta.plan ?? 'unknown',
          channel:          meta.utm_source ?? 'organic',
          variant:          meta.pricing_variant ?? 'control',
          currency:         sub.currency ?? 'usd',
          trialDurationDays: trialDays,
          planAmountCents:  sub.items.data[0]?.price?.unit_amount ?? 0,
        });
        break;
      }

      case 'customer.subscription.updated': {
        const prev = event.data.previous_attributes as Partial<Stripe.Subscription>;
        const sub  = event.data.object as Stripe.Subscription;

        if (prev.status === 'trialing' && sub.status === 'active') {
          const meta = sub.metadata ?? {};
          const start   = sub.start_date ?? 0;
          const now     = Math.floor(Date.now() / 1000);
          const days    = Math.round((now - start) / 86400);

          emitTrialConverted(env, {
            plan:              meta.plan ?? 'unknown',
            channel:           meta.utm_source ?? 'organic',
            variant:           meta.pricing_variant ?? 'control',
            currency:          sub.currency ?? 'usd',
            trialDurationDays: days,
            planAmountCents:   sub.items.data[0]?.price?.unit_amount ?? 0,
            daysToConvert:     days,
          });
        }
        break;
      }

      case 'customer.subscription.deleted': {
        const sub  = event.data.object as Stripe.Subscription;
        const meta = sub.metadata ?? {};

        // Only emit churn if customer never converted (status was trialing at deletion)
        if ((event.data.previous_attributes as Partial<Stripe.Subscription>).status === 'trialing'
            || sub.status === 'trialing') {
          emitTrialChurned(env, {
            plan:              meta.plan ?? 'unknown',
            channel:           meta.utm_source ?? 'organic',
            variant:           meta.pricing_variant ?? 'control',
            currency:          sub.currency ?? 'usd',
            trialDurationDays: 0,
            planAmountCents:   sub.items.data[0]?.price?.unit_amount ?? 0,
          });
        }
        break;
      }
    }

    return Response.json({ received: true });
  },
};
```

---

## 4. Querying Trial Conversion Rate by Channel

```graphql
# GraphQL Analytics API — query trial_converted vs trial_started by channel
{
  viewer {
    accounts(filter: { accountTag: "YOUR_ACCOUNT_TAG" }) {
      trialConversions: analyticsEngineAdaptiveGroups(
        limit: 10
        filter: {
          datetimeGeq: "2026-08-01T00:00:00Z"
          datetimeLeq: "2026-08-23T23:59:59Z"
          blob1: "trial_converted"
        }
        orderBy: [count_DESC]
      ) {
        dimensions { blob2 }  # plan
        count
        avg { double3 }       # avg daysToConvert
      }
      trialStarts: analyticsEngineAdaptiveGroups(
        limit: 10
        filter: {
          datetimeGeq: "2026-08-01T00:00:00Z"
          datetimeLeq: "2026-08-23T23:59:59Z"
          blob1: "trial_started"
          blob3: "google"  # filter by channel
        }
        orderBy: [count_DESC]
      ) {
        dimensions { blob2 }
        count
      }
    }
  }
}
```

---

## 5. wrangler.toml Binding

```toml
# wrangler.toml
name = "trial-conversion-tracker"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "trial_events"
```

---

## Anti-patterns

- **Writing PII (customer ID, email) to Analytics Engine indexes** — AE data is queryable by anyone with account API access; store only anonymized dimension values.
- **Emitting conversion only from the frontend** — client-side events are dropped on ad blockers or page-close; the Stripe webhook is the authoritative source.
- **Using one mega-event type** — splitting `trial_started` / `trial_converted` / `trial_churned` into separate `blob1` values lets the GraphQL query filter without scanning all rows.
- **Storing UTM params only in session storage** — write them to Stripe subscription metadata on creation so they survive webhook delivery hours later.

---

## Gotchas

- Analytics Engine `writeDataPoint()` is fire-and-forget; it does not return a promise — do not `await` it.
- AE data is aggregated at hourly granularity in the GraphQL API; real-time row-level queries are not supported.
- Index strings (`blob1`–`blob20`) are case-sensitive in filters.
- If `trial_end` is `null` on the subscription, the customer has no trial — guard against this before computing `trialDurationDays`.
- `customer.subscription.updated` fires for every subscription change; check `previous_attributes.status` before emitting to avoid flooding with non-conversion events.

---

## Verification

```bash
# Trigger a test trial subscription via Stripe CLI
stripe trigger customer.subscription.created \
  --override customer.subscription.status=trialing

# Query AE via REST API
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob1, count() as cnt FROM trial_events WHERE timestamp > NOW() - INTERVAL '1' HOUR GROUP BY blob1"
```

---

## Related

- `stripe-trial-periods.md`
- `free-trial-credit-card-required.md`
- `freemium-to-paid-conversion.md`
- `churn-calculation.md`
- `mrr-arr-calculation.md`

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://docs.stripe.com/api/subscriptions/object#subscription_object-status
- https://docs.stripe.com/billing/subscriptions/trials
