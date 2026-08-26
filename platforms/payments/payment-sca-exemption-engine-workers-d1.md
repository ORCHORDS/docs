# Payment SCA Exemption Engine Workers D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Under PSD2, every electronic payment in the EEA and UK requires Strong Customer
Authentication (SCA) unless a valid exemption applies. Blindly triggering 3DS on
every transaction kills conversion. You need an exemption engine that evaluates
each payment against the exemption hierarchy, stamps the appropriate exemption
flag on the Stripe PaymentIntent or Checkout Session, and falls back to 3DS when
no exemption qualifies — all with audit trails in D1.

## Context

PSD2 SCA exemptions (Article 10-18 of RTS on SCA) that a payment service provider
can request:

| Exemption | Condition |
|-----------|-----------|
| `low_value` | ≤ €30, running total ≤ €100 or ≤ 5 consecutive uses since last SCA |
| `transaction_risk_analysis` (TRA) | PSP fraud rate below RTS threshold + transaction ≤ €500 |
| `recurring_transaction` | Fixed amount, fixed merchant, same payer — subsequent payments |
| `trusted_beneficiary` | Customer has whitelisted the merchant with their bank |
| `corporate` | Payment on a corporate/lodge card with limited payer network access |
| `secure_corporate` | Corporate card + virtual card with one-time credential |

The engine runs in a Cloudflare Worker at checkout time. Decision state is persisted
to D1 for audit, RTS threshold monitoring, and TRA fraud-rate tracking.

## D1 Schema

```sql
-- SCA exemption decisions per payment
CREATE TABLE sca_decisions (
  id               TEXT PRIMARY KEY,
  payment_intent_id TEXT,
  customer_id      TEXT NOT NULL,
  merchant_id      TEXT NOT NULL DEFAULT 'self',
  amount_cents     INTEGER NOT NULL,
  currency         TEXT NOT NULL,
  exemption_type   TEXT,               -- NULL = full SCA required
  exemption_granted INTEGER NOT NULL DEFAULT 0,
  challenged       INTEGER NOT NULL DEFAULT 0, -- bank rejected exemption, ran 3DS
  outcome          TEXT,               -- authenticated | declined | soft_decline
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_sca_customer ON sca_decisions(customer_id, created_at);
CREATE INDEX idx_sca_merchant ON sca_decisions(merchant_id, created_at);

-- Low-value exemption state per customer (rolling window)
CREATE TABLE lv_exemption_state (
  customer_id        TEXT PRIMARY KEY,
  consecutive_uses   INTEGER NOT NULL DEFAULT 0,
  rolling_total_cents INTEGER NOT NULL DEFAULT 0,
  last_sca_at        TEXT,
  last_use_at        TEXT
);

-- TRA fraud rate tracking (aggregate, not per-transaction)
-- Updated by a daily cron or webhook processor
CREATE TABLE tra_metrics (
  period       TEXT PRIMARY KEY,  -- YYYY-MM
  total_txns   INTEGER NOT NULL DEFAULT 0,
  fraud_txns   INTEGER NOT NULL DEFAULT 0,
  fraud_rate   REAL GENERATED ALWAYS AS (
    CASE WHEN total_txns > 0 THEN CAST(fraud_txns AS REAL) / total_txns ELSE 0 END
  ) STORED
);
```

## Exemption Engine

