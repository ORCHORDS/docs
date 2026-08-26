# PayPal Payouts API Mass Disbursement with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to pay multiple recipients simultaneously — affiliate commissions, marketplace seller payouts, referral bonuses — using PayPal. The PayPal Payouts API supports batches of up to 15,000 items per request. Doing this from a Cloudflare Worker requires handling OAuth tokens, building the batch payload, persisting batch state in D1 for reconciliation, and processing status webhooks.

## Context

PayPal Payouts is a separate API from Orders. It uses the same OAuth2 client-credentials flow but targets `/v1/payments/payouts`. Batch items can be sent to email addresses, phone numbers, or PayPal account IDs. The API is asynchronous — the batch is queued on PayPal's side and item statuses arrive via webhook or polling. Worker-side state in D1 tracks each item's lifecycle from PENDING through SUCCESS/FAILED/UNCLAIMED.

---

## Environment (wrangler.toml)

```toml
[vars]
PAYPAL_ENV = "sandbox"   # or "live"

[[d1_databases]]
binding       = "DB"
database_name = "payouts"
database_id   = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[queues.producers]]
binding = "PAYOUT_STATUS_QUEUE"
queue   = "paypal-payout-status"
```

## D1 Schema

```sql
-- migrations/0001_payouts.sql
CREATE TABLE IF NOT EXISTS payout_batches (
  batch_id      TEXT PRIMARY KEY,     -- PayPal payout_batch_id
  sender_item_ids TEXT NOT NULL,      -- JSON array
  status        TEXT NOT NULL DEFAULT 'PENDING',
  total_amount  TEXT NOT NULL,        -- decimal string
  currency      TEXT NOT NULL,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch('now') * 1000)
);

CREATE TABLE IF NOT EXISTS payout_items (
  sender_item_id TEXT PRIMARY KEY,
  batch_id       TEXT NOT NULL,
  recipient      TEXT NOT NULL,       -- email or paypal account
  amount         TEXT NOT NULL,
  currency       TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'PENDING', -- PENDING|SUCCESS|FAILED|UNCLAIMED|BLOCKED
  paypal_item_id TEXT,                -- returned in webhook
  updated_at     INTEGER
);
```

## OAuth Token Helper (with KV Caching)

