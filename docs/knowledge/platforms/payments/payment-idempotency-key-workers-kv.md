# Implementing Payment Idempotency in a Cloudflare Worker with KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A mobile client retries a failed network request and triggers a double charge. You need the Worker to detect duplicate payment requests using a client-supplied idempotency key, return the cached response for repeats, and record every attempt in D1 for auditing.

---

## Context

Idempotency keys are short-lived, client-generated tokens (UUID v4) that uniquely identify a payment intent creation attempt. The Worker stores the result of the first successful attempt in KV under a compound key (`idem:{key}`) with a TTL matching Stripe's own idempotency window (24 hours). On duplicate requests the KV-cached response is returned verbatim without touching Stripe. D1 records every inbound attempt — hit or miss — so finance teams can audit retries and detect abuse. The KV entry stores both the HTTP status code and the response body to faithfully replay the original outcome, including errors, so the client cannot force a success by retrying a failed payment.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS payment_attempts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT NOT NULL,
  user_id         TEXT NOT NULL,
  amount          INTEGER NOT NULL,
  currency        TEXT NOT NULL,
  status          TEXT NOT NULL CHECK(status IN ('pending','success','error','duplicate')),
  stripe_pi_id    TEXT,                   -- NULL for duplicates and errors
  response_status INTEGER NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_key
  ON payment_attempts (idempotency_key, created_at);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_user
  ON payment_attempts (user_id, created_at);
```

---

## Section 2 — Worker Implementation

```typescript
import Stripe from 'stripe';

export interface Env {
  DB: D1Database;
  IDEM_CACHE: KVNamespace;
  STRIPE_SECRET_KEY: string;
}

interface PaymentRequest {
  idempotency_key: string;   // UUID v4 supplied by the client
  user_id: string;
  amount: number;            // cents
  currency: string;
  payment_method_id: string;
}

interface CachedResponse {
  status: number;
  body: string;
}

const IDEM_TTL_SECONDS = 60 * 60 * 24;  // 24 hours — matches Stripe's window

