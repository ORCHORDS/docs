# Stripe Connect Standard OAuth Flow with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project plans a creator monetization layer where verified users can receive tips from anonymous
supporters. Stripe Connect Standard lets creators attach their existing personal Stripe accounts
with minimal onboarding friction — Stripe handles KYC and payouts directly, reducing example project's
liability. The OAuth authorization flow, code exchange, and account ID storage must happen
server-side in Workers to keep the client secret off the browser.

## Context
Stripe Connect Standard OAuth uses a standard authorization-code grant: the platform redirects the
creator to Stripe, Stripe redirects back with a code, and Workers exchanges the code for
`access_token` + `stripe_user_id`. All platform-initiated charges then use `on_behalf_of` or
`transfer_data.destination` to route funds. D1 stores the connected account association; the OAuth
state parameter is short-lived in Workers KV to prevent CSRF.

## Section 1 — OAuth Authorization Redirect
Generate a cryptographically random `state` value, store it in KV with a short TTL, then redirect
the creator to Stripe's OAuth endpoint. The `state` ties the callback to the originating session.

```typescript
interface Env {
  DB: D1Database;
  OAUTH_STATE_KV: KVNamespace;
  STRIPE_CLIENT_ID: string;           // Stripe Connect platform client_id (ca_…)
  STRIPE_SECRET_KEY: string;
  STRIPE_CONNECT_REDIRECT_URI: string; // e.g. https://example.com/connect/callback
}

// Route: GET /connect/authorize?userId=<userId>
async function handleAuthorize(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.searchParams.get('userId');
  if (!userId) return new Response('Missing userId', { status: 400 });

  const state = crypto.randomUUID();

  // Store state → userId mapping; 10-minute TTL
  await env.OAUTH_STATE_KV.put(`oauth_state:${state}`, userId, { expirationTtl: 600 });

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: env.STRIPE_CLIENT_ID,
    scope: 'read_write',
    redirect_uri: env.STRIPE_CONNECT_REDIRECT_URI,
    state,
    // Pre-fill the creator's email if available to smooth onboarding
    'stripe_user[business_type]': 'individual',
  });

  return Response.redirect(
    `https://connect.stripe.com/oauth/authorize?${params.toString()}`,
    302
  );
}
```

## Section 2 — OAuth Callback: Code Exchange and Account Storage
On the callback, validate the `state`, exchange the code for tokens, then persist the connected
account ID in D1 for future charge routing.

```typescript
// Route: GET /connect/callback?code=<code>&state=<state>
async function handleCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  if (error) {
    // Creator denied access
    return Response.redirect('https://example.com/connect/declined', 302);
  }

  if (!code || !state) return new Response('Missing parameters', { status: 400 });

  // Validate CSRF state
  const userId = await env.OAUTH_STATE_KV.get(`oauth_state:${state}`);
  if (!userId) return new Response('Invalid or expired state', { status: 400 });

  // Consume state immediately to prevent replay
  await env.OAUTH_STATE_KV.delete(`oauth_state:${state}`);

  // Exchange authorization code for access token
  const tokenRes = await fetch('https://connect.stripe.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_secret: env.STRIPE_SECRET_KEY,
      code,
      grant_type: 'authorization_code',
    }),
  });

  if (!tokenRes.ok) {
    const body = await tokenRes.text();
    console.error(`Stripe OAuth token exchange failed: ${tokenRes.status} ${body}`);
    return new Response('Token exchange failed', { status: 502 });
  }

  const token = await tokenRes.json<{
    access_token: string;
    stripe_user_id: string;
    scope: string;
    token_type: string;
    refresh_token?: string;
    livemode: boolean;
  }>();

  if (!token.stripe_user_id) {
    return new Response('No stripe_user_id in response', { status: 502 });
  }

  // Store connected account; access_token stored only if needed for platform-side API calls
  await env.DB
    .prepare(
      `INSERT INTO stripe_connect_accounts
         (user_id, stripe_account_id, scope, livemode, connected_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(user_id) DO UPDATE SET
         stripe_account_id = excluded.stripe_account_id,
         scope             = excluded.scope,
         livemode          = excluded.livemode,
         updated_at        = excluded.updated_at`
    )
    .bind(
      userId,
      token.stripe_user_id,
      token.scope,
      token.livemode ? 1 : 0,
      Date.now(),
      Date.now()
    )
    .run();

  return Response.redirect('https://example.com/connect/success', 302);
}
```

## Section 3 — Creating Charges on Behalf of Connected Accounts
Once a creator is connected, use `transfer_data.destination` on a PaymentIntent so the tip flows
through the platform to the creator, with a platform fee retained.

```typescript
interface TipRequest {
  creatorUserId: string;
  amountCents: number;   // e.g. 500 = $5.00
  currency: string;      // e.g. 'usd'
  paymentMethodId: string;
  idempotencyKey: string;
}

const PLATFORM_FEE_PERCENT = 0.10; // 10% platform fee

