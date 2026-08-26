# Refund Automation Pipeline with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Customer support processes refund requests manually, which is slow, inconsistent, and creates an audit gap between the Stripe refund and the internal accounting journal. You want to automate eligible refunds — within a configurable eligibility window, below a fraud-risk threshold, and within a refund amount cap — while routing edge cases to human review, restocking physical inventory via a Queue, creating double-entry accounting journal entries in D1, and notifying the customer on completion.

## Context

The pipeline is a Cloudflare Worker that:
1. Receives a refund request (from the customer portal or an internal admin API).
2. Runs an eligibility rules engine backed by D1.
3. Performs fraud-prevention scoring before auto-approving.
4. Calls the Stripe Refund API with an idempotency key.
5. Enqueues an inventory restock job for physical goods.
6. Writes a double-entry journal entry to D1.
7. Sends a customer notification via a Queue.

All steps after the Stripe call are idempotent so the Worker can be safely retried on transient failure.

## Solution

```typescript
import Stripe from 'stripe';
import { Env } from './types';

// ── Types ─────────────────────────────────────────────────────────────────────

type RefundRequest = {
  orderId: string;
  customerId: string;
  requestedAmount: number | null; // null = full refund
  reason: 'duplicate' | 'fraudulent' | 'requested_by_customer';
  items?: Array<{ sku: string; quantity: number }>; // for partial + restock
};

type EligibilityRule = {
  rule_id: string;
  description: string;
  max_age_hours: number;
  max_refund_cents: number;
  allow_partial: boolean;
  require_item_return: boolean;
};

type OrderRecord = {
  order_id: string;
  stripe_payment_intent_id: string;
  customer_id: string;
  amount_cents: number;
  refunded_cents: number;
  currency: string;
  placed_at: number; // Unix seconds
  has_physical_items: number; // SQLite boolean
  fraud_score: number; // 0.0–1.0
  status: string;
};

type RefundOutcome =
  | { status: 'approved'; refundId: string; amount: number }
  | { status: 'manual_review'; reason: string }
  | { status: 'rejected'; reason: string };

// ── Fraud prevention ──────────────────────────────────────────────────────────

const FRAUD_SCORE_AUTO_BLOCK = 0.75; // above this → manual review
const FRAUD_SCORE_HARD_BLOCK = 0.95; // above this → reject

async function getFraudScore(
  db: D1Database,
  customerId: string,
  orderId: string,
): Promise<number> {
  // Composite score from: refund rate in last 90 days, chargeback history,
  // account age, and the order's original fraud_score from the payment flow.
  const row = await db
    .prepare(
      `SELECT
         o.fraud_score                                         AS order_score,
         COALESCE(r.refund_count, 0)                          AS recent_refunds,
         COALESCE(c.chargeback_count, 0)                      AS chargebacks,
         CAST((unixepoch() - u.created_at) / 86400 AS REAL)  AS account_age_days
       FROM orders o
       JOIN users u ON u.customer_id = o.customer_id
       LEFT JOIN (
         SELECT customer_id, COUNT(*) AS refund_count
         FROM refunds
         WHERE created_at > unixepoch() - 90 * 86400
         GROUP BY customer_id
       ) r ON r.customer_id = o.customer_id
       LEFT JOIN (
         SELECT customer_id, COUNT(*) AS chargeback_count
         FROM chargebacks
         GROUP BY customer_id
       ) c ON c.customer_id = o.customer_id
       WHERE o.order_id = ?
       LIMIT 1`,
    )
    .bind(orderId)
    .first<{
      order_score: number;
      recent_refunds: number;
      chargebacks: number;
      account_age_days: number;
    }>();

  if (!row) return 0.5; // unknown order — flag for review

  // Simple weighted composite. Replace with your ML model score in production.
  const recencyPenalty = Math.min(row.recent_refunds / 5, 1) * 0.3;
  const chargebackPenalty = Math.min(row.chargebacks / 2, 1) * 0.4;
  const ageFactor = Math.max(0, 1 - row.account_age_days / 365) * 0.1;
  const composite = row.order_score * 0.2 + recencyPenalty + chargebackPenalty + ageFactor;

  return Math.min(composite, 1);
}

// ── Eligibility rules engine ──────────────────────────────────────────────────

async function checkEligibility(
  db: D1Database,
  order: OrderRecord,
  request: RefundRequest,
): Promise<{ eligible: boolean; reason?: string; rule?: EligibilityRule }> {
  // Load the applicable rule for this order's product category.
  const rule = await db
    .prepare(
      `SELECT er.*
       FROM eligibility_rules er
       JOIN order_product_categories opc ON opc.rule_id = er.rule_id
       WHERE opc.order_id = ?
       LIMIT 1`,
    )
    .bind(order.order_id)
    .first<EligibilityRule>();

  if (!rule) {
    return { eligible: false, reason: 'No eligibility rule found for this order category' };
  }

  const ageHours = (Date.now() / 1000 - order.placed_at) / 3600;
  if (ageHours > rule.max_age_hours) {
    return {
      eligible: false,
      reason: `Order is ${Math.round(ageHours)}h old; eligibility window is ${rule.max_age_hours}h`,
    };
  }

  const requestedAmount = request.requestedAmount ?? order.amount_cents - order.refunded_cents;
  if (requestedAmount > rule.max_refund_cents) {
    return {
      eligible: false,
      reason: `Requested refund ${requestedAmount}¢ exceeds rule max ${rule.max_refund_cents}¢`,
    };
  }

  const isPartial = requestedAmount < order.amount_cents - order.refunded_cents;
  if (isPartial && !rule.allow_partial) {
    return { eligible: false, reason: 'Partial refunds not allowed for this product category' };
  }

  if (order.status === 'refunded') {
    return { eligible: false, reason: 'Order already fully refunded' };
  }

  return { eligible: true, rule };
}

// ── Stripe refund ─────────────────────────────────────────────────────────────

async function issueStripeRefund(
  stripe: Stripe,
  order: OrderRecord,
  amount: number,
  reason: RefundRequest['reason'],
  idempotencyKey: string,
): Promise<Stripe.Refund> {
  return stripe.refunds.create(
    {
      payment_intent: order.stripe_payment_intent_id,
      amount,
      reason: reason === 'requested_by_customer' ? 'requested_by_customer' :
              reason === 'duplicate' ? 'duplicate' : 'fraudulent',
    },
    { idempotencyKey },
  );
}

// ── Accounting journal entry ──────────────────────────────────────────────────

async function createJournalEntry(
  db: D1Database,
  orderId: string,
  refundId: string,
  amount: number,
  currency: string,
): Promise<void> {
  // Double-entry: debit Revenue, credit Cash (both in cents).
  const now = Math.floor(Date.now() / 1000);
  const batchId = crypto.randomUUID();

  await db.batch([
    db
      .prepare(
        `INSERT INTO journal_entries
           (batch_id, account, entry_type, amount_cents, currency, reference_id, created_at)
         VALUES (?, 'revenue', 'debit', ?, ?, ?, ?)`,
      )
      .bind(batchId, amount, currency, refundId, now),
    db
      .prepare(
        `INSERT INTO journal_entries
           (batch_id, account, entry_type, amount_cents, currency, reference_id, created_at)
         VALUES (?, 'cash', 'credit', ?, ?, ?, ?)`,
      )
      .bind(batchId, amount, currency, refundId, now),
    db
      .prepare(
        `INSERT INTO refunds
           (stripe_refund_id, order_id, amount_cents, currency, created_at)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT (stripe_refund_id) DO NOTHING`,
      )
      .bind(refundId, orderId, amount, currency, now),
    db
      .prepare(
        `UPDATE orders
         SET refunded_cents = refunded_cents + ?,
             status = CASE WHEN refunded_cents + ? >= amount_cents THEN 'refunded' ELSE 'partial_refund' END
         WHERE order_id = ?`,
      )
      .bind(amount, amount, orderId),
  ]);
}

// ── Inventory restock ─────────────────────────────────────────────────────────

async function enqueueInventoryRestock(
  queue: Queue,
  orderId: string,
  items: Array<{ sku: string; quantity: number }>,
): Promise<void> {
  await queue.send({ type: 'inventory_restock', orderId, items, enqueuedAt: Date.now() });
}

// ── Customer notification ─────────────────────────────────────────────────────

async function enqueueCustomerNotification(
  queue: Queue,
  customerId: string,
  orderId: string,
  refundId: string,
  amount: number,
  currency: string,
): Promise<void> {
  await queue.send({
    type: 'refund_confirmed',
    customerId,
    orderId,
    refundId,
    amount,
    currency,
    enqueuedAt: Date.now(),
  });
}

// ── Main pipeline ─────────────────────────────────────────────────────────────

async function processRefund(
  stripe: Stripe,
  env: Env,
  request: RefundRequest,
): Promise<RefundOutcome> {
  // 1. Load order.
  const order = await env.DB.prepare(
    `SELECT * FROM orders WHERE order_id = ? AND customer_id = ? LIMIT 1`,
  )
    .bind(request.orderId, request.customerId)
    .first<OrderRecord>();

  if (!order) return { status: 'rejected', reason: 'Order not found or does not belong to customer' };

  // 2. Fraud check.
  const fraudScore = await getFraudScore(env.DB, request.customerId, request.orderId);
  if (fraudScore >= FRAUD_SCORE_HARD_BLOCK) {
    return { status: 'rejected', reason: `Fraud score ${fraudScore.toFixed(2)} exceeds hard block threshold` };
  }
  if (fraudScore >= FRAUD_SCORE_AUTO_BLOCK) {
    return { status: 'manual_review', reason: `Fraud score ${fraudScore.toFixed(2)} requires manual review` };
  }

  // 3. Eligibility check.
  const { eligible, reason } = await checkEligibility(env.DB, order, request);
  if (!eligible) return { status: 'rejected', reason: reason! };

  // 4. Determine amount.
  const refundAmount = request.requestedAmount ?? (order.amount_cents - order.refunded_cents);

  // 5. Stripe refund with idempotency key.
  const idempotencyKey = `refund-${request.orderId}-${refundAmount}`;
  const stripeRefund = await issueStripeRefund(
    stripe,
    order,
    refundAmount,
    request.reason,
    idempotencyKey,
  );

  // 6. Accounting journal entry (D1 batch — atomic).
  await createJournalEntry(env.DB, request.orderId, stripeRefund.id, refundAmount, order.currency);

  // 7. Inventory restock (physical items only).
  if (order.has_physical_items && request.items?.length) {
    await enqueueInventoryRestock(env.INVENTORY_QUEUE, request.orderId, request.items);
  }

  // 8. Notify customer.
  await enqueueCustomerNotification(
    env.NOTIFICATION_QUEUE,
    request.customerId,
    request.orderId,
    stripeRefund.id,
    refundAmount,
    order.currency,
  );

  return { status: 'approved', refundId: stripeRefund.id, amount: refundAmount };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<RefundRequest>();
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

    try {
      const outcome = await processRefund(stripe, env, body);
      const statusCode = outcome.status === 'approved' ? 200 :
                         outcome.status === 'manual_review' ? 202 : 422;
      return Response.json(outcome, { status: statusCode });
    } catch (err) {
      console.error('[refund] Pipeline error:', err);
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

## Implementation Details

**D1 schema (additions):**

```sql
CREATE TABLE eligibility_rules (
  rule_id             TEXT PRIMARY KEY,
  description         TEXT NOT NULL,
  max_age_hours       INTEGER NOT NULL DEFAULT 720, -- 30 days
  max_refund_cents    INTEGER NOT NULL DEFAULT 10000,
  allow_partial       INTEGER NOT NULL DEFAULT 1,
  require_item_return INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE order_product_categories (
  order_id TEXT NOT NULL,
  rule_id  TEXT NOT NULL REFERENCES eligibility_rules(rule_id),
  PRIMARY KEY (order_id, rule_id)
);

CREATE TABLE refunds (
  stripe_refund_id TEXT PRIMARY KEY,
  order_id         TEXT NOT NULL,
  amount_cents     INTEGER NOT NULL,
  currency         TEXT NOT NULL,
  created_at       INTEGER NOT NULL
);

CREATE TABLE journal_entries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id      TEXT NOT NULL,
  account       TEXT NOT NULL,
  entry_type    TEXT NOT NULL CHECK(entry_type IN ('debit','credit')),
  amount_cents  INTEGER NOT NULL,
  currency      TEXT NOT NULL,
  reference_id  TEXT NOT NULL,
  created_at    INTEGER NOT NULL
);

