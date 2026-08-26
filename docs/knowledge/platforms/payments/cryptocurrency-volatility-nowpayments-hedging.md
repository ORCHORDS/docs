# cryptocurrency-volatility-nowpayments-hedging

**Date:** 2026-08-22
**Author:** example.com
**Repo:** example-org/example-repo
**Status:** published

## Symptom

example project accepts crypto payments via NOWPayments. Between the moment
a payment invoice is created (rate locked by NOWPayments) and the
moment the user's transaction is confirmed on-chain, the fiat-equivalent
value of the received crypto can fall below the order amount. Without
rate-risk controls, the platform settles less than the invoiced amount
and takes a revenue loss on every adverse price move.

## Context

NOWPayments creates a payment invoice by:
1. Taking the fiat amount (e.g. €29.00 for a example project subscription).
2. Fetching the current exchange rate via its rate feed.
3. Calculating the equivalent crypto amount (e.g. 0.000312 BTC).
4. Locking that crypto amount as the `pay_amount` on the invoice for
   the validity window.

The validity window for most coins is **20–60 minutes**. Solana and
other fast-finality chains confirm in seconds; Bitcoin and Ethereum can
take minutes to hours under congestion. The risk window is the time
between invoice creation and `payment_status: finished`.

Exchange rate risk flows:
```
Invoice created    → rate locked by NOWPayments
User sends payment → broadcast (1–60+ min delay)
Network confirms   → NOWPayments marks finished or partially_paid
Fiat settlement    → NOWPayments converts at settlement-time rate
```

If NOWPayments has **fixed-rate mode** enabled on your plan, the rate
is guaranteed for the invoice validity period — risk is borne by
NOWPayments. If fixed-rate mode is off (the default), you receive
the crypto amount and bear the conversion risk.

## IPN verification

NOWPayments IPN payloads must be HMAC-SHA512 verified before any
state mutation. See `payments/nowpayments-webhook-hmac-sha512.md`
for the full re-serialization pipeline. Summary:

```typescript
import { createHmac, timingSafeEqual } from 'node:crypto';

function verifySig(body: string, header: string,
                   secret: string): boolean {
  // Re-parse, deep-sort keys, compact re-stringify
  const sorted = JSON.stringify(deepSortKeys(JSON.parse(body)));
  const expected = createHmac('sha512', secret)
    .update(sorted).digest('hex');
  return timingSafeEqual(
    Buffer.from(expected), Buffer.from(header.toLowerCase()));
}
```

In the Cloudflare Workers runtime use `SubtleCrypto` instead:

```typescript
async function verifySigWorkers(
  rawBody: string, header: string, secret: string
): Promise<boolean> {
  const enc  = new TextEncoder();
  const key  = await crypto.subtle.importKey(
    'raw', enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-512' }, false, ['sign']);
  const sorted = JSON.stringify(deepSortKeys(JSON.parse(rawBody)));
  const sig  = await crypto.subtle.sign(
    'HMAC', key, enc.encode(sorted));
  const hex  = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0')).join('');
  // constant-time compare via XOR of equal-length hex strings
  const expected = enc.encode(hex);
  const actual   = enc.encode(header.toLowerCase().padEnd(hex.length,'0'));
  return timingSafeEqual(expected, actual);
}
```

## D1 exchange rate snapshot

At invoice creation time, snapshot the exchange rate into D1.
This records what rate was used so post-mortem analysis can
distinguish a price-drop loss from a mis-configured invoice.

```sql
CREATE TABLE IF NOT EXISTS crypto_rate_snapshots (
  snapshot_id    TEXT PRIMARY KEY,           -- UUID
  payment_id     TEXT NOT NULL,              -- NOWPayments payment_id
  order_id       TEXT NOT NULL,
  fiat_amount    INTEGER NOT NULL,           -- cents
  fiat_currency  TEXT NOT NULL,              -- EUR, USD, etc.
  crypto_amount  TEXT NOT NULL,              -- string to preserve precision
  crypto_currency TEXT NOT NULL,            -- BTC, SOL, etc.
  rate_at_creation REAL NOT NULL,           -- fiat per 1 crypto unit
  created_at     INTEGER NOT NULL,           -- Unix ms
  expiry         INTEGER NOT NULL,           -- Unix ms (invoice validity)
  settled_amount TEXT,                       -- actual received (from IPN)
  settled_at     INTEGER
);
```

