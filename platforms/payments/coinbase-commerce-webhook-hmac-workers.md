# Coinbase Commerce Webhook HMAC Verification on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Coinbase Commerce sends `charge:confirmed`, `charge:failed`, and `charge:delayed` webhook events to your endpoint. Without strict HMAC-SHA256 verification you cannot distinguish genuine payment confirmations from spoofed requests, leading to orders fulfilled without actual crypto settlement or duplicate processing on retried deliveries.

---

## Context

Coinbase Commerce signs every webhook with a shared secret (`COINBASE_COMMERCE_WEBHOOK_SECRET`). The signature is placed in the `X-CC-Webhook-Signature` header as a hex-encoded HMAC-SHA256 digest of the raw request body. Because Cloudflare Workers expose the `SubtleCrypto` API natively, no Node.js `crypto` module is needed — the entire verification path runs at the edge with zero cold-start overhead. Idempotent processing is enforced via a D1 table so retried deliveries do not double-credit accounts.

Commerce webhooks are delivered with a `created_at` timestamp inside the event; requests older than five minutes should be rejected to prevent replay attacks using previously captured valid signatures.

---

## 1. Webhook Signature Verification

```typescript
// src/coinbase-webhook.ts

export async function verifyCoinbaseSignature(
  request: Request,
  secret: string
): Promise<{ valid: boolean; body: string }> {
  const signature = request.headers.get('X-CC-Webhook-Signature');
  if (!signature) return { valid: false, body: '' };

  const body = await request.text();
  const encoder = new TextEncoder();

  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const mac = await crypto.subtle.sign('HMAC', key, encoder.encode(body));
  const expected = Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  // Constant-time comparison to prevent timing attacks
  if (expected.length !== signature.length) return { valid: false, body };
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return { valid: diff === 0, body };
}
```

---

## 2. Replay Attack Prevention

```typescript
// src/coinbase-webhook.ts

const MAX_AGE_SECONDS = 300; // 5 minutes

export function isReplayAttack(eventBody: string): boolean {
  try {
    const event = JSON.parse(eventBody);
    const createdAt = new Date(event.event?.created_at ?? event.created_at);
    const ageMs = Date.now() - createdAt.getTime();
    return ageMs > MAX_AGE_SECONDS * 1000;
  } catch {
    return true; // malformed body — reject
  }
}
```

---

## 3. D1 Idempotency Guard

```sql
-- migrations/0001_coinbase_events.sql
CREATE TABLE IF NOT EXISTS coinbase_webhook_events (
  event_id   TEXT PRIMARY KEY,
  charge_id  TEXT NOT NULL,
  event_type TEXT NOT NULL,
  processed_at TEXT NOT NULL
);
```

```typescript
// src/coinbase-webhook.ts

export async function processOnce(
  db: D1Database,
  eventId: string,
  chargeId: string,
  eventType: string,
  handler: () => Promise<void>
): Promise<{ duplicate: boolean }> {
  const existing = await db
    .prepare('SELECT event_id FROM coinbase_webhook_events WHERE event_id = ?')
    .bind(eventId)
    .first();

  if (existing) return { duplicate: true };

  await handler();

  await db
    .prepare(
      'INSERT INTO coinbase_webhook_events (event_id, charge_id, event_type, processed_at) VALUES (?, ?, ?, ?)'
    )
    .bind(eventId, chargeId, eventType, new Date().toISOString())
    .run();

  return { duplicate: false };
}
```

---

## 4. Worker Entry Point