CREATE TABLE chargebacks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id TEXT NOT NULL,
  amount      INTEGER NOT NULL,
  created_at  INTEGER NOT NULL
);
```

**`wrangler.toml`:**

```toml
[[queues.producers]]
binding = "INVENTORY_QUEUE"
queue   = "inventory-restock"

[[queues.producers]]
binding = "NOTIFICATION_QUEUE"
queue   = "notifications"
```

## Anti-patterns

- **Issuing the Stripe refund inside a database transaction.** Stripe calls are not transactional. Call Stripe first, then write to D1. If D1 write fails, the idempotency key on the next retry will return the existing Stripe refund, keeping both sides consistent.
- **Auto-refunding without fraud scoring.** A compromised customer account can trigger unlimited refunds if there is no fraud gate. Always score before auto-approval.
- **Partial refund without tracking `refunded_cents`.** The `orders.refunded_cents` column must be incremented atomically (via `UPDATE orders SET refunded_cents = refunded_cents + ?`) — never read-modify-write from application code.
- **Sending customer notification before Stripe confirms.** Await the Stripe refund response before enqueuing the notification. A failed Stripe call must not send a confirmation email.

## Gotchas

- Stripe refunds are asynchronous for some payment methods (bank transfers). The returned `Refund` object may have `status: 'pending'`. Listen for the `charge.refund.updated` webhook to confirm settlement before updating your accounting records.
- The `ON CONFLICT (stripe_refund_id) DO NOTHING` on `refunds` insert is the idempotency guard for duplicate Worker invocations — the Stripe API returns the same `refund.id` for the same idempotency key.
- D1 `batch()` is atomic: either all statements succeed or none do. Use it for the journal entry + refund log + order update to avoid partial writes.
- `crypto.randomUUID()` is available globally in the Workers runtime. No import needed.

## Verification

```bash
# Submit a refund request:
curl -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ord_test","customerId":"cus_test","requestedAmount":null,"reason":"requested_by_customer"}'

# Check journal entries:
wrangler d1 execute payments --command \
  "SELECT * FROM journal_entries ORDER BY created_at DESC LIMIT 10;"

# Verify refund log:
wrangler d1 execute payments --command \
  "SELECT stripe_refund_id, order_id, amount_cents FROM refunds ORDER BY created_at DESC LIMIT 5;"

# Inspect inventory restock queue:
wrangler queues consumer messages inventory-restock
```

## Related

- `documentation/docs/policies/payments/workers-stripe-webhook-idempotency.md`
- `documentation/docs/policies/payments/workers-payment-retry-exponential-backoff.md`
- `documentation/docs/policies/payments/workers-tax-calculation-edge.md`

## Sources

- Stripe Refunds API: https://stripe.com/docs/api/refunds
- Stripe Idempotency Keys: https://stripe.com/docs/api/idempotent_requests
- Cloudflare D1 Batch: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Double-entry bookkeeping: https://en.wikipedia.org/wiki/Double-entry_bookkeeping