```typescript
// src/lib/paypal-auth.ts

interface Env {
  PAYPAL_ENV: string;
  PAYPAL_CLIENT_ID: string;
  PAYPAL_CLIENT_SECRET: string;
  PAYPAL_TOKEN_KV: KVNamespace;
}

const PAYPAL_BASE: Record<string, string> = {
  sandbox: "https://api-m.sandbox.paypal.com",
  live:    "https://api-m.paypal.com",
};

export function paypalBase(env: Env): string {
  return PAYPAL_BASE[env.PAYPAL_ENV] ?? PAYPAL_BASE.sandbox;
}

export async function getAccessToken(env: Env): Promise<string> {
  const cached = await env.PAYPAL_TOKEN_KV.get("pp_access_token");
  if (cached) return cached;

  const creds = btoa(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_CLIENT_SECRET}`);
  const res = await fetch(`${paypalBase(env)}/v1/oauth2/token`, {
    method: "POST",
    headers: {
      Authorization: `Basic ${creds}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: "grant_type=client_credentials",
  });

  if (!res.ok) throw new Error(`PayPal auth failed: ${await res.text()}`);
  const { access_token, expires_in } = await res.json<{
    access_token: string;
    expires_in: number;
  }>();

  await env.PAYPAL_TOKEN_KV.put("pp_access_token", access_token, {
    expirationTtl: expires_in - 60,
  });
  return access_token;
}
```

## Create a Payout Batch

```typescript
// src/handlers/create-payout-batch.ts
import { getAccessToken, paypalBase } from "../lib/paypal-auth";

interface PayoutRecipient {
  senderItemId: string;
  recipientEmail: string;
  amount: string;   // decimal string, e.g. "25.00"
  currency: string;
  note?: string;
}

export async function createPayoutBatch(
  env: Env,
  recipients: PayoutRecipient[],
  emailSubject = "Your payout has arrived"
): Promise<string> {
  const token = await getAccessToken(env);

  const body = {
    sender_batch_header: {
      sender_batch_id: `batch_${Date.now()}`,
      email_subject: emailSubject,
      email_message: "You have received a payout.",
    },
    items: recipients.map((r) => ({
      recipient_type: "EMAIL",
      amount: { value: r.amount, currency: r.currency },
      receiver: r.recipientEmail,
      sender_item_id: r.senderItemId,
      note: r.note ?? "",
    })),
  };

  const res = await fetch(`${paypalBase(env)}/v1/payments/payouts`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`PayPal Payouts API error: ${await res.text()}`);
  }

  const { batch_header } = await res.json<{
    batch_header: { payout_batch_id: string };
  }>();
  const batchId = batch_header.payout_batch_id;

  // Persist batch to D1
  const totalAmount = recipients
    .reduce((sum, r) => sum + parseFloat(r.amount), 0)
    .toFixed(2);

  await env.DB.prepare(
    `INSERT INTO payout_batches (batch_id, sender_item_ids, total_amount, currency)
     VALUES (?, ?, ?, ?)`
  ).bind(
    batchId,
    JSON.stringify(recipients.map((r) => r.senderItemId)),
    totalAmount,
    recipients[0]?.currency ?? "USD"
  ).run();

  // Persist each item
  const stmt = env.DB.prepare(
    `INSERT INTO payout_items (sender_item_id, batch_id, recipient, amount, currency)
     VALUES (?, ?, ?, ?, ?)`
  );
  await env.DB.batch(
    recipients.map((r) =>
      stmt.bind(r.senderItemId, batchId, r.recipientEmail, r.amount, r.currency)
    )
  );

  return batchId;
}
```

## Webhook Handler: Update Item Status

```typescript
// src/handlers/paypal-payout-webhook.ts
// PayPal fires PAYMENT.PAYOUTSBATCH.SUCCESS, PAYMENT.PAYOUTS-ITEM.SUCCEEDED,
// PAYMENT.PAYOUTS-ITEM.FAILED, PAYMENT.PAYOUTS-ITEM.UNCLAIMED, etc.

import { verifyPayPalWebhook } from "../lib/paypal-webhook-verify";

export async function handlePayoutWebhook(
  req: Request,
  env: Env
): Promise<Response> {
  const rawBody = await req.text();
  const valid = await verifyPayPalWebhook(req.headers, rawBody, env);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const event = JSON.parse(rawBody) as {
    event_type: string;
    resource: {
      payout_item_id?: string;
      payout_batch_id?: string;
      sender_item_id?: string;
      transaction_status?: string;
      batch_header?: { batch_status: string; payout_batch_id: string };
    };
  };

  if (event.event_type.startsWith("PAYMENT.PAYOUTS-ITEM.")) {
    const itemStatus = event.event_type.split(".").pop() ?? "UNKNOWN";
    const { sender_item_id, payout_item_id } = event.resource;

    await env.DB.prepare(
      `UPDATE payout_items
          SET status = ?, paypal_item_id = ?, updated_at = ?
        WHERE sender_item_id = ?`
    ).bind(itemStatus, payout_item_id ?? null, Date.now(), sender_item_id).run();
  }

  if (event.event_type === "PAYMENT.PAYOUTSBATCH.SUCCESS") {
    const batchId = event.resource.batch_header?.payout_batch_id;
    if (batchId) {
      await env.DB.prepare(
        "UPDATE payout_batches SET status = 'SUCCESS' WHERE batch_id = ?"
      ).bind(batchId).run();
    }
  }

  return new Response("OK");
}
```

## Poll Batch Status for Reconciliation

```typescript
// src/lib/poll-payout-batch.ts
export async function pollBatchStatus(
  env: Env,
  batchId: string
): Promise<void> {
  const token = await getAccessToken(env);
  const res = await fetch(`${paypalBase(env)}/v1/payments/payouts/${batchId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json<{
    batch_header: { batch_status: string };
    items: Array<{
      payout_item: { sender_item_id: string };
      payout_item_id: string;
      transaction_status: string;
    }>;
  }>();

  const stmt = env.DB.prepare(
    `UPDATE payout_items
        SET status = ?, paypal_item_id = ?, updated_at = ?
      WHERE sender_item_id = ?`
  );
  await env.DB.batch(
    data.items.map((item) =>
      stmt.bind(
        item.transaction_status,
        item.payout_item_id,
        Date.now(),
        item.payout_item.sender_item_id
      )
    )
  );

  await env.DB.prepare(
    "UPDATE payout_batches SET status = ? WHERE batch_id = ?"
  ).bind(data.batch_header.batch_status, batchId).run();
}
```

---

## Anti-patterns

- Sending more than 15,000 items per batch — the API rejects it; split into sub-batches of up to 15,000.
- Using order-API credentials for Payouts — Payouts requires the `Payouts` permission enabled separately in the PayPal developer dashboard for your app.
- Relying solely on webhooks for reconciliation — PayPal webhooks can be delayed or missed; poll `/v1/payments/payouts/{batch_id}` for large batches after 10 minutes.
- Storing amounts as floats — always use decimal strings (`"25.00"`); floating-point arithmetic causes penny rounding errors at scale.

## Gotchas

- `UNCLAIMED` status means the recipient does not have a PayPal account; they receive an email to claim it. Funds return to sender after 30 days if unclaimed.
- `sender_batch_id` must be unique per PayPal account; a duplicate within 30 days returns the original batch (idempotency by PayPal design).
- Sandbox webhook events are only delivered if you configure a sandbox webhook endpoint in the developer portal, separate from the live one.
- PayPal Payouts is subject to separate fee schedules (typically 2% per transaction, capped) — factor into your disbursement calculations.
- The `PAYMENT.PAYOUTS-ITEM.BLOCKED` event means PayPal's compliance team blocked the transfer; manual review is required.

## Verification

```bash
# Create a single-item test payout in sandbox
curl -X POST https://api-m.sandbox.paypal.com/v1/payments/payouts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sender_batch_header":{"sender_batch_id":"test_'$(date +%s)'","email_subject":"Test payout"},"items":[{"recipient_type":"EMAIL","amount":{"value":"1.00","currency":"USD"},"receiver":"sb-recipient@example.com","sender_item_id":"item_001"}]}'
# Poll status
curl "https://api-m.sandbox.paypal.com/v1/payments/payouts/<batch_id>" \
  -H "Authorization: Bearer $TOKEN"
```

## Related

- `paypal-orders-v2-workers-integration.md`
- `paypal-webhook-idempotency-d1-workers.md`
- `paypal-webhook-certificate-verification.md`
- `wise-payouts-api-mass-payouts-workers.md`
- `nowpayments-mass-payout-authorization-and-expiry.md`

## Sources

- https://developer.paypal.com/docs/payouts/
- https://developer.paypal.com/docs/payouts/integrate/
- https://developer.paypal.com/api/payments.payouts-batch/v1/
