# Paddle Billing Webhook Verification and Processing in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Products using Paddle Billing on Cloudflare Workers receive webhooks for subscription and transaction lifecycle events but need to verify authenticity before trusting the payload. Paddle uses a different signing scheme from Stripe — an Ed25519 signature on the raw body — which requires the Web Crypto `verify` operation with the `NODE-ED25519` / `Ed25519` algorithm. This article shows how to verify Paddle webhook signatures without external SDKs, handle the key subscription and transaction events, and map Paddle price IDs to feature flags stored in KV.

---

## Context

Paddle Billing (the 2023+ API, distinct from Paddle Classic) signs webhooks using Ed25519. The signature is provided in the `Paddle-Signature` header as `ts=<timestamp>;h1=<hex-encoded-signature>`. Paddle publishes a webhook secret in your Dashboard under Developer Tools > Notifications; this secret is a base64-encoded Ed25519 public key used for verification. Workers' Web Crypto API supports Ed25519 natively under the `NODE-ED25519` algorithm name (Chrome-compatible runtimes) or the `Ed25519` name on modern runtimes. The key events to handle are `subscription.created`, `subscription.updated`, `subscription.canceled`, and `transaction.completed`. D1 stores canonical subscription records; KV maps Paddle price IDs to feature-flag sets for fast access gating.

---

## Section 1 — D1 Schema and KV Configuration

```sql
-- migrations/0003_paddle_subscriptions.sql
CREATE TABLE IF NOT EXISTS paddle_subscriptions (
  id                    TEXT PRIMARY KEY,    -- Paddle subscription ID: sub_xxx
  customer_id           TEXT NOT NULL,       -- Paddle customer ID: ctm_xxx
  status                TEXT NOT NULL,       -- active | trialing | paused | canceled | past_due
  price_id              TEXT NOT NULL,       -- pri_xxx
  quantity              INTEGER NOT NULL DEFAULT 1,
  current_period_start  INTEGER NOT NULL,    -- Unix timestamp
  current_period_end    INTEGER NOT NULL,    -- Unix timestamp
  canceled_at           INTEGER,
  custom_data           TEXT,                -- JSON blob of your metadata
  updated_at            INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_paddle_subs_customer
  ON paddle_subscriptions (customer_id);
CREATE INDEX IF NOT EXISTS idx_paddle_subs_status
  ON paddle_subscriptions (status);

CREATE TABLE IF NOT EXISTS paddle_transactions (
  id           TEXT PRIMARY KEY,   -- txn_xxx
  customer_id  TEXT NOT NULL,
  subscription_id TEXT,
  status       TEXT NOT NULL,      -- completed | billed | canceled | refunded
  total        TEXT NOT NULL,      -- String decimal, e.g. "29.99"
  currency     TEXT NOT NULL,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);
```

```toml
# wrangler.toml additions
[[kv_namespaces]]
binding = "FEATURE_FLAGS_KV"
id = "<your-feature-flags-kv-id>"

# Seed feature flags in KV (key: price:<priceId>)
# Example value: {"features":["analytics","export","api_access"],"tier":"pro"}
```

---

## Section 2 — Worker Webhook Verification and Handler

