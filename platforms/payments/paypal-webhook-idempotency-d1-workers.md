# PayPal Webhook Idempotency and Deduplication with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

PayPal retries webhook notifications for up to **3 days** with exponential
backoff. Your Workers handler processes order captures, subscription renewals,
and dispute events. Without idempotency guards, a single payment event is
processed multiple times: revenue is double-counted, fulfillment emails fire
twice, and dispute responses are sent repeatedly.

You need a D1-backed event log that (a) verifies PayPal's HTTPS webhook
certificate, (b) deduplicates on `transmission_id`, and (c) guarantees
at-least-once delivery with no double-processing.

---

## Context

PayPal webhook verification flow:

1. PayPal signs the request using an asymmetric certificate. The
   `PAYPAL-TRANSMISSION-SIG` header contains the signature.
2. You call PayPal's `/v1/notifications/verify-webhook-signature` API to
   verify. Alternatively, verify locally using the downloaded PayPal cert
   (see `paypal-webhook-certificate-verification.md`).
3. Once verified, check the D1 event log for `transmission_id`. If present,
   return HTTP 200 immediately without re-processing.
4. Process the event, then write to D1 atomically.

Critical constraint: PayPal expects HTTP 200 within **30 seconds**. D1 writes
complete in < 5 ms on Cloudflare's backbone; the verification API call to PayPal
is the bottleneck (~100–300 ms). Use local cert verification in production for
speed.

---

## D1 Schema

```sql
-- migrations/0003_paypal_events.sql
CREATE TABLE IF NOT EXISTS paypal_events (
  transmission_id   TEXT PRIMARY KEY,
  event_id          TEXT NOT NULL,            -- PayPal PAYPAL-TRANSMISSION-ID
  event_type        TEXT NOT NULL,            -- e.g. CHECKOUT.ORDER.APPROVED
  resource_type     TEXT NOT NULL,
  resource_id       TEXT NOT NULL,            -- order ID, subscription ID, etc.
  status            TEXT NOT NULL DEFAULT 'received',  -- received | processed | failed
  raw_payload       TEXT NOT NULL,
  received_at       INTEGER NOT NULL,         -- unix ms
  processed_at      INTEGER                   -- null until handled
);

-- Fast lookup by resource for "has this order been captured?"
CREATE INDEX IF NOT EXISTS idx_paypal_events_resource
  ON paypal_events(resource_id, event_type);

CREATE INDEX IF NOT EXISTS idx_paypal_events_received
  ON paypal_events(received_at);
```

---

## PayPal Webhook Verification (Remote API)

```typescript
// src/paypal-verify.ts
interface PayPalVerifyRequest {
  auth_algo: string;
  cert_url: string;
  transmission_id: string;
  transmission_sig: string;
  transmission_time: string;
  webhook_id: string;
  webhook_event: unknown;
}

export async function verifyWebhookRemote(
  headers: Headers,
  body: string,
  webhookId: string,
  accessToken: string,
): Promise<boolean> {
  const payload: PayPalVerifyRequest = {
    auth_algo: headers.get('PAYPAL-AUTH-ALGO') ?? '',
    cert_url: headers.get('PAYPAL-CERT-URL') ?? '',
    transmission_id: headers.get('PAYPAL-TRANSMISSION-ID') ?? '',
    transmission_sig: headers.get('PAYPAL-TRANSMISSION-SIG') ?? '',
    transmission_time: headers.get('PAYPAL-TRANSMISSION-TIME') ?? '',
    webhook_id: webhookId,
    webhook_event: JSON.parse(body),
  };

  const res = await fetch(
    'https://api-m.paypal.com/v1/notifications/verify-webhook-signature',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  );

  if (!res.ok) {
    console.error('PayPal verify API error', res.status, await res.text());
    return false;
  }

  const { verification_status } = await res.json<{ verification_status: string }>();
  return verification_status === 'SUCCESS';
}
```

---

## Worker: Idempotent Webhook Handler

