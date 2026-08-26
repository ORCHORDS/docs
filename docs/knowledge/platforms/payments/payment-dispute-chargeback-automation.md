# payment-dispute-chargeback-automation

**Date:** 2026-08-22
**Author:** example.com
**Repo:** example-org/example-repo
**Status:** published

## Symptom

A example project subscriber files a chargeback after consuming a month of
access. Stripe creates a dispute, withdraws the disputed amount plus
a $15 dispute fee, and sets a deadline (typically 7–21 days) to
submit evidence. Without automation, evidence gathering is manual,
deadlines are missed, and the platform loses the dispute by default.

## Context

Stripe disputes arrive as `charge.dispute.created` webhook events.
Each dispute object tracks: `status`, `reason`, `evidence_due_by`
(Unix timestamp), `evidence` (submitted fields), and `charge` (the
original charge ID). The flow is:

`charge.dispute.created → Worker receives event → D1 state machine
records new dispute → Worker fetches context from R2 + D1 →
Worker auto-submits evidence via Stripe API → D1 status updated →
periodic cron monitors approaching deadlines → alert if unresolved`

example project uses Stripe Connect; disputes on connected-account charges
arrive on both the platform and connected-account webhook endpoints.
Always handle `charge.dispute.created` on the **connected-account**
endpoint (the one with `account` context) for accurate charge context.

## D1 dispute state machine

```sql
CREATE TABLE IF NOT EXISTS disputes (
  dispute_id      TEXT PRIMARY KEY,        -- dp_xxx
  charge_id       TEXT NOT NULL,
  amount          INTEGER NOT NULL,        -- cents
  currency        TEXT NOT NULL,
  reason          TEXT NOT NULL,           -- fraudulent | duplicate | etc.
  status          TEXT NOT NULL,           -- new | evidence_submitted |
                                           --  won | lost | under_review
  evidence_due_by INTEGER NOT NULL,        -- Unix seconds
  order_id        TEXT,
  evidence_r2_key TEXT,                    -- R2 object key for ZIP
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disputes_status
  ON disputes (status, evidence_due_by);
```

States and transitions:

```
new → evidence_submitted → under_review → won
                                        → lost
new → needs_response (if automation fails, alert fires)
```

## Webhook handler

```typescript
import Stripe from 'stripe';

async function onDisputeCreated(
  dispute: Stripe.Dispute, env: Env): Promise<void> {

  // Idempotency: already handled in outer processed_events guard
  // (see stripe-webhook-idempotency-workers.md)

  // 1. Persist the dispute record
  await env.DB.prepare(`
    INSERT OR IGNORE INTO disputes
      (dispute_id, charge_id, amount, currency, reason, status,
       evidence_due_by, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, 'new', ?, ?, ?)
  `).bind(
    dispute.id,
    dispute.charge as string,
    dispute.amount,
    dispute.currency,
    dispute.reason,
    dispute.evidence_details.due_by!,
    Date.now(),
    Date.now()
  ).run();

  // 2. Gather evidence asynchronously (Worker waitUntil context)
  await gatherAndSubmitEvidence(dispute, env);
}

async function onDisputeUpdated(
  dispute: Stripe.Dispute, env: Env): Promise<void> {
  const terminalStatuses = ['won', 'lost', 'warning_closed'];
  const status = terminalStatuses.includes(dispute.status)
    ? dispute.status : 'under_review';

  await env.DB.prepare(`
    UPDATE disputes SET status = ?, updated_at = ?
    WHERE dispute_id = ?
  `).bind(status, Date.now(), dispute.id).run();
}
```

## Evidence gathering pipeline

