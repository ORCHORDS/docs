# Klarna Order Management Webhook Handler

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You integrate Klarna as a payment method and need to handle post-authorization lifecycle events (capture, refund, cancel) pushed by Klarna to your Cloudflare Worker. Without proper signature verification and a durable order state machine you risk processing duplicate or spoofed events.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Database: D1 (SQLite) for order state
- Klarna Payments API (EU region)
- Webhook event types: `order_management.v1.capture_created`, `order_management.v1.refund_initiated`, `order_management.v1.order_cancelled`

---

## Step 1 – D1 Schema

```sql
-- migrations/0001_klarna_orders.sql
CREATE TABLE IF NOT EXISTS klarna_orders (
  klarna_order_id TEXT PRIMARY KEY,
  internal_order_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'authorized',  -- authorized | captured | refunded | cancelled
  captured_amount INTEGER DEFAULT 0,          -- minor units
  refunded_amount INTEGER DEFAULT 0,
  currency TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS klarna_events (
  event_id TEXT PRIMARY KEY,                  -- idempotency key from Klarna
  klarna_order_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  processed_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (klarna_order_id) REFERENCES klarna_orders(klarna_order_id)
);

CREATE INDEX IF NOT EXISTS idx_klarna_events_order ON klarna_events(klarna_order_id);
```

---

## Step 2 – Signature Verification

Klarna signs each webhook request with HMAC-SHA256. The shared secret is set in the Klarna Merchant Portal and stored in a Worker secret.

```typescript
// src/klarna/verify.ts
export async function verifyKlarnaSignature(
  body: string,
  signatureHeader: string | null,
  secret: string
): Promise<boolean> {
  if (!signatureHeader) return false;

  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const msgData = encoder.encode(body);

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signature = await crypto.subtle.sign('HMAC', cryptoKey, msgData);
  const hexSig = Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  // Constant-time comparison
  if (hexSig.length !== signatureHeader.length) return false;
  let diff = 0;
  for (let i = 0; i < hexSig.length; i++) {
    diff |= hexSig.charCodeAt(i) ^ signatureHeader.charCodeAt(i);
  }
  return diff === 0;
}
```

---

## Step 3 – Order State Machine

```typescript
// src/klarna/state-machine.ts
import type { D1Database } from '@cloudflare/workers-types';

type KlarnaStatus = 'authorized' | 'captured' | 'refunded' | 'cancelled';

const TRANSITIONS: Record<string, KlarnaStatus[]> = {
  authorized: ['captured', 'cancelled'],
  captured: ['refunded'],
  refunded: [],
  cancelled: [],
};

export async function transitionOrder(
  db: D1Database,
  klarnaOrderId: string,
  nextStatus: KlarnaStatus,
  delta: { capturedAmount?: number; refundedAmount?: number }
): Promise<void> {
  const row = await db
    .prepare('SELECT status FROM klarna_orders WHERE klarna_order_id = ?')
    .bind(klarnaOrderId)
    .first<{ status: KlarnaStatus }>();

  if (!row) throw new Error(`Order not found: ${klarnaOrderId}`);

  const allowed = TRANSITIONS[row.status] ?? [];
  if (!allowed.includes(nextStatus)) {
    throw new Error(
      `Invalid transition ${row.status} -> ${nextStatus} for ${klarnaOrderId}`
    );
  }

  await db
    .prepare(
      `UPDATE klarna_orders
       SET status = ?,
           captured_amount = captured_amount + ?,
           refunded_amount = refunded_amount + ?,
           updated_at = datetime('now')
       WHERE klarna_order_id = ?`
    )
    .bind(
      nextStatus,
      delta.capturedAmount ?? 0,
      delta.refundedAmount ?? 0,
      klarnaOrderId
    )
    .run();
}
```

---

## Step 4 – Webhook Handler