function isValidUUIDv4(key: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(key);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/payments') {
      return new Response('Not found', { status: 404 });
    }

    let body: PaymentRequest;
    try {
      body = await request.json<PaymentRequest>();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    const { idempotency_key, user_id, amount, currency, payment_method_id } = body;

    // Validate idempotency key format
    if (!idempotency_key || !isValidUUIDv4(idempotency_key)) {
      return new Response(
        JSON.stringify({ error: 'idempotency_key must be a UUID v4' }),
        { status: 422, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const kvKey = `idem:${idempotency_key}`;

    // --- Check KV cache first (fast path) ---
    const cached = await env.IDEM_CACHE.get<CachedResponse>(kvKey, 'json');
    if (cached) {
      // Log the duplicate attempt to D1 for audit
      await logAttempt(env, {
        idempotency_key,
        user_id,
        amount,
        currency,
        status: 'duplicate',
        stripe_pi_id: null,
        response_status: cached.status,
      });

      return new Response(cached.body, {
        status: cached.status,
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Replay': 'true',
        },
      });
    }

    // --- First attempt — call Stripe ---
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
    let responseStatus = 500;
    let responseBody = '';
    let stripePaymentIntentId: string | null = null;
    let attemptStatus: 'success' | 'error' = 'error';

    try {
      const pi = await stripe.paymentIntents.create(
        {
          amount,
          currency,
          payment_method: payment_method_id,
          confirm: true,
          automatic_payment_methods: { enabled: true, allow_redirects: 'never' },
          metadata: { idempotency_key, user_id },
        },
        {
          // Forward the idempotency key to Stripe so THEY also deduplicate
          idempotencyKey: idempotency_key,
        }
      );

      stripePaymentIntentId = pi.id;
      attemptStatus = 'success';
      responseStatus = 201;
      responseBody = JSON.stringify({ id: pi.id, status: pi.status, client_secret: <redacted-secret> });
    } catch (err) {
      const stripeErr = err as Stripe.errors.StripeError;
      responseStatus = stripeErr.statusCode ?? 500;
      responseBody = JSON.stringify({ error: stripeErr.message, code: stripeErr.code });
    }

    // --- Store result in KV regardless of success/error ---
    await env.IDEM_CACHE.put(
      kvKey,
      JSON.stringify({ status: responseStatus, body: responseBody } satisfies CachedResponse),
      { expirationTtl: IDEM_TTL_SECONDS }
    );

    // --- Persist attempt to D1 ---
    await logAttempt(env, {
      idempotency_key,
      user_id,
      amount,
      currency,
      status: attemptStatus,
      stripe_pi_id: stripePaymentIntentId,
      response_status: responseStatus,
    });

    return new Response(responseBody, {
      status: responseStatus,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};

async function logAttempt(
  env: Env,
  data: {
    idempotency_key: string;
    user_id: string;
    amount: number;
    currency: string;
    status: string;
    stripe_pi_id: string | null;
    response_status: number;
  }
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO payment_attempts
       (idempotency_key, user_id, amount, currency, status, stripe_pi_id, response_status)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`
  )
    .bind(
      data.idempotency_key,
      data.user_id,
      data.amount,
      data.currency,
      data.status,
      data.stripe_pi_id,
      data.response_status
    )
    .run();
}
```

---

## Section 3 — Abuse Detection Query

```typescript
// GET /payments/abuse-report — find keys with excessive retries
export async function abuseReport(env: Env): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT idempotency_key,
            user_id,
            COUNT(*) AS total_attempts,
            SUM(CASE WHEN status = 'duplicate' THEN 1 ELSE 0 END) AS duplicate_count,
            MIN(created_at) AS first_seen,
            MAX(created_at) AS last_seen
     FROM payment_attempts
     WHERE created_at >= datetime('now', '-1 day')
     GROUP BY idempotency_key, user_id
     HAVING duplicate_count > 5
     ORDER BY duplicate_count DESC
     LIMIT 50`
  ).all();

  return Response.json({ report_date: new Date().toISOString(), results });
}
```

---

## Anti-patterns

- **Generating the idempotency key server-side** — The key must come from the client; a server-generated key on every request is just a nonce and provides no deduplication.
- **Only caching successes** — If the first attempt errors and you do not cache the error, a retry will re-attempt the charge, which can double-charge if the first attempt partially succeeded.
- **Using D1 as the primary idempotency check** — D1 has higher latency than KV; always hit KV first and fall back to D1 only for audit writes.
- **Accepting arbitrary strings as idempotency keys** — Validate UUID v4 format to prevent key collisions or injection attempts via malformed keys.

---

## Gotchas

- KV `get` returns `null` for missing keys; distinguish between `null` (cache miss) and `undefined` (API error) with explicit null checks.
- Forwarding the same idempotency key to Stripe (`idempotencyKey` option) is important — if your Worker retries the Stripe call on a 500, Stripe will replay the original result.
- KV `put` with `expirationTtl` must be at least 60 seconds; values under 60 s are rejected with a 400 error.
- The `CachedResponse` must store the HTTP status, not just the body, so error responses are replayed faithfully.
- In regions where KV read-after-write is not guaranteed, two near-simultaneous first requests with the same key may both reach Stripe; Stripe's own idempotency key handling will deduplicate at that layer.

---

## Verification

```bash
# First request — should charge
curl -X POST https://your-worker.workers.dev/payments \
  -H 'Content-Type: application/json' \
  -d '{"idempotency_key":"550e8400-e29b-41d4-a716-446655440000","user_id":"u1","amount":1000,"currency":"usd","payment_method_id":"pm_card_visa"}'

# Second request — same key, should return cached response with X-Idempotency-Replay: true
curl -v -X POST https://your-worker.workers.dev/payments \
  -H 'Content-Type: application/json' \
  -d '{"idempotency_key":"550e8400-e29b-41d4-a716-446655440000","user_id":"u1","amount":1000,"currency":"usd","payment_method_id":"pm_card_visa"}'

# Audit log
npx wrangler d1 execute billing --command \
  "SELECT idempotency_key, status, response_status, created_at FROM payment_attempts ORDER BY created_at DESC LIMIT 10;"
```

---

## Related

- `stripe-connect-platform-workers-d1.md`
- `paddle-webhook-workers-d1-billing.md`

---

## Sources

- Stripe Idempotency Keys — https://stripe.com/docs/api/idempotent_requests
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- RFC 4122 UUID v4 — https://www.rfc-editor.org/rfc/rfc4122
