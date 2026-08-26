# Square Terminal In-Person Payments via Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You operate physical retail or event-ticket locations with Square Terminal card readers and need
your Cloudflare Workers backend to create Terminal checkout requests, poll for completion, handle
cancellations, and reconcile in-person payments with the same D1 ledger used by your online
checkout — all without running a persistent Node.js server.

---

## Context

Square Terminal is Square's dedicated card reader for in-person payments. The integration model
differs fundamentally from online payments:

```
Worker  →  POST /v2/terminals/checkouts  →  Square API
Square API  →  pushes checkout to Terminal device
Customer taps/dips card on reader
Square  →  emits webhook  →  Worker callback
Worker  →  writes to D1 + reconciles with online ledger
```

Key objects:
- **TerminalCheckout** — the payment request sent to a specific device
- **DeviceCode** — links your device to a Square location during pairing
- **TerminalAction** — used for non-payment flows (save card, get card details)

The Square Terminals API is REST-based; webhooks deliver final status. On example project we use
Cloudflare Queues as a buffer between the Square webhook and D1 writes to handle burst traffic
at event venues.

---

## D1 Schema

```sql
-- migrations/0020_terminal_checkouts.sql
CREATE TABLE IF NOT EXISTS terminal_checkouts (
  id                TEXT PRIMARY KEY,   -- Square checkout id
  idempotency_key   TEXT NOT NULL UNIQUE,
  device_id         TEXT NOT NULL,
  location_id       TEXT NOT NULL,
  amount            INTEGER NOT NULL,   -- smallest unit
  currency          TEXT NOT NULL DEFAULT 'USD',
  reference_id      TEXT,               -- your internal order id
  status            TEXT NOT NULL DEFAULT 'PENDING',
  payment_id        TEXT,               -- Square PaymentId on completion
  created_at        INTEGER NOT NULL DEFAULT (unixepoch()),
  completed_at      INTEGER,
  canceled_at       INTEGER
);

CREATE INDEX IF NOT EXISTS idx_terminal_ref ON terminal_checkouts(reference_id);
CREATE INDEX IF NOT EXISTS idx_terminal_device ON terminal_checkouts(device_id, status);
```

---

## Square SDK Wrapper

```typescript
// src/lib/square-terminal.ts
import { Env } from '../types';

const SQUARE_BASE = 'https://connect.squareupstaging.com'; // swap to connect.squareup.com in prod

interface CreateCheckoutParams {
  deviceId: string;
  locationId: string;
  amountCents: number;
  currency: string;
  referenceId?: string;
  note?: string;
  idempotencyKey: string;
}

interface SquareTerminalCheckout {
  id: string;
  status: string;
  payment_ids?: string[];
  amount_money: { amount: number; currency: string };
  device_options: { device_id: string };
  reference_id?: string;
  created_at: string;
}

export async function createTerminalCheckout(
  params: CreateCheckoutParams,
  env: Env,
): Promise<SquareTerminalCheckout> {
  const body = {
    idempotency_key: params.idempotencyKey,
    checkout: {
      amount_money: { amount: params.amountCents, currency: params.currency },
      device_options: { device_id: params.deviceId, skip_receipt_screen: false },
      reference_id: params.referenceId,
      note: params.note,
    },
  };

  const resp = await fetch(`${SQUARE_BASE}/v2/terminals/checkouts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${env.SQUARE_ACCESS_TOKEN}`,
      'Square-Version': '2024-10-17',
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const err = await resp.json<{ errors: Array<{ code: string; detail: string }> }>();
    throw new Error(`Square Terminal error: ${err.errors[0]?.detail}`);
  }

  const data = await resp.json<{ checkout: SquareTerminalCheckout }>();
  return data.checkout;
}

export async function getTerminalCheckout(
  checkoutId: string,
  env: Env,
): Promise<SquareTerminalCheckout> {
  const resp = await fetch(`${SQUARE_BASE}/v2/terminals/checkouts/${checkoutId}`, {
    headers: {
      Authorization: `Bearer ${env.SQUARE_ACCESS_TOKEN}`,
      'Square-Version': '2024-10-17',
    },
  });
  if (!resp.ok) throw new Error(`Square get checkout error: ${resp.status}`);
  const data = await resp.json<{ checkout: SquareTerminalCheckout }>();
  return data.checkout;
}

export async function cancelTerminalCheckout(
  checkoutId: string,
  env: Env,
): Promise<void> {
  const resp = await fetch(`${SQUARE_BASE}/v2/terminals/checkouts/${checkoutId}/cancel`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.SQUARE_ACCESS_TOKEN}`,
      'Square-Version': '2024-10-17',
    },
  });
  if (!resp.ok && resp.status !== 404) {
    throw new Error(`Square cancel error: ${resp.status}`);
  }
}
```

---

## Worker Handler — Create Checkout

```typescript
// src/handlers/terminal-create.ts
import { Env } from '../types';
import { createTerminalCheckout } from '../lib/square-terminal';
import { generateIdempotencyKey } from '../lib/crypto';

