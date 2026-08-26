# Stripe Connect Payouts Dashboard via Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You operate a Stripe Connect platform and need a custom payouts dashboard — showing connected
account balances, pending vs available breakdown, payout history, and instant-payout eligibility
— without redirecting sellers to the Stripe Express dashboard.

## Context
Stripe Connect platforms can make API calls on behalf of connected accounts using the
`Stripe-Account` header (OAuth or direct-charge configurations). A Workers edge layer fetches
balance and payout list data per connected account, caches the snapshot in KV with a 60-second
TTL to avoid N×API calls on dashboard load, and serves a typed JSON response. For platforms
with hundreds of sellers, a Durable Object fan-out pattern batches the Stripe calls.

---

## Fetching Connected Account Balance and Payouts

The platform secret key plus the `Stripe-Account` header gives read access to a connected
account's financial data.

```typescript
// src/connect-balance.ts
export interface Env {
  STRIPE_SECRET_KEY: string; // platform key
  PAYOUT_CACHE: KVNamespace;
}

interface StripeBalance {
  available: { amount: number; currency: string }[];
  pending: { amount: number; currency: string }[];
  instant_available?: { amount: number; currency: string }[];
}

interface StripePayout {
  id: string;
  amount: number;
  currency: string;
  status: 'paid' | 'pending' | 'in_transit' | 'canceled' | 'failed';
  arrival_date: number;
  created: number;
  automatic: boolean;
}

interface PayoutsDashboardData {
  accountId: string;
  balance: StripeBalance;
  recentPayouts: StripePayout[];
  instantPayoutEligible: boolean;
  cachedAt: number;
}

async function stripeGet<T>(
  path: string,
  connectedAccountId: string,
  env: Env
): Promise<T> {
  const res = await fetch(`https://api.stripe.com/v1${path}`, {
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Stripe-Account': connectedAccountId,
      'Stripe-Version': '2024-06-20',
    },
  });
  if (!res.ok) {
    const err = await res.json<{ error: { message: string } }>();
    throw new Error(`Stripe ${path} failed: ${err.error.message}`);
  }
  return res.json<T>();
}

export async function getPayoutsDashboard(
  connectedAccountId: string,
  env: Env
): Promise<PayoutsDashboardData> {
  const cacheKey = `payout_dash:${connectedAccountId}`;
  const cached = await env.PAYOUT_CACHE.get(cacheKey, 'json');
  if (cached) return cached as PayoutsDashboardData;

  const [balance, payoutsResponse] = await Promise.all([
    stripeGet<StripeBalance>('/balance', connectedAccountId, env),
    stripeGet<{ data: StripePayout[] }>(
      '/payouts?limit=10&expand[]=data.destination',
      connectedAccountId,
      env
    ),
  ]);

  const instantPayoutEligible =
    (balance.instant_available ?? []).some((b) => b.amount > 0);

  const data: PayoutsDashboardData = {
    accountId: connectedAccountId,
    balance,
    recentPayouts: payoutsResponse.data,
    instantPayoutEligible,
    cachedAt: Date.now(),
  };

  await env.PAYOUT_CACHE.put(cacheKey, JSON.stringify(data), {
    expirationTtl: 60,
  });
  return data;
}
```

## Triggering an Instant Payout on Behalf of a Connected Account

```typescript
// src/instant-payout.ts
interface PayoutCreateParams {
  amount: number;         // in cents
  currency: string;       // e.g. 'usd'
  destinationId: string;  // bank account or debit card id
}

export async function createInstantPayout(
  connectedAccountId: string,
  params: PayoutCreateParams,
  env: Env
): Promise<StripePayout> {
  const body = new URLSearchParams({
    amount: String(params.amount),
    currency: params.currency,
    destination: params.destinationId,
    method: 'instant',
    // Idempotency key prevents duplicate payouts on Worker retry
  });

  const idempotencyKey = `instant-payout-${connectedAccountId}-${Date.now()}`;

  const res = await fetch('https://api.stripe.com/v1/payouts', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Stripe-Account': connectedAccountId,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Idempotency-Key': idempotencyKey,
      'Stripe-Version': '2024-06-20',
    },
    body,
  });

  if (!res.ok) {
    const err = await res.json<{ error: { code: string; message: string } }>();
    throw new Error(`Instant payout failed [${err.error.code}]: ${err.error.message}`);
  }

  // Bust the dashboard cache for this account
  await env.PAYOUT_CACHE.delete(`payout_dash:${connectedAccountId}`);
  return res.json<StripePayout>();
}
```

## Worker Route Handler with Platform Auth Guard

The platform must authenticate that the caller owns the connected account before proxying
any Stripe call — never trust a client-supplied `account_id` without server-side binding.

```typescript
// src/index.ts
import { getPayoutsDashboard } from './connect-balance';
import { createInstantPayout } from './instant-payout';

