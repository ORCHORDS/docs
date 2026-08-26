# PayPal Webhook Processing with Signature Validation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your PayPal webhook handler is accepting events without verifying the signature, leaving it vulnerable to spoofed requests. You need a Cloudflare Workers handler that validates the `PAYPAL-TRANSMISSION-SIG` RSA-SHA256 signature, rejects replays, and idempotently updates order status in D1.

## Context

PayPal signs webhook events using RSA-SHA256. The signature covers a concatenation of `PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-TIME`, `PAYPAL-WEBHOOK-ID`, and a CRC32 of the raw body. The signing certificate is available at the URL in the `PAYPAL-CERT-URL` header and rotates periodically — cache it in KV with a 24-hour TTL to avoid hammering PayPal's CDN.

Replay protection uses `PAYPAL-TRANSMISSION-TIME` (ISO 8601); events older than 5 minutes are rejected. Idempotency uses a D1 `paypal_events` table with a `UNIQUE` constraint on `event_id`.

## Worker Implementation

```typescript
// src/paypal-webhooks.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  CERT_CACHE: KVNamespace;
  PAYPAL_WEBHOOK_ID: string;
}

// D1 schema:
// CREATE TABLE paypal_events (
//   event_id   TEXT UNIQUE NOT NULL,
//   event_type TEXT NOT NULL,
//   resource   TEXT NOT NULL,  -- JSON blob
//   received_at INTEGER NOT NULL
// );
// CREATE TABLE orders (
//   order_id TEXT PRIMARY KEY,
//   status   TEXT NOT NULL,
//   updated_at INTEGER NOT NULL
// );

const app = new Hono<{ Bindings: Env }>();

async function crc32(data: string): Promise<number> {
  // Cloudflare Workers does not expose a CRC32 API; implement via table lookup
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c;
  }
  let crc = 0xffffffff;
  for (const byte of new TextEncoder().encode(data)) {
    crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

async function fetchCertificate(certUrl: string, kv: KVNamespace): Promise<CryptoKey> {
  const cacheKey = `paypal-cert:${certUrl}`;
  const cached = await kv.get(cacheKey);
  let pemChain: string;

  if (cached) {
    pemChain = cached;
  } else {
    const res = await fetch(certUrl);
    if (!res.ok) throw new Error(`Failed to fetch PayPal cert: ${res.status}`);
    pemChain = await res.text();
    await kv.put(cacheKey, pemChain, { expirationTtl: 86400 }); // 24 h
  }

  // Extract only the first certificate (leaf) from the chain
  const match = pemChain.match(/-----BEGIN CERTIFICATE-----([\s\S]+?)-----END CERTIFICATE-----/);
  if (!match) throw new Error('Could not parse PayPal certificate PEM');

  const der = Uint8Array.from(atob(match[1].replace(/\s/g, '')), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    'spki',
    der,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify']
  );
}

async function verifyPayPalSignature(
  headers: Record<string, string>,
  rawBody: string,
  webhookId: string,
  kv: KVNamespace
): Promise<boolean> {
  const transmissionId = headers['paypal-transmission-id'];
  const transmissionTime = headers['paypal-transmission-time'];
  const certUrl = headers['paypal-cert-url'];
  const sig = headers['paypal-transmission-sig'];

  if (!transmissionId || !transmissionTime || !certUrl || !sig) return false;

  // Replay protection: reject events older than 5 minutes
  const eventTime = new Date(transmissionTime).getTime();
  if (Date.now() - eventTime > 5 * 60 * 1000) return false;

  const bodyCrc = await crc32(rawBody);
  const message = `${transmissionId}|${transmissionTime}|${webhookId}|${bodyCrc}`;

  const publicKey = await fetchCertificate(certUrl, kv);
  const sigBytes = Uint8Array.from(atob(sig), (c) => c.charCodeAt(0));

  return crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    publicKey,
    sigBytes,
    new TextEncoder().encode(message)
  );
}

const STATUS_MAP: Record<string, string> = {
  'PAYMENT.CAPTURE.COMPLETED': 'paid',
  'PAYMENT.CAPTURE.DENIED': 'failed',
  'PAYMENT.CAPTURE.REFUNDED': 'refunded',
  'CHECKOUT.ORDER.APPROVED': 'approved',
};

app.post('/webhooks/paypal', async (c) => {
  const rawBody = await c.req.text();
  const headers: Record<string, string> = {};
  for (const [k, v] of c.req.raw.headers.entries()) {
    headers[k.toLowerCase()] = v;
  }

  const valid = await verifyPayPalSignature(
    headers,
    rawBody,
    c.env.PAYPAL_WEBHOOK_ID,
    c.env.CERT_CACHE
  );
  if (!valid) {
    return c.json({ error: 'invalid_signature_or_replay' }, 401);
  }

  const event = JSON.parse(rawBody) as {
    id: string;
    event_type: string;
    resource: { id: string; [k: string]: unknown };
  };

  // Idempotency: insert with UNIQUE constraint; skip on conflict
  const insert = await c.env.DB.prepare(
    `INSERT OR IGNORE INTO paypal_events (event_id, event_type, resource, received_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(event.id, event.event_type, JSON.stringify(event.resource), Date.now())
    .run();

  if (insert.meta.changes === 0) {
    // Already processed — acknowledge without re-processing
    return c.json({ status: 'duplicate' }, 200);
  }

  const newStatus = STATUS_MAP[event.event_type];
  if (newStatus && event.resource.id) {
    await c.env.DB.prepare(
      `INSERT INTO orders (order_id, status, updated_at)
       VALUES (?, ?, ?)
       ON CONFLICT(order_id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at`
    )
      .bind(String(event.resource.id), newStatus, Date.now())
      .run();
  }

  return c.json({ status: 'ok' }, 200);
});

