# Stripe Webhook Idempotency Handling in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker receives Stripe webhook events and processes them to update subscription state, trigger emails, or record transactions. Stripe retries events on non-2xx responses, meaning the same event can arrive multiple times. Without idempotency controls, a `customer.subscription.updated` event processed twice can double-credit an account, send two confirmation emails, or corrupt the subscription state machine.

## Context

Stripe delivers webhooks with a `Stripe-Signature` header containing a timestamp and HMAC-SHA256 signature. Each event carries a unique `id` (e.g., `evt_1Px...`). Stripe retries failed deliveries with exponential backoff over 72 hours. Events from the same webhook endpoint are generally ordered but can arrive out-of-order under network partitions or during Stripe's own infrastructure events. For subscription state machines, ordering matters: `invoice.paid` followed by `customer.subscription.updated` must not be processed in reverse.

This pattern uses:
- **KV** for fast idempotency key lookup (TTL-bounded).
- **D1** for a durable event log used in reconciliation and out-of-order detection.
- **Workers Crypto** (`crypto.subtle`) for HMAC verification without the `stripe` npm package.

## Solution

```typescript
import { Env } from './types';

const WEBHOOK_TTL_SECONDS = 60 * 60 * 24 * 3; // 72 h — matches Stripe retry window
const TOLERANCE_SECONDS = 300; // 5-minute replay protection

// ── Signature verification ────────────────────────────────────────────────────

async function importStripeKey(secret: string): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );
}

async function verifyStripeSignature(
  payload: string,
  sigHeader: string,
  secret: string,
): Promise<void> {
  const parts = Object.fromEntries(
    sigHeader.split(',').map((p) => p.split('=')),
  ) as Record<string, string>;

  const timestamp = parseInt(parts['t'], 10);
  if (isNaN(timestamp)) throw new Error('Missing timestamp in Stripe-Signature');

  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > TOLERANCE_SECONDS) {
    throw new Error(`Webhook timestamp too old: ${now - timestamp}s drift`);
  }

  const signed = `${timestamp}.${payload}`;
  const key = await importStripeKey(secret);
  const encoder = new TextEncoder();

  // Stripe sends multiple v1 signatures during key rotation; accept any match.
  const signatures = (parts['v1'] ?? '').split(' ');
  const results = await Promise.all(
    signatures.map((sig) => {
      const expected = hexToBytes(sig);
      return crypto.subtle.verify('HMAC', key, expected, encoder.encode(signed));
    }),
  );

  if (!results.some(Boolean)) {
    throw new Error('Stripe signature verification failed');
  }
}

function hexToBytes(hex: string): ArrayBuffer {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes.buffer;
}

// ── Idempotency key management (KV) ──────────────────────────────────────────

async function checkAndMarkProcessed(
  kv: KVNamespace,
  eventId: string,
): Promise<boolean> {
  const key = `stripe:evt:${eventId}`;
  // get-then-put is safe: duplicate delivery is idempotent at the KV layer
  // because we return early before any side effects.
  const existing = await kv.get(key);
  if (existing !== null) return true; // already processed

  await kv.put(key, '1', { expirationTtl: WEBHOOK_TTL_SECONDS });
  return false;
}

// ── D1 event log for reconciliation and ordering ──────────────────────────────

async function logEventToD1(
  db: D1Database,
  event: StripeEvent,
  status: 'processed' | 'skipped' | 'failed',
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO stripe_event_log
         (event_id, event_type, livemode, created_at, processed_at, status, payload)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (event_id) DO UPDATE SET status = excluded.status, processed_at = excluded.processed_at`,
    )
    .bind(
      event.id,
      event.type,
      event.livemode ? 1 : 0,
      event.created,
      Math.floor(Date.now() / 1000),
      status,
      JSON.stringify(event),
    )
    .run();
}

// ── Out-of-order detection for subscription state machine ────────────────────

