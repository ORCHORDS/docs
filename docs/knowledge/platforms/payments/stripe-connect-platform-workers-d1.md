# Stripe Connect Platform Integration in a Cloudflare Worker with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a marketplace or SaaS platform on Cloudflare Workers and need to onboard third-party sellers or service providers as Stripe Connect accounts. Charges must be routed from the platform to connected accounts, and webhook events must update D1 accordingly.

---

## Context

Stripe Connect allows a platform to create and manage connected accounts, split payments, and transfer funds. In a Workers environment there is no persistent process, so all state — account IDs, onboarding status, payout records — lives in D1 (SQLite at the edge). The platform account holds the secret key; connected-account actions use it with a `Stripe-Account` header or `transfer_data.destination`. Webhooks arrive on both the platform endpoint and per-account endpoints, requiring separate signing secrets. D1 is accessed via the binding `env.DB` and all SQL must be issued through the `prepare/bind/run` pattern.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS connected_accounts (
  id              TEXT PRIMARY KEY,          -- Stripe account_id e.g. acct_xxx
  user_id         TEXT NOT NULL,             -- your internal user id
  email           TEXT,
  charges_enabled INTEGER NOT NULL DEFAULT 0,
  payouts_enabled INTEGER NOT NULL DEFAULT 0,
  onboarding_url  TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_connected_accounts_user
  ON connected_accounts (user_id);

CREATE TABLE IF NOT EXISTS platform_payouts (
  id              TEXT PRIMARY KEY,          -- Stripe payout id po_xxx
  account_id      TEXT NOT NULL REFERENCES connected_accounts(id),
  amount          INTEGER NOT NULL,          -- cents
  currency        TEXT NOT NULL,
  arrival_date    TEXT,
  status          TEXT NOT NULL,
  recorded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Section 2 — Worker Implementation

```typescript
import Stripe from 'stripe';

export interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;           // platform webhook secret
  STRIPE_CONNECT_WEBHOOK_SECRET: string;   // connect webhook secret
}

function getStripe(env: Env): Stripe {
  return new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
}

// POST /connect/accounts  — create a connected account and return the onboarding URL
export async function createConnectedAccount(
  request: Request,
  env: Env
): Promise<Response> {
  const { user_id, email, country = 'US' } = await request.json<{
    user_id: string;
    email: string;
    country?: string;
  }>();

  const stripe = getStripe(env);

  // Create the Stripe Express account
  const account = await stripe.accounts.create({
    type: 'express',
    email,
    country,
    capabilities: {
      card_payments: { requested: true },
      transfers: { requested: true },
    },
  });

  // Generate an onboarding link
  const accountLink = await stripe.accountLinks.create({
    account: account.id,
    refresh_url: `https://example.com/connect/refresh?account=${account.id}`,
    return_url: `https://example.com/connect/return?account=${account.id}`,
    type: 'account_onboarding',
  });

  // Persist to D1
  await env.DB.prepare(
    `INSERT INTO connected_accounts (id, user_id, email, onboarding_url)
     VALUES (?1, ?2, ?3, ?4)
     ON CONFLICT(id) DO UPDATE SET onboarding_url = excluded.onboarding_url,
                                    updated_at = datetime('now')`
  )
    .bind(account.id, user_id, email, accountLink.url)
    .run();

  return Response.json({ account_id: account.id, onboarding_url: accountLink.url });
}

