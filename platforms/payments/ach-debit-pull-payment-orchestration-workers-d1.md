# ACH Debit Pull Payment Orchestration Workers D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to initiate ACH debit pulls (pulling funds from a customer's bank account)
on a recurring or on-demand basis, track each NACHA file submission lifecycle,
handle R-codes (return codes) from the receiving bank, and reconcile settled funds
— all with Cloudflare Workers as the orchestration layer and D1 as the state store.

Typical scenarios: SaaS platform collecting subscription fees via ACH, a lending
platform pulling loan repayments, or a marketplace sweeping merchant balances.

## Context

ACH is a batch-oriented network. Entries submitted today settle next business day
(standard ACH) or same-day for Same-Day ACH (SDACH). Banks return R-codes within
2 banking days for consumer entries and 60 days for unauthorized claims. Your
orchestration layer must:

- Initiate debit entries through a payment processor (Stripe ACH, Dwolla, Moov, etc.)
- Track entry state: `pending`, `submitted`, `settled`, `returned`, `corrected`
- Process return R-codes and route them: retry, notify, close mandate
- Enforce NACHA exposure limits and debit velocity controls
- Produce settlement reconciliation against your D1 ledger

Cloudflare Workers handle API calls and webhook ingestion; D1 is the transactional
state store; Queues handle async retry and notification fan-out.

## D1 Schema

```sql
-- ACH entries and their lifecycle
CREATE TABLE ach_entries (
  id            TEXT PRIMARY KEY,
  external_id   TEXT UNIQUE,          -- processor payment id
  customer_id   TEXT NOT NULL,
  mandate_id    TEXT NOT NULL,
  amount_cents  INTEGER NOT NULL,
  currency      TEXT NOT NULL DEFAULT 'usd',
  sec_code      TEXT NOT NULL,        -- PPD, CCD, WEB
  description   TEXT,
  effective_date TEXT,                -- YYYY-MM-DD banking day
  status        TEXT NOT NULL DEFAULT 'pending',
  r_code        TEXT,
  r_description TEXT,
  return_at     TEXT,
  settled_at    TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_ach_entries_customer ON ach_entries(customer_id, status);
CREATE INDEX idx_ach_entries_effective ON ach_entries(effective_date, status);

-- Mandates (authorizations to debit)
CREATE TABLE ach_mandates (
  id              TEXT PRIMARY KEY,
  customer_id     TEXT NOT NULL,
  processor_id    TEXT UNIQUE,        -- e.g. Stripe bank_account id
  bank_last4      TEXT,
  routing_number  TEXT,
  account_type    TEXT,               -- checking | savings
  status          TEXT NOT NULL DEFAULT 'active', -- active | paused | revoked
  failure_count   INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_ach_mandates_customer ON ach_mandates(customer_id, status);
```

## Initiating ACH Debit Pulls

