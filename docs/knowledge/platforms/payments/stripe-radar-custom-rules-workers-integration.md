# Stripe Radar Custom Rules with Cloudflare Workers Fraud Enrichment

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your default Stripe Radar rules block too little fraud or flag too many legitimate payments. You need a real-time fraud enrichment layer that Stripe can call during authorization to inject signals — device fingerprint, purchase velocity, and IP reputation — into custom Radar rule conditions.

## Context

Stripe Radar Extensions (early access) lets you register a HTTPS endpoint that Stripe calls synchronously before evaluating your custom rules. The endpoint receives a `payment_intent_id` and must return enrichment metadata within 2 seconds. Cloudflare Workers is an ideal host: sub-millisecond cold starts, D1 for velocity lookups, and KV for IP reputation cache.

Pre-requisites:
- Stripe account with Radar Extensions early access enabled
- Cloudflare Workers project with D1 database and KV namespace bound
- `fraud_signals` D1 table pre-created (schema below)
- IP reputation data loaded into KV (e.g. from MaxMind or IPQualityScore)

## Worker Implementation

```typescript
// src/radar-enrichment.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  IP_REPUTATION: KVNamespace;
  STRIPE_RADAR_SIGNING_SECRET: string;
}

const app = new Hono<{ Bindings: Env }>();

// D1 schema:
// CREATE TABLE fraud_signals (
//   payment_intent_id TEXT PRIMARY KEY,
//   device_fp         TEXT NOT NULL,
//   velocity_1h       INTEGER NOT NULL DEFAULT 0,
//   ip_score          REAL NOT NULL DEFAULT 0.0,
//   fraud_score       REAL NOT NULL DEFAULT 0.0,
//   created_at        INTEGER NOT NULL
// );

function computeFraudScore(velocity: number, ipScore: number): number {
  // Weighted formula: velocity contributes 60%, IP reputation 40%
  // velocity_1h >= 10 → velocity component maxes out at 100
  const velocityNorm = Math.min(velocity / 10, 1) * 100;
  const ipNorm = ipScore * 100; // ipScore is 0–1 where 1 = high risk
  return Math.round(velocityNorm * 0.6 + ipNorm * 0.4);
}

async function verifyStripeSignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const parts = Object.fromEntries(
    signature.split(',').map((p) => p.split('=') as [string, string])
  );
  const timestamp = parts['t'];
  const sig = parts['v1'];
  if (!timestamp || !sig) return false;

  const payload = `${timestamp}.${body}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const expected = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const expectedHex = Array.from(new Uint8Array(expected))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return expectedHex === sig;
}

app.post('/radar/enrich', async (c) => {
  const rawBody = await c.req.text();
  const signature = c.req.header('stripe-signature') ?? '';

  const valid = await verifyStripeSignature(
    rawBody,
    signature,
    c.env.STRIPE_RADAR_SIGNING_SECRET
  );
  if (!valid) return c.json({ error: 'invalid_signature' }, 401);

  const body = JSON.parse(rawBody) as {
    payment_intent_id: string;
    device_fingerprint: string;
    ip_address: string;
  };

  const { payment_intent_id, device_fingerprint, ip_address } = body;
  const now = Date.now();
  const oneHourAgo = now - 60 * 60 * 1000;

  // Velocity: count purchases from same device fingerprint in last 1 hour
  const velocityRow = await c.env.DB.prepare(
    `SELECT COUNT(*) as cnt FROM fraud_signals
     WHERE device_fp = ? AND created_at >= ?`
  )
    .bind(device_fingerprint, oneHourAgo)
    .first<{ cnt: number }>();
  const velocity1h = velocityRow?.cnt ?? 0;

  // IP reputation: 0.0 (clean) to 1.0 (high risk), stored as string in KV
  const ipRepRaw = await c.env.IP_REPUTATION.get(`ip:${ip_address}`);
  const ipScore = ipRepRaw ? parseFloat(ipRepRaw) : 0.1; // default low risk

  const fraudScore = computeFraudScore(velocity1h, ipScore);

  // Persist enrichment for audit and future velocity lookups
  await c.env.DB.prepare(
    `INSERT OR REPLACE INTO fraud_signals
       (payment_intent_id, device_fp, velocity_1h, ip_score, fraud_score, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(payment_intent_id, device_fingerprint, velocity1h, ipScore, fraudScore, now)
    .run();

  // Stripe Radar Extensions expect this shape
  return c.json({
    metadata: {
      fraud_score: fraudScore,
      velocity_1h: velocity1h,
      ip_score: ipScore,
    },
  });
});

export default app;
```

## Stripe Radar Custom Rule Configuration

Once the Worker is deployed and registered as a Radar Extension, create these rules in the Stripe Dashboard under **Radar → Rules**:

```
# Block high-risk payments
Block if :fraud_score: > 80

# Request 3DS for medium-risk payments
Request 3D Secure if :fraud_score: > 50 and :fraud_score: <= 80

# Flag for manual review
Flag for review if :velocity_1h: > 5
```

## D1 Migration

```sql
-- migrations/0001_fraud_signals.sql
CREATE TABLE IF NOT EXISTS fraud_signals (
  payment_intent_id TEXT PRIMARY KEY,
  device_fp         TEXT NOT NULL,
  velocity_1h       INTEGER NOT NULL DEFAULT 0,
  ip_score          REAL NOT NULL DEFAULT 0.0,
  fraud_score       REAL NOT NULL DEFAULT 0.0,
  created_at        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fraud_signals_device_fp_created
  ON fraud_signals (device_fp, created_at);
```

## Anti-patterns

- **Returning enrichment after 2 s**: Stripe will time out and treat the extension as unavailable, falling back to default Radar rules. Keep all D1 + KV operations under 200 ms each and set a 1.5 s total Worker timeout.
- **Trusting device fingerprint from the client unconditionally**: Always combine it with at least one server-side signal (IP, velocity) since clients can spoof fingerprints.
- **Storing raw PII in fraud_signals**: Store only the fingerprint hash, not the full IP or email, to limit GDPR exposure.

## Gotchas

- The `stripe-signature` header uses the same format as Stripe webhook signatures but with a different secret — do not reuse your webhook endpoint secret.
- D1 `COUNT(*)` queries are fast but add an index on `(device_fp, created_at)` before going to production; without it, full table scans will blow your 2 s budget at scale.
- `INSERT OR REPLACE` removes and re-inserts the row, resetting any columns not specified — use `INSERT ... ON CONFLICT DO UPDATE` if you want to preserve old columns.

## Verification

```bash
# 1. Send a test enrichment request (Stripe provides a test tool in the Dashboard)
# 2. Query D1 to confirm the row was written
wrangler d1 execute <DB_NAME> \
  --command "SELECT * FROM fraud_signals ORDER BY created_at DESC LIMIT 5;"

# 3. Trigger a Stripe test payment and confirm the Radar rule fired
stripe payments create --amount 5000 --currency usd \
  --payment-method pm_card_visa \
  --metadata fraud_score=85
```

## Related

- `paypal-webhooks-workers-signature-validation.md`
- `adyen-payments-workers-integration.md`
- Stripe Radar Extensions docs: https://stripe.com/docs/radar/radar-extensions

## Sources

- Stripe Radar custom rules reference: https://stripe.com/docs/radar/rules
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