```typescript
// exemption-engine.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

type ExemptionType =
  | 'low_value'
  | 'transaction_risk_analysis'
  | 'recurring_transaction'
  | 'trusted_beneficiary'
  | 'none'; // full SCA required

interface ExemptionDecision {
  exemption: ExemptionType;
  requestExemption: boolean;
  reason: string;
  stripeFlag: string | null; // value for payment_method_options.card.request_three_d_secure or exemption field
}

interface PaymentContext {
  customerId: string;
  amountCents: number;
  currency: string;
  isRecurring: boolean;
  isInitialRecurring: boolean;  // first payment in a recurring series
  customerCountry: string;      // ISO-3166-1 alpha-2
  ipCountry: string;
  isTrustedBeneficiary: boolean; // customer has whitelisted merchant with their bank
  isCorporateCard: boolean;
}

// RTS TRA fraud rate thresholds (Article 18)
const TRA_THRESHOLDS: Record<number, number> = {
  100_00: 0.0013,   // ≤ €100: PSP fraud rate < 0.13%
  250_00: 0.0006,   // ≤ €250: PSP fraud rate < 0.06%
  500_00: 0.0001,   // ≤ €500: PSP fraud rate < 0.01%
};
const LOW_VALUE_LIMIT_CENTS = 3000;   // €30
const LOW_VALUE_ROLLING_LIMIT_CENTS = 10000; // €100
const LOW_VALUE_MAX_CONSECUTIVE = 5;

export async function evaluateExemption(
  env: Env,
  ctx: PaymentContext
): Promise<ExemptionDecision> {
  // SCA only applies to EEA/UK transactions
  const EEA_COUNTRIES = new Set([
    'AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU',
    'IE','IT','LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES',
    'SE','IS','LI','NO','GB',
  ]);

  if (!EEA_COUNTRIES.has(ctx.customerCountry)) {
    return {
      exemption: 'none',
      requestExemption: false,
      reason: 'Out of SCA scope (non-EEA)',
      stripeFlag: 'any', // Let Stripe decide
    };
  }

  // 1. Trusted beneficiary
  if (ctx.isTrustedBeneficiary) {
    return {
      exemption: 'trusted_beneficiary',
      requestExemption: true,
      reason: 'Merchant on customer trusted beneficiary list',
      stripeFlag: 'exemption=trusted_beneficiary',
    };
  }

  // 2. Recurring transaction (subsequent only)
  if (ctx.isRecurring && !ctx.isInitialRecurring) {
    return {
      exemption: 'recurring_transaction',
      requestExemption: true,
      reason: 'Fixed-amount recurring subscription subsequent payment',
      stripeFlag: 'exemption=recurring_transaction',
    };
  }

  // 3. Low-value exemption
  if (ctx.amountCents <= LOW_VALUE_LIMIT_CENTS) {
    const lvState = await getLvState(env, ctx.customerId);

    const rollingOk = lvState.rolling_total_cents + ctx.amountCents <= LOW_VALUE_ROLLING_LIMIT_CENTS;
    const consecutiveOk = lvState.consecutive_uses < LOW_VALUE_MAX_CONSECUTIVE;

    if (rollingOk && consecutiveOk) {
      return {
        exemption: 'low_value',
        requestExemption: true,
        reason: `LV: consecutive=${lvState.consecutive_uses}, rolling=${lvState.rolling_total_cents}`,
        stripeFlag: 'exemption=low_value',
      };
    }
  }

  // 4. Transaction Risk Analysis
  const traApplicable = await isTRAApplicable(env, ctx.amountCents);
  if (traApplicable) {
    return {
      exemption: 'transaction_risk_analysis',
      requestExemption: true,
      reason: 'PSP fraud rate within RTS TRA threshold',
      stripeFlag: 'exemption=transaction_risk_analysis',
    };
  }

  // No exemption qualifies
  return {
    exemption: 'none',
    requestExemption: false,
    reason: 'No qualifying exemption; SCA required',
    stripeFlag: 'automatic',
  };
}

async function getLvState(
  env: Env,
  customerId: string
): Promise<{ consecutive_uses: number; rolling_total_cents: number }> {
  const row = await env.DB.prepare(
    `SELECT consecutive_uses, rolling_total_cents, last_sca_at
     FROM lv_exemption_state WHERE customer_id = ?`
  ).bind(customerId).first() as {
    consecutive_uses: number;
    rolling_total_cents: number;
    last_sca_at: string | null;
  } | null;

  if (!row) return { consecutive_uses: 0, rolling_total_cents: 0 };

  // Rolling window resets after a successful SCA
  // (Article 11: counter resets when SCA is performed or cumulative limit exceeded)
  return {
    consecutive_uses: row.consecutive_uses,
    rolling_total_cents: row.rolling_total_cents,
  };
}

async function isTRAApplicable(env: Env, amountCents: number): Promise<boolean> {
  // Find applicable tier
  const tier = Object.keys(TRA_THRESHOLDS)
    .map(Number)
    .sort((a, b) => a - b)
    .find(limit => amountCents <= limit);

  if (!tier) return false; // above €500

  const threshold = TRA_THRESHOLDS[tier];
  const period = new Date().toISOString().slice(0, 7); // YYYY-MM

  const row = await env.DB.prepare(
    `SELECT fraud_rate FROM tra_metrics WHERE period = ?`
  ).bind(period).first() as { fraud_rate: number } | null;

  if (!row) return false; // No data — conservative: do not claim TRA

  return row.fraud_rate < threshold;
}
```

