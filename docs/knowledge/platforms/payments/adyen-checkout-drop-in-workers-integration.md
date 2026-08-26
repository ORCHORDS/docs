# Adyen Web Drop-in Checkout Integration with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to embed Adyen's hosted Drop-in UI on your frontend while keeping all
server-side session creation, payment result handling, and webhook notification
processing inside Cloudflare Workers. You need the Workers edge to act as both
the `/sessions` proxy and the notification webhook receiver with HMAC
verification.

---

## Context

Adyen's Web Drop-in is a pre-built, PCI-DSS-compliant UI component. The
integration flow is:

1. Frontend loads the Drop-in component (JS + CSS from Adyen CDN).
2. Frontend calls your Workers `/checkout/session` endpoint to obtain a
   `sessionId` and `sessionData` blob.
3. Drop-in mounts, handles 3DS redirects, and fires a final `onPaymentCompleted`
   callback with a `resultCode`.
4. Adyen asynchronously sends STANDARD_NOTIFICATION webhooks to your Workers
   endpoint — the authoritative payment result.

The critical rule: **never trust the client-side `resultCode` as payment proof**.
Always rely on the webhook `success` field stored in D1.

---

## Architecture

```
Browser (Drop-in JS)
  │  POST /checkout/session  ──►  Worker (create Adyen /sessions)
  │◄─────── { sessionId, sessionData, clientKey } ──────────────
  │
  │  [User completes payment in Drop-in]
  │
  │  GET /checkout/result?sessionId=…  ──►  Worker (poll D1)
  │◄─────── { status: "authorised" | "pending" | "failed" }

Adyen Notification Server  POST /webhooks/adyen  ──►  Worker (verify + write D1)
```

---

## D1 Schema

```sql
-- migrations/0001_adyen_sessions.sql
CREATE TABLE IF NOT EXISTS adyen_sessions (
  session_id      TEXT PRIMARY KEY,
  merchant_ref    TEXT NOT NULL,
  amount_value    INTEGER NOT NULL,
  amount_currency TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'created',  -- created | authorised | refused | error | cancelled
  psp_reference   TEXT,
  raw_result_code TEXT,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_adyen_sessions_merchant_ref
  ON adyen_sessions(merchant_ref);

CREATE TABLE IF NOT EXISTS adyen_notifications (
  event_id        TEXT PRIMARY KEY,   -- pspReference + eventCode composite
  psp_reference   TEXT NOT NULL,
  event_code      TEXT NOT NULL,
  success         INTEGER NOT NULL,   -- 0 | 1
  merchant_ref    TEXT,
  raw_payload     TEXT NOT NULL,
  received_at     INTEGER NOT NULL
);
```

---

## Worker: Create Adyen /sessions