interface CreateCheckoutBody {
  deviceId: string;
  locationId: string;
  amountCents: number;
  currency?: string;
  referenceId?: string;
  note?: string;
}

export async function handleCreateTerminalCheckout(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<CreateCheckoutBody>();
  const idempotencyKey = await generateIdempotencyKey(body.referenceId ?? crypto.randomUUID());

  // Prevent duplicate checkouts for same order
  const existing = await env.DB.prepare(
    'SELECT id, status FROM terminal_checkouts WHERE reference_id = ? AND status IN (?,?)',
  )
    .bind(body.referenceId ?? null, 'PENDING', 'IN_PROGRESS')
    .first<{ id: string; status: string }>();

  if (existing) {
    return new Response(JSON.stringify({ checkoutId: existing.id, status: existing.status }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const checkout = await createTerminalCheckout(
    {
      deviceId: body.deviceId,
      locationId: body.locationId,
      amountCents: body.amountCents,
      currency: body.currency ?? 'USD',
      referenceId: body.referenceId,
      note: body.note,
      idempotencyKey,
    },
    env,
  );

  await env.DB.prepare(
    `INSERT INTO terminal_checkouts
       (id, idempotency_key, device_id, location_id, amount, currency, reference_id, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      checkout.id,
      idempotencyKey,
      body.deviceId,
      body.locationId,
      body.amountCents,
      body.currency ?? 'USD',
      body.referenceId ?? null,
      checkout.status,
    )
    .run();

  return new Response(JSON.stringify({ checkoutId: checkout.id, status: checkout.status }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## Webhook Handler

```typescript
// src/handlers/terminal-webhook.ts
import { Env } from '../types';
import { createHmac } from 'node:crypto'; // available in Workers runtime

interface SquareWebhookEvent {
  merchant_id: string;
  type: string;
  event_id: string;
  data: {
    type: string;
    id: string;
    object: {
      checkout?: {
        id: string;
        status: string;
        payment_ids?: string[];
        reference_id?: string;
      };
    };
  };
}

function verifySquareSignature(
  body: string,
  signature: string,
  webhookSignatureKey: string,
  notificationUrl: string,
): boolean {
  const stringToSign = notificationUrl + body;
  const hmac = createHmac('sha256', webhookSignatureKey)
    .update(stringToSign)
    .digest('base64');
  return hmac === signature;
}

export async function handleTerminalWebhook(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.text();
  const signature = request.headers.get('x-square-hmacsha256-signature') ?? '';
  const notificationUrl = 'https://example project.example.com/webhooks/square/terminal';

  if (!verifySquareSignature(body, signature, env.SQUARE_WEBHOOK_SIGNATURE_KEY, notificationUrl)) {
    return new Response('Bad signature', { status: 403 });
  }

  const event = JSON.parse(body) as SquareWebhookEvent;

  if (!event.type.startsWith('terminal.checkout.')) {
    return new Response('Ignored', { status: 200 });
  }

  const checkout = event.data.object.checkout;
  if (!checkout) return new Response('No checkout', { status: 200 });

  // Push to Queue for durable processing
  await env.TERMINAL_QUEUE.send({ event });

  return new Response('Accepted', { status: 202 });
}
```

---

## Queue Consumer — D1 Write

```typescript
// src/consumers/terminal-queue.ts
import { Env } from '../types';

interface TerminalQueueMessage {
  event: {
    type: string;
    data: { object: { checkout: { id: string; status: string; payment_ids?: string[] } } };
  };
}

export async function processTerminalQueue(
  batch: MessageBatch<TerminalQueueMessage>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    const { checkout } = msg.body.event.data.object;
    try {
      if (checkout.status === 'COMPLETED') {
        await env.DB.prepare(
          `UPDATE terminal_checkouts
           SET status = ?, payment_id = ?, completed_at = unixepoch()
           WHERE id = ?`,
        )
          .bind('COMPLETED', checkout.payment_ids?.[0] ?? null, checkout.id)
          .run();
      } else if (checkout.status === 'CANCELED') {
        await env.DB.prepare(
          'UPDATE terminal_checkouts SET status = ?, canceled_at = unixepoch() WHERE id = ?',
        )
          .bind('CANCELED', checkout.id)
          .run();
      }
      msg.ack();
    } catch (err) {
      msg.retry();
    }
  }
}
```

---

## Device Pairing Helper

```typescript
// src/handlers/terminal-devices.ts
import { Env } from '../types';

const SQUARE_BASE = 'https://connect.squareup.com';

export async function listDeviceCodes(env: Env, locationId: string): Promise<Response> {
  const resp = await fetch(
    `${SQUARE_BASE}/v2/devices/codes?location_id=${locationId}&status=PAIRED`,
    {
      headers: {
        Authorization: `Bearer ${env.SQUARE_ACCESS_TOKEN}`,
        'Square-Version': '2024-10-17',
      },
    },
  );
  return new Response(resp.body, { status: resp.status, headers: { 'Content-Type': 'application/json' } });
}
```

---

## Anti-patterns

- **Polling for checkout status instead of using webhooks**: The `GET /v2/terminals/checkouts/{id}`
  endpoint works but creates unnecessary load and latency. Always rely on webhooks for final status
  and use polling only as a fallback after webhook timeout.
- **Sending a checkout to an unpaired device**: The API accepts the request and returns 200, but
  the Terminal never shows the checkout. Always validate device pairing status before creating a
  checkout.
- **Not canceling orphaned checkouts**: If your Worker crashes between creating a checkout and
  receiving the webhook, the device may be stuck. Build a cron Worker that cancels checkouts
  with status PENDING older than 5 minutes.
- **Reusing idempotency keys across different amounts**: Square idempotency keys are scoped to a
  specific checkout object. Reusing a key with a different amount returns the original response
  silently — the new amount is ignored.
- **Hardcoding Square API versions**: Square uses calendar-based versioning. Older versions are
  sunset periodically. Pin `Square-Version` explicitly and test upgrades.

---

## Gotchas

- **Terminal checkout status lifecycle**: PENDING → IN_PROGRESS → COMPLETED or CANCELED.
  There is no FAILED state; a declined card results in IN_PROGRESS transitioning back to PENDING
  for retry or eventually CANCELED.
- **Multiple payment_ids on a single checkout**: Square can attach multiple payment IDs if the
  customer splits payment. Always handle `payment_ids` as an array.
- **Sandbox vs production endpoints**: Sandbox uses `connect.squareupstaging.com`, production uses
  `connect.squareup.com`. A hardcoded wrong URL returns a valid-looking 401 that can mislead.
- **Webhook event ordering is not guaranteed**: COMPLETED can arrive before IN_PROGRESS in high
  load. Use the checkout status from the webhook body, not your D1 row, as authoritative.
- **Square webhook retry policy**: Square retries failed webhooks up to 5 times with exponential
  backoff. Using Cloudflare Queues means your handler always returns 202 quickly; idempotency in
  the queue consumer prevents double-writes.

---

## Verification

```bash
# 1. Create a sandbox checkout
curl -X POST https://connect.squareupstaging.com/v2/terminals/checkouts \
  -H "Authorization: Bearer $SQUARE_SANDBOX_TOKEN" \
  -H "Square-Version: 2024-10-17" \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "test-001",
    "checkout": {
      "amount_money": {"amount": 1000, "currency": "USD"},
      "device_options": {"device_id": "YOUR_SANDBOX_DEVICE_ID"}
    }
  }'

# 2. Poll status (for testing only)
curl https://connect.squareupstaging.com/v2/terminals/checkouts/$CHECKOUT_ID \
  -H "Authorization: Bearer $SQUARE_SANDBOX_TOKEN"

# 3. Verify D1 row written from webhook
wrangler d1 execute example project-db \
  --command "SELECT * FROM terminal_checkouts WHERE id='$CHECKOUT_ID'"

# 4. Simulate webhook via Square Dashboard sandbox event delivery
# or use the Square CLI: square terminal checkout complete $CHECKOUT_ID
```

---

## Related

- `/payments/square-payments-workers-integration.md`
- `/payments/tap-to-pay-nfc-mobile-pos.md`
- `/payments/terminal-offline-payment-forwarding-and-reconciliation.md`
- `/payments/payment-retry-exponential-backoff-cloudflare-queues.md`
- `/payments/payment-reconciliation-settlement.md`

---

## Sources

- Square Terminal Checkouts API: https://developer.squareup.com/reference/square/terminal-api/create-terminal-checkout
- Square Webhooks: https://developer.squareup.com/docs/webhooks/overview
- Square Terminal In-Person Payments Guide: https://developer.squareup.com/docs/terminal-api/overview
- Cloudflare Queues: https://developers.cloudflare.com/queues/