export default app;
```

## D1 Schema

```sql
-- migrations/0001_paypal_events.sql
CREATE TABLE IF NOT EXISTS paypal_events (
  event_id    TEXT UNIQUE NOT NULL,
  event_type  TEXT NOT NULL,
  resource    TEXT NOT NULL,
  received_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  order_id   TEXT PRIMARY KEY,
  status     TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

## Anti-patterns

- **Using PayPal's `/v1/notifications/verify-webhook-signature` REST endpoint instead of local verification**: This adds 200–500 ms of latency and an extra network call on every event. Local verification with `crypto.subtle` is both faster and more reliable.
- **Not caching the signing certificate**: PayPal's cert URL changes when they rotate certificates, not on every request. Cache aggressively (24 h) but key on the full URL so a rotation is picked up automatically.
- **Skipping the CRC32 of the body**: PayPal's signature covers the body CRC, not the raw body. Omitting it produces a verification string that never matches.

## Gotchas

- `PAYPAL-TRANSMISSION-TIME` is in ISO 8601 format but timezone is not always `Z` — use `new Date(ts).getTime()` rather than string-comparing.
- PayPal can send the same event multiple times if your endpoint returns a non-2xx response. Always return 200 after successful insertion, even if the business logic produces no state change.
- The certificate chain in `PAYPAL-CERT-URL` may contain intermediate certificates. The signature uses the leaf certificate's public key, so extract only the first PEM block.

## Verification

```bash
# 1. Use PayPal Webhooks Simulator (sandbox dashboard) to send a test event
# 2. Check D1 for the inserted event
wrangler d1 execute <DB_NAME> \
  --command "SELECT event_id, event_type, received_at FROM paypal_events ORDER BY received_at DESC LIMIT 5;"

# 3. Confirm a duplicate is rejected
# Re-send the same event ID from the simulator; the response should be {status: 'duplicate'}

# 4. Tamper test: modify the body by 1 byte before sending
# The Worker should return 401
```

## Related

- `stripe-radar-custom-rules-workers-integration.md`
- `adyen-payments-workers-integration.md`
- PayPal webhook reference: https://developer.paypal.com/api/rest/webhooks/

## Sources

- PayPal webhook signature verification: https://developer.paypal.com/api/rest/webhooks/rest/#link-eventpayloadvalidation
- Web Crypto API — RSASSA-PKCS1-v1_5: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
- Cloudflare D1: https://developers.cloudflare.com/d1/