```typescript
// src/paddle-webhook.ts
import { D1Database, KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  FEATURE_FLAGS_KV: KVNamespace;
  PADDLE_WEBHOOK_SECRET: string;   // Base64-encoded Ed25519 public key from Dashboard
}

/**
 * Verify Paddle Billing webhook signature using Ed25519 / Web Crypto.
 * Header format: `ts=1234567890;h1=<hex-signature>`
 */
async function verifyPaddleSignature(
  rawBody: ArrayBuffer,
  signatureHeader: string,
  secretBase64: string,
): Promise<boolean> {
  const parts: Record<string, string> = {};
  for (const part of signatureHeader.split(';')) {
    const [k, v] = part.split('=');
    if (k && v) parts[k.trim()] = v.trim();
  }

  const timestamp = parts['ts'];
  const hexSig = parts['h1'];
  if (!timestamp || !hexSig) return false;

  // Verify timestamp freshness (5 minute tolerance)
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > 300) return false;

  // Decode public key from base64
  const publicKeyBytes = Uint8Array.from(atob(secretBase64), (c) => c.charCodeAt(0));

  // Import as Ed25519 public key for verification
  let publicKey: CryptoKey;
  try {
    publicKey = await crypto.subtle.importKey(
      'raw',
      publicKeyBytes,
      { name: 'Ed25519' },
      false,
      ['verify'],
    );
  } catch {
    // Fallback for runtimes that use NODE-ED25519 name
    publicKey = await crypto.subtle.importKey(
      'raw',
      publicKeyBytes,
      { name: 'NODE-ED25519', namedCurve: 'NODE-ED25519' } as AlgorithmIdentifier,
      false,
      ['verify'],
    );
  }

  // Signed payload is `ts:body`
  const encoder = new TextEncoder();
  const bodyText = new TextDecoder().decode(rawBody);
  const signedPayload = encoder.encode(`${timestamp}:${bodyText}`);

  // Decode hex signature
  const sigBytes = new Uint8Array(
    hexSig.match(/.{2}/g)!.map((byte) => parseInt(byte, 16)),
  );

  return crypto.subtle.verify('Ed25519', publicKey, sigBytes, signedPayload);
}

interface PaddleSubscription {
  id: string;
  customer_id: string;
  status: string;
  items: Array<{ price: { id: string }; quantity: number }>;
  current_billing_period: { starts_at: string; ends_at: string };
  canceled_at?: string;
  custom_data?: Record<string, unknown>;
}

interface PaddleTransaction {
  id: string;
  customer_id: string;
  subscription_id?: string;
  status: string;
  details: { totals: { total: string; currency_code: string } };
}

async function handleSubscriptionCreatedOrUpdated(
  sub: PaddleSubscription,
  env: Env,
): Promise<void> {
  const periodStart = Math.floor(new Date(sub.current_billing_period.starts_at).getTime() / 1000);
  const periodEnd = Math.floor(new Date(sub.current_billing_period.ends_at).getTime() / 1000);
  const canceledAt = sub.canceled_at
    ? Math.floor(new Date(sub.canceled_at).getTime() / 1000)
    : null;
  const priceId = sub.items[0]?.price?.id ?? '';
  const quantity = sub.items[0]?.quantity ?? 1;

  await env.DB.prepare(
    `INSERT INTO paddle_subscriptions
       (id, customer_id, status, price_id, quantity, current_period_start, current_period_end, canceled_at, custom_data)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (id) DO UPDATE SET
       status                = excluded.status,
       price_id              = excluded.price_id,
       quantity              = excluded.quantity,
       current_period_start  = excluded.current_period_start,
       current_period_end    = excluded.current_period_end,
       canceled_at           = excluded.canceled_at,
       custom_data           = excluded.custom_data,
       updated_at            = unixepoch()`,
  )
    .bind(
      sub.id,
      sub.customer_id,
      sub.status,
      priceId,
      quantity,
      periodStart,
      periodEnd,
      canceledAt,
      sub.custom_data ? JSON.stringify(sub.custom_data) : null,
    )
    .run();
}

async function handleTransactionCompleted(
  txn: PaddleTransaction,
  env: Env,
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR IGNORE INTO paddle_transactions
       (id, customer_id, subscription_id, status, total, currency)
     VALUES (?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      txn.id,
      txn.customer_id,
      txn.subscription_id ?? null,
      txn.status,
      txn.details.totals.total,
      txn.details.totals.currency_code,
    )
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const sigHeader = request.headers.get('Paddle-Signature');
    if (!sigHeader) return new Response('Missing signature', { status: 400 });

    const rawBody = await request.arrayBuffer();
    const valid = await verifyPaddleSignature(rawBody, sigHeader, env.PADDLE_WEBHOOK_SECRET);
    if (!valid) return new Response('Invalid signature', { status: 400 });

    const event = JSON.parse(new TextDecoder().decode(rawBody)) as {
      event_type: string;
      data: PaddleSubscription | PaddleTransaction;
    };

    switch (event.event_type) {
      case 'subscription.created':
      case 'subscription.updated':
      case 'subscription.canceled':
        await handleSubscriptionCreatedOrUpdated(event.data as PaddleSubscription, env);
        break;

      case 'transaction.completed':
        await handleTransactionCompleted(event.data as PaddleTransaction, env);
        break;

      default:
        console.log(`Unhandled Paddle event: ${event.event_type}`);
    }

    return new Response('OK', { status: 200 });
  },
};
```

