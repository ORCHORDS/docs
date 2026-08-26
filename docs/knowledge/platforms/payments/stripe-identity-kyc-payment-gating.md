# Stripe Identity KYC Verification Gating Payments in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

High-value transactions (e.g. marketplace payouts above $2,000, crypto settlement, or regulated financial products) require identity verification before funds are released. You need to collect a government ID and selfie, verify the result asynchronously, store the verified status in D1, and gate payout or high-value payment routes until verification passes — all without running your own document validation infrastructure.

Stripe Identity provides a hosted verification flow (`VerificationSession`) that handles document capture, liveness detection, and fraud-risk scoring. The result lands via webhook.

---

## Context

Stripe Identity is billed per verification attempt (~$1.50 USD). A `VerificationSession` goes through states:

```
requires_input → processing → verified
                           → canceled
                           → requires_input (re-try if documents rejected)
```

Key objects:
- `VerificationSession` — the top-level container for one KYC attempt
- `VerificationReport` — the detailed result with extracted data (name, DOB, document number)
- `identity.verification_session.verified` webhook event — fires when the session reaches `verified`
- `identity.verification_session.requires_input` — fires when the user must retry (e.g. blurry document)

Personal data returned in `VerificationReport` is sensitive PII. Store only the session ID and verified flag in D1; retrieve raw data from Stripe only when legally required, and apply data minimization.

---

## Section 1 — Creating a VerificationSession and Ephemeral Client Secret

```typescript
// workers/src/handlers/create-verification-session.ts
import Stripe from 'stripe';

export interface KycOptions {
  userId: string;
  returnUrl: string;
  requiredDocumentTypes?: ('driving_license' | 'passport' | 'id_card')[];
}

export async function createVerificationSession(
  stripe: Stripe,
  env: Env,
  opts: KycOptions,
): Promise<{ clientSecret: string; sessionId: string }> {
  // Check if user is already verified — avoid double-charging
  const existing = await env.DB.prepare(
    `SELECT kyc_status FROM users WHERE id = ?1`,
  )
    .bind(opts.userId)
    .first<{ kyc_status: string }>();

  if (existing?.kyc_status === 'verified') {
    throw Object.assign(new Error('User already verified'), { code: 'ALREADY_VERIFIED' });
  }

  const session = await stripe.identity.verificationSessions.create({
    type: 'document',
    metadata: { user_id: opts.userId },
    options: {
      document: {
        allowed_types: opts.requiredDocumentTypes ?? [
          'driving_license',
          'passport',
          'id_card',
        ],
        require_id_number: false,
        require_live_capture: true,
        require_matching_selfie: true,
      },
    },
    return_url: opts.returnUrl,
  });

  // Store pending verification in D1
  await env.DB.prepare(
    `INSERT INTO kyc_sessions (user_id, stripe_session_id, status, created_at)
     VALUES (?1, ?2, 'pending', unixepoch())
     ON CONFLICT(user_id) DO UPDATE
       SET stripe_session_id = excluded.stripe_session_id,
           status            = 'pending',
           created_at        = unixepoch()`,
  )
    .bind(opts.userId, session.id)
    .run();

  // The client_secret is short-lived and must be passed to the frontend SDK
  return {
    clientSecret: <redacted-secret>
    sessionId: session.id,
  };
}
```

---

## Section 2 — D1 Schema for KYC State

```sql
-- migration: 0016_kyc.sql
CREATE TABLE IF NOT EXISTS kyc_sessions (
  user_id           TEXT    PRIMARY KEY,
  stripe_session_id TEXT    NOT NULL,
  status            TEXT    NOT NULL DEFAULT 'pending',
  -- pending | processing | verified | failed | canceled
  verified_at       INTEGER,
  failed_at         INTEGER,
  failure_reason    TEXT,
  created_at        INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at        INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Lightweight flag on the users table for fast gate checks
-- ALTER TABLE users ADD COLUMN kyc_status TEXT NOT NULL DEFAULT 'unverified';
-- Valid values: unverified | pending | verified | failed
```

