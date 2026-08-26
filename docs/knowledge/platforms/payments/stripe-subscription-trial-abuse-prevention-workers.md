# Stripe Subscription Trial Abuse Prevention in Cloudflare Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A SaaS product offering a 14-day free trial sees the same users creating accounts with different email addresses to chain back-to-back trials indefinitely. Stripe's trial infrastructure has no built-in cross-customer fingerprinting; each `Customer` object is independent. You need Workers-side logic to detect trial abuse before the Stripe customer is created, gate trial eligibility at checkout, and block known-abuser signals without degrading the legitimate new-user funnel.

---

## Context

Trial abuse takes three main forms:

1. **Email alias cycling** — `user+1@gmail.com`, `user+2@gmail.com`, same inbox.
2. **Card reuse** — the same payment method fingerprint (card BIN + last4 + exp) attached to multiple Stripe customers.
3. **Device/browser fingerprint cycling** — same device, cleared cookies, new account.

Cloudflare Workers is the right enforcement layer because it intercepts the registration and checkout requests before they hit your origin. D1 stores the abuse signal history. Stripe's `payment_method.fingerprint` field (available after attaching a card) is the highest-fidelity signal for card reuse. Email normalisation catches alias tricks. Workers AI can optionally score risk in real time.

Trial eligibility is checked at two points:
- **Registration** — normalise email, check D1 for prior trial.
- **Checkout session creation** — verify card fingerprint has not been used in a prior trial.

---

## 1. D1 Schema for Trial Tracking

```sql
-- migrations/0001_trial_abuse.sql
CREATE TABLE IF NOT EXISTS trial_fingerprints (
  id                TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  customer_id       TEXT NOT NULL,
  email_normalised  TEXT NOT NULL,
  card_fingerprint  TEXT,           -- Stripe payment_method.card.fingerprint
  ip_address        TEXT,
  cf_device_id      TEXT,           -- from CF-Device-Id header if available
  trial_started_at  INTEGER NOT NULL,
  status            TEXT NOT NULL DEFAULT 'active'  -- active | expired | converted | abused
);

CREATE INDEX IF NOT EXISTS idx_tf_email  ON trial_fingerprints (email_normalised);
CREATE INDEX IF NOT EXISTS idx_tf_card   ON trial_fingerprints (card_fingerprint) WHERE card_fingerprint IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tf_ip     ON trial_fingerprints (ip_address);
```

---

## 2. Email Normalisation

```typescript
// src/lib/normalise-email.ts

/**
 * Normalise an email address to collapse common alias tricks.
 * - Strip subaddressing (user+anything@domain)
 * - Remove dots from Gmail local parts (g.m.a.i.l → gmail)
 * - Lowercase everything
 */
export function normaliseEmail(raw: string): string {
  const [localRaw, domain] = raw.toLowerCase().trim().split('@');
  if (!domain) throw new Error('Invalid email');

  let local = localRaw.split('+')[0]; // strip subaddress

  // Gmail and Googlemail treat dots as insignificant
  if (domain === 'gmail.com' || domain === 'googlemail.com') {
    local = local.replace(/\./g, '');
    return `${local}@gmail.com`; // googlemail.com → gmail.com alias
  }

  return `${local}@${domain}`;
}
```

---

## 3. Trial Eligibility Gate

