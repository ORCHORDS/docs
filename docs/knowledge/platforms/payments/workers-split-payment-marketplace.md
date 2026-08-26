# Marketplace Split Payment Distribution via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your marketplace collects a payment from a buyer, takes a platform fee, and must distribute the remainder to one or more sellers via Stripe Connect. The split must be deterministic, auditable, resilient to webhook replay, and respectful of payout holds during open disputes.

---

## Context

Stripe Connect Transfers move money from your platform account to connected seller accounts. A configurable 7-day hold prevents premature payouts while the chargeback window is partly open. Dispute webhooks trigger an automatic hold extension. D1 tracks ledger entries for each split; a Scheduled Worker generates a daily reconciliation report to R2.

---

## Solution

```typescript
// workers-marketplace-split/src/index.ts

import { Env } from './types';
import { verifyStripeSignature } from './stripe-sig';
import { handlePaymentSucceeded } from './splits';
import { handleDisputeCreated } from './disputes';
import { generateReconciliation } from './reconcile';

export default {
  // Stripe webhook receiver
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const rawBody = await request.text();
    const sig = request.headers.get('stripe-signature') ?? '';

    const event = verifyStripeSignature(rawBody, sig, env.STRIPE_WEBHOOK_SECRET);
    if (!event) return new Response('Invalid signature', { status: 400 });

    // Idempotency guard
    const processed = await env.DB
      .prepare('SELECT 1 FROM processed_events WHERE event_id = ?')
      .bind(event.id)
      .first();
    if (processed) return new Response('Already processed', { status: 200 });

    switch (event.type) {
      case 'payment_intent.succeeded':
        ctx.waitUntil(handlePaymentSucceeded(env, event));
        break;
      case 'charge.dispute.created':
        ctx.waitUntil(handleDisputeCreated(env, event));
        break;
    }

    await env.DB
      .prepare('INSERT INTO processed_events (event_id, processed_at) VALUES (?, CURRENT_TIMESTAMP)')
      .bind(event.id)
      .run();

    return new Response('OK');
  },

  // Scheduled reconciliation
  async scheduled(_: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(generateReconciliation(env));
  },
};
```

```typescript
// workers-marketplace-split/src/splits.ts

import Stripe from 'stripe';
import { Env } from './types';

const PLATFORM_FEE_RATE = 0.10;  // 10 %
const PAYOUT_HOLD_DAYS = 7;

export interface SplitLine {
  sellerId: string;             // Stripe Connect account ID
  grossCents: number;           // seller's share before fee
  feeCents: number;
  netCents: number;
  payoutAfter: string;          // ISO date
}

export async function handlePaymentSucceeded(
  env: Env,
  event: Stripe.PaymentIntentSucceededEvent,
): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-04-10' });
  const pi = event.data.object;

  // Metadata must be set at checkout time:
  //   metadata.order_id, metadata.seller_splits = JSON ({ sellerId, shareCents }[])
  const orderId: string = pi.metadata?.order_id;
  const rawSplits: { sellerId: string; shareCents: number }[] = JSON.parse(
    pi.metadata?.seller_splits ?? '[]',
  );

  if (!rawSplits.length) return; // platform-only order, no split needed

  const payoutAfter = new Date(
    Date.now() + PAYOUT_HOLD_DAYS * 86_400_000,
  ).toISOString().slice(0, 10);

  const splits: SplitLine[] = rawSplits.map(({ sellerId, shareCents }) => {
    const feeCents = Math.round(shareCents * PLATFORM_FEE_RATE);
    return { sellerId, grossCents: shareCents, feeCents, netCents: shareCents - feeCents, payoutAfter };
  });

  // Record ledger entries and schedule transfers
  const inserts = env.DB.batch(
    splits.map((s) =>
      env.DB.prepare(
        `INSERT INTO seller_ledger
           (order_id, seller_id, gross_cents, fee_cents, net_cents, payout_after, status)
         VALUES (?, ?, ?, ?, ?, ?, 'pending')`,
      ).bind(orderId, s.sellerId, s.grossCents, s.feeCents, s.netCents, s.payoutAfter),
    ),
  );
  await inserts;

  // Queue KV markers so the payout Scheduled Worker picks them up
  await Promise.all(
    splits.map((s) =>
      env.KV.put(
        `payout:${s.payoutAfter}:${orderId}:${s.sellerId}`,
        JSON.stringify(s),
        { expirationTtl: (PAYOUT_HOLD_DAYS + 2) * 86_400 },
      ),
    ),
  );
}

export async function executePayout(
  stripe: Stripe,
  split: SplitLine,
  orderId: string,
): Promise<string> {
  const transfer = await stripe.transfers.create({
    amount: split.netCents,
    currency: 'usd',
    destination: split.sellerId,
    transfer_group: orderId,
    description: `Marketplace payout for order ${orderId}`,
  });
  return transfer.id;
}
```

