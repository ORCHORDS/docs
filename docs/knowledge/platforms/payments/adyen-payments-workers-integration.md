# Adyen Payments Integration with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to integrate Adyen Drop-in on a Cloudflare Pages site with a Workers backend that creates payment sessions, validates HMAC-signed webhook notifications, stores notification history in D1, and runs a nightly reconciliation cron against Adyen's settlement reports.

## Context

Adyen uses a two-phase web checkout: first, your server creates a `/sessions` object (server-to-server); then the browser loads the Drop-in web component which completes the payment. Webhook notifications are signed with HMAC-SHA256 using a key you configure in the Adyen Customer Area. Reconciliation compares Adyen's batch settlement CSV (fetched from the Reports API) against your D1 `orders` table to catch discrepancies.

## Worker Implementation

```typescript
// src/adyen.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  ADYEN_API_KEY: string;
  ADYEN_HMAC_KEY: string;        // Hex-encoded HMAC key from Adyen Customer Area
  ADYEN_MERCHANT_ACCOUNT: string;
  ADYEN_LIVE_URL_PREFIX: string; // e.g. "1234abcd" for live, empty for test
}

const app = new Hono<{ Bindings: Env }>();

function adyenBaseUrl(env: Env, service: 'checkout' | 'reports'): string {
  if (!env.ADYEN_LIVE_URL_PREFIX) {
    return service === 'checkout'
      ? 'https://checkout-test.adyen.com/v71'
      : 'https://ca-test.adyen.com/ca/services/ReportService/v4';
  }
  return service === 'checkout'
    ? `https://${env.ADYEN_LIVE_URL_PREFIX}-checkout-live.adyenpayments.com/checkout/v71`
    : `https://ca-live.adyen.com/ca/services/ReportService/v4`;
}