```typescript
async function createPaymentWithSnapshot(
  orderId: string, fiatAmount: number, fiatCurrency: string,
  cryptoCurrency: string, env: Env
): Promise<NowPaymentsInvoice> {

  // 1. Estimate: fetch current rate
  const estimate = await fetch(
    `https://api.nowpayments.io/v1/estimate?` +
    `amount=${fiatAmount / 100}&` +
    `currency_from=${fiatCurrency.toLowerCase()}&` +
    `currency_to=${cryptoCurrency.toLowerCase()}`,
    { headers: { 'x-api-key': env.NOWPAYMENTS_API_KEY } }
  ).then(r => r.json()) as EstimateResponse;

  const cryptoAmount = estimate.estimated_amount;
  const rate = (fiatAmount / 100) / parseFloat(cryptoAmount);

  // 2. Create NOWPayments invoice
  const invoice = await fetch(
    'https://api.nowpayments.io/v1/payment', {
    method: 'POST',
    headers: {
      'x-api-key': env.NOWPAYMENTS_API_KEY,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      price_amount:   fiatAmount / 100,
      price_currency: fiatCurrency.toLowerCase(),
      pay_currency:   cryptoCurrency.toLowerCase(),
      order_id:       orderId,
      ipn_callback_url: env.IPN_URL,
    }),
  }).then(r => r.json()) as NowPaymentsInvoice;

  // 3. Snapshot rate into D1
  await env.DB.prepare(`
    INSERT INTO crypto_rate_snapshots
      (snapshot_id, payment_id, order_id, fiat_amount,
       fiat_currency, crypto_amount, crypto_currency,
       rate_at_creation, created_at, expiry)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    crypto.randomUUID(),
    invoice.payment_id,
    orderId,
    fiatAmount,
    fiatCurrency,
    String(invoice.pay_amount),
    cryptoCurrency,
    rate,
    Date.now(),
    Date.now() + 30 * 60_000   // 30-minute validity window
  ).run();

  return invoice;
}
```

## Crypto-to-fiat conversion timing risk window

```
Time                 Event
────────────────────────────────────────────────────────
T+0                  Invoice created; rate locked
T+0 → T+EXP         User expected to send payment
T+EXP                Invoice expires if unconfirmed
T+EXP+1             NOWPayments marks payment expired or
                     accepts late deposit at new rate
T+CONFIRM            tx confirmed on-chain;
                     payment_status → confirming / finished
T+SETTLE             NOWPayments converts received crypto
                     to fiat at time-of-settlement rate
```

For fixed-rate mode the risk window is zero — NOWPayments guarantees
the fiat equivalent. Without it, the settlement rate is the rate at
`T+SETTLE` which can be minutes or hours after `T+CONFIRM`.

## Partial payment and underpayment handling

```typescript
async function onIpnReceived(
  paymentId: string, status: string,
  actualAmount: string, env: Env): Promise<void> {

  const snap = await env.DB.prepare(
    `SELECT * FROM crypto_rate_snapshots WHERE payment_id = ?`
  ).bind(paymentId).first<RateSnapshot>();
  if (!snap) return; // unknown payment

  const expected = parseFloat(snap.crypto_amount);
  const actual   = parseFloat(actualAmount);
  const shortfall = expected - actual;  // in crypto units

  if (status === 'finished') {
    // Check for underpayment beyond tolerance
    const tolerancePct = 0.005; // 0.5%
    if (shortfall / expected > tolerancePct) {
      await handleUnderpayment(snap, actual, env);
    } else {
      await fulfillOrder(snap.order_id, env);
    }
    await env.DB.prepare(
      `UPDATE crypto_rate_snapshots
       SET settled_amount = ?, settled_at = ?
       WHERE payment_id = ?`
    ).bind(actualAmount, Date.now(), paymentId).run();
  }

  if (status === 'partially_paid') {
    await alertPartialPayment(snap.order_id, expected, actual, env);
  }
}

async function handleUnderpayment(
  snap: RateSnapshot, actual: number, env: Env) {
  // Options: issue partial credit, request top-up, refund
  const fiatReceived = actual * snap.rate_at_creation;
  await env.DB.prepare(
    `UPDATE orders SET status = 'partial', paid_fiat = ?
     WHERE id = ?`
  ).bind(Math.round(fiatReceived * 100), snap.order_id).run();
  // Notify customer with a top-up link
}
```

## Exchange rate risk mitigation strategies

| Strategy | How | Trade-off |
|---|---|---|
| Fixed-rate mode | Enable in NOWPayments plan | May cost more per transaction |
| Short validity window | Set `expiry_period` ≤ 15 min | User may not pay in time |
| Immediate liquidation | Use NOWPayments auto-conversion | Fiat exposure, no crypto upside |
| Buffer amount | Collect 101% of required amount | UX friction, partial-pay risk |
| Stablecoin preference | Accept USDC/USDT/SOL-USDC | Near-zero volatility |
| Rate snapshot + alert | Flag settlements < 98% of invoice fiat | Reactive, not preventive |

For example project subscriptions, **stablecoin preference** is the primary
hedge: present USDC (Solana) and USDT as the first crypto options.
Fixed-rate mode is the fallback for BTC and ETH orders above €100.

## Auto-conversion to fiat via NOWPayments

NOWPayments supports auto-conversion (custody → fiat bank transfer)
via their Custody/Settlement product. Configuration is per-currency
in the NOWPayments Dashboard → Settlements. When enabled:
- Received crypto is liquidated at market rate immediately after
  `finished` status.
- Settlement arrives in EUR/USD via SEPA or wire within 1–3 business days.
- Auto-conversion rate is NOWPayments' internal spread (typically 0.5–1%).

## Anti-patterns

- Reading the exchange rate from the IPN payload and using it for
  financial accounting — always read from the D1 snapshot created at
  invoice time.
- Fulfilling orders on `confirming` status — the payment can still
  fail; wait for `finished`.
- Setting `expiry_period` to 60+ minutes for BTC orders — gives
  a large adverse-rate window; use fixed-rate mode for long windows.
- Ignoring `partially_paid` IPN events — they continue arriving;
  without handling them they clog the IPN queue and delay `finished`.
- Storing `crypto_amount` as a REAL (float) in D1 — floating-point
  precision errors on small amounts; store as TEXT and parse when needed.

## Gotchas

- NOWPayments rounds `pay_amount` to the coin's precision; the estimate
  endpoint may return more decimal places. Always compare `pay_amount`
  from the invoice object, not the estimate.
- The IPN `payment_status` ladder is:
  `waiting → confirming → confirmed → sending → partially_paid →
  finished` (or `expired` / `failed` / `refunding`).
  Not all coins pass through every status; `finished` is the only
  reliable terminal success state.
- Rate snapshots must be created **before** returning the invoice URL
  to the user; a Worker crash after invoice creation but before the
  D1 write leaves a dangling payment with no snapshot.
- NOWPayments' minimum payment amounts change daily; always call the
  `/v1/min-amount` endpoint at invoice creation time rather than
  hard-coding minimums.
- `payment_id` in the IPN is a string, not an integer, in some NOWPayments
  API versions; store and compare as TEXT in D1.

## Verification checklist

- Create a test invoice in NOWPayments sandbox; confirm D1 snapshot
  row exists with matching `payment_id` and `rate_at_creation`.
- Simulate an IPN with `payment_status: finished` and `actually_paid`
  0.1% below `pay_amount`; confirm order fulfils (within tolerance).
- Simulate `actually_paid` 1% below `pay_amount`; confirm underpayment
  handler fires and order status is `partial`.
- Simulate `payment_status: partially_paid`; confirm alert is sent
  and no fulfilment occurs.
- Send an IPN with incorrect HMAC; confirm 403 and zero D1 writes.
- Run the expiry cron; confirm invoices older than `expiry` with
  status `waiting` are marked `expired` in D1.

## Related

- `payments/nowpayments-webhook-hmac-sha512.md`
- `payments/crypto-payments-nowpayments-settlement.md`
- `payments/nowpayments-callback-payment-intent-integrity.md`
- `payments/nowpayments-minimum-amount-and-estimate-validity.md`
- `payments/crypto-price-volatility-handling.md`

## Source URLs (verified 2026-08-22)

- https://documenter.getpostman.com/view/7907941/S1a32n38
- https://nowpayments.io/payment-tools/crypto-payment-api
- https://nowpayments.io/help/faq/what-is-fixed-rate-payment
- https://nowpayments.io/help/faq/what-is-underpayment
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