```typescript
async function gatherAndSubmitEvidence(
  dispute: Stripe.Dispute, env: Env): Promise<void> {

  const chargeId = dispute.charge as string;

  // 1. Load associated order from D1
  const order = await env.DB.prepare(
    `SELECT * FROM orders WHERE stripe_charge_id = ?`
  ).bind(chargeId).first<Order>();

  if (!order) {
    await alertDisputeNeedsManualReview(dispute.id,
      'no-order-found', env);
    return;
  }

  // 2. Fetch access logs from D1 (proves service delivery)
  const logs = await env.DB.prepare(
    `SELECT accessed_at, resource FROM access_log
     WHERE order_id = ? ORDER BY accessed_at ASC LIMIT 100`
  ).bind(order.id).all<AccessLog>();

  // 3. Retrieve original receipt PDF from R2
  const receiptKey = `receipts/${order.id}/receipt.pdf`;
  const receiptObj = await env.R2.get(receiptKey);
  const receiptBytes = receiptObj
    ? new Uint8Array(await receiptObj.arrayBuffer()) : null;

  // 4. Build evidence package and upload to R2
  const evidenceKey = await packageEvidence(
    dispute, order, logs.results, receiptBytes, env);

  // 5. Submit evidence to Stripe
  await submitEvidence(dispute, order, logs.results,
    evidenceKey, env);
}
```

## R2 evidence storage

```typescript
async function packageEvidence(
  dispute: Stripe.Dispute,
  order: Order,
  logs: AccessLog[],
  receipt: Uint8Array | null,
  env: Env
): Promise<string> {

  // Store a JSON bundle — attach PDF separately via Stripe File API
  const bundle = {
    disputeId:  dispute.id,
    orderId:    order.id,
    customerId: order.customer_id,
    amount:     dispute.amount,
    currency:   dispute.currency,
    reason:     dispute.reason,
    accessLogs: logs.map(l => ({
      accessedAt: new Date(l.accessed_at).toISOString(),
      resource:   l.resource,
    })),
    generatedAt: new Date().toISOString(),
  };

  const key = `disputes/${dispute.id}/evidence.json`;
  await env.R2.put(key, JSON.stringify(bundle, null, 2), {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { orderId: order.id, disputeReason: dispute.reason },
  });

  // If receipt exists, store alongside
  if (receipt) {
    await env.R2.put(
      `disputes/${dispute.id}/receipt.pdf`, receipt,
      { httpMetadata: { contentType: 'application/pdf' } }
    );
  }

  await env.DB.prepare(
    `UPDATE disputes SET evidence_r2_key = ? WHERE dispute_id = ?`
  ).bind(key, dispute.id).run();

  return key;
}
```

## Evidence submission to Stripe

```typescript
async function submitEvidence(
  dispute: Stripe.Dispute, order: Order,
  logs: AccessLog[], r2Key: string, env: Env
): Promise<void> {

  const stripe = new Stripe(env.STRIPE_SECRET_KEY);

  // Upload receipt PDF as a Stripe File (if available)
  let receiptFileId: string | undefined;
  const pdfObj = await env.R2.get(
    `disputes/${dispute.id}/receipt.pdf`);
  if (pdfObj) {
    const blob = await pdfObj.blob();
    const file = await stripe.files.create({
      purpose: 'dispute_evidence',
      file: { name: 'receipt.pdf', type: 'application/pdf',
               data: blob },
    });
    receiptFileId = file.id;
  }

  const accessSummary = logs.slice(0, 50).map(l =>
    `${new Date(l.accessed_at).toISOString()} – ${l.resource}`
  ).join('\n');

  await stripe.disputes.update(dispute.id, {
    evidence: {
      product_description:
        `example project subscription – ${order.plan_name}`,
      customer_name:        order.customer_name,
      customer_email_address: order.customer_email,
      billing_address:      order.billing_address,
      receipt:              receiptFileId,
      service_date:         String(Math.floor(
                              order.created_at / 1000)),
      service_documentation:
        `Access log (${logs.length} events):\n${accessSummary}`,
      uncategorized_text:
        `Order ID: ${order.id}. Customer accessed the service ` +
        `${logs.length} times between purchase and dispute.`,
    },
    submit: true,     // submit immediately; omit for draft
  });

  await env.DB.prepare(`
    UPDATE disputes SET status = 'evidence_submitted',
      updated_at = ? WHERE dispute_id = ?
  `).bind(Date.now(), dispute.id).run();
}
```

