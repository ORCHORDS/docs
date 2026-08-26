# Coinbase Commerce Crypto Payment on Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to accept cryptocurrency payments (BTC, ETH, USDC) using Coinbase Commerce. Your Cloudflare Worker creates charges via the Commerce API, caches pending charge state in KV to avoid redundant API calls, verifies incoming webhook signatures (`X-CC-Webhook-Signature`), and persists confirmed payments in D1.

## Context

- Runtime: Cloudflare Workers (ES modules)
- KV: Pending charge cache (TTL-based, keyed by internal order ID)
- D1: Confirmed payment log
- Coinbase Commerce API v2 (api.commerce.coinbase.com)
- Webhook events: `charge:confirmed`, `charge:failed`, `charge:expired`

---

## Step 1 - D1 Schema

```sql
-- migrations/0003_crypto_payments.sql
CREATE TABLE IF NOT EXISTS crypto_payments (
  charge_id      TEXT PRIMARY KEY,
  order_id       TEXT NOT NULL UNIQUE,
  crypto_amount  TEXT,               -- e.g. "0.00123 BTC"
  fiat_amount    INTEGER NOT NULL,   -- minor units
  currency       TEXT NOT NULL,
  network        TEXT,
  status         TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | failed | expired
  confirmed_at   TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crypto_webhook_events (
  event_id    TEXT PRIMARY KEY,
  charge_id   TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  payload     TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Step 2 - Create a Charge

```typescript
// src/coinbase/create-charge.ts
export interface ChargeRequest {
  orderId: string;
  name: string;
  description: string;
  amountUsd: number;
  redirectUrl: string;
  cancelUrl: string;
}

export interface CoinbaseCharge {
  id: string;
  code: string;
  hosted_url: string;
  expires_at: string;
}

export async function createCharge(
  req: ChargeRequest,
  apiKey: string
): Promise<CoinbaseCharge> {
  const body = {
    name: req.name,
    description: req.description,
    pricing_type: 'fixed_price',
    local_price: {
      amount: req.amountUsd.toFixed(2),
      currency: 'USD',
    },
    metadata: { order_id: req.orderId },
    redirect_url: req.redirectUrl,
    cancel_url: req.cancelUrl,
  };

  const res = await fetch('https://api.commerce.coinbase.com/charges', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CC-Api-Key': apiKey,
      'X-CC-Version': '2018-03-22',
    },
    body: JSON.stringify(body),
  });

  const json = await res.json() as {
    data: CoinbaseCharge;
    error?: { message: string };
  };
  if (!res.ok) throw new Error(json.error?.message ?? 'Coinbase Commerce error');
  return json.data;
}
```

---

## Step 3 - KV Charge Cache

```typescript
// src/coinbase/charge-cache.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import type { CoinbaseCharge } from './create-charge';

const CACHE_TTL_SECONDS = 3600;

export async function cacheCharge(
  kv: KVNamespace,
  orderId: string,
  charge: CoinbaseCharge
): Promise<void> {
  await kv.put(`charge:${orderId}`, JSON.stringify(charge), {
    expirationTtl: CACHE_TTL_SECONDS,
  });
}

export async function getCachedCharge(
  kv: KVNamespace,
  orderId: string
): Promise<CoinbaseCharge | null> {
  const raw = await kv.get(`charge:${orderId}`);
  if (!raw) return null;
  return JSON.parse(raw) as CoinbaseCharge;
}
```

---

## Step 4 - Webhook Signature Verification

```typescript
// src/coinbase/verify-webhook.ts
export async function verifyCommerceWebhook(
  body: string,
  signatureHeader: string | null,
  sharedSecret: string
): Promise<boolean> {
  if (!signatureHeader) return false;

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(sharedSecret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(body));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  if (computed.length !== signatureHeader.length) return false;
  let diff = 0;
  for (let i = 0; i < computed.length; i++) {
    diff |= computed.charCodeAt(i) ^ signatureHeader.charCodeAt(i);
  }
  return diff === 0;
}
```

---

## Step 5 - Webhook Handler

```typescript
// src/index.ts
import { createCharge, type ChargeRequest } from './coinbase/create-charge';
import { cacheCharge, getCachedCharge } from './coinbase/charge-cache';
import { verifyCommerceWebhook } from './coinbase/verify-webhook';

interface Env {
  DB: D1Database;
  CHARGE_CACHE: KVNamespace;
  COINBASE_API_KEY: string;
  COINBASE_WEBHOOK_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/charges' && request.method === 'POST') {
      const req = await request.json() as ChargeRequest;

      const cached = await getCachedCharge(env.CHARGE_CACHE, req.orderId);
      if (cached) {
        return Response.json({ charge: cached, cached: true });
      }

      const charge = await createCharge(req, env.COINBASE_API_KEY);
      await cacheCharge(env.CHARGE_CACHE, req.orderId, charge);