```typescript
// src/lib/trial-eligibility.ts
import { normaliseEmail } from './normalise-email';
import type { Env } from '../types';

export interface EligibilityResult {
  eligible: boolean;
  reason?: string;
}

export async function checkTrialEligibility(
  env: Env,
  rawEmail: string,
  ip: string | null,
  cardFingerprint?: string
): Promise<EligibilityResult> {
  const emailNorm = normaliseEmail(rawEmail);

  // 1. Email has already had a trial
  const emailRow = await env.DB
    .prepare(
      `SELECT id, status FROM trial_fingerprints
        WHERE email_normalised = ?
          AND trial_started_at > UNIXEPOCH() - 86400 * 365
        LIMIT 1`
    )
    .bind(emailNorm)
    .first<{ id: string; status: string }>();

  if (emailRow) {
    return { eligible: false, reason: 'email_already_trialled' };
  }

  // 2. Card fingerprint has already been used for a trial
  if (cardFingerprint) {
    const cardRow = await env.DB
      .prepare(
        `SELECT id FROM trial_fingerprints
          WHERE card_fingerprint = ?
          LIMIT 1`
      )
      .bind(cardFingerprint)
      .first<{ id: string }>();

    if (cardRow) {
      return { eligible: false, reason: 'card_already_trialled' };
    }
  }

  // 3. IP velocity — more than 3 trials from the same IP in 30 days is suspicious
  if (ip) {
    const ipCount = await env.DB
      .prepare(
        `SELECT COUNT(*) AS cnt FROM trial_fingerprints
          WHERE ip_address = ?
            AND trial_started_at > UNIXEPOCH() - 86400 * 30`
      )
      .bind(ip)
      .first<{ cnt: number }>();

    if ((ipCount?.cnt ?? 0) >= 3) {
      return { eligible: false, reason: 'ip_velocity_exceeded' };
    }
  }

  return { eligible: true };
}
```

---

## 4. Registration Handler with Eligibility Gate

```typescript
// src/handlers/register.ts
import Stripe from 'stripe';
import { checkTrialEligibility } from '../lib/trial-eligibility';
import { normaliseEmail } from '../lib/normalise-email';
import type { Env } from '../types';

export async function handleRegister(request: Request, env: Env): Promise<Response> {
  const { email, password } = await request.json<{ email: string; password: string }>();
  const ip = request.headers.get('CF-Connecting-IP');

  const eligibility = await checkTrialEligibility(env, email, ip);
  if (!eligibility.eligible) {
    // Soft-decline: do not expose the exact reason to avoid enumeration
    return Response.json(
      { error: 'This email is not eligible for a free trial. Please contact support.' },
      { status: 422 }
    );
  }

  // Create your app user …
  const userId = await createUser(email, password, env);

  // Log the trial start (card fingerprint added later at checkout)
  const emailNorm = normaliseEmail(email);
  await env.DB
    .prepare(
      `INSERT INTO trial_fingerprints
         (customer_id, email_normalised, ip_address, trial_started_at)
       VALUES (?, ?, ?, UNIXEPOCH())`
    )
    .bind(userId, emailNorm, ip ?? '')
    .run();

  return Response.json({ user_id: userId }, { status: 201 });
}

async function createUser(_email: string, _password: string, _env: Env): Promise<string> {
  // Stub — replace with your actual user creation
  return crypto.randomUUID();
}
```

---

## 5. Post-Checkout Card Fingerprint Recording

Once Stripe confirms the card, record its fingerprint so future signups with the same card are blocked.

```typescript
// src/handlers/stripe-webhook.ts — handles customer.subscription.trial_will_end, etc.
import Stripe from 'stripe';
import type { Env } from '../types';

export async function handleStripeWebhook(request: Request, env: Env): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY);
  const sig = request.headers.get('stripe-signature') ?? '';
  const rawBody = await request.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(rawBody, sig, env.STRIPE_WEBHOOK_SECRET);
  } catch {
    return new Response('Invalid signature', { status: 400 });
  }

  if (event.type === 'customer.subscription.created') {
    const sub = event.data.object as Stripe.Subscription;
    if (sub.trial_end) {
      await recordCardFingerprint(stripe, sub, env);
    }
  }

  if (event.type === 'customer.subscription.deleted') {
    // Mark trial as expired so aggregate metrics are clean
    await env.DB
      .prepare(
        `UPDATE trial_fingerprints SET status = 'expired'
          WHERE customer_id = ?`
      )
      .bind((event.data.object as Stripe.Subscription).customer as string)
      .run();
  }

  return new Response('ok');
}

async function recordCardFingerprint(
  stripe: Stripe,
  sub: Stripe.Subscription,
  env: Env
): Promise<void> {
  const customerId = sub.customer as string;
  const paymentMethods = await stripe.paymentMethods.list({
    customer: customerId,
    type: 'card',
    limit: 1,
  });

  const fingerprint = paymentMethods.data[0]?.card?.fingerprint;
  if (!fingerprint) return;

  await env.DB
    .prepare(
      `UPDATE trial_fingerprints
          SET card_fingerprint = ?
        WHERE customer_id = ?`
    )
    .bind(fingerprint, customerId)
    .run();
}
```