// POST /charges  — create a charge routed to a connected account
export async function createCharge(
  request: Request,
  env: Env
): Promise<Response> {
  const { user_id, amount, currency = 'usd', payment_method_id } =
    await request.json<{
      user_id: string;
      amount: number;
      currency?: string;
      payment_method_id: string;
    }>();

  const { results } = await env.DB.prepare(
    'SELECT id FROM connected_accounts WHERE user_id = ?1 AND charges_enabled = 1'
  )
    .bind(user_id)
    .all<{ id: string }>();

  if (!results.length) {
    return Response.json({ error: 'No charges-enabled account for user' }, { status: 422 });
  }
  const destination = results[0].id;
  const stripe = getStripe(env);

  const paymentIntent = await stripe.paymentIntents.create({
    amount,
    currency,
    payment_method: payment_method_id,
    confirm: true,
    transfer_data: { destination },
    automatic_payment_methods: { enabled: true, allow_redirects: 'never' },
  });

  return Response.json({ client_secret: <redacted-secret> id: paymentIntent.id });
}
```

---

## Section 3 — Webhook Event Handling

```typescript
// POST /webhooks/stripe/connect
export async function handleConnectWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const sig = request.headers.get('stripe-signature') ?? '';
  const body = await request.text();
  const stripe = getStripe(env);

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      body,
      sig,
      env.STRIPE_CONNECT_WEBHOOK_SECRET
    );
  } catch (err) {
    return new Response(`Webhook signature invalid: ${(err as Error).message}`, { status: 400 });
  }

  switch (event.type) {
    case 'account.updated': {
      const acct = event.data.object as Stripe.Account;
      await env.DB.prepare(
        `UPDATE connected_accounts
         SET charges_enabled = ?1,
             payouts_enabled = ?2,
             updated_at      = datetime('now')
         WHERE id = ?3`
      )
        .bind(
          acct.charges_enabled ? 1 : 0,
          acct.payouts_enabled ? 1 : 0,
          acct.id
        )
        .run();
      break;
    }

    case 'payout.paid': {
      const payout = event.data.object as Stripe.Payout;
      // event.account is set on Connect events
      const accountId = (event as unknown as { account: string }).account;
      await env.DB.prepare(
        `INSERT OR IGNORE INTO platform_payouts
           (id, account_id, amount, currency, arrival_date, status)
         VALUES (?1, ?2, ?3, ?4, date(?5, 'unixepoch'), ?6)`
      )
        .bind(
          payout.id,
          accountId,
          payout.amount,
          payout.currency,
          payout.arrival_date,
          payout.status
        )
        .run();
      break;
    }

    default:
      // Unhandled event — acknowledge to avoid retries
      break;
  }

  return new Response('ok', { status: 200 });
}
```

---

## Anti-patterns

- **Storing Stripe secret key in `wrangler.toml` plaintext** — Use `wrangler secret put STRIPE_SECRET_KEY` so the value is encrypted at rest and never committed to source control.
- **Skipping signature verification** — Always call `constructEventAsync` before processing any webhook body; omitting it allows arbitrary event injection.
- **Querying by email instead of account ID** — Email is not unique across Stripe Connect accounts; always join on the stored `account_id`.
- **Creating a new account on every request** — Check D1 first and return the existing onboarding URL if the account is already created but not yet completed.

---

## Gotchas

- `event.account` is only present on Connect webhook events; platform-level events omit it. Cast carefully.
- Express accounts cannot be charged directly without completing onboarding; check `charges_enabled` before routing.
- Stripe's `accountLinks` expire after a short window; regenerate them on the `/connect/refresh` route.
- D1's `datetime('now')` returns UTC; store and display all timestamps consistently in UTC.
- The Stripe npm package must be bundled; add `stripe` to your `package.json` and use `npm run deploy` rather than `wrangler dev --local`.

---

## Verification

```bash
# Create a test connected account
curl -X POST https://your-worker.workers.dev/connect/accounts \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u_001","email":"seller@example.com"}'

# Confirm it landed in D1
npx wrangler d1 execute your-db --command \
  "SELECT id, charges_enabled, payouts_enabled FROM connected_accounts;"

# Replay a webhook locally with Stripe CLI
stripe listen --forward-connect-to localhost:8787/webhooks/stripe/connect
stripe trigger account.updated
```

---

## Related

- `stripe-subscription-pause-resume-workers.md`
- `payment-idempotency-key-workers-kv.md`

---

## Sources

- Stripe Connect documentation — https://stripe.com/docs/connect
- Stripe Webhooks guide — https://stripe.com/docs/webhooks
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
