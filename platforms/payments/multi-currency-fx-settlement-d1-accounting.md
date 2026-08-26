# Multi-Currency FX Settlement Accounting with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your platform charges customers in multiple presentment currencies (EUR, GBP,
JPY, BRL) but your company books and reports in a single functional currency
(USD). You need to track:

1. FX gains and losses as exchange rates fluctuate between charge date and
   settlement date.
2. A per-currency ledger in D1 so every payout reconciles exactly to the pence.
3. A P&L report that breaks out realised FX gain/loss separately from revenue.

---

## Context

When Stripe settles a EUR charge to your USD bank account, two distinct exchange
rates are involved:

- **Transaction rate** — the rate Stripe applied at charge time (recorded in
  `charge.currency` and `balance_transaction.exchange_rate`).
- **Payout rate** — the rate applied when Stripe converts the EUR balance to USD
  during the payout.

The difference between these two rates creates a **realised FX gain or loss**
that must appear in your accounts. For currencies where Stripe pays out in the
presentment currency (e.g., EUR SEPA payouts to a EUR bank account), the FX
conversion happens when you subsequently convert to USD — at which point it is
an **unrealised** gain/loss until that conversion settles.

GAAP / IFRS requirements:
- Record revenue at the **spot rate on transaction date**.
- Remeasure foreign-currency monetary items (receivables, balances) at the rate
  on the **balance sheet date** → unrealised FX.
- Record **realised FX** on the settlement/conversion date.

This article focuses on the **cash accounting** variant common in early-stage
SaaS: record FX at charge time, then compare to actual payout rate and record
the delta.

---

## D1 Schema

```sql
-- migrations/0002_fx_ledger.sql

CREATE TABLE IF NOT EXISTS fx_transactions (
  id                TEXT PRIMARY KEY,       -- Stripe balance_transaction.id
  charge_id         TEXT,
  customer_id       TEXT,
  presentment_amt   INTEGER NOT NULL,       -- in presentment currency minor units
  presentment_cur   TEXT NOT NULL,          -- ISO 4217, e.g. 'EUR'
  functional_amt    INTEGER NOT NULL,       -- converted to USD cents at tx rate
  tx_rate           REAL NOT NULL,          -- USD/presentment at charge time
  stripe_fee_usd    INTEGER NOT NULL,       -- Stripe fee in USD cents
  net_functional    INTEGER NOT NULL,       -- functional_amt - stripe_fee_usd
  created_at        INTEGER NOT NULL        -- unix ms
);

CREATE TABLE IF NOT EXISTS fx_payouts (
  payout_id         TEXT PRIMARY KEY,       -- Stripe payout.id
  currency          TEXT NOT NULL,
  gross_presentment INTEGER NOT NULL,       -- total presentment units paid out
  payout_rate       REAL,                   -- USD/presentment at payout time (null if native currency payout)
  gross_usd         INTEGER,               -- gross in USD cents (null if not converted)
  settled_at        INTEGER                 -- unix ms
);

CREATE TABLE IF NOT EXISTS fx_gain_loss (
  id                TEXT PRIMARY KEY,
  payout_id         TEXT NOT NULL REFERENCES fx_payouts(payout_id),
  currency          TEXT NOT NULL,
  booked_usd        INTEGER NOT NULL,       -- sum of functional_amt for included txs
  settled_usd       INTEGER NOT NULL,       -- gross_usd after fees from payout
  realised_delta    INTEGER NOT NULL,       -- settled_usd - booked_usd (+ = gain)
  recorded_at       INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fx_tx_currency ON fx_transactions(presentment_cur);
CREATE INDEX IF NOT EXISTS idx_fx_tx_created  ON fx_transactions(created_at);
```

---

## Worker: Ingest Stripe Balance Transactions

```typescript
// src/fx-ingest.ts
import Stripe from 'stripe';

interface Env {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
}

/**
 * Called from a Stripe webhook handler when event type is
 * charge.succeeded or payment_intent.payment_failed (for refunds).
 */
export async function ingestBalanceTransaction(
  balanceTxId: string,
  env: Env,
): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const bt = await stripe.balanceTransactions.retrieve(balanceTxId);

  // Skip USD transactions — no FX exposure
  if (bt.currency === 'usd') return;

  const presentmentAmt = bt.amount;                    // e.g., 10000 = 100.00 EUR
  const functionalAmt  = Math.round(bt.amount * (bt.exchange_rate ?? 1) * 100) / 100;
  // bt.fee is already in the account's settlement currency (USD cents)
  const stripeFeeUsd   = bt.fee;
  const netFunctional  = Math.round(functionalAmt - stripeFeeUsd);

  await env.DB.prepare(
    `INSERT OR IGNORE INTO fx_transactions
       (id, charge_id, presentment_amt, presentment_cur, functional_amt,
        tx_rate, stripe_fee_usd, net_functional, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      bt.id,
      typeof bt.source === 'string' ? bt.source : bt.source?.id ?? null,
      presentmentAmt,
      bt.currency.toUpperCase(),
      Math.round(functionalAmt),
      bt.exchange_rate ?? 1,
      stripeFeeUsd,
      netFunctional,
      bt.created * 1000,
    )
    .run();
}
```

---

## Worker: Ingest Payout and Calculate Realised FX Gain/Loss

```typescript
// src/fx-payout.ts
import Stripe from 'stripe';
import { nanoid } from 'nanoid';

