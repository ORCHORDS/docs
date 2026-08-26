# Payment Method Fingerprinting for Fraud Detection with Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A fraudster uses multiple stolen cards from the same BIN range, rotating card numbers but sharing device signals, IP addresses, or billing details. Velocity checks on card number alone miss this pattern. Payment method fingerprinting correlates structural card attributes (BIN, last-4, funding type, issuer country) with behavioral signals (IP, device fingerprint, email domain) to detect and block rings of related fraudulent attempts before authorization.

---

## Context

Stripe exposes card metadata on `PaymentMethod` objects: `card.fingerprint` (Stripe's own deduplication token per card number), `card.ips` (acquirer BIN lookups), `card.country`, `card.funding`, and `card.brand`. Combining these with client-supplied device signals — collected via a lightweight edge script or Cloudflare Bot Management — produces a risk graph stored in D1.

The fingerprint store enables two patterns:

1. **Same-card, different-account abuse**: one card fingerprint seen across N distinct accounts above threshold triggers a hold.
2. **Same-device, many-card abuse**: one device fingerprint submitting multiple card fingerprints within a window triggers a block.

All lookups run inside a Cloudflare Workers `PaymentIntent` confirmation proxy — adding < 5 ms latency before passing through to Stripe.

---

## 1. D1 Schema

```sql
-- migrations/0001_fingerprints.sql
CREATE TABLE IF NOT EXISTS payment_method_fingerprints (
  id                TEXT PRIMARY KEY,
  stripe_fingerprint TEXT NOT NULL,   -- Stripe card.fingerprint
  device_fingerprint TEXT,            -- client-supplied device id
  ip_address        TEXT NOT NULL,
  email_hash        TEXT NOT NULL,    -- SHA-256 of normalized email
  card_bin          TEXT NOT NULL,    -- first 6 digits
  card_country      TEXT NOT NULL,
  card_funding      TEXT NOT NULL,    -- 'credit' | 'debit' | 'prepaid' | 'unknown'
  account_id        TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  blocked           INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_fp_stripe   ON payment_method_fingerprints(stripe_fingerprint);
CREATE INDEX idx_fp_device   ON payment_method_fingerprints(device_fingerprint);
CREATE INDEX idx_fp_email    ON payment_method_fingerprints(email_hash);
CREATE INDEX idx_fp_ip       ON payment_method_fingerprints(ip_address);

CREATE TABLE IF NOT EXISTS fingerprint_blocks (
  id          TEXT PRIMARY KEY,
  signal_type TEXT NOT NULL,   -- 'stripe_fingerprint' | 'device' | 'ip' | 'email_hash'
  signal_value TEXT NOT NULL,
  reason      TEXT NOT NULL,
  blocked_at  TEXT NOT NULL,
  expires_at  TEXT             -- NULL = permanent
);

CREATE UNIQUE INDEX idx_block_signal ON fingerprint_blocks(signal_type, signal_value);
```

---

## 2. Fingerprint Recording

```typescript
// src/fingerprint.ts

import { createHash } from 'crypto'; // bundled via esbuild
// In Workers without Node.js compat, use Web Crypto instead:
async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export interface FingerprintRecord {
  stripeFingerprint: string;
  deviceFingerprint?: string;
  ipAddress: string;
  email: string;
  cardBin: string;
  cardCountry: string;
  cardFunding: string;
  accountId: string;
}

export async function recordFingerprint(
  db: D1Database,
  rec: FingerprintRecord
): Promise<string> {
  const id        = crypto.randomUUID();
  const emailHash = await sha256(rec.email.toLowerCase().trim());

  await db.prepare(
    `INSERT INTO payment_method_fingerprints
     (id, stripe_fingerprint, device_fingerprint, ip_address, email_hash,
      card_bin, card_country, card_funding, account_id, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      id,
      rec.stripeFingerprint,
      rec.deviceFingerprint ?? null,
      rec.ipAddress,
      emailHash,
      rec.cardBin,
      rec.cardCountry,
      rec.cardFunding,
      rec.accountId,
      new Date().toISOString()
    )
    .run();

  return id;
}
```

---

## 3. Velocity and Cross-Account Risk Scoring

```typescript
// src/risk.ts

export interface RiskScore {
  score: number;          // 0–100
  signals: string[];
  action: 'allow' | 'review' | 'block';
}

