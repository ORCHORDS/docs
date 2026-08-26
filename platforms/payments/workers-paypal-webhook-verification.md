# PayPal Webhook Signature Verification in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker receives PayPal webhook events for `PAYMENT.CAPTURE.COMPLETED` and needs to verify that the payload is authentic before updating an order in D1. PayPal uses RSA-SHA256 signatures with a rotating certificate fetched from `cert_url` in the payload headers. Verifying this in Workers avoids a round-trip to PayPal's `/v1/notifications/verify-webhook-signature` REST API.

---

## Context

PayPal signs webhooks using RSASSA-PKCS1-v1_5 with SHA-256. The signing certificate URL (`PAYPAL-CERT-URL`) is included in the HTTP headers, and the signature (`PAYPAL-TRANSMISSION-SIG`) is base64-encoded. The verification message is a pipe-delimited string of `PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-TIME`, your webhook ID, and a CRC32 of the raw body. The certificate itself (an X.509 PEM) must be fetched from PayPal's CDN and its public key imported via `crypto.subtle`. Certificates are cached in KV for 24 hours to avoid redundant fetches. Processed transmission IDs are stored in D1 to implement idempotency and prevent replay attacks.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS orders (
  id              TEXT PRIMARY KEY,
  paypal_order_id TEXT UNIQUE,
  amount_cents    INTEGER NOT NULL,
  currency        TEXT    NOT NULL,
  status          TEXT    NOT NULL DEFAULT 'pending',
  updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS paypal_transmissions (
  transmission_id TEXT PRIMARY KEY,
  processed_at    TEXT NOT NULL,
  event_type      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transmissions_processed
  ON paypal_transmissions(processed_at);
```

```bash
wrangler d1 create paypal-orders
wrangler d1 execute paypal-orders --file schema.sql
```

---

## Section 2 — Worker Implementation

```typescript
export interface Env {
  DB: D1Database;
  CERT_CACHE: KVNamespace;
  PAYPAL_WEBHOOK_ID: string;
}

// CRC32 lookup table
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let j = 0; j < 8; j++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

async function fetchCertificate(
  certUrl: string,
  env: Env
): Promise<CryptoKey> {
  const allowedBase = "https://api.paypal.com";
  if (!certUrl.startsWith(allowedBase) && !certUrl.startsWith("https://api.sandbox.paypal.com")) {
    throw new Error(`Untrusted PayPal cert URL: ${certUrl}`);
  }

  const cacheKey = `paypal:cert:${encodeURIComponent(certUrl)}`;
  const cached = await env.CERT_CACHE.get(cacheKey);

  let pemText: string;
  if (cached) {
    pemText = cached;
  } else {
    const res = await fetch(certUrl);
    if (!res.ok) throw new Error(`Failed to fetch PayPal cert: ${res.status}`);
    pemText = await res.text();
    await env.CERT_CACHE.put(cacheKey, pemText, { expirationTtl: 86400 });
  }

  // Extract DER from PEM
  const b64 = pemText
    .replace(/-----BEGIN CERTIFICATE-----|-----END CERTIFICATE-----/g, "")
    .replace(/\s/g, "");
  const der = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  return crypto.subtle.importKey(
    "spki",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"]
  );
}

async function verifyPayPalSignature(
  request: Request,
  rawBody: string,
  env: Env
): Promise<boolean> {
  const transmissionId = request.headers.get("PAYPAL-TRANSMISSION-ID") ?? "";
  const transmissionTime = request.headers.get("PAYPAL-TRANSMISSION-TIME") ?? "";
  const certUrl = request.headers.get("PAYPAL-CERT-URL") ?? "";
  const sigBase64 = request.headers.get("PAYPAL-TRANSMISSION-SIG") ?? "";

  if (!transmissionId || !transmissionTime || !certUrl || !sigBase64) {
    return false;
  }

  const encoder = new TextEncoder();
  const bodyCrc = crc32(encoder.encode(rawBody));
  const message = `${transmissionId}|${transmissionTime}|${env.PAYPAL_WEBHOOK_ID}|${bodyCrc}`;

  const publicKey = await fetchCertificate(certUrl, env);
  const signature = Uint8Array.from(atob(sigBase64), (c) => c.charCodeAt(0));

  return crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    publicKey,
    signature,
    encoder.encode(message)
  );
}

async function isAlreadyProcessed(
  db: D1Database,
  transmissionId: string
): Promise<boolean> {
  const row = await db
    .prepare("SELECT 1 FROM paypal_transmissions WHERE transmission_id = ?")
    .bind(transmissionId)
    .first();
  return row !== null;
}

async function markProcessed(
  db: D1Database,
  transmissionId: string,
  eventType: string
): Promise<void> {
  await db
    .prepare(
      `INSERT OR IGNORE INTO paypal_transmissions
       (transmission_id, processed_at, event_type) VALUES (?, ?, ?)`
    )
    .bind(transmissionId, new Date().toISOString(), eventType)
    .run();
}

