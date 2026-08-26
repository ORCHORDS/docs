# Recurring Subscription & Chargeback Fraud Detection in D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project offers optional paid features (e.g., boosted anonymous posts, premium stickers). Fraudulent actors cycle through stolen card BINs to activate subscriptions, collect the benefits, then trigger chargebacks — leaving the platform holding Stripe dispute fees (~$15 USD each) and reversal losses. Anonymous sessions make traditional account-level fraud linking difficult. A second pattern: "subscription stuffing" — creating hundreds of free trials from the same device fingerprint across VPN-rotated IPs.

## Context

Anonymous platforms are disproportionately targeted because there is no verified identity to ban. Mitigation must operate on device signals, payment metadata, and behavioural velocity, not user identity. Stripe's Radar alone is insufficient because example project controls the session layer and can enrich signals Stripe never sees.

Key regulatory note: PSD2 SCA (EU/UK) and Nacha rules require disputed charges to have evidence of device continuity — log Turnstile tokens and CF-Ray IDs at payment time or you cannot defend disputes.

## 1. Payment Session Binding at Checkout

```typescript
// src/payments/checkout-init.ts
import type { Env } from "../types";

export async function initCheckout(
  request: Request,
  env: Env
): Promise<{ sessionToken: string; checkoutId: string }> {
  const cfRay    = request.headers.get("CF-Ray") ?? "unknown";
  const ip       = request.headers.get("CF-Connecting-IP") ?? "0.0.0.0";
  const country  = request.cf?.country ?? "XX";
  const asn      = String(request.cf?.asn ?? 0);
  const turnstile = request.headers.get("X-Turnstile-Token") ?? "";

  const checkoutId = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO checkout_sessions
       (id, cf_ray, ip_hash, country, asn, turnstile_token, created_at, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')`
  ).bind(
    checkoutId,
    cfRay,
    await hashIp(ip),            // SHA-256, never raw IP
    country,
    asn,
    turnstile,
    Date.now()
  ).run();

  return { sessionToken: checkoutId, checkoutId };
}

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}
```

## 2. BIN Velocity Tracking in D1

```sql
-- migration: 0043_payment_fraud_tables.sql
CREATE TABLE checkout_sessions (
  id              TEXT PRIMARY KEY,
  cf_ray          TEXT NOT NULL,
  ip_hash         TEXT NOT NULL,
  country         TEXT NOT NULL,
  asn             TEXT NOT NULL,
  turnstile_token TEXT NOT NULL,
  bin6            TEXT,            -- populated after card entry
  card_fingerprint TEXT,           -- from Stripe PaymentMethod
  created_at      INTEGER NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX idx_checkout_bin6_hour
  ON checkout_sessions (bin6, created_at);

CREATE INDEX idx_checkout_fp
  ON checkout_sessions (card_fingerprint, created_at);

CREATE TABLE chargeback_events (
  id              TEXT PRIMARY KEY,
  checkout_id     TEXT NOT NULL REFERENCES checkout_sessions(id),
  stripe_dispute_id TEXT NOT NULL,
  amount_cents    INTEGER NOT NULL,
  reason          TEXT NOT NULL,
  received_at     INTEGER NOT NULL,
  evidence_filed  INTEGER NOT NULL DEFAULT 0
);
```

## 3. Velocity Rule Evaluation Worker

```typescript
// src/payments/fraud-check.ts
interface VelocityResult {
  blocked: boolean;
  reason?: string;
  riskScore: number;
}

export async function evaluatePaymentVelocity(
  env: Env,
  bin6: string,
  cardFingerprint: string,
  ipHash: string
): Promise<VelocityResult> {
  const windowMs = 3600_000; // 1 hour
  const cutoff   = Date.now() - windowMs;

  const [binHits, fpHits, ipHits] = await Promise.all([
    env.DB.prepare(
      `SELECT COUNT(*) AS n FROM checkout_sessions
       WHERE bin6 = ? AND created_at > ?`
    ).bind(bin6, cutoff).first<{ n: number }>(),

    env.DB.prepare(
      `SELECT COUNT(*) AS n FROM checkout_sessions
       WHERE card_fingerprint = ? AND created_at > ?`
    ).bind(cardFingerprint, cutoff).first<{ n: number }>(),

    env.DB.prepare(
      `SELECT COUNT(*) AS n FROM checkout_sessions
       WHERE ip_hash = ? AND created_at > ?`
    ).bind(ipHash, cutoff).first<{ n: number }>(),
  ]);

  const binCount = binHits?.n ?? 0;
  const fpCount  = fpHits?.n ?? 0;
  const ipCount  = ipHits?.n ?? 0;

  if (fpCount >= 3)  return { blocked: true, reason: "card_fingerprint_velocity", riskScore: 1.0 };
  if (binCount >= 8) return { blocked: true, reason: "bin_velocity", riskScore: 0.9 };
  if (ipCount >= 5)  return { blocked: true, reason: "ip_velocity", riskScore: 0.8 };

  const riskScore = Math.min(1, (binCount / 8) * 0.4 + (fpCount / 3) * 0.4 + (ipCount / 5) * 0.2);
  return { blocked: false, riskScore };
}
```

## 4. Stripe Webhook: Chargeback Evidence Auto-Filing

```typescript
// src/payments/dispute-handler.ts
export async function handleStripeDispute(
  disputeEvent: Stripe.Event,
  env: Env
): Promise<void> {
  const dispute = disputeEvent.data.object as Stripe.Dispute;
  const paymentIntentId = dispute.payment_intent as string;

  // Look up our checkout session for this PaymentIntent
  const session = await env.DB.prepare(
    `SELECT cs.* FROM checkout_sessions cs
     JOIN stripe_payment_intents spi ON spi.checkout_id = cs.id
     WHERE spi.stripe_pi_id = ?`
  ).bind(paymentIntentId).first<CheckoutSession>();

  if (!session) {
    console.warn("No checkout session for dispute", dispute.id);
    return;
  }

  // File evidence: CF-Ray + Turnstile token prove device continuity
  await stripe.disputes.update(dispute.id, {
    evidence: {
      customer_ip_address: "see_cf_ray",   // raw IP not stored
      uncategorized_text:
        `CF-Ray: ${session.cf_ray}\n` +
        `Turnstile: ${session.turnstile_token}\n` +
        `Country: ${session.country}\n` +
        `ASN: ${session.asn}`,
    },
    submit: true,
  });

  await env.DB.prepare(
    `INSERT INTO chargeback_events
       (id, checkout_id, stripe_dispute_id, amount_cents, reason, received_at, evidence_filed)
     VALUES (?, ?, ?, ?, ?, ?, 1)`
  ).bind(
    crypto.randomUUID(), session.id, dispute.id,
    dispute.amount, dispute.reason, Date.now()
  ).run();
}
```

## 5. Free-Trial Stuffing Guard (Device Fingerprint + Turnstile)

```typescript
// src/payments/trial-guard.ts
export async function guardFreeTrial(
  env: Env,
  turnstileToken: string,
  cfRay: string
): Promise<{ allowed: boolean }> {
  // Turnstile server-side verification
  const resp = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    body: new URLSearchParams({
      secret: env.TURNSTILE_SECRET,
      response: turnstileToken,
      remoteip: cfRay,       // use as idempotency proxy; real IP not stored
    }),
  });
  const { success, error_codes } = await resp.json<TurnstileResponse>();
  if (!success) return { allowed: false };

  // One free trial per Turnstile challenge (challenge_ts is embedded in token)
  const existing = await env.DB.prepare(
    `SELECT id FROM checkout_sessions
     WHERE turnstile_token = ? AND status = 'trial_activated'`
  ).bind(turnstileToken).first();

  return { allowed: !existing };
}
```

## Anti-patterns

- **Storing raw IPs** — hash at ingress; Stripe and CF-Ray provide dispute evidence without GDPR-sensitive IP storage.
- **Relying on Stripe Radar alone** — Radar lacks Turnstile, CF-ASN, and session-layer signals.
- **Blocking entire BIN ranges** — BIN-6 blocking is over-broad; use velocity thresholds, not blanket bans.
- **No evidence auto-filing** — manual dispute responses arrive after the 7-day Stripe deadline ~40% of the time.

## Gotchas

- Stripe card fingerprint is per-account, not global — a fraudster using two Stripe integrations gets different fingerprints. Use BIN + IP hash correlation as secondary signal.
- D1 `COUNT(*)` on `created_at` index is O(log n) only if the index exists; verify with `EXPLAIN QUERY PLAN`.
- Turnstile tokens are single-use and expire after ~5 minutes — store the token immediately on checkout init, not after payment confirmation.
- PSD2 SCA exemption thresholds (€30 low-value, €500 cumulative) still require fraud rate below 0.01%; track this in `chargeback_events`.

## Verification

```bash
# Verify BIN velocity index exists
wrangler d1 execute example project-db --command \
  "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='checkout_sessions';"

# Simulate high-velocity BIN
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) FROM checkout_sessions WHERE bin6='411111' AND created_at > $(date -d '1 hour ago' +%s)000;"

# Check chargeback evidence filing rate
wrangler d1 execute example project-db --command \
  "SELECT SUM(evidence_filed)*1.0/COUNT(*) AS filing_rate FROM chargeback_events;"
# Target: > 0.95
```

## Related

- `financial-fraud-detection-digital-goods.md`
- `cryptocurrency-fraud-detection-workers.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `platform-token-economy-abuse-prevention.md`

## Sources

- Stripe Radar documentation — https://stripe.com/docs/radar
- Cloudflare Turnstile siteverify — https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- PSD2 Strong Customer Authentication RTS, EBA/RTS/2017/02
- Nacha Operating Rules 2025, Article Two, Section 8