```typescript
// src/checkout-session.ts
interface Env {
  ADYEN_API_KEY: string;
  ADYEN_MERCHANT_ACCOUNT: string;
  ADYEN_CLIENT_KEY: string;
  ADYEN_ENVIRONMENT: 'test' | 'live';
  DB: D1Database;
}

interface SessionRequest {
  amount: { value: number; currency: string };
  reference: string;  // your internal order ID
  returnUrl: string;
}

export async function createCheckoutSession(
  req: Request,
  env: Env,
): Promise<Response> {
  const body = await req.json<SessionRequest>();

  const adyenHost =
    env.ADYEN_ENVIRONMENT === 'live'
      ? 'https://checkout-live.adyen.com/v71'
      : 'https://checkout-test.adyen.com/v71';

  const adyenRes = await fetch(`${adyenHost}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': env.ADYEN_API_KEY,
    },
    body: JSON.stringify({
      amount: body.amount,
      reference: body.reference,
      merchantAccount: env.ADYEN_MERCHANT_ACCOUNT,
      returnUrl: body.returnUrl,
      // Enable 3DS2 by default
      authenticationData: {
        threeDSRequestData: { nativeThreeDS: 'preferred' },
      },
      channel: 'Web',
      shopperInteraction: 'Ecommerce',
    }),
  });

  if (!adyenRes.ok) {
    const err = await adyenRes.text();
    console.error('Adyen /sessions error', adyenRes.status, err);
    return new Response(JSON.stringify({ error: 'adyen_session_failed' }), {
      status: 502,
    });
  }

  const session = await adyenRes.json<{ id: string; sessionData: string }>();
  const now = Date.now();

  await env.DB.prepare(
    `INSERT INTO adyen_sessions
       (session_id, merchant_ref, amount_value, amount_currency, status, created_at, updated_at)
     VALUES (?, ?, ?, ?, 'created', ?, ?)`,
  )
    .bind(
      session.id,
      body.reference,
      body.amount.value,
      body.amount.currency,
      now,
      now,
    )
    .run();

  return new Response(
    JSON.stringify({
      sessionId: session.id,
      sessionData: session.sessionData,
      clientKey: env.ADYEN_CLIENT_KEY,
      environment: env.ADYEN_ENVIRONMENT,
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );
}
```

---

## Worker: HMAC Webhook Verification and Processing

```typescript
// src/adyen-webhook.ts
import { createHmac, timingSafeEqual } from 'node:crypto';

interface AdyenNotificationItem {
  NotificationRequestItem: {
    pspReference: string;
    merchantReference: string;
    eventCode: string;      // AUTHORISATION | CAPTURE | REFUND | CANCELLATION …
    success: string;        // 'true' | 'false'
    amount?: { value: number; currency: string };
    additionalData?: Record<string, string>;
  };
}

function verifyHmac(item: AdyenNotificationItem['NotificationRequestItem'], hmacKey: string): boolean {
  const ri = item;
  // Adyen HMAC signing string order (v2 format)
  const parts = [
    ri.pspReference,
    ri.originalReference ?? '',
    ri.merchantAccountCode ?? '',
    ri.merchantReference,
    String(ri.amount?.value ?? ''),
    ri.amount?.currency ?? '',
    ri.eventCode,
    ri.success,
  ];
  const signingString = parts.map(p => p.replace(/\\/g, '\\\\').replace(/:/g, '\\:')).join(':');
  const key = Buffer.from(hmacKey, 'hex');
  const expected = createHmac('sha256', key).update(signingString, 'utf8').digest('base64');
  const received = ri.additionalData?.hmacSignature ?? '';
  try {
    return timingSafeEqual(Buffer.from(expected), Buffer.from(received));
  } catch {
    return false;
  }
}

export async function handleAdyenWebhook(req: Request, env: Env): Promise<Response> {
  const payload = await req.json<{ notificationItems: AdyenNotificationItem[] }>();

  for (const { NotificationRequestItem: item } of payload.notificationItems) {
    if (!verifyHmac(item, env.ADYEN_HMAC_KEY)) {
      console.error('Adyen HMAC mismatch for', item.pspReference);
      return new Response('[rejected]', { status: 401 });
    }

    const eventId = `${item.pspReference}:${item.eventCode}`;
    const now = Date.now();

    // Idempotent insert
    await env.DB.prepare(
      `INSERT OR IGNORE INTO adyen_notifications
         (event_id, psp_reference, event_code, success, merchant_ref, raw_payload, received_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        eventId,
        item.pspReference,
        item.eventCode,
        item.success === 'true' ? 1 : 0,
        item.merchantReference,
        JSON.stringify(item),
        now,
      )
      .run();

    if (item.eventCode === 'AUTHORISATION') {
      const status = item.success === 'true' ? 'authorised' : 'refused';
      await env.DB.prepare(
        `UPDATE adyen_sessions
         SET status = ?, psp_reference = ?, raw_result_code = ?, updated_at = ?
         WHERE merchant_ref = ?`,
      )
        .bind(status, item.pspReference, item.success, now, item.merchantReference)
        .run();
    }
  }

  // Adyen requires this exact response body
  return new Response('[accepted]', { status: 200 });
}
```

---

## Anti-patterns

- **Trusting client-side `resultCode`** — Drop-in fires `onPaymentCompleted`
  before Adyen sends the webhook. Network failures or user-side manipulation can
  cause divergence. Always confirm against D1.
- **Returning HTTP 200 before persisting** — Adyen retries on any non-200. Write
  to D1 inside the handler, then respond `[accepted]`.
- **Skipping HMAC on test notifications** — Adyen test notifications include a
  real HMAC. Verify in all environments.
- **Hardcoding `v71` version** — Pin explicitly; Adyen API versions are stable
  but old versions are eventually sunset. Track Adyen's changelog.
- **Missing `returnUrl` for 3DS redirects** — Drop-in needs a `returnUrl` in the
  session payload; without it, card-not-present 3DS challenges break.

---

## Gotchas

- **`sessionData` is a signed blob** — do not parse or mutate it; pass it
  verbatim to the Drop-in constructor.
- **Event code order is not guaranteed** — a CAPTURE can arrive before
  AUTHORISATION on some payment methods (e.g., SEPA mandate prenotification).
  Use `INSERT OR IGNORE` to handle replays safely.
- **`[accepted]` response must be plain text** — Adyen's notification service
  checks the literal string `[accepted]` (no JSON wrapper).
- **Live endpoint hostname** — for live environments the hostname is
  `checkout-live.adyen.com` (not `checkout.adyen.com`); using the wrong host
  returns 404.
- **HMAC key is hex-encoded** — decode with `Buffer.from(key, 'hex')` before
  passing to `createHmac`; using it as UTF-8 string produces wrong signatures.

---

## Verification

```bash
# 1. Create a test session
curl -X POST https://your-worker.example.com/checkout/session \
  -H 'Content-Type: application/json' \
  -d '{"amount":{"value":1000,"currency":"EUR"},"reference":"test-001","returnUrl":"https://example.com/return"}'

# 2. Confirm row in D1
wrangler d1 execute DB --command "SELECT * FROM adyen_sessions WHERE merchant_ref='test-001';"

# 3. Trigger a test notification via Adyen CA
#    Adyen Customer Area → Developers → Webhooks → Test notification

# 4. Confirm notification stored and session status updated
wrangler d1 execute DB --command "SELECT status, psp_reference FROM adyen_sessions WHERE merchant_ref='test-001';"
```

---

## Related

- `adyen-webhook-hmac-payload-contract.md`
- `adyen-token-lifecycle-shopper-binding.md`
- `stripe-checkout-session-cloudflare-workers.md`
- `payment-sca-exemption-engine-workers-d1.md`
- `idempotency-keys-payment-apis.md`

---

## Sources

- Adyen Web Drop-in docs: https://docs.adyen.com/online-payments/web-drop-in/
- Adyen Sessions API: https://docs.adyen.com/api-explorer/Checkout/71/post/sessions
- Adyen HMAC calculation: https://docs.adyen.com/development-resources/webhooks/verify-hmac-signatures/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