async function handleCaptureCompleted(
  db: D1Database,
  event: Record<string, unknown>
): Promise<void> {
  const resource = event.resource as Record<string, unknown>;
  const supplementaryData = resource.supplementary_data as Record<string, unknown> | undefined;
  const relatedIds = supplementaryData?.related_ids as Record<string, string> | undefined;
  const orderId = relatedIds?.order_id;
  if (!orderId) return;

  await db
    .prepare(
      `UPDATE orders SET status = 'paid', updated_at = ?
       WHERE paypal_order_id = ? AND status = 'pending'`
    )
    .bind(new Date().toISOString(), orderId)
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (
      request.method !== "POST" ||
      new URL(request.url).pathname !== "/paypal/webhook"
    ) {
      return new Response("Not Found", { status: 404 });
    }

    const rawBody = await request.text();
    const transmissionId =
      request.headers.get("PAYPAL-TRANSMISSION-ID") ?? "";

    // Idempotency check
    if (await isAlreadyProcessed(env.DB, transmissionId)) {
      return new Response("Already processed", { status: 200 });
    }

    const isValid = await verifyPayPalSignature(request, rawBody, env);
    if (!isValid) {
      return new Response("Signature verification failed", { status: 401 });
    }

    let event: Record<string, unknown>;
    try {
      event = JSON.parse(rawBody);
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const eventType = (event.event_type as string) ?? "UNKNOWN";

    if (eventType === "PAYMENT.CAPTURE.COMPLETED") {
      await handleCaptureCompleted(env.DB, event);
    }

    await markProcessed(env.DB, transmissionId, eventType);

    return new Response("ok");
  },
};
```

---

## Section 3 — Configuration & Secrets

```bash
# Set secrets
wrangler secret put PAYPAL_WEBHOOK_ID
# Paste the Webhook ID from PayPal Developer Dashboard

# Create KV namespace for cert caching
wrangler kv namespace create CERT_CACHE

# Deploy
wrangler deploy
```

```toml
# wrangler.toml additions
[[kv_namespaces]]
binding = "CERT_CACHE"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "paypal-orders"
database_id = "<your-d1-database-id>"
```

---

## Anti-patterns

- **Calling PayPal's verify-webhook-signature REST API** — This adds ~200ms latency per webhook and has rate limits. Local crypto verification using `crypto.subtle` is faster and has no external dependency.
- **Not validating `cert_url` hostname** — PayPal's cert URL can be spoofed in a crafted request. Always check it begins with `https://api.paypal.com` or `https://api.sandbox.paypal.com`.
- **Consuming the request body twice** — `request.text()` can only be called once. Store the raw body string before parsing JSON, since you need it for signature verification.
- **Using `INSERT` instead of `INSERT OR IGNORE` for idempotency** — Under concurrent webhook delivery, two simultaneous requests with the same `transmissionId` could both pass the idempotency check before either writes. `INSERT OR IGNORE` at the D1 level is the safe guard.

---

## Gotchas

- PayPal's CRC32 uses the standard Castagnoli polynomial (0xEDB88320). Do not confuse it with CRC32C used in other contexts.
- The verification message must use the exact raw body string—do not re-serialize the parsed JSON, as key ordering may differ.
- PayPal rotates certificates periodically. The 24-hour KV TTL means stale certs are evicted automatically; if you set a longer TTL you may verify against an expired certificate.
- In sandbox mode, `PAYPAL-CERT-URL` points to `api.sandbox.paypal.com`. Your allowlist must include both sandbox and production domains.
- The `PAYMENT.CAPTURE.COMPLETED` event's `resource.supplementary_data.related_ids.order_id` field is only present when the capture was created from a PayPal Order. Direct capture flows use a different payload shape.

---

## Verification

```bash
# Send a test webhook from PayPal Developer Dashboard
# (Webhooks > Simulate > PAYMENT.CAPTURE.COMPLETED)

# Check D1 for processed transmission
wrangler d1 execute paypal-orders \
  --command "SELECT * FROM paypal_transmissions ORDER BY processed_at DESC LIMIT 5"

# Verify order status updated
wrangler d1 execute paypal-orders \
  --command "SELECT * FROM orders WHERE status = 'paid' ORDER BY updated_at DESC LIMIT 5"

# Confirm KV cert cache populated
wrangler kv key list --namespace-id <your-kv-namespace-id>
```

---

## Related

- `stripe-checkout-session-workers-d1.md`
- `workers-apple-pay-payment-session.md`
- `workers-invoice-pdf-r2.md`

---

## Sources

- PayPal Webhook Signature Verification — https://developer.paypal.com/api/rest/webhooks/
- Web Crypto RSASSA-PKCS1-v1_5 — https://developer.mozilla.org/en-US/docs/Web/API/RsaPssParams
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare KV — https://developers.cloudflare.com/kv/