```typescript
// src/index.ts
import { verifyKlarnaSignature } from './klarna/verify';
import { transitionOrder } from './klarna/state-machine';

interface Env {
  DB: D1Database;
  KLARNA_WEBHOOK_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();
    const signature = request.headers.get('X-Klarna-Signature');

    const valid = await verifyKlarnaSignature(
      body,
      signature,
      env.KLARNA_WEBHOOK_SECRET
    );
    if (!valid) {
      return new Response('Unauthorized', { status: 401 });
    }

    const event = JSON.parse(body) as {
      event_id: string;
      type: string;
      order_id: string;
      captured_amount?: number;
      refunded_amount?: number;
    };

    // Idempotency - skip if already processed
    const existing = await env.DB
      .prepare('SELECT event_id FROM klarna_events WHERE event_id = ?')
      .bind(event.event_id)
      .first();
    if (existing) {
      return new Response('Already processed', { status: 200 });
    }

    const typeMap: Record<string, { status: 'captured' | 'refunded' | 'cancelled'; key: 'capturedAmount' | 'refundedAmount' | undefined }> = {
      'order_management.v1.capture_created': { status: 'captured', key: 'capturedAmount' },
      'order_management.v1.refund_initiated': { status: 'refunded', key: 'refundedAmount' },
      'order_management.v1.order_cancelled': { status: 'cancelled', key: undefined },
    };

    const mapping = typeMap[event.type];
    if (!mapping) {
      return new Response('Ignored', { status: 200 });
    }

    await transitionOrder(env.DB, event.order_id, mapping.status, {
      capturedAmount: mapping.key === 'capturedAmount' ? (event.captured_amount ?? 0) : 0,
      refundedAmount: mapping.key === 'refundedAmount' ? (event.refunded_amount ?? 0) : 0,
    });

    await env.DB
      .prepare(
        'INSERT INTO klarna_events (event_id, klarna_order_id, event_type, payload) VALUES (?, ?, ?, ?)'
      )
      .bind(event.event_id, event.order_id, event.type, body)
      .run();

    return new Response('OK', { status: 200 });
  },
};
```

---

## Anti-patterns

- Never trust the `order_id` in the payload without first verifying the HMAC signature.
- Do not update order status outside the state machine - bypass leads to impossible states.
- Do not store the raw webhook secret in `wrangler.toml`; always use `wrangler secret put KLARNA_WEBHOOK_SECRET`.
- Avoid using wall-clock time for idempotency - rely on Klarna's stable `event_id`.

## Gotchas

- Klarna may deliver the same event more than once; always check `klarna_events` before processing.
- `X-Klarna-Signature` contains only the hex digest (no `sha256=` prefix), unlike Stripe.
- The Klarna EU and NA APIs have different base URLs; ensure the merchant portal webhook URL matches the Worker route region.
- D1's `INTEGER` stores amounts in minor units (cents). Do not convert to floats inside the database.

## Verification

```bash
# Apply migration
wrangler d1 migrations apply DB --env production

# Seed a test order
wrangler d1 execute DB --env production \
  --command "INSERT INTO klarna_orders VALUES ('KO-123','ORD-456','authorized',0,0,'EUR',datetime('now'),datetime('now'))"

# Send a test capture webhook
SECRET="<redacted-secret>"
PAYLOAD='{"event_id":"EVT-1","type":"order_management.v1.capture_created","order_id":"KO-123","captured_amount":4999}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')
curl -X POST https://my-worker.orchords.workers.dev/klarna/webhook \
  -H 'Content-Type: application/json' \
  -H "X-Klarna-Signature: $SIG" \
  -d "$PAYLOAD"

# Confirm state transition
wrangler d1 execute DB --env production \
  --command "SELECT status, captured_amount FROM klarna_orders WHERE klarna_order_id='KO-123'"
```

## Related

- `documentation/categories/payments/stripe-payment-link-webhook-fulfillment-workers.md`
- `documentation/categories/payments/workers-subscription-dunning-retry-d1.md`

## Sources

- https://docs.klarna.com/order-management/api/
- https://docs.klarna.com/klarna-payments/integrate-with-klarna-payments/step-3-authorize-and-place-the-order/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