## Stripe Integration

```typescript
// checkout-worker.ts
import { evaluateExemption } from './exemption-engine';

async function createPaymentIntentWithExemption(
  env: Env,
  ctx: PaymentContext & { paymentMethod: string }
): Promise<{ clientSecret: string; requiresSca: boolean }> {
  const decision = await evaluateExemption(env, ctx);

  // Map exemption decision to Stripe request_three_d_secure param
  const requestThreeDS = decision.requestExemption ? 'automatic' : 'any';

  const params = new URLSearchParams({
    amount: String(ctx.amountCents),
    currency: ctx.currency.toLowerCase(),
    customer: ctx.customerId,
    payment_method: ctx.paymentMethod,
    confirm: 'true',
    'payment_method_options[card][request_three_d_secure]': requestThreeDS,
    ...(decision.requestExemption && decision.exemption !== 'none'
      ? { 'payment_method_options[card][exemption]': decision.exemption }
      : {}),
  });

  const resp = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params,
  });

  const pi = await resp.json() as {
    id: string;
    client_secret: string;
    status: string;
    next_action?: { type: string };
  };

  // Persist decision
  await env.DB.prepare(
    `INSERT INTO sca_decisions
       (id, payment_intent_id, customer_id, merchant_id, amount_cents,
        currency, exemption_type, exemption_granted)
     VALUES (?, ?, ?, 'self', ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    pi.id,
    ctx.customerId,
    ctx.amountCents,
    ctx.currency,
    decision.exemption === 'none' ? null : decision.exemption,
    decision.requestExemption ? 1 : 0,
  ).run();

  const requiresSca = pi.next_action?.type === 'use_stripe_sdk' ||
                      pi.status === 'requires_action';

  // Update LV state after exemption granted
  if (decision.exemption === 'low_value' && !requiresSca) {
    await incrementLvState(env, ctx.customerId, ctx.amountCents);
  }

  return { clientSecret: <redacted-secret> requiresSca };
}

async function incrementLvState(
  env: Env,
  customerId: string,
  amountCents: number
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO lv_exemption_state
       (customer_id, consecutive_uses, rolling_total_cents, last_use_at)
     VALUES (?, 1, ?, datetime('now'))
     ON CONFLICT(customer_id) DO UPDATE SET
       consecutive_uses = consecutive_uses + 1,
       rolling_total_cents = rolling_total_cents + excluded.rolling_total_cents,
       last_use_at = datetime('now')`
  ).bind(customerId, amountCents).run();
}

// Call this when SCA is performed successfully (reset LV counter)
async function resetLvState(env: Env, customerId: string): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO lv_exemption_state
       (customer_id, consecutive_uses, rolling_total_cents, last_sca_at, last_use_at)
     VALUES (?, 0, 0, datetime('now'), datetime('now'))
     ON CONFLICT(customer_id) DO UPDATE SET
       consecutive_uses = 0,
       rolling_total_cents = 0,
       last_sca_at = datetime('now'),
       last_use_at = datetime('now')`
  ).bind(customerId).run();
}
```

## TRA Fraud Rate Updater (Cron)

```typescript
// tra-updater.ts — runs daily via a Cron Trigger

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const period = new Date().toISOString().slice(0, 7);

    // Fetch fraud data from Stripe Radar / your fraud system
    // Here we count early_fraud_warnings as fraud signals
    const fraudCount = await countStripeFraudWarnings(env, period);
    const totalCount = await countTotalTransactions(env, period);

    await env.DB.prepare(
      `INSERT INTO tra_metrics (period, total_txns, fraud_txns)
       VALUES (?, ?, ?)
       ON CONFLICT(period) DO UPDATE SET
         total_txns = excluded.total_txns,
         fraud_txns = excluded.fraud_txns`
    ).bind(period, totalCount, fraudCount).run();
  },
};