---

## Section 3 — Webhook Handler for Verification Events

```typescript
// workers/src/webhooks/stripe-identity.ts
import Stripe from 'stripe';

type IdentityEvent =
  | Stripe.IdentityVerificationSessionVerifiedEvent
  | Stripe.IdentityVerificationSessionRequiresInputEvent
  | Stripe.IdentityVerificationSessionCanceledEvent;

export async function handleIdentityEvent(
  env: Env,
  event: IdentityEvent,
): Promise<void> {
  const session = event.data.object as Stripe.Identity.VerificationSession;
  const userId = session.metadata?.user_id;

  if (!userId) {
    console.error('VerificationSession missing user_id metadata', session.id);
    return;
  }

  switch (event.type) {
    case 'identity.verification_session.verified': {
      await env.DB.prepare(
        `UPDATE kyc_sessions
            SET status      = 'verified',
                verified_at = unixepoch(),
                updated_at  = unixepoch()
          WHERE user_id = ?1`,
      )
        .bind(userId)
        .run();

      await env.DB.prepare(
        `UPDATE users SET kyc_status = 'verified' WHERE id = ?1`,
      )
        .bind(userId)
        .run();

      break;
    }

    case 'identity.verification_session.requires_input': {
      // Document rejected — user must retry
      const reason =
        session.last_error?.code ?? 'document_unverified_other';

      await env.DB.prepare(
        `UPDATE kyc_sessions
            SET status = 'failed', failure_reason = ?1, failed_at = unixepoch(), updated_at = unixepoch()
          WHERE user_id = ?2`,
      )
        .bind(reason, userId)
        .run();

      await env.DB.prepare(
        `UPDATE users SET kyc_status = 'failed' WHERE id = ?1`,
      )
        .bind(userId)
        .run();

      break;
    }

    case 'identity.verification_session.canceled': {
      await env.DB.prepare(
        `UPDATE kyc_sessions
            SET status = 'canceled', updated_at = unixepoch()
          WHERE user_id = ?1`,
      )
        .bind(userId)
        .run();

      // Leave kyc_status as 'pending' — user can restart
      break;
    }
  }
}
```

---

## Section 4 — KYC Gate Middleware for High-Value Routes

```typescript
// workers/src/middleware/kyc-guard.ts
import type { MiddlewareHandler } from 'hono';

/**
 * Blocks payout and high-value payment endpoints until KYC is verified.
 * Mount on routes such as POST /payouts and POST /payments (above threshold).
 */
export const kycGuard: MiddlewareHandler = async (c, next) => {
  const userId: string = c.get('userId');

  const user = await c.env.DB.prepare(
    `SELECT kyc_status FROM users WHERE id = ?1`,
  )
    .bind(userId)
    .first<{ kyc_status: string }>();

  if (!user) return c.json({ error: 'user_not_found' }, 404);

  if (user.kyc_status !== 'verified') {
    return c.json(
      {
        error: 'kyc_required',
        kyc_status: user.kyc_status,
        start_verification_url: '/account/verify-identity',
      },
      403,
    );
  }

  await next();
};

/**
 * Threshold guard: only require KYC for amounts above a limit.
 * Reads amount from the JSON body already parsed by Hono.
 */
export const kycThresholdGuard =
  (thresholdCents: number): MiddlewareHandler =>
  async (c, next) => {
    const body = await c.req.json<{ amount?: number }>();
    if ((body.amount ?? 0) < thresholdCents) {
      await next();
      return;
    }
    return kycGuard(c, next);
  };
```

---

## Section 5 — Redeeming a VerificationSession from the Frontend