      await env.DB
        .prepare(
          `INSERT OR IGNORE INTO crypto_payments
           (charge_id, order_id, fiat_amount, currency, status)
           VALUES (?, ?, ?, 'USD', 'pending')`
        )
        .bind(charge.id, req.orderId, Math.round(req.amountUsd * 100))
        .run();

      return Response.json({ charge, cached: false });
    }

    if (url.pathname === '/webhook' && request.method === 'POST') {
      const body = await request.text();
      const sig = request.headers.get('X-CC-Webhook-Signature');

      const valid = await verifyCommerceWebhook(
        body,
        sig,
        env.COINBASE_WEBHOOK_SECRET
      );
      if (!valid) return new Response('Unauthorized', { status: 401 });

      const event = JSON.parse(body) as {
        id: string;
        type: string;
        data: {
          id: string;
          metadata?: { order_id?: string };
          payments?: Array<{
            value: { crypto: { amount: string; currency: string } };
            network: string;
          }>;
        };
      };

      const seen = await env.DB
        .prepare('SELECT event_id FROM crypto_webhook_events WHERE event_id = ?')
        .bind(event.id)
        .first();
      if (seen) return new Response('Already processed', { status: 200 });

      await env.DB
        .prepare(
          'INSERT INTO crypto_webhook_events (event_id, charge_id, event_type, payload) VALUES (?, ?, ?, ?)'
        )
        .bind(event.id, event.data.id, event.type, body)
        .run();

      if (event.type === 'charge:confirmed') {
        const payment = event.data.payments?.[0];
        const cryptoAmount = payment
          ? `${payment.value.crypto.amount} ${payment.value.crypto.currency}`
          : null;

        await env.DB
          .prepare(
            `UPDATE crypto_payments
             SET status='confirmed', crypto_amount=?, network=?,
                 confirmed_at=datetime('now'), updated_at=datetime('now')
             WHERE charge_id=?`
          )
          .bind(cryptoAmount, payment?.network ?? null, event.data.id)
          .run();

        const orderId = event.data.metadata?.order_id;
        if (orderId) await env.CHARGE_CACHE.delete(`charge:${orderId}`);
      } else {
        const statusMap: Record<string, string> = {
          'charge:failed': 'failed',
          'charge:expired': 'expired',
        };
        const newStatus = statusMap[event.type];
        if (newStatus) {
          await env.DB
            .prepare(
              `UPDATE crypto_payments
               SET status=?, updated_at=datetime('now')
               WHERE charge_id=?`
            )
            .bind(newStatus, event.data.id)
            .run();
        }
      }

      return new Response('OK', { status: 200 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Anti-patterns

- Never poll the Coinbase API to check charge status - always rely on webhooks.
- Do not store crypto amounts as floats in D1 - use TEXT to preserve precision.
- Do not trust the `order_id` in the webhook without first verifying the HMAC signature.
- Avoid returning the charge `hosted_url` without persisting the charge ID first.

## Gotchas

- Coinbase Commerce charges expire after 1 hour by default; KV TTL should match.
- `X-CC-Webhook-Signature` contains a plain hex digest - no `sha256=` prefix.
- `charge:pending` fires when payment is detected on-chain but not yet confirmed; do not fulfil until `charge:confirmed`.
- Commerce API v2 wraps responses in a `{ data: ... }` envelope.

## Verification

```bash
# Apply D1 migration
wrangler d1 migrations apply DB --env production

# Create the KV namespace
wrangler kv:namespace create CHARGE_CACHE

# Create a test charge
curl -X POST https://my-worker.orchords.workers.dev/charges \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ORD-001","name":"Test","description":"Test charge","amountUsd":9.99,"redirectUrl":"https://example.com/success","cancelUrl":"https://example.com/cancel"}'

# Simulate a confirmed webhook
SECRET="<redacted-secret>"
PAYLOAD='{"id":"EVT-1","type":"charge:confirmed","data":{"id":"CHG-123","metadata":{"order_id":"ORD-001"},"payments":[{"value":{"crypto":{"amount":"0.001","currency":"BTC"}},"network":"bitcoin"}]}}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')
curl -X POST https://my-worker.orchords.workers.dev/webhook \
  -H 'Content-Type: application/json' \
  -H "X-CC-Webhook-Signature: $SIG" \
  -d "$PAYLOAD"

# Verify status in D1
wrangler d1 execute DB --env production \
  --command "SELECT * FROM crypto_payments WHERE order_id='ORD-001'"
```

## Related

- `documentation/categories/payments/workers-klarna-order-management-webhook.md`
- `documentation/categories/payments/stripe-payment-link-webhook-fulfillment-workers.md`

## Sources

- https://docs.cloud.coinbase.com/commerce/docs/
- https://docs.cloud.coinbase.com/commerce/reference/createcharge
- https://docs.cloud.coinbase.com/commerce/docs/webhooks-fields-and-types
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