```typescript
// workers-marketplace-split/src/disputes.ts

import Stripe from 'stripe';
import { Env } from './types';

const DISPUTE_HOLD_EXTRA_DAYS = 90;

export async function handleDisputeCreated(
  env: Env,
  event: Stripe.ChargeDisputeCreatedEvent,
): Promise<void> {
  const dispute = event.data.object;
  const chargeId = dispute.charge as string;

  // Find the order linked to this charge
  const row = await env.DB
    .prepare('SELECT order_id FROM orders WHERE stripe_charge_id = ?')
    .bind(chargeId)
    .first<{ order_id: string }>();

  if (!row) return;

  const newPayoutAfter = new Date(
    Date.now() + DISPUTE_HOLD_EXTRA_DAYS * 86_400_000,
  ).toISOString().slice(0, 10);

  // Extend hold and mark as disputed
  await env.DB
    .prepare(
      `UPDATE seller_ledger
         SET payout_after = ?, status = 'disputed'
       WHERE order_id = ? AND status = 'pending'`,
    )
    .bind(newPayoutAfter, row.order_id)
    .run();
}
```

```typescript
// workers-marketplace-split/src/payout-scheduler.ts
// Triggered as a separate Scheduled Worker: cron = "0 9 * * *" (daily 09:00 UTC)

import Stripe from 'stripe';
import { Env } from './types';
import { executePayout, SplitLine } from './splits';

export async function runDailyPayouts(env: Env): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-04-10' });
  const today = new Date().toISOString().slice(0, 10);

  const { results } = await env.DB
    .prepare(
      `SELECT id, order_id, seller_id, net_cents, payout_after
         FROM seller_ledger
        WHERE payout_after <= ? AND status = 'pending'
        LIMIT 500`,
    )
    .bind(today)
    .all<{ id: number; order_id: string; seller_id: string; net_cents: number; payout_after: string }>();

  for (const row of results) {
    try {
      const split: SplitLine = {
        sellerId: row.seller_id,
        grossCents: 0, // not needed for transfer
        feeCents: 0,
        netCents: row.net_cents,
        payoutAfter: row.payout_after,
      };
      const transferId = await executePayout(stripe, split, row.order_id);

      await env.DB
        .prepare(`UPDATE seller_ledger SET status = 'paid', transfer_id = ? WHERE id = ?`)
        .bind(transferId, row.id)
        .run();
    } catch (err) {
      console.error(`Payout failed for ledger row ${row.id}:`, err);
      // Leave as 'pending'; next daily run will retry
    }
  }
}
```

```typescript
// workers-marketplace-split/src/reconcile.ts

import { Env } from './types';

export async function generateReconciliation(env: Env): Promise<void> {
  const today = new Date().toISOString().slice(0, 10);

  const { results } = await env.DB
    .prepare(
      `SELECT
         seller_id,
         SUM(gross_cents)  AS gross_total,
         SUM(fee_cents)    AS fee_total,
         SUM(net_cents)    AS net_total,
         COUNT(*)          AS order_count,
         status
       FROM seller_ledger
      WHERE DATE(payout_after) = ?
      GROUP BY seller_id, status`,
    )
    .bind(today)
    .all();

  const report = JSON.stringify({ generatedAt: new Date().toISOString(), date: today, rows: results }, null, 2);
  await env.REPORTS_BUCKET.put(
    `reconciliation/${today}.json`,
    new TextEncoder().encode(report),
    { httpMetadata: { contentType: 'application/json' } },
  );
}
```