```typescript
// src/paypal-webhook.ts
interface Env {
  PAYPAL_WEBHOOK_ID: string;
  PAYPAL_CLIENT_ID: string;
  PAYPAL_CLIENT_SECRET: string;
  DB: D1Database;
}

interface PayPalEvent {
  id: string;
  event_type: string;
  resource_type: string;
  resource: { id: string; [k: string]: unknown };
  summary: string;
}

async function getAccessToken(env: Env): Promise<string> {
  const credentials = btoa(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_CLIENT_SECRET}`);
  const res = await fetch('https://api-m.paypal.com/v1/oauth2/token', {
    method: 'POST',
    headers: {
      Authorization: `Basic ${credentials}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: 'grant_type=client_credentials',
  });
  const { access_token } = await res.json<{ access_token: string }>();
  return access_token;
}

export async function handlePayPalWebhook(req: Request, env: Env): Promise<Response> {
  const body = await req.text();
  const transmissionId = req.headers.get('PAYPAL-TRANSMISSION-ID') ?? '';

  if (!transmissionId) {
    return new Response('Missing transmission ID', { status: 400 });
  }

  // --- Step 1: Idempotency check BEFORE verification (fast path) ---
  const existing = await env.DB.prepare(
    `SELECT status FROM paypal_events WHERE transmission_id = ?`,
  )
    .bind(transmissionId)
    .first<{ status: string }>();

  if (existing !== null) {
    // Already seen — return 200 without re-processing
    console.log(`PayPal event ${transmissionId} already ${existing.status}; skipping`);
    return new Response('ok', { status: 200 });
  }

  // --- Step 2: Verify signature ---
  const accessToken = await getAccessToken(env);
  const valid = await verifyWebhookRemote(
    req.headers,
    body,
    env.PAYPAL_WEBHOOK_ID,
    accessToken,
  );

  if (!valid) {
    console.error('PayPal webhook signature invalid for', transmissionId);
    return new Response('Invalid signature', { status: 401 });
  }

  // --- Step 3: Parse and insert atomically ---
  const event: PayPalEvent = JSON.parse(body);
  const now = Date.now();

  // Use INSERT OR IGNORE for race-condition safety (concurrent Workers instances)
  const { success } = await env.DB.prepare(
    `INSERT OR IGNORE INTO paypal_events
       (transmission_id, event_id, event_type, resource_type, resource_id,
        status, raw_payload, received_at)
     VALUES (?, ?, ?, ?, ?, 'received', ?, ?)`,
  )
    .bind(
      transmissionId,
      event.id,
      event.event_type,
      event.resource_type,
      event.resource?.id ?? 'unknown',
      body,
      now,
    )
    .run()
    .then(r => r);

  if (!success) {
    // Another instance beat us to the insert — idempotency preserved
    return new Response('ok', { status: 200 });
  }

  // --- Step 4: Process the event ---
  try {
    await dispatchPayPalEvent(event, env);

    await env.DB.prepare(
      `UPDATE paypal_events SET status = 'processed', processed_at = ? WHERE transmission_id = ?`,
    )
      .bind(Date.now(), transmissionId)
      .run();
  } catch (err) {
    console.error('PayPal event processing failed:', err);
    await env.DB.prepare(
      `UPDATE paypal_events SET status = 'failed', processed_at = ? WHERE transmission_id = ?`,
    )
      .bind(Date.now(), transmissionId)
      .run();
    // Still return 200 so PayPal stops retrying; handle via DLQ or manual review
    return new Response('ok', { status: 200 });
  }

  return new Response('ok', { status: 200 });
}

async function dispatchPayPalEvent(event: PayPalEvent, env: Env): Promise<void> {
  switch (event.event_type) {
    case 'CHECKOUT.ORDER.APPROVED':
      await handleOrderApproved(event, env);
      break;
    case 'PAYMENT.CAPTURE.COMPLETED':
      await handleCaptureCompleted(event, env);
      break;
    case 'CUSTOMER.DISPUTE.CREATED':
      await handleDisputeCreated(event, env);
      break;
    default:
      console.log(`Unhandled PayPal event type: ${event.event_type}`);
  }
}

async function handleOrderApproved(event: PayPalEvent, env: Env): Promise<void> {
  // Your order approval logic here
  console.log('Order approved:', event.resource.id);
}

async function handleCaptureCompleted(event: PayPalEvent, env: Env): Promise<void> {
  console.log('Capture completed:', event.resource.id);
}

async function handleDisputeCreated(event: PayPalEvent, env: Env): Promise<void> {
  console.log('Dispute created:', event.resource.id);
}
```

---

## Handling Concurrent Workers Instances

Multiple Workers instances can receive the same webhook simultaneously (PayPal
may fire to the same endpoint in parallel during retries). The D1 `INSERT OR
IGNORE` on `transmission_id` (PRIMARY KEY) provides the final guard:

- First instance: INSERT succeeds → processes the event.
- Second instance: INSERT returns `success: false` (duplicate) → returns 200
  immediately without re-processing.

This is safe because D1 serialises writes at the database level.

---

## Replaying Failed Events

```typescript
// src/replay.ts
export async function replayFailed(env: Env): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT transmission_id, raw_payload
     FROM paypal_events
     WHERE status = 'failed'
     ORDER BY received_at ASC
     LIMIT 50`,
  ).all<{ transmission_id: string; raw_payload: string }>();

  for (const row of results) {
    const event: PayPalEvent = JSON.parse(row.raw_payload);
    try {
      await dispatchPayPalEvent(event, env);
      await env.DB.prepare(
        `UPDATE paypal_events SET status = 'processed', processed_at = ? WHERE transmission_id = ?`,
      )
        .bind(Date.now(), row.transmission_id)
        .run();
    } catch (err) {
      console.error('Replay failed for', row.transmission_id, err);
    }
  }
}
```

---

## Anti-patterns

- **Checking idempotency AFTER verification** — this doubles latency on replays
  (you pay the PayPal API round-trip cost twice for already-seen events). Check
  D1 first; only call the verification API for genuinely new events.
- **Using `event.id` as the dedup key** — PayPal can send the same logical event
  with different `PAYPAL-TRANSMISSION-ID` values (multiple delivery attempts).
  The `transmission_id` header is the per-delivery unique identifier; `event.id`
  is the per-event identifier. Store both, dedup on `transmission_id`.
- **Returning non-200 on processing errors** — PayPal interprets any 4xx/5xx as
  a signal to retry indefinitely. Return 200 to acknowledge receipt, and handle
  processing failures internally.
- **Not handling `INSERT OR IGNORE` false-success** — check `meta.changes` or
  the return value to confirm the row was actually inserted vs ignored.
- **Logging full `raw_payload` at INFO level in production** — PayPal payloads
  contain PII and card-adjacent data. Store in D1 but do not log.

---

## Gotchas

- **`cert_url` must be a PayPal domain** — before calling `/verify-webhook-signature`,
  validate that `cert_url` starts with `https://api.paypal.com/` or
  `https://api.sandbox.paypal.com/` to prevent SSRF attacks where an attacker
  points `cert_url` to their own server.
- **PayPal retries for 3 days** — events from 72 hours ago can arrive. Keep your
  `paypal_events` table retention policy longer than 3 days.
- **Sandbox uses `api.sandbox.paypal.com`** — hardcode the production base URL
  in the verification call but derive it from environment config. A mismatch
  causes all sandbox verifications to fail silently.
- **Access tokens expire in 9 hours** — cache the token in KV with an expiry of
  `expires_in - 60` seconds rather than fetching it on every webhook.
- **`resource` shape varies by `event_type`** — the `resource` field on
  `PAYMENT.CAPTURE.COMPLETED` is a Capture object; on `CHECKOUT.ORDER.APPROVED`
  it is an Order. Type your handlers specifically.

---

## Verification

```bash
# 1. Check event log
wrangler d1 execute DB --command \
  "SELECT event_type, status, COUNT(*) FROM paypal_events GROUP BY event_type, status;"

# 2. Trigger a test webhook from PayPal Developer Dashboard
#    My Apps → Webhooks → Send test event

# 3. Verify deduplication: send same transmission_id twice
#    Second call should return 200 with "Already processed" log line and no DB change

# 4. Find failed events for replay
wrangler d1 execute DB --command \
  "SELECT transmission_id, event_type, received_at FROM paypal_events WHERE status='failed';"
```

---

## Related

- `paypal-webhook-certificate-verification.md`
- `paypal-webhooks.md`
- `paypal-orders-v2-workers-integration.md`
- `stripe-webhook-idempotency-d1-event-log.md`
- `idempotency-keys-payment-apis.md`

---

## Sources

- PayPal Webhook Event Types: https://developer.paypal.com/api/rest/webhooks/event-names/
- PayPal Webhook Verification: https://developer.paypal.com/api/rest/webhooks/
- PayPal retry policy: https://developer.paypal.com/api/rest/webhooks/#link-notificationmessages
- Cloudflare D1 INSERT OR IGNORE: https://developers.cloudflare.com/d1/sql-api/sql-statements/