export interface Env {
  STRIPE_SECRET_KEY: string;
  PAYOUT_CACHE: KVNamespace;
  DB: D1Database;
}

async function resolveConnectedAccountId(
  platformUserId: string,
  env: Env
): Promise<string | null> {
  const row = await env.DB.prepare(
    `SELECT stripe_account_id FROM connected_accounts WHERE platform_user_id = ?`
  )
    .bind(platformUserId)
    .first<{ stripe_account_id: string }>();
  return row?.stripe_account_id ?? null;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Caller identity from JWT / session cookie (simplified)
    const platformUserId = req.headers.get('x-platform-user-id');
    if (!platformUserId) return new Response('Unauthorized', { status: 401 });

    const accountId = await resolveConnectedAccountId(platformUserId, env);
    if (!accountId) return new Response('No connected account', { status: 404 });

    if (url.pathname === '/payouts/dashboard' && req.method === 'GET') {
      const data = await getPayoutsDashboard(accountId, env);
      return Response.json(data);
    }

    if (url.pathname === '/payouts/instant' && req.method === 'POST') {
      const { amount, currency, destinationId } = await req.json<{
        amount: number;
        currency: string;
        destinationId: string;
      }>();
      const payout = await createInstantPayout(accountId, { amount, currency, destinationId }, env);
      return Response.json(payout, { status: 201 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Anti-patterns
- Accepting a client-supplied `stripe_account_id` and passing it directly to the Stripe API
  — any authenticated user could pull another seller's balance.
- Skipping KV caching for the balance endpoint — Stripe's balance API is not rate-limited
  generously for per-request dashboard loads with many sellers.
- Creating payouts without idempotency keys — network retries on Worker timeout can
  double-payout a seller.
- Exposing `instant_available` amounts to the UI without verifying `instant_payout_eligible`
  on the account's capabilities — the payout call will fail if the feature isn't enabled.

## Gotchas
- `instant_available` only appears when the connected account's bank supports instant payouts
  and the card/bank has been verified; it may be absent even if the balance object succeeds.
- Platform-controlled payouts require the `transfers` or `legacy_payments` capability on the
  connected account — check `account.capabilities.transfers === 'active'` before allowing
  the UI to show the payout button.
- Stripe imposes a minimum payout amount (typically $1 USD equivalent); validate `amount`
  server-side before the Stripe call.
- KV TTL of 60 seconds means a just-completed payout won't appear in the history until the
  next cache miss — bust the cache explicitly after a payout write.

## Verification
```bash
# Fetch balance for a connected account directly
curl https://api.stripe.com/v1/balance \
  -H "Authorization: Bearer sk_test_xxx" \
  -H "Stripe-Account: acct_xxx"

# List recent payouts
curl "https://api.stripe.com/v1/payouts?limit=5" \
  -H "Authorization: Bearer sk_test_xxx" \
  -H "Stripe-Account: acct_xxx"
```

```sql
-- Verify platform account binding
SELECT platform_user_id, stripe_account_id FROM connected_accounts LIMIT 10;
```

## Related
- `stripe-connect-payouts.md`
- `stripe-connect-platform.md`
- `stripe-instant-payouts-scheduling.md`
- `stripe-connect-marketplace-platform-payments.md`
- `stripe-connect-reserve-hold-lifecycle.md`

## Sources
- https://stripe.com/docs/connect/account-balances
- https://stripe.com/docs/connect/payouts
- https://stripe.com/docs/api/balance
- https://stripe.com/docs/api/payouts/create
- https://stripe.com/docs/connect/instant-payouts
- https://developers.cloudflare.com/kv/