---

## Implementation Details

**D1 schema**:
```sql
CREATE TABLE seller_ledger (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id     TEXT NOT NULL,
  seller_id    TEXT NOT NULL,  -- Stripe Connect account
  gross_cents  INTEGER NOT NULL,
  fee_cents    INTEGER NOT NULL,
  net_cents    INTEGER NOT NULL,
  payout_after TEXT NOT NULL,  -- ISO date YYYY-MM-DD
  status       TEXT NOT NULL DEFAULT 'pending', -- pending|paid|disputed|refunded
  transfer_id  TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ledger_payout ON seller_ledger (payout_after, status);
CREATE INDEX idx_ledger_order  ON seller_ledger (order_id);

CREATE TABLE processed_events (
  event_id     TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);
```

**wrangler.toml**:
```toml
[triggers]
crons = ["0 9 * * *"]   # daily payout + reconciliation

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id   = "<D1_ID>"

[[kv_namespaces]]
binding = "KV"
id      = "<SPLITS_KV_ID>"

[[r2_buckets]]
binding = "REPORTS_BUCKET"
bucket_name = "reports"
```

---

## Anti-patterns

- **Do not transfer funds before the hold period** — chargebacks arrive up to 90 days post-transaction; a 7-day hold is minimum; extend on dispute automatically.
- **Do not use a single transfer for multiple sellers** — one transfer per seller account keeps failure scope minimal and Stripe's dashboard readable.
- **Do not calculate fees using floating-point division** — always use integer arithmetic on cents: `Math.round(shareCents * 0.10)` never `shareCents / 10`.
- **Do not skip idempotency** — webhook replays must not create duplicate ledger rows or duplicate Stripe transfers; use `processed_events` and `transfer_group` deduplication.

---

## Gotchas

- `stripe.transfers.create` requires the platform account to hold the funds (via `on_behalf_of` at charge time or direct charges). Confirm Connect mode (Standard / Express / Custom) before implementing.
- The Stripe `transfer_group` does not prevent duplicates by itself — Stripe's API allows multiple transfers with the same `transfer_group`. The D1 `processed_events` guard is your canonical idempotency control.
- D1 `batch()` is not transactional across multiple statements; if one insert fails, partial rows may exist. Use `BEGIN / COMMIT` inside a single `.exec()` call for atomic batches when consistency is critical.
- The KV payout marker is informational; the payout Scheduled Worker re-queries D1 as the source of truth. KV TTL just avoids accumulating stale keys indefinitely.

---

## Verification

```bash
# Simulate payment_intent.succeeded webhook
curl -X POST https://split-worker.example.com/webhook \
  -H 'stripe-signature: t=...,v1=...' \
  -H 'Content-Type: application/json' \
  -d '{"type":"payment_intent.succeeded","id":"evt_test","data":{"object":{"id":"pi_test","amount":10000,"metadata":{"order_id":"ord_1","seller_splits":"[{\"sellerId\":\"acct_sel\",\"shareCents\":9000}]"}}}}'

# Check ledger
npx wrangler d1 execute payments --command "SELECT * FROM seller_ledger WHERE order_id = 'ord_1'"
```

---

## Related

- `documentation/docs/policies/payments/stripe-webhook-idempotency.md`
- `documentation/docs/policies/payments/workers-invoice-generation-pdf.md`
- `documentation/docs/policies/payments/workers-payment-fraud-detection.md`
- Stripe Connect Transfers: https://stripe.com/docs/connect/separate-charges-and-transfers

---

## Sources

- https://stripe.com/docs/connect/transfers
- https://stripe.com/docs/connect/separate-charges-and-transfers
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