```typescript
// worker.ts
import { D1Database, Queue } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
  ACH_EVENTS: Queue;
  STRIPE_SECRET_KEY: string;
}

async function initiateAchDebit(
  env: Env,
  customerId: string,
  mandateId: string,
  amountCents: number,
  description: string,
  secCode: 'PPD' | 'CCD' | 'WEB' = 'PPD'
): Promise<{ entryId: string; externalId: string }> {
  // Load mandate
  const mandate = await env.DB.prepare(
    `SELECT * FROM ach_mandates WHERE id = ? AND customer_id = ? AND status = 'active'`
  ).bind(mandateId, customerId).first();

  if (!mandate) throw new Error('No active mandate found');

  // Velocity guard: max $25,000 per customer in 30 days
  const windowStart = new Date(Date.now() - 30 * 86400_000).toISOString();
  const { total } = await env.DB.prepare(
    `SELECT COALESCE(SUM(amount_cents), 0) AS total
     FROM ach_entries
     WHERE customer_id = ? AND status IN ('pending','submitted','settled')
       AND created_at > ?`
  ).bind(customerId, windowStart).first() as { total: number };

  if (total + amountCents > 2_500_000) {
    throw new Error('ACH debit velocity limit exceeded');
  }

  // Call processor (Stripe example)
  const stripeResp = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      amount: String(amountCents),
      currency: 'usd',
      customer: customerId,
      payment_method: mandate.processor_id as string,
      'payment_method_types[]': 'us_bank_account',
      confirm: 'true',
      description,
      'metadata[mandate_id]': mandateId,
      'metadata[sec_code]': secCode,
    }),
  });

  if (!stripeResp.ok) {
    const err = await stripeResp.json() as { error: { message: string } };
    throw new Error(`Stripe error: ${err.error.message}`);
  }

  const pi = await stripeResp.json() as { id: string; status: string };

  const entryId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO ach_entries
       (id, external_id, customer_id, mandate_id, amount_cents, sec_code,
        description, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')`
  ).bind(entryId, pi.id, customerId, mandateId, amountCents, secCode, description)
   .run();

  return { entryId, externalId: pi.id };
}
```

## Webhook Handler for ACH Status Updates

```typescript
// Stripe sends payment_intent.succeeded, payment_intent.payment_failed,
// and payment_intent.processing for ACH entries

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const sig = request.headers.get('stripe-signature') ?? '';
    const body = await request.text();

    // Verify Stripe webhook signature (use crypto.subtle with HMAC-SHA256)
    const isValid = await verifyStripeSignature(body, sig, env.STRIPE_WEBHOOK_SECRET);
    if (!isValid) return new Response('Invalid signature', { status: 400 });

    const event = JSON.parse(body) as { type: string; data: { object: Record<string, unknown> } };
    const pi = event.data.object;

    switch (event.type) {
      case 'payment_intent.processing':
        await env.DB.prepare(
          `UPDATE ach_entries SET status='submitted', updated_at=datetime('now')
           WHERE external_id=?`
        ).bind(pi['id']).run();
        break;

      case 'payment_intent.succeeded':
        await env.DB.prepare(
          `UPDATE ach_entries SET status='settled', settled_at=datetime('now'),
             updated_at=datetime('now')
           WHERE external_id=?`
        ).bind(pi['id']).run();
        await env.ACH_EVENTS.send({ type: 'settled', paymentIntentId: pi['id'] });
        break;

      case 'payment_intent.payment_failed': {
        const failureCode = (pi['last_payment_error'] as Record<string, string> | null)?.code ?? '';
        const rCode = mapStripeFailureToRCode(failureCode);
        await handleReturn(env, pi['id'] as string, rCode);
        break;
      }
    }

    return new Response('ok');
  },
};

function mapStripeFailureToRCode(code: string): string {
  const map: Record<string, string> = {
    'bank_account_unusable': 'R02',
    'insufficient_funds': 'R01',
    'debit_not_authorized': 'R10',
    'account_closed': 'R16',
    'no_account': 'R03',
  };
  return map[code] ?? 'R99';
}

async function handleReturn(env: Env, externalId: string, rCode: string): Promise<void> {
  const HARD_RETURNS = new Set(['R02', 'R03', 'R10', 'R16', 'R29']);

  const entry = await env.DB.prepare(
    `SELECT * FROM ach_entries WHERE external_id=?`
  ).bind(externalId).first() as { mandate_id: string; customer_id: string } | null;

  if (!entry) return;

  await env.DB.prepare(
    `UPDATE ach_entries SET status='returned', r_code=?, return_at=datetime('now'),
       updated_at=datetime('now')
     WHERE external_id=?`
  ).bind(rCode, externalId).run();

  if (HARD_RETURNS.has(rCode)) {
    // Revoke mandate — do not retry
    await env.DB.prepare(
      `UPDATE ach_mandates SET status='revoked', updated_at=datetime('now')
       WHERE id=?`
    ).bind(entry.mandate_id).run();
  } else {
    // Soft return — increment failure count; pause after 3
    await env.DB.prepare(
      `UPDATE ach_mandates
         SET failure_count = failure_count + 1,
             status = CASE WHEN failure_count + 1 >= 3 THEN 'paused' ELSE status END,
             updated_at=datetime('now')
       WHERE id=?`
    ).bind(entry.mandate_id).run();
  }

  await env.ACH_EVENTS.send({
    type: 'returned',
    customerId: entry.customer_id,
    mandateId: entry.mandate_id,
    rCode,
  });
}
```

## Settlement Reconciliation

```typescript
// Daily reconciliation Worker triggered by a Cron Trigger
// Compares expected settled entries against actual D1 records