async function countStripeFraudWarnings(env: Env, period: string): Promise<number> {
  const [year, month] = period.split('-').map(Number);
  const startTs = Math.floor(new Date(year, month - 1, 1).getTime() / 1000);
  const endTs = Math.floor(new Date(year, month, 1).getTime() / 1000);

  let count = 0;
  let startingAfter: string | null = null;

  do {
    const params = new URLSearchParams({
      'created[gte]': String(startTs),
      'created[lt]': String(endTs),
      limit: '100',
      ...(startingAfter ? { starting_after: startingAfter } : {}),
    });

    const resp = await fetch(`https://api.stripe.com/v1/radar/early_fraud_warnings?${params}`, {
      headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
    });
    const data = await resp.json() as { data: { id: string }[]; has_more: boolean };

    count += data.data.length;
    startingAfter = data.has_more ? data.data[data.data.length - 1].id : null;
  } while (startingAfter);

  return count;
}

async function countTotalTransactions(env: Env, period: string): Promise<number> {
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS n FROM sca_decisions
     WHERE strftime('%Y-%m', created_at) = ?`
  ).bind(period).first() as { n: number };
  return row.n;
}
```

## Anti-patterns

- **Claiming TRA without monitoring fraud rate**: RTS requires your PSP fraud rate
  to be demonstrably below the threshold. Claiming TRA blindly without tracking
  exposes you to regulatory fines and card scheme liability.
- **Not resetting the LV counter on SCA**: If you increment `consecutive_uses`
  without resetting on a successful 3DS challenge, you'll exempt transactions that
  should require SCA per Article 11.
- **Soft-declining silently**: When an issuer soft-declines an exemption request
  (Stripe `payment_intent.payment_failed` with code `authentication_required`),
  you must retry the payment with SCA — never just decline to the user without
  offering 3DS.
- **Applying SCA exemptions outside EEA/UK**: SCA is a PSD2 requirement scoped to
  EEA/UK transactions. Applying exemption logic to US transactions adds latency
  with no regulatory benefit.

## Gotchas

- Stripe does not expose a first-class `exemption` field on PaymentIntent creation
  for all exemption types. `low_value` and `transaction_risk_analysis` are
  communicated via `request_three_d_secure: 'automatic'` combined with Stripe
  Radar rules that detect the exemption conditions server-side. Confirm exact
  Stripe API parameters with the current Stripe docs for your account type.
- The LV exemption rolling counter is per-customer-per-PSP, not per-customer
  globally. If your customer pays multiple merchants through your platform, each
  platform counts separately.
- TRA is not available to all Stripe accounts by default; it may require Stripe
  Enterprise and a negotiated fraud rate SLA.
- `strftime('%Y-%m', datetime('now'))` in D1 uses UTC. Ensure your period
  calculations consistently use UTC to avoid month-boundary discrepancies.

## Verification

```bash
# Check LV exemption state for a customer
wrangler d1 execute <DB> --command \
  "SELECT * FROM lv_exemption_state WHERE customer_id='cus_xxx';"

# Exemption type distribution for the current month
wrangler d1 execute <DB> --command \
  "SELECT exemption_type, COUNT(*) AS n,
          SUM(exemption_granted) AS granted,
          SUM(challenged) AS challenged
   FROM sca_decisions
   WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
   GROUP BY exemption_type;"

# Current TRA fraud rate
wrangler d1 execute <DB> --command \
  "SELECT period, total_txns, fraud_txns, fraud_rate
   FROM tra_metrics ORDER BY period DESC LIMIT 3;"
```

## Related

- `psd2-sca-exemption-strategies.md` — High-level exemption strategy overview
- `sca-3d-secure-2-psd2-authentication.md` — 3DS2 authentication flows
- `3ds2-frictionless-flow-optimization.md` — Frictionless 3DS2 optimization
- `stripe-radar-fraud-rules.md` — Stripe Radar and early fraud warnings
- `stripe-early-fraud-warning-lifecycle.md` — EFW lifecycle handling

## Sources

- EBA RTS on SCA (EU 2018/389): https://eba.europa.eu/regulation-and-policy/payment-services-and-electronic-money/regulatory-technical-standards-on-strong-customer-authentication-and-secure-communication-under-psd2
- Stripe SCA documentation: https://stripe.com/docs/strong-customer-authentication
- Stripe exemptions: https://stripe.com/docs/strong-customer-authentication/exemptions
- Cloudflare D1: https://developers.cloudflare.com/d1/