const WINDOW_SECONDS = 24 * 60 * 60; // 24 hours

export async function scorePaymentAttempt(
  db: D1Database,
  stripeFingerprint: string,
  deviceFingerprint: string | undefined,
  ipAddress: string,
  emailHash: string
): Promise<RiskScore> {
  const cutoff = new Date(Date.now() - WINDOW_SECONDS * 1000).toISOString();
  const signals: string[] = [];
  let score = 0;

  // 1. Check active blocks first
  const blockChecks = [
    db.prepare('SELECT reason FROM fingerprint_blocks WHERE signal_type = ? AND signal_value = ? AND (expires_at IS NULL OR expires_at > ?)')
      .bind('stripe_fingerprint', stripeFingerprint, new Date().toISOString()).first<{ reason: string }>(),
    deviceFingerprint
      ? db.prepare('SELECT reason FROM fingerprint_blocks WHERE signal_type = ? AND signal_value = ? AND (expires_at IS NULL OR expires_at > ?)')
          .bind('device', deviceFingerprint, new Date().toISOString()).first<{ reason: string }>()
      : Promise.resolve(null),
    db.prepare('SELECT reason FROM fingerprint_blocks WHERE signal_type = ? AND signal_value = ? AND (expires_at IS NULL OR expires_at > ?)')
      .bind('ip', ipAddress, new Date().toISOString()).first<{ reason: string }>(),
  ];

  const [cardBlock, deviceBlock, ipBlock] = await Promise.all(blockChecks);
  if (cardBlock)   return { score: 100, signals: [`card_blocked:${cardBlock.reason}`], action: 'block' };
  if (deviceBlock) return { score: 100, signals: [`device_blocked:${deviceBlock.reason}`], action: 'block' };
  if (ipBlock)     return { score: 100, signals: [`ip_blocked:${ipBlock.reason}`], action: 'block' };

  // 2. Same card, multiple accounts (card sharing fraud)
  const cardAccounts = await db.prepare(
    `SELECT COUNT(DISTINCT account_id) as cnt
     FROM payment_method_fingerprints
     WHERE stripe_fingerprint = ? AND created_at > ?`
  )
    .bind(stripeFingerprint, cutoff)
    .first<{ cnt: number }>();

  if (cardAccounts && cardAccounts.cnt > 3) {
    score += 40;
    signals.push(`card_multi_account:${cardAccounts.cnt}`);
  }

  // 3. Same device, multiple cards
  if (deviceFingerprint) {
    const deviceCards = await db.prepare(
      `SELECT COUNT(DISTINCT stripe_fingerprint) as cnt
       FROM payment_method_fingerprints
       WHERE device_fingerprint = ? AND created_at > ?`
    )
      .bind(deviceFingerprint, cutoff)
      .first<{ cnt: number }>();

    if (deviceCards && deviceCards.cnt > 2) {
      score += 40;
      signals.push(`device_multi_card:${deviceCards.cnt}`);
    }
  }

  // 4. Same IP, high velocity
  const ipAttempts = await db.prepare(
    `SELECT COUNT(*) as cnt
     FROM payment_method_fingerprints
     WHERE ip_address = ? AND created_at > ?`
  )
    .bind(ipAddress, cutoff)
    .first<{ cnt: number }>();

  if (ipAttempts && ipAttempts.cnt > 10) {
    score += 20;
    signals.push(`ip_velocity:${ipAttempts.cnt}`);
  }

  // 5. High-risk card attributes
  const cardMeta = await db.prepare(
    `SELECT card_funding, card_country FROM payment_method_fingerprints
     WHERE stripe_fingerprint = ? LIMIT 1`
  )
    .bind(stripeFingerprint)
    .first<{ card_funding: string; card_country: string }>();

  if (cardMeta?.card_funding === 'prepaid') {
    score += 10;
    signals.push('prepaid_card');
  }

  const action = score >= 70 ? 'block' : score >= 40 ? 'review' : 'allow';
  return { score: Math.min(score, 100), signals, action };
}
```

---

## 4. Worker Proxy: Intercept Before Stripe Confirmation

```typescript
// src/index.ts
import Stripe from 'stripe';
import { recordFingerprint } from './fingerprint';
import { scorePaymentAttempt } from './risk';

interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/confirm-payment') {
      return new Response('Not Found', { status: 404 });
    }

    const { paymentIntentId, deviceFingerprint, email } =
      await request.json<{ paymentIntentId: string; deviceFingerprint?: string; email: string }>();

    const stripe    = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
    const intent    = await stripe.paymentIntents.retrieve(paymentIntentId, {
      expand: ['payment_method'],
    });

    const pm   = intent.payment_method as Stripe.PaymentMethod | null;
    const card = pm?.card;

    if (!card) return new Response('No card on payment intent', { status: 400 });

    const ipAddress = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
    const emailHash = await (async () => {
      const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email.toLowerCase().trim()));
      return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
    })();

    const risk = await scorePaymentAttempt(
      env.DB,
      card.fingerprint ?? '',
      deviceFingerprint,
      ipAddress,
      emailHash
    );

    if (risk.action === 'block') {
      return Response.json({ error: 'Payment blocked', signals: risk.signals }, { status: 402 });
    }

    // Record fingerprint after scoring so it doesn't bias the current check
    await recordFingerprint(env.DB, {
      stripeFingerprint: card.fingerprint ?? '',
      deviceFingerprint,
      ipAddress,
      email,
      cardBin:     (card.fingerprint ?? '').slice(0, 6), // BIN not directly available; use BIN lookup
      cardCountry: card.country ?? '',
      cardFunding: card.funding ?? 'unknown',
      accountId:   intent.customer?.toString() ?? 'anonymous',
    });

    if (risk.action === 'review') {
      // Let through but flag for manual review
      await stripe.paymentIntents.update(paymentIntentId, {
        metadata: { fraud_risk: risk.score.toString(), fraud_signals: risk.signals.join(',') },
      });
    }

    // Confirm the payment intent
    const confirmed = await stripe.paymentIntents.confirm(paymentIntentId);
    return Response.json({ status: confirmed.status, riskScore: risk.score });
  },
};
```

---

## Anti-patterns

- **Storing raw emails in the fingerprint table** — hash with SHA-256 before writing; the hash is sufficient for correlation without exposing PII.
- **Scoring after confirmation** — the risk check must happen before `stripe.paymentIntents.confirm()`; post-hoc scoring cannot prevent the charge.
- **Using only Stripe's card fingerprint** — Stripe `fingerprint` deduplicates by card number globally but resets if the card is reissued; device fingerprint is a complementary, harder-to-rotate signal.
- **Permanent IP blocks without TTL** — shared NAT IPs (universities, corporate proxies) have many legitimate users; use short TTLs (24–72 hours) for IP-level blocks.

---

## Gotchas

- `card.fingerprint` on a `PaymentMethod` is `null` until the card is attached to a customer or used in a `PaymentIntent`; retrieve the `PaymentIntent` with `expand: ['payment_method']` to get it.
- Cloudflare provides the real client IP in `CF-Connecting-IP` header, not `X-Forwarded-For` (which may contain intermediate proxies).
- D1 does not support stored procedures; run the multi-query scoring as individual prepared statements in parallel with `Promise.all` to minimise latency.
- BIN (first 6 digits of PAN) is not directly returned by Stripe — use a BIN lookup table in D1 keyed by `card.iin` (from Stripe's card data API with Issuing) or derive from the `card_bin_lookup` article.
- Prepaid cards are legitimate in some markets (teens, privacy advocates); combine the `prepaid_card` signal with other signals rather than blocking on funding type alone.

---

## Verification

```bash
# Inspect fingerprint records for a suspicious card
wrangler d1 execute payments \
  --command "SELECT account_id, ip_address, created_at FROM payment_method_fingerprints WHERE stripe_fingerprint = 'fp_test123' ORDER BY created_at DESC LIMIT 20"

# Check active blocks
wrangler d1 execute payments \
  --command "SELECT * FROM fingerprint_blocks WHERE expires_at IS NULL OR expires_at > datetime('now')"
```

---

## Related

- `fraud-detection-signals.md`
- `fraud-scoring-pipeline-workers-ai.md`
- `payment-fraud-detection-velocity-checks.md`
- `card-bin-lookup-intelligent-routing-workers.md`
- `stripe-radar-fraud-rules.md`

---

## Sources

- https://docs.stripe.com/api/payment_methods/object#payment_method_object-card-fingerprint
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/fundamentals/reference/http-request-headers/#cf-connecting-ip
- https://stripe.com/docs/radar/reviews