interface ReconciliationResult {
  date: string;
  expectedSettled: number;
  actualSettled: number;
  missing: string[];
}

async function reconcileSettledEntries(
  env: Env,
  date: string  // YYYY-MM-DD
): Promise<ReconciliationResult> {
  // Entries that should have settled by this date
  const expected = await env.DB.prepare(
    `SELECT id, external_id FROM ach_entries
     WHERE effective_date <= ? AND status = 'submitted'`
  ).bind(date).all();

  const missing: string[] = [];
  for (const row of expected.results as { id: string; external_id: string }[]) {
    // Check live status from Stripe
    const resp = await fetch(`https://api.stripe.com/v1/payment_intents/${row.external_id}`, {
      headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
    });
    const pi = await resp.json() as { status: string };

    if (pi.status === 'succeeded') {
      await env.DB.prepare(
        `UPDATE ach_entries SET status='settled', settled_at=datetime('now'),
           updated_at=datetime('now') WHERE id=?`
      ).bind(row.id).run();
    } else if (pi.status === 'requires_payment_method') {
      missing.push(row.external_id);
    }
  }

  const { actual } = await env.DB.prepare(
    `SELECT COUNT(*) AS actual FROM ach_entries
     WHERE effective_date = ? AND status = 'settled'`
  ).bind(date).first() as { actual: number };

  return {
    date,
    expectedSettled: expected.results.length,
    actualSettled: actual,
    missing,
  };
}
```

## Anti-patterns

- **Fire-and-forget**: Submitting ACH entries without tracking state in D1 makes
  R-code handling and reconciliation impossible.
- **Retrying hard returns**: R10 (unauthorized) or R16 (account frozen) should
  never be retried; doing so violates NACHA rules and risks card network fines.
- **No velocity limits**: NACHA exposure limits exist; ignoring them can result in
  funding losses when entries return after settlement.
- **Same-day ACH for all entries without surcharge logic**: SDACH carries an
  interchange fee (~$0.045/entry on Stripe); don't default to it unnecessarily.

## Gotchas

- ACH returns can arrive up to 60 calendar days after settlement for consumer
  unauthorized claims (R10, R29). Your D1 schema must keep `settled` entries
  queryable long after the payment date.
- `effective_date` is a NACHA banking-day concept. Saturday/Sunday/federal holiday
  submissions advance to the next banking day. Compute this server-side.
- Stripe's ACH returns surface as `payment_intent.payment_failed` with a
  `last_payment_error.code` — map these to NACHA R-codes yourself; Stripe does not
  expose R-codes directly.
- D1 is eventually consistent across regions. For mandate revocation, use
  `D1.prepare(...).run()` with immediate follow-up reads routed to the same
  primary via `waitUntil` patterns to avoid stale reads issuing new debits.

## Verification

```bash
# Check pending entries older than 3 banking days (may be stuck)
wrangler d1 execute <DB> --command \
  "SELECT id, external_id, amount_cents, effective_date, status
   FROM ach_entries
   WHERE status = 'submitted'
     AND effective_date < date('now', '-3 days')
   ORDER BY effective_date;"

# R-code distribution report
wrangler d1 execute <DB> --command \
  "SELECT r_code, COUNT(*) AS n, SUM(amount_cents)/100.0 AS dollars
   FROM ach_entries WHERE status='returned'
   GROUP BY r_code ORDER BY n DESC;"

# Mandate health summary
wrangler d1 execute <DB> --command \
  "SELECT status, COUNT(*) AS n FROM ach_mandates GROUP BY status;"
```

## Related

- `stripe-acss-debit.md` — Canadian pre-authorized debit via Stripe
- `stripe-sepa-debit.md` — European SEPA direct debit patterns
- `gocardless-direct-debit-mandate-workers.md` — GoCardless mandate lifecycle
- `payment-dunning-management-cloudflare-queues.md` — Retry orchestration
- `idempotency-keys-payment-apis.md` — Safe retry mechanics

## Sources

- NACHA Operating Rules 2024: https://www.nacha.org/rules
- Stripe ACH documentation: https://stripe.com/docs/payments/ach-debit
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