---

## 6. Scheduled Abuse Report (Cron)

```typescript
// src/cron/abuse-report.ts — runs daily, flags patterns
import type { Env } from '../types';

export async function generateAbuseReport(env: Env): Promise<void> {
  // Cards used for more than 1 trial (strong abuse signal)
  const abuseRows = await env.DB
    .prepare(
      `SELECT card_fingerprint, COUNT(*) AS cnt
         FROM trial_fingerprints
        WHERE card_fingerprint IS NOT NULL
        GROUP BY card_fingerprint
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 50`
    )
    .all<{ card_fingerprint: string; cnt: number }>();

  // Mark abusive fingerprints
  for (const row of abuseRows.results) {
    await env.DB
      .prepare(
        `UPDATE trial_fingerprints
            SET status = 'abused'
          WHERE card_fingerprint = ?`
      )
      .bind(row.card_fingerprint)
      .run();
  }
}
```

---

## Anti-patterns

- **Blocking on raw email equality** — `user@gmail.com` and `u.s.e.r@gmail.com` are the same inbox. Always normalise before storing and querying.
- **Exposing the abuse reason in the API response** — returning `"card_already_trialled"` tells the abuser exactly which signal to rotate next. Use a generic decline message.
- **Checking eligibility after Stripe customer creation** — Stripe customers cost nothing to delete but the billing relationship has already started. Gate before creating the customer.
- **Trusting `CF-Connecting-IP` without the `CF-IPCountry` context** — shared egress IPs (VPNs, CGNATs) inflate IP velocity counts. Use IP signals as one factor, not a hard block.

---

## Gotchas

- Stripe's `card.fingerprint` is the same for a given card number across all Stripe accounts. It is available on `PaymentMethod.card.fingerprint` only after the PM is attached to a customer.
- Gmail ignores dots in local parts at the MTA level, but some sign-up forms already normalise before sending, so normalise defensively on both inbound and stored values.
- The `trial_fingerprints` table must accommodate legitimate cases where a household shares a card (parents and adult children). Consider allowing an appeal flow rather than a permanent block.
- Workers AI-based email risk scoring adds ~80 ms latency at P50; run it asynchronously with `ctx.waitUntil()` and store the score for human review rather than using it as a hard gate.

---

## Verification

```bash
# Simulate abuse: same normalised email, different raw email
curl -X POST https://payment-api.workers.dev/register \
  -d '{"email":"u.s.e.r+trial1@gmail.com","password":"test"}' -H 'Content-Type: application/json'

curl -X POST https://payment-api.workers.dev/register \
  -d '{"email":"user+trial2@gmail.com","password":"test"}' -H 'Content-Type: application/json'
# Second call must return 422

# Check D1 state
wrangler d1 execute YOUR_DB --command \
  "SELECT email_normalised, card_fingerprint, status FROM trial_fingerprints"
```

---

## Related

- `stripe-trial-periods.md`
- `subscription-trial-conversion-tracking-workers-analytics-engine.md`
- `card-testing-attack-prevention.md`
- `fraud-scoring-pipeline-velocity-device-fingerprint-workers-ai.md`
- `free-trial-credit-card-required.md`

---

## Sources

- Stripe `PaymentMethod.card.fingerprint`: https://stripe.com/docs/api/payment_methods/object#payment_method_object-card-fingerprint
- Gmail address normalisation: https://support.google.com/mail/answer/7436150
- Cloudflare D1 Workers bindings: https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