export async function ingestPayout(payoutId: string, env: Env): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const payout = await stripe.payouts.retrieve(payoutId);

  if (payout.status !== 'paid') return;  // wait for final state

  // For automatic payouts Stripe records an exchange_rate on the payout object
  // when it converts from a presentment currency to USD.
  const payoutRate  = (payout as any).exchange_rate as number | null;
  const currency    = payout.currency.toUpperCase();
  const grossPresentment = payout.amount;
  const grossUsd    = payoutRate
    ? Math.round(grossPresentment * payoutRate)
    : null;   // native-currency payout — no conversion at this stage

  await env.DB.prepare(
    `INSERT OR IGNORE INTO fx_payouts
       (payout_id, currency, gross_presentment, payout_rate, gross_usd, settled_at)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
    .bind(payoutId, currency, grossPresentment, payoutRate, grossUsd, payout.arrival_date * 1000)
    .run();

  if (grossUsd === null) return;  // no conversion, no realised FX to record

  // Sum up the booked USD for all transactions in this payout's window
  // Approximation: match by currency and time window (Stripe groups by payout period)
  const { results } = await env.DB.prepare(
    `SELECT SUM(net_functional) AS booked_usd
     FROM fx_transactions
     WHERE presentment_cur = ?
       AND created_at <= ?`,
  )
    .bind(currency, payout.arrival_date * 1000)
    .first<{ booked_usd: number | null }>();

  const bookedUsd = results?.booked_usd ?? 0;
  const realisedDelta = grossUsd - bookedUsd;

  await env.DB.prepare(
    `INSERT OR IGNORE INTO fx_gain_loss
       (id, payout_id, currency, booked_usd, settled_usd, realised_delta, recorded_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(nanoid(), payoutId, currency, bookedUsd, grossUsd, realisedDelta, Date.now())
    .run();

  console.log(
    `FX ${currency}: booked=$${(bookedUsd / 100).toFixed(2)} settled=$${(grossUsd / 100).toFixed(2)} delta=$${(realisedDelta / 100).toFixed(2)}`,
  );
}
```

---

## Webhook Router

```typescript
// src/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const sig = req.headers.get('stripe-signature') ?? '';
    const body = await req.text();
    let event: Stripe.Event;
    try {
      event = stripe.webhooks.constructEvent(body, sig, env.STRIPE_WEBHOOK_SECRET);
    } catch {
      return new Response('Bad signature', { status: 401 });
    }

    switch (event.type) {
      case 'balance_transaction.created':
        await ingestBalanceTransaction((event.data.object as any).id, env);
        break;
      case 'payout.paid':
        await ingestPayout((event.data.object as Stripe.Payout).id, env);
        break;
    }

    return new Response('ok');
  },
};
```

---

## Reporting Query: Monthly FX P&L

```sql
SELECT
  strftime('%Y-%m', datetime(recorded_at / 1000, 'unixepoch')) AS month,
  currency,
  SUM(booked_usd)    / 100.0 AS booked_usd,
  SUM(settled_usd)   / 100.0 AS settled_usd,
  SUM(realised_delta)/ 100.0 AS realised_fx_gain_loss
FROM fx_gain_loss
GROUP BY month, currency
ORDER BY month DESC, currency;
```

---

## Anti-patterns

- **Using `charge.amount` directly as revenue** — for multi-currency charges,
  `charge.amount` is in the presentment currency. Always convert via
  `balance_transaction.exchange_rate` before recording functional-currency revenue.
- **Recording FX gain/loss per charge (not per payout)** — realised FX occurs
  at the payout/conversion event, not at charge time. Per-charge FX is an
  estimate until settlement.
- **Ignoring Stripe fees in functional currency** — Stripe deducts fees in USD.
  Your net revenue is `bt.net` converted to USD, not `bt.amount` converted.
- **Rounding to float** — always work in integer minor units (cents). Floating
  point accumulates errors across thousands of rows.

---

## Gotchas

- **`exchange_rate` on `BalanceTransaction` is null for USD transactions** —
  guard with `bt.exchange_rate ?? 1`.
- **Automatic payouts group transactions by settlement date** — manual payouts
  can include any subset. For precise attribution, use
  `stripe.payouts.listTransactions(payoutId)` to get exact membership.
- **Stripe's exchange rate is their mid-market rate minus a spread** — it is not
  the ECB or Bloomberg mid-market rate; document which rate source you use for
  audit purposes.
- **`payout.exchange_rate` is only set when Stripe converts the currency** — if
  you collect in EUR and payout to a EUR bank account, the field is null.
- **D1 has no native DECIMAL type** — store all amounts as INTEGER cents and
  convert at the presentation layer.

---

## Verification

```bash
# Confirm FX transactions are being ingested
wrangler d1 execute DB --command \
  "SELECT presentment_cur, COUNT(*), SUM(functional_amt)/100.0 AS usd_revenue FROM fx_transactions GROUP BY presentment_cur;"

# Check realised FX entries
wrangler d1 execute DB --command \
  "SELECT currency, SUM(realised_delta)/100.0 AS total_fx_gain_loss FROM fx_gain_loss GROUP BY currency;"

# Cross-check: Stripe Dashboard → Reports → Balance summary → FX conversions
```

---

## Related

- `multi-currency-handling.md`
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md`
- `multi-currency-rounding-fees.md`
- `stripe-revenue-recognition-d1-reporting.md`
- `double-entry-ledger-payments.md`
- `payment-reconciliation-settlement.md`

---

## Sources

- Stripe Balance Transactions: https://docs.stripe.com/reports/balance-transaction-types
- Stripe FX and presentment currency: https://docs.stripe.com/currencies/conversions
- IAS 21 — The Effects of Changes in Foreign Exchange Rates
- FASB ASC 830 — Foreign Currency Matters
- Cloudflare D1 best practices: https://developers.cloudflare.com/d1/best-practices/
