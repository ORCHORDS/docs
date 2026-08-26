# Verifying and Processing Paddle Billing Webhooks in a Cloudflare Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are migrating from Stripe to Paddle Billing (v2) or running both in parallel. Paddle sends signed webhook notifications for subscription lifecycle events, and you need to verify the HMAC-SHA256 signature using the Web Crypto API, persist events to D1 idempotently, and advance a subscription state machine.

---

## Context

Paddle Billing webhooks carry an `h1` HMAC-SHA256 signature in the `Paddle-Signature` header, constructed from a timestamp and the raw JSON body. Because the Workers runtime does not include Node.js `crypto`, verification must use `crypto.subtle` from the Web Crypto API. D1 stores every inbound event in a `paddle_events` table with `INSERT OR IGNORE` so replays are silently deduplicated. Subscription state is tracked in a separate `paddle_subscriptions` table using an explicit state machine: `trialing → active → past_due → cancelled`. A single Worker handles all event types through a typed dispatch table.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS paddle_events (
  event_id        TEXT PRIMARY KEY,          -- Paddle's evt_xxx UUID
  event_type      TEXT NOT NULL,
  occurred_at     TEXT NOT NULL,
  payload         TEXT NOT NULL,             -- raw JSON
  processed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paddle_subscriptions (
  paddle_sub_id   TEXT PRIMARY KEY,          -- sub_xxx
  customer_id     TEXT NOT NULL,             -- ctm_xxx
  plan_id         TEXT NOT NULL,
  status          TEXT NOT NULL CHECK(status IN
                    ('trialing','active','past_due','paused','cancelled')),
  current_period_start TEXT,
  current_period_end   TEXT,
  cancel_at            TEXT,
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_paddle_events_type
  ON paddle_events (event_type, occurred_at);
```

---

## Section 2 — Signature Verification and Worker

```typescript
export interface Env {
  DB: D1Database;
  PADDLE_WEBHOOK_SECRET: string;   // from Paddle dashboard — 64-char hex key
}

// Verify Paddle h1 HMAC-SHA256 signature
async function verifyPaddleSignature(
  header: string,
  rawBody: string,
  secret: string
): Promise<boolean> {
  // Header format: ts=1234567890;h1=<hex>
  const parts = Object.fromEntries(
    header.split(';').map((p) => p.split('=') as [string, string])
  );
  const ts = parts['ts'];
  const receivedHmac = parts['h1'];
  if (!ts || !receivedHmac) return false;

  const signedPayload = `${ts}:${rawBody}`;
  const encoder = new TextEncoder();

  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signatureBuffer = await crypto.subtle.sign(
    'HMAC',
    keyMaterial,
    encoder.encode(signedPayload)
  );

  const computedHmac = Array.from(new Uint8Array(signatureBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  // Constant-time comparison to prevent timing attacks
  if (computedHmac.length !== receivedHmac.length) return false;
  let diff = 0;
  for (let i = 0; i < computedHmac.length; i++) {
    diff |= computedHmac.charCodeAt(i) ^ receivedHmac.charCodeAt(i);
  }
  return diff === 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const signatureHeader = request.headers.get('Paddle-Signature') ?? '';
    const rawBody = await request.text();

    const valid = await verifyPaddleSignature(
      signatureHeader,
      rawBody,
      env.PADDLE_WEBHOOK_SECRET
    );
    if (!valid) {
      return new Response('Invalid Paddle signature', { status: 401 });
    }

    let event: PaddleEvent;
    try {
      event = JSON.parse(rawBody) as PaddleEvent;
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    // Idempotent insert — silently ignore duplicates
    await env.DB.prepare(
      `INSERT OR IGNORE INTO paddle_events (event_id, event_type, occurred_at, payload)
       VALUES (?1, ?2, ?3, ?4)`
    )
      .bind(event.event_id, event.event_type, event.occurred_at, rawBody)
      .run();

    await dispatchEvent(event, env);

    return new Response('ok', { status: 200 });
  },
};

type PaddleEvent = {
  event_id: string;
  event_type: string;
  occurred_at: string;
  data: Record<string, unknown>;
};
```

---

## Section 3 — Subscription State Machine

```typescript
type SubStatus = 'trialing' | 'active' | 'past_due' | 'paused' | 'cancelled';

// Map Paddle status strings to our state machine values
const STATUS_MAP: Record<string, SubStatus> = {
  trialing:  'trialing',
  active:    'active',
  past_due:  'past_due',
  paused:    'paused',
  canceled:  'cancelled',  // Paddle uses American spelling
  cancelled: 'cancelled',
};

async function upsertSubscription(
  data: Record<string, unknown>,
  env: Env
): Promise<void> {
  const sub = data as {
    id: string;
    customer_id: string;
    items: Array<{ price: { product_id: string } }>;
    status: string;
    current_billing_period: { starts_at: string; ends_at: string } | null;
    scheduled_change: { action: string; effective_at: string } | null;
  };

  const status: SubStatus = STATUS_MAP[sub.status] ?? 'active';
  const planId = sub.items[0]?.price?.product_id ?? 'unknown';
  const periodStart = sub.current_billing_period?.starts_at ?? null;
  const periodEnd = sub.current_billing_period?.ends_at ?? null;
  const cancelAt =
    sub.scheduled_change?.action === 'cancel'
      ? sub.scheduled_change.effective_at
      : null;

  await env.DB.prepare(
    `INSERT INTO paddle_subscriptions
       (paddle_sub_id, customer_id, plan_id, status,
        current_period_start, current_period_end, cancel_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
     ON CONFLICT(paddle_sub_id) DO UPDATE
       SET status               = excluded.status,
           plan_id              = excluded.plan_id,
           current_period_start = excluded.current_period_start,
           current_period_end   = excluded.current_period_end,
           cancel_at            = excluded.cancel_at,
           updated_at           = datetime('now')`
  )
    .bind(sub.id, sub.customer_id, planId, status, periodStart, periodEnd, cancelAt)
    .run();
}

async function dispatchEvent(event: PaddleEvent, env: Env): Promise<void> {
  switch (event.event_type) {
    case 'subscription.created':
    case 'subscription.updated':
    case 'subscription.activated':
    case 'subscription.past_due':
    case 'subscription.paused':
    case 'subscription.cancelled':
      await upsertSubscription(event.data, env);
      break;

    case 'transaction.completed':
      // Grant entitlement — implement your own logic here
      console.log('Transaction completed', event.event_id);
      break;

    default:
      console.log('Unhandled Paddle event', event.event_type);
  }
}
```

---

## Anti-patterns

- **Using Node.js `crypto` module** — It is unavailable in the Workers runtime; always use `crypto.subtle` from the global Web Crypto API.
- **Parsing the body before signature verification** — Always read the raw body first and verify before parsing; re-reading from a parsed object can alter whitespace and break the HMAC.
- **Trusting `event_type` without verifying the signature** — An attacker can POST arbitrary events; verification must happen before any business logic.
- **Using `INSERT OR REPLACE` instead of `INSERT OR IGNORE`** — `OR REPLACE` deletes then re-inserts, resetting `processed_at` and losing the original ingestion timestamp.

---

## Gotchas

- Paddle's timestamp in the signature header uses seconds since epoch; replay-attack windows are your responsibility to enforce (reject events older than 300 s).
- `crypto.subtle.importKey` with `extractable: false` is required for secret keys; passing `true` will succeed but is a security anti-pattern.
- Paddle sends `canceled` (one `l`) in some event payloads; normalise with `STATUS_MAP` to avoid CHECK constraint failures.
- The `data` object schema differs between event types; type-guard before accessing nested fields.
- Workers free tier has a 10 ms CPU limit per request; the HMAC operation is fast but avoid blocking async chains before returning the response.

---

## Verification

```bash
# Send a test webhook from Paddle dashboard or CLI
curl -X POST https://your-worker.workers.dev/ \
  -H 'Content-Type: application/json' \
  -H 'Paddle-Signature: ts=1700000000;h1=<computed-hmac>' \
  -d @test_payload.json

# Check event landed in D1
npx wrangler d1 execute billing --command \
  "SELECT event_id, event_type, processed_at FROM paddle_events ORDER BY processed_at DESC LIMIT 5;"

# Verify subscription state
npx wrangler d1 execute billing --command \
  "SELECT paddle_sub_id, status, updated_at FROM paddle_subscriptions;"
```

---

## Related

- `payment-idempotency-key-workers-kv.md`
- `stripe-subscription-pause-resume-workers.md`

---

## Sources

- Paddle Webhook Verification — https://developer.paddle.com/webhooks/signature-verification
- Paddle Subscription Events — https://developer.paddle.com/webhooks/entities/subscriptions
- Web Crypto API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API