## Deadline monitoring (Cron Trigger)

```typescript
// Cron: '0 8 * * *'  (daily at 08:00 UTC)
async function monitorDisputeDeadlines(env: Env) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const warning48h = nowSeconds + 48 * 3600;

  const approaching = await env.DB.prepare(`
    SELECT dispute_id, evidence_due_by, order_id FROM disputes
    WHERE status NOT IN ('won','lost','warning_closed')
      AND evidence_due_by < ?
  `).bind(warning48h).all<DisputeRow>();

  for (const row of approaching.results) {
    const hoursLeft = Math.floor(
      (row.evidence_due_by - nowSeconds) / 3600);
    await alertDisputeDeadline(
      row.dispute_id, hoursLeft, row.order_id, env);
  }
}
```

## Reason-specific evidence strategy

| Dispute reason       | Key evidence                                      |
|----------------------|---------------------------------------------------|
| `fraudulent`         | IP logs, device fingerprint, email verification   |
| `duplicate`          | Show distinct charge IDs and dates                |
| `product_not_received` | Access log timestamps + resource names          |
| `subscription_canceled` | Cancellation email + effective date + access log |
| `credit_not_processed` | Refund record + Stripe refund object ID         |
| `unrecognized`       | Customer IP, login records, purchase email        |

For `fraudulent` disputes on Connect accounts, also attach
Stripe Radar risk score and rule evaluation from the charge object.

## Anti-patterns

- Submitting evidence with `submit: false` and forgetting to flip
  to `true` before the deadline — draft evidence is never sent.
- Storing evidence only in the Worker's temporary memory and not R2
  — the Worker terminates before the Stripe API call completes.
- Using `charge.dispute.created` from the platform-level webhook when
  the charge belongs to a connected account — the `charge` object
  will not expand correctly without the connected-account Stripe key.
- Auto-closing disputes with `charge.dispute.closed` without updating
  D1 — the cron continues alerting on already-closed disputes.

## Gotchas

- Stripe's evidence `due_by` is in **Unix seconds**, not milliseconds;
  mixing units causes off-by-1000x errors in deadline calculations.
- The `receipt` evidence field accepts a Stripe File ID, not a URL.
  Files must be uploaded via `stripe.files.create` with
  `purpose: 'dispute_evidence'` before referencing.
- A dispute's `status` can move backward from `under_review` to
  `needs_response` if Stripe reopens it; handle this in
  `onDisputeUpdated` to re-trigger evidence submission.
- Stripe limits total evidence text fields to 150 000 characters
  across all fields; truncate access logs in the summary.
- R2 object keys containing `/` are logical prefixes, not directories;
  `list({ prefix: 'disputes/dp_xxx/' })` returns all evidence files.

## Verification checklist

- Trigger `stripe trigger charge.dispute.created`; confirm D1 row
  with `status = 'new'` within 2 s.
- Confirm `status` advances to `evidence_submitted` if order + logs
  exist in D1.
- Confirm R2 contains `disputes/<id>/evidence.json` and optionally
  `disputes/<id>/receipt.pdf`.
- Fire the cron with `evidence_due_by` set to 1 hour from now;
  confirm alert fires.
- Trigger `charge.dispute.closed` with `status: won`; confirm D1
  row shows `won`.

## Related

- `payments/chargeback-representment-workflow.md`
- `payments/chargeback-prevention.md`
- `payments/stripe-webhook-idempotency-workers.md`
- `payments/payment-audit-logging.md`
- `payments/stripe-early-fraud-warning-lifecycle.md`

## Source URLs (verified 2026-08-22)

- https://docs.stripe.com/disputes
- https://docs.stripe.com/disputes/responding
- https://docs.stripe.com/api/disputes/update
- https://docs.stripe.com/api/files/create
- https://docs.stripe.com/connect/webhooks#disputes
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/d1/