---

## Section 3 — Feature Flag Lookup from KV

```typescript
// src/feature-access.ts
import { D1Database, KVNamespace } from '@cloudflare/workers-types';

interface PriceFeatureFlags {
  features: string[];
  tier: string;
}

export async function getCustomerFeatures(
  customerId: string,
  db: D1Database,
  kv: KVNamespace,
): Promise<{ tier: string; features: string[] } | null> {
  const sub = await db
    .prepare(
      `SELECT price_id FROM paddle_subscriptions
       WHERE customer_id = ? AND status IN ('active', 'trialing')
       ORDER BY updated_at DESC LIMIT 1`,
    )
    .bind(customerId)
    .first<{ price_id: string }>();

  if (!sub) return null;

  const flags = await kv.get<PriceFeatureFlags>(`price:${sub.price_id}`, 'json');
  return flags ?? { tier: 'unknown', features: [] };
}

// Usage in a request handler:
// const features = await getCustomerFeatures(customerId, env.DB, env.FEATURE_FLAGS_KV);
// if (!features?.features.includes('api_access')) return new Response('Forbidden', { status: 403 });
```

---

## Anti-patterns

- **Using the Paddle Node.js SDK in Workers** — The SDK uses Node.js-specific crypto modules not available in the Workers runtime. Implement verification manually with Web Crypto as shown above.
- **Trusting `event_type` without signature verification** — Paddle webhook bodies are unauthenticated without the signature check; always verify before acting.
- **Keying feature flags by subscription ID** — Price IDs are stable across customers; subscription IDs are per-customer. Key your flag map by price ID for reuse.
- **Ignoring `subscription.updated` events** — Price changes (upgrades/downgrades) fire `subscription.updated`, not `subscription.created`. Always upsert on both.

---

## Gotchas

- Paddle's Ed25519 `secretBase64` is the **public key** from your notification settings — it is safe to store as a Worker secret and use only for `verify` operations, never `sign`.
- The signed payload format is `<timestamp>:<rawBody>` with a colon separator, not a period as in Stripe.
- `subscription.canceled` sets `status: 'canceled'` but the access period extends to `current_billing_period.ends_at` — do not revoke access immediately.
- Paddle's `items` array can contain multiple price IDs for multi-seat subscriptions; index `[0]` only covers the primary price.
- In Paddle sandbox, the webhook secret is different from production — use separate Worker environments with separate secrets.

---

## Verification

```bash
# Apply migrations
npx wrangler d1 execute example project-db --file migrations/0003_paddle_subscriptions.sql

# Seed feature flags in KV
npx wrangler kv:key put --binding FEATURE_FLAGS_KV \
  "price:pri_01example" \
  '{"features":["analytics","export","api_access"],"tier":"pro"}'

# Simulate Paddle webhook (replace with real Paddle test event)
curl -X POST https://your-worker.workers.dev/webhooks/paddle \
  -H 'Content-Type: application/json' \
  -H 'Paddle-Signature: ts=1234567890;h1=<test-sig>' \
  -d @test-paddle-subscription-created.json

# Check D1
npx wrangler d1 execute example project-db --command \
  "SELECT id, customer_id, status, price_id FROM paddle_subscriptions LIMIT 10;"
```

---

## Related

- `stripe-webhooks-workers-d1-event-deduplication.md`
- `workers-payment-retry-exponential-backoff-queues.md`

---

## Sources

- Paddle Webhook Verification — https://developer.paddle.com/webhooks/signature-verification
- Paddle Billing Events — https://developer.paddle.com/webhooks/overview
- Web Crypto Ed25519 — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
- Cloudflare D1 — https://developers.cloudflare.com/d1/