```typescript
// Frontend (browser) — using Stripe.js
import { loadStripe } from '@stripe/stripe-js';

const stripe = await loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);

// 1. Fetch a client_secret from your Workers API
const { clientSecret } = await fetch('/api/kyc/start', {
  method: 'POST',
  headers: { Authorization: `Bearer ${accessToken}` },
}).then((r) => r.json());

// 2. Mount the Stripe Identity hosted flow
const { error } = await stripe!.verifyIdentity(clientSecret);

if (error) {
  console.error('Identity verification error', error.message);
} else {
  // Session is processing; webhook will fire when complete
  console.log('Identity verification submitted — awaiting result');
}
```

---

## Anti-patterns

- **Storing raw VerificationReport PII in D1**: extracted name, DOB, and document numbers are highly sensitive. Store only the session ID and status; retrieve PII from Stripe only for legal compliance and immediately discard.
- **Treating `processing` status as `verified`**: the session transitions `requires_input → processing → verified`. Do not grant access during `processing` — await the `identity.verification_session.verified` webhook.
- **Allowing unlimited retry attempts**: each `VerificationSession` costs ~$1.50. Rate-limit retries per user per rolling 24-hour window (e.g. maximum 3 attempts).
- **Using the same session for multiple users**: each `VerificationSession` is bound to one person. Create a new session for each user.
- **Skipping selfie matching**: setting `require_matching_selfie: false` makes it trivial to pass someone else's document. Always require a selfie for payout scenarios.

---

## Gotchas

- The `client_secret` on a `VerificationSession` expires after 24 hours. Redirect the user to restart if they abandon and return later.
- Stripe Identity has country-level document availability restrictions. Not all document types are accepted in all regions — check the Stripe dashboard "Supported countries" list before promising coverage.
- Redacting a `VerificationSession` (GDPR/right to erasure) via `stripe.identity.verificationSessions.redact(id)` removes PII from Stripe's systems but does not remove your D1 records. Implement your own data deletion logic in parallel.
- The `identity.verification_session.requires_input` event fires for both fresh failures and user retries. Deduplicate by checking `session.id` against `kyc_sessions.stripe_session_id`.
- Workers KV or D1 reads in middleware add ~1–3 ms per request. Cache `kyc_status` in a Workers KV namespace with a TTL of 60 seconds to avoid D1 reads on every API call.

---

## Verification

```bash
# 1. Start a KYC session
curl -X POST https://api.yourapp.com/kyc/start \
  -H "Authorization: Bearer $JWT"
# Returns { clientSecret, sessionId }

# 2. Simulate a verified event with Stripe CLI
stripe trigger identity.verification_session.verified \
  --override identity.verification_session:metadata.user_id=$USER_ID

# 3. Confirm D1 updated
wrangler d1 execute DB --command \
  "SELECT kyc_status FROM users WHERE id='$USER_ID';"
# Expected: verified

# 4. Confirm high-value route now unblocked
curl -X POST https://api.yourapp.com/payouts \
  -H "Authorization: Bearer $JWT" \
  -d '{"amount":250000,"currency":"usd"}'
# Expected: 200 (not 403)

# 5. Simulate failure and confirm gate restored
stripe trigger identity.verification_session.requires_input \
  --override identity.verification_session:metadata.user_id=$USER_ID
wrangler d1 execute DB --command \
  "SELECT kyc_status FROM users WHERE id='$USER_ID';"
# Expected: failed
```

---

## Related

- `pci-dss-saq-a-compliance.md` — compliance context for identity requirements
- `stripe-connect-custom.md` — Stripe Connect accounts also require identity verification
- `payment-fraud-detection-velocity-checks.md` — combine KYC with velocity checks for layered fraud defence
- `payment-audit-logging.md` — log KYC state changes for compliance audit trail
- `payment-data-retention.md` — PII retention rules post-verification

---

## Sources

- Stripe Identity Docs: https://stripe.com/docs/identity
- Stripe API — VerificationSession: https://stripe.com/docs/api/identity/verification_sessions
- Stripe Identity webhooks: https://stripe.com/docs/identity/verify-identity-documents#handle-verification-outcomes
- Stripe CLI trigger: https://stripe.com/docs/stripe-cli/triggers