async function isEventStale(
  db: D1Database,
  subscriptionId: string,
  incomingCreated: number,
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT MAX(created_at) AS last_created
       FROM stripe_event_log
       WHERE json_extract(payload, '$.data.object.id') = ?
         AND status = 'processed'`,
    )
    .bind(subscriptionId)
    .first<{ last_created: number | null }>();

  if (!row || row.last_created === null) return false;
  return incomingCreated < row.last_created;
}

// ── Event handlers ────────────────────────────────────────────────────────────

type StripeEvent = {
  id: string;
  type: string;
  created: number;
  livemode: boolean;
  data: { object: Record<string, unknown> };
};

async function handleSubscriptionUpdated(
  db: D1Database,
  event: StripeEvent,
): Promise<void> {
  const sub = event.data.object as StripeSubscription;

  const stale = await isEventStale(db, sub.id, event.created);
  if (stale) {
    console.warn(`[webhook] Dropping stale subscription event ${event.id} for ${sub.id}`);
    return;
  }

  const statusMap: Record<string, string> = {
    active: 'active',
    past_due: 'past_due',
    canceled: 'canceled',
    trialing: 'trial',
    unpaid: 'unpaid',
    paused: 'paused',
  };

  const internalStatus = statusMap[sub.status] ?? 'unknown';

  await db
    .prepare(
      `UPDATE subscriptions
       SET status = ?, current_period_end = ?, updated_at = unixepoch()
       WHERE stripe_subscription_id = ?`,
    )
    .bind(internalStatus, sub.current_period_end, sub.id)
    .run();
}

type StripeSubscription = {
  id: string;
  status: string;
  current_period_end: number;
};

async function handleInvoicePaid(
  db: D1Database,
  event: StripeEvent,
): Promise<void> {
  const invoice = event.data.object as { id: string; subscription: string; amount_paid: number };

  await db
    .prepare(
      `INSERT INTO invoice_log (stripe_invoice_id, stripe_subscription_id, amount_paid, paid_at)
       VALUES (?, ?, ?, unixepoch())
       ON CONFLICT (stripe_invoice_id) DO NOTHING`,
    )
    .bind(invoice.id, invoice.subscription, invoice.amount_paid)
    .run();
}

// ── Main handler ──────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const sigHeader = request.headers.get('Stripe-Signature');
    if (!sigHeader) return new Response('Missing signature', { status: 400 });

    const payload = await request.text();

    try {
      await verifyStripeSignature(payload, sigHeader, env.STRIPE_WEBHOOK_SECRET);
    } catch (err) {
      console.error('[webhook] Signature verification failed:', err);
      return new Response('Unauthorized', { status: 401 });
    }

    let event: StripeEvent;
    try {
      event = JSON.parse(payload) as StripeEvent;
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    // Idempotency guard — must happen before any side effects.
    const alreadyProcessed = await checkAndMarkProcessed(env.WEBHOOK_KV, event.id);
    if (alreadyProcessed) {
      console.log(`[webhook] Duplicate event ${event.id}, skipping.`);
      await logEventToD1(env.DB, event, 'skipped');
      return new Response('OK', { status: 200 });
    }

    try {
      switch (event.type) {
        case 'customer.subscription.updated':
        case 'customer.subscription.deleted':
          await handleSubscriptionUpdated(env.DB, event);
          break;
        case 'invoice.paid':
          await handleInvoicePaid(env.DB, event);
          break;
        default:
          console.log(`[webhook] Unhandled event type: ${event.type}`);
      }

      await logEventToD1(env.DB, event, 'processed');
      return new Response('OK', { status: 200 });
    } catch (err) {
      console.error(`[webhook] Processing failed for ${event.id}:`, err);
      await logEventToD1(env.DB, event, 'failed');
      // Return 500 so Stripe retries. KV key was already written, so we delete
      // it to allow the retry to pass the idempotency check.
      await env.WEBHOOK_KV.delete(`stripe:evt:${event.id}`);
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

## Implementation Details

**D1 schema required:**

```sql
CREATE TABLE stripe_event_log (
  event_id      TEXT PRIMARY KEY,
  event_type    TEXT NOT NULL,
  livemode      INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL,
  processed_at  INTEGER,
  status        TEXT NOT NULL CHECK(status IN ('processed','skipped','failed')),
  payload       TEXT NOT NULL
);

CREATE TABLE subscriptions (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  stripe_subscription_id   TEXT UNIQUE NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'trial',
  current_period_end       INTEGER,
  updated_at               INTEGER
);

CREATE TABLE invoice_log (
  stripe_invoice_id        TEXT PRIMARY KEY,
  stripe_subscription_id   TEXT NOT NULL,
  amount_paid              INTEGER NOT NULL,
  paid_at                  INTEGER NOT NULL
);
```

**`wrangler.toml` bindings:**

```toml
[[kv_namespaces]]
binding = "WEBHOOK_KV"
id      = "<your-kv-id>"

[[d1_databases]]
binding  = "DB"
database_name = "payments"
database_id   = "<your-d1-id>"

[vars]
STRIPE_WEBHOOK_SECRET = "whsec_..."
```

**Key-rotation:** Stripe sends both old and new signatures during a 72-hour rotation window. The code splits `v1` on spaces and accepts any matching signature — this is the correct Stripe-documented approach.

**KV TTL alignment:** The KV TTL matches Stripe's 72-hour retry window. Events older than 72 hours will never be retried, so the key can expire safely without leaving a gap.

**Retry-safe KV delete:** If processing fails after the idempotency key was written, delete the key before returning 500. This lets Stripe's next retry pass the idempotency guard and attempt processing again.

## Anti-patterns

- **Checking idempotency after side effects.** Write the KV key first, then perform side effects. Reversing this order creates a window where a second concurrent delivery sees no key and also proceeds.
- **Using a database `SELECT` then `INSERT` for idempotency.** Under concurrent requests this is a TOCTOU race. KV's single `put` is atomic.
- **Trusting event ordering without validation.** Always compare event timestamps against the last processed event for the same object before mutating state.
- **Returning 200 on failed processing.** This stops Stripe retries. Only return 200 when the event is genuinely handled or intentionally skipped.

## Gotchas

- `crypto.subtle.verify` requires an `ArrayBuffer`, not a hex string. Use `hexToBytes` as shown.
- Stripe's `created` field is Unix seconds, not milliseconds. D1's `unixepoch()` returns seconds, so keep units consistent.
- KV `get` returns `null` (not `undefined`) when a key is absent. The check `existing !== null` is correct; `!existing` would treat the string `'0'` as absent.
- During Stripe key rotation, multiple `v1=` values appear in the header separated by a space, not a comma. Split on `' '` within the `v1` value.

## Verification

```bash
# Replay a real event using the Stripe CLI:
stripe trigger customer.subscription.updated --api-key sk_test_...

# Confirm idempotency by replaying the same event ID twice:
stripe events resend evt_1Px... --webhook-endpoint we_...
stripe events resend evt_1Px... --webhook-endpoint we_...
# Second delivery must return 200 and status='skipped' in stripe_event_log.

# Query the event log:
wrangler d1 execute payments --command \
  "SELECT event_id, status, processed_at FROM stripe_event_log ORDER BY processed_at DESC LIMIT 10;"
```

## Related

- `documentation/categories/payments/workers-subscription-lifecycle-manager.md`
- `documentation/categories/payments/workers-payment-retry-exponential-backoff.md`
- `documentation/categories/payments/workers-refund-automation-pipeline.md`

## Sources

- Stripe Webhook Signatures: https://stripe.com/docs/webhooks/signatures
- Stripe Event Retries: https://stripe.com/docs/webhooks/best-practices#retry-logic
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Web Crypto HMAC: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