```typescript
// src/index.ts

import { verifyCoinbaseSignature, isReplayAttack, processOnce } from './coinbase-webhook';

interface Env {
  COINBASE_COMMERCE_WEBHOOK_SECRET: string;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { valid, body } = await verifyCoinbaseSignature(
      request,
      env.COINBASE_COMMERCE_WEBHOOK_SECRET
    );

    if (!valid) {
      return new Response('Invalid signature', { status: 401 });
    }

    if (isReplayAttack(body)) {
      return new Response('Replay rejected', { status: 400 });
    }

    const event = JSON.parse(body);
    const eventId   = event.event?.id ?? event.id;
    const chargeId  = event.event?.data?.id ?? event.data?.id;
    const eventType = event.event?.type ?? event.type;

    const { duplicate } = await processOnce(
      env.DB,
      eventId,
      chargeId,
      eventType,
      async () => {
        switch (eventType) {
          case 'charge:confirmed':
            await fulfillOrder(env.DB, chargeId);
            break;
          case 'charge:failed':
            await cancelOrder(env.DB, chargeId);
            break;
          case 'charge:delayed':
            await flagDelayedOrder(env.DB, chargeId);
            break;
        }
      }
    );

    return new Response(JSON.stringify({ received: true, duplicate }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};

async function fulfillOrder(db: D1Database, chargeId: string): Promise<void> {
  await db
    .prepare("UPDATE orders SET status = 'fulfilled' WHERE charge_id = ?")
    .bind(chargeId)
    .run();
}

async function cancelOrder(db: D1Database, chargeId: string): Promise<void> {
  await db
    .prepare("UPDATE orders SET status = 'cancelled' WHERE charge_id = ?")
    .bind(chargeId)
    .run();
}

async function flagDelayedOrder(db: D1Database, chargeId: string): Promise<void> {
  await db
    .prepare("UPDATE orders SET status = 'delayed' WHERE charge_id = ?")
    .bind(chargeId)
    .run();
}
```

---

## 5. wrangler.toml Binding

```toml
name = "coinbase-commerce-webhook"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id   = "<your-d1-database-id>"

[vars]
# Store in Wrangler secrets, not vars:
# wrangler secret put COINBASE_COMMERCE_WEBHOOK_SECRET
```

---

## Anti-patterns

- **Parsing JSON before verifying** — always verify on the raw text body; JSON re-serialization changes byte order and breaks the HMAC.
- **Using `===` for signature comparison** — string equality short-circuits on first mismatch, enabling timing oracle attacks.
- **Trusting `charge:pending` as payment confirmation** — only `charge:confirmed` indicates settled funds on-chain.
- **Skipping replay check** — an attacker who intercepts a valid webhook for an unrelated order can replay it against a second endpoint.

---

## Gotchas

- Coinbase Commerce retries webhooks up to 30 times over 3 days; idempotency is mandatory, not optional.
- The `event.event.id` path differs between legacy and v2 webhook shapes — always check both `event.event?.id` and `event.id`.
- `charge:confirmed` fires after sufficient block confirmations per network; for USDC on Base this is near-instant, while BTC requires 6 confirmations (~60 min).
- The webhook secret rotates when you regenerate it in the Commerce dashboard — update `COINBASE_COMMERCE_WEBHOOK_SECRET` before the old secret expires, or deliveries will fail.
- Commerce does not send a `charge:resolved` event for overpaid charges; monitor `charge:delayed` and inspect the timeline array.

---

## Verification

```bash
# Send a test webhook using the Commerce dashboard "Send test event" button
# or construct a valid HMAC locally:
SECRET="your_webhook_secret"
PAYLOAD='{"event":{"id":"test-id","type":"charge:confirmed","created_at":"2026-08-23T12:00:00Z","data":{"id":"charge-abc"}}}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')
curl -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -H "X-CC-Webhook-Signature: $SIG" \
  -d "$PAYLOAD"
# Expected: {"received":true,"duplicate":false}
```

---

## Related

- `nowpayments-webhook-hmac-sha512.md`
- `stripe-webhook-idempotency-workers.md`
- `crypto-confirmation-depth-finality.md`
- `idempotency-keys-payment-apis.md`

---

## Sources

- https://docs.cdp.coinbase.com/commerce/docs/webhooks
- https://developers.cloudflare.com/d1/
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