// ── 1. Create Payment Session ────────────────────────────────────────────────
app.post('/adyen/sessions', async (c) => {
  const { amount, currency, reference, returnUrl } = await c.req.json<{
    amount: number;
    currency: string;
    reference: string;
    returnUrl: string;
  }>();

  const res = await fetch(`${adyenBaseUrl(c.env, 'checkout')}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-API-key': c.env.ADYEN_API_KEY,
    },
    body: JSON.stringify({
      merchantAccount: c.env.ADYEN_MERCHANT_ACCOUNT,
      amount: { currency, value: amount },
      reference,
      returnUrl,
      channel: 'Web',
    }),
  });

  if (!res.ok) {
    const err = await res.json();
    return c.json({ error: 'adyen_session_error', detail: err }, 502);
  }

  const session = await res.json() as { id: string; sessionData: string };
  return c.json({ sessionId: session.id, sessionData: session.sessionData });
});

// ── 2. HMAC Signature Verification ──────────────────────────────────────────
async function verifyAdyenHmac(
  notification: Record<string, string>,
  hmacKey: string
): Promise<boolean> {
  // Adyen signs: pspReference + originalReference + merchantAccountCode +
  //              merchantReference + value + currency + eventCode + success
  const fields = [
    notification.pspReference ?? '',
    notification.originalReference ?? '',
    notification.merchantAccountCode ?? '',
    notification.merchantReference ?? '',
    notification.amount_value ?? '',
    notification.amount_currency ?? '',
    notification.eventCode ?? '',
    notification.success ?? '',
  ];
  const message = fields.join(':');
  const keyBytes = hexToBytes(hmacKey);
  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(message));
  const expected = btoa(String.fromCharCode(...new Uint8Array(sig)));
  return expected === (notification.additionalData_hmacSignature ?? '');
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

// ── 3. Webhook Notification Handler ─────────────────────────────────────────
app.post('/adyen/notifications', async (c) => {
  const body = await c.req.json<{
    notificationItems: Array<{ NotificationRequestItem: Record<string, string> }>;
  }>();

  for (const { NotificationRequestItem: item } of body.notificationItems) {
    const valid = await verifyAdyenHmac(item, c.env.ADYEN_HMAC_KEY);
    if (!valid) {
      return c.json({ error: 'invalid_hmac' }, 401);
    }

    // Idempotent upsert
    await c.env.DB.prepare(
      `INSERT INTO adyen_notifications
         (psp_reference, event_code, success, amount, processed_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(psp_reference) DO NOTHING`
    )
      .bind(
        item.pspReference,
        item.eventCode,
        item.success === 'true' ? 1 : 0,
        parseInt(item.amount_value ?? '0', 10),
        Date.now()
      )
      .run();

    if (item.eventCode === 'AUTHORISATION' && item.success === 'true') {
      await c.env.DB.prepare(
        `UPDATE orders SET status = 'paid', updated_at = ? WHERE adyen_reference = ?`
      )
        .bind(Date.now(), item.merchantReference)
        .run();
    }
  }

  return c.text('[accepted]', 200);
});

// ── 4. Reconciliation Cron (scheduled handler) ───────────────────────────────
export async function reconcileCron(env: Env): Promise<void> {
  const yesterday = new Date(Date.now() - 86400_000);
  const dateStr = yesterday.toISOString().slice(0, 10).replace(/-/g, '_');
  const reportUrl =
    `${adyenBaseUrl(env, 'reports')}/getAccountSettlementReport?` +
    `merchantAccount=${env.ADYEN_MERCHANT_ACCOUNT}&date=${dateStr}`;

  const res = await fetch(reportUrl, {
    headers: { 'x-API-key': env.ADYEN_API_KEY },
  });
  if (!res.ok) throw new Error(`Report fetch failed: ${res.status}`);

  const csvText = await res.text();
  const lines = csvText.split('\n').slice(1); // skip header

  for (const line of lines) {
    if (!line.trim()) continue;
    const cols = line.split(',');
    const pspRef = cols[2]?.trim();
    const settledAmount = parseInt(cols[7]?.trim() ?? '0', 10);

    if (!pspRef) continue;

    const row = await env.DB.prepare(
      `SELECT amount FROM adyen_notifications WHERE psp_reference = ? AND event_code = 'SETTLEMENT_DETAIL'`
    )
      .bind(pspRef)
      .first<{ amount: number }>();

    if (!row) {
      console.warn(`Reconciliation: PSP reference ${pspRef} not found in D1`);
    } else if (row.amount !== settledAmount) {
      console.error(
        `Reconciliation mismatch for ${pspRef}: D1=${row.amount}, report=${settledAmount}`
      );
    }
  }
}

export default {
  fetch: app.fetch,
  async scheduled(_event: ScheduledEvent, env: Env) {
    await reconcileCron(env);
  },
};
```

## D1 Schema

```sql
-- migrations/0001_adyen.sql
CREATE TABLE IF NOT EXISTS adyen_notifications (
  psp_reference TEXT PRIMARY KEY,
  event_code    TEXT NOT NULL,
  success       INTEGER NOT NULL,  -- 1 = true, 0 = false
  amount        INTEGER NOT NULL,  -- minor units
  processed_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  order_id        TEXT PRIMARY KEY,
  adyen_reference TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  updated_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_adyen_ref ON orders (adyen_reference);
```

## Anti-patterns

- **Using the test endpoint on live keys or vice versa**: Adyen's live endpoint URL includes a merchant-specific prefix. Hardcoding the test URL in production silently fails to capture real payments.
- **Not returning `[accepted]` immediately**: Adyen retries notifications if your endpoint returns non-200 or takes more than 10 seconds. Always ACK first, process asynchronously if needed.
- **Verifying only the first notification item**: `notificationItems` is an array — validate and persist every item in the batch.

## Gotchas

- The HMAC key in Adyen Customer Area is displayed as hex. Do not base64-decode it before importing into `crypto.subtle` — use the raw hex bytes.
- `amount_value` in webhook notification items is a string representing minor currency units (e.g. `"1999"` for £19.99). Parse it with `parseInt` before storing.
- The cron reconciliation report is generated by Adyen at around 02:00 UTC the following day. Schedule the cron for 06:00 UTC to ensure the report is ready.

## Verification

```bash
# 1. Create a test session
curl -X POST https://your-worker.workers.dev/adyen/sessions \
  -H 'Content-Type: application/json' \
  -d '{"amount":1999,"currency":"GBP","reference":"test-001","returnUrl":"https://example.com/return"}'

# 2. In Adyen Customer Area → Developers → Webhooks → test notification
# Confirm the D1 row appears:
wrangler d1 execute <DB_NAME> \
  --command "SELECT * FROM adyen_notifications ORDER BY processed_at DESC LIMIT 5;"

# 3. Verify reconciliation (dry run against test report)
wrangler dev --test-scheduled  # triggers the cron handler
```

## Related

- `paypal-webhooks-workers-signature-validation.md`
- `stripe-radar-custom-rules-workers-integration.md`
- Adyen Drop-in Web Component docs: https://docs.adyen.com/online-payments/web-drop-in/

## Sources

- Adyen Sessions API: https://docs.adyen.com/online-payments/web-drop-in/additional-use-cases/advanced-flow/
- Adyen HMAC signatures: https://docs.adyen.com/development-resources/webhooks/verify-hmac-signatures/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