async function createTipPaymentIntent(
  env: Env,
  tip: TipRequest
): Promise<{ clientSecret: string }> {
  const account = await env.DB
    .prepare(
      `SELECT stripe_account_id, livemode
       FROM stripe_connect_accounts WHERE user_id = ?`
    )
    .bind(tip.creatorUserId)
    .first<{ stripe_account_id: string; livemode: number }>();

  if (!account) throw new Error(`Creator ${tip.creatorUserId} has no connected Stripe account`);

  const applicationFeeAmount = Math.floor(tip.amountCents * PLATFORM_FEE_PERCENT);

  const piRes = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Idempotency-Key': tip.idempotencyKey,
    },
    body: new URLSearchParams({
      amount: String(tip.amountCents),
      currency: tip.currency,
      payment_method: tip.paymentMethodId,
      confirm: 'true',
      'automatic_payment_methods[enabled]': 'true',
      'automatic_payment_methods[allow_redirects]': 'never',
      application_fee_amount: String(applicationFeeAmount),
      'transfer_data[destination]': account.stripe_account_id,
    }),
  });

  if (!piRes.ok) {
    const err = await piRes.text();
    throw new Error(`PaymentIntent creation failed: ${piRes.status} ${err}`);
  }

  const pi = await piRes.json<{ client_secret: string; status: string }>();
  return { clientSecret: <redacted-secret> };
}
```

## Section 4 — Account Deauthorization Webhook
When a creator disconnects their Stripe account, Stripe sends an `account.application.deauthorized`
event. Remove the stored account association and halt future tip routing.

```typescript
interface StripeAccountEvent {
  type: string;
  account: string; // stripe_user_id of the connected account
}

async function handleDeauthorization(
  env: Env,
  event: StripeAccountEvent
): Promise<void> {
  if (event.type !== 'account.application.deauthorized') return;

  const stripeAccountId = event.account;

  await env.DB
    .prepare(
      `UPDATE stripe_connect_accounts
       SET stripe_account_id = NULL, disconnected_at = ?, updated_at = ?
       WHERE stripe_account_id = ?`
    )
    .bind(Date.now(), Date.now(), stripeAccountId)
    .run();

  console.log(JSON.stringify({
    level: 'info',
    service: 'stripe-connect-standard',
    event: 'account_deauthorized',
    stripe_account_id: stripeAccountId,
    ts: new Date().toISOString(),
  }));
}

async function monitorConnectedAccounts(env: Env): Promise<void> {
  const stats = await env.DB
    .prepare(
      `SELECT
         COUNT(*) AS total,
         SUM(CASE WHEN stripe_account_id IS NULL THEN 1 ELSE 0 END) AS disconnected,
         SUM(CASE WHEN livemode = 1 THEN 1 ELSE 0 END) AS live
       FROM stripe_connect_accounts`
    )
    .first<{ total: number; disconnected: number; live: number }>();

  console.log(JSON.stringify({
    level: 'info',
    service: 'stripe-connect-standard',
    total_accounts: stats?.total ?? 0,
    disconnected: stats?.disconnected ?? 0,
    live_accounts: stats?.live ?? 0,
    ts: new Date().toISOString(),
  }));
}
```

## Anti-patterns
- Returning the Stripe `access_token` to the client or storing it in a cookie — it grants full API access to the connected account
- Skipping the `state` parameter in the authorization redirect — this enables CSRF attacks that hijack creator account connections
- Reusing the same `state` value across multiple authorization attempts — each attempt must generate a fresh random state
- Using `on_behalf_of` instead of `transfer_data.destination` when you want funds to land directly in the creator's account
- Trusting the `stripe_user_id` returned in the callback query string instead of the token exchange response body

## Gotchas
- Stripe Connect Standard `scope: 'read_write'` is being replaced by more granular scopes; check the Connect dashboard for the current recommendation
- The `redirect_uri` must exactly match one of the URIs registered in the Stripe dashboard (including protocol and trailing slash)
- `account.application.deauthorized` is delivered to the platform's webhook endpoint, not the connected account's — configure it on your platform account
- In livemode, only real Stripe accounts can authorize; use `stripe_user[email]` prefill to route to the right test account in sandbox

## Verification
1. Trigger the OAuth flow with a Stripe test account and confirm `stripe_connect_accounts` row is populated in D1
2. Create a tip PaymentIntent and verify the `application_fee_amount` deduction in the Stripe dashboard
3. Deauthorize via the Stripe dashboard and confirm `disconnected_at` is set in D1
4. Submit an expired `state` value to the callback and confirm a 400 response

## Related
- /documentation/categories/payments/stripe-connect-express.md
- /documentation/categories/payments/stripe-connect-custom.md
- /documentation/categories/payments/stripe-connect-platform.md
- /documentation/categories/payments/stripe-webhook-signature-verification.md

## Sources
- https://docs.stripe.com/connect/oauth-reference
- https://docs.stripe.com/connect/standard-accounts
- https://docs.stripe.com/connect/collect-then-transfer-guide
- https://docs.stripe.com/api/payment_intents/create#create_payment_intent-transfer_data
