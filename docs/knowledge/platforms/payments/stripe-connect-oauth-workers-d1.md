# Stripe Connect OAuth Flow in Workers with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Marketplace and platform products on Cloudflare Workers need to onboard sellers or service providers via Stripe Connect so that platform charges can be routed directly to connected accounts. The OAuth flow requires a secure state parameter to prevent CSRF, temporary storage while the user completes authorization on Stripe, and persisted `access_token` / `stripe_user_id` pairs for subsequent charges. This article implements the full Connect OAuth flow — redirect initiation, callback handling, token exchange — entirely in Workers with D1 for durable storage.

---

## Context

Stripe Connect Standard OAuth is a three-legged OAuth 2.0 flow. The platform redirects the user to `https://connect.stripe.com/oauth/authorize` with `client_id`, `state`, and `redirect_uri`. After authorization, Stripe redirects back with `code` and `state`; the platform exchanges `code` for `access_token` and `stripe_user_id` via `https://connect.stripe.com/oauth/token`. The `state` parameter must be a cryptographically random nonce stored server-side to prevent CSRF; Cloudflare KV is a convenient ephemeral store with short TTL for this. The resulting `access_token` and `stripe_user_id` are stored in D1 for durable association with your internal user ID. Subsequent charges on behalf of the connected account use the `Stripe-Account: acct_xxx` header or `stripe_account` parameter in the API request.

---

## Section 1 — D1 Schema

```sql
-- migrations/0002_connected_accounts.sql
CREATE TABLE IF NOT EXISTS connected_accounts (
  id                   TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id              TEXT NOT NULL UNIQUE,      -- Your internal user/merchant ID
  stripe_user_id       TEXT NOT NULL UNIQUE,      -- acct_xxx
  access_token         TEXT NOT NULL,             -- sk_live_xxx (store encrypted in prod)
  refresh_token        TEXT,
  token_type           TEXT NOT NULL DEFAULT 'bearer',
  scope                TEXT,
  livemode             INTEGER NOT NULL DEFAULT 0,
  connected_at         INTEGER NOT NULL DEFAULT (unixepoch()),
  disconnected_at      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_connected_accounts_user
  ON connected_accounts (user_id);
CREATE INDEX IF NOT EXISTS idx_connected_accounts_stripe
  ON connected_accounts (stripe_user_id);
```

---

## Section 2 — Worker Implementation

```typescript
// src/stripe-connect.ts
import { D1Database, KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  CONNECT_STATE_KV: KVNamespace;      // Ephemeral state store (TTL: 10 min)
  STRIPE_CLIENT_ID: string;           // ca_xxx from Stripe Connect settings
  STRIPE_SECRET_KEY: string;          // sk_live_xxx or sk_test_xxx
  CONNECT_REDIRECT_URI: string;       // https://your-worker.workers.dev/connect/callback
  BASE_URL: string;                   // https://your-worker.workers.dev
}

const STRIPE_OAUTH_AUTHORIZE = 'https://connect.stripe.com/oauth/authorize';
const STRIPE_OAUTH_TOKEN = 'https://connect.stripe.com/oauth/token';
const STATE_TTL_SECONDS = 600; // 10 minutes

function generateState(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function handleBegin(request: Request, env: Env): Promise<Response> {
  // In production, derive userId from your session/JWT
  const url = new URL(request.url);
  const userId = url.searchParams.get('user_id');
  if (!userId) return new Response('Missing user_id', { status: 400 });

  const state = generateState();

  // Store state -> userId mapping with a short TTL
  await env.CONNECT_STATE_KV.put(
    `oauth_state:${state}`,
    JSON.stringify({ userId }),
    { expirationTtl: STATE_TTL_SECONDS },
  );

  const authUrl = new URL(STRIPE_OAUTH_AUTHORIZE);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('client_id', env.STRIPE_CLIENT_ID);
  authUrl.searchParams.set('scope', 'read_write');
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('redirect_uri', env.CONNECT_REDIRECT_URI);

  return Response.redirect(authUrl.toString(), 302);
}

async function handleCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  if (error) {
    const desc = url.searchParams.get('error_description') ?? error;
    return new Response(`Stripe Connect error: ${desc}`, { status: 400 });
  }

  if (!code || !state) {
    return new Response('Missing code or state', { status: 400 });
  }

  // Validate state (CSRF protection)
  const stateData = await env.CONNECT_STATE_KV.get(`oauth_state:${state}`, 'json') as
    | { userId: string }
    | null;
  if (!stateData) {
    return new Response('Invalid or expired state', { status: 400 });
  }

  // Consume state — delete immediately to prevent replay
  await env.CONNECT_STATE_KV.delete(`oauth_state:${state}`);

  // Exchange authorization code for access token
  const tokenResponse = await fetch(STRIPE_OAUTH_TOKEN, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
    }),
  });

  if (!tokenResponse.ok) {
    const err = await tokenResponse.text();
    console.error('Token exchange failed:', err);
    return new Response('Token exchange failed', { status: 502 });
  }

  const token = await tokenResponse.json<{
    access_token: string;
    refresh_token: string;
    token_type: string;
    stripe_user_id: string;
    scope: string;
    livemode: boolean;
  }>();

  // Persist connected account in D1
  await env.DB.prepare(
    `INSERT INTO connected_accounts
       (user_id, stripe_user_id, access_token, refresh_token, token_type, scope, livemode)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (user_id) DO UPDATE SET
       stripe_user_id  = excluded.stripe_user_id,
       access_token    = <redacted-secret>
       refresh_token   = excluded.refresh_token,
       token_type      = excluded.token_type,
       scope           = excluded.scope,
       livemode        = excluded.livemode,
       disconnected_at = NULL`,
  )
    .bind(
      stateData.userId,
      token.stripe_user_id,
      token.access_token,
      token.refresh_token ?? null,
      token.token_type,
      token.scope ?? null,
      token.livemode ? 1 : 0,
    )
    .run();

  return Response.redirect(`${env.BASE_URL}/dashboard?connected=true`, 302);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/connect/begin') return handleBegin(request, env);
    if (url.pathname === '/connect/callback') return handleCallback(request, env);
    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Section 3 — Charging via Connected Account

```typescript
// src/platform-charge.ts
// After OAuth, use the connected account's stripe_user_id for charges

async function createPlatformCharge(
  env: Env,
  userId: string,
  amount: number,
  currency: string,
  paymentMethodId: string,
  applicationFeeAmount: number,
): Promise<{ chargeId: string }> {
  // Look up connected account
  const row = await env.DB.prepare(
    `SELECT stripe_user_id, access_token FROM connected_accounts
     WHERE user_id = ? AND disconnected_at IS NULL`,
  ).bind(userId).first<{ stripe_user_id: string; access_token: string }>();

  if (!row) throw new Error(`No connected account for user ${userId}`);

  // Create PaymentIntent on behalf of connected account
  const response = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      // Use the platform's secret key — Stripe-Account header routes to connected account
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Stripe-Account': row.stripe_user_id,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      amount: amount.toString(),
      currency,
      payment_method: paymentMethodId,
      confirm: 'true',
      application_fee_amount: applicationFeeAmount.toString(),
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Stripe charge failed: ${err}`);
  }

  const pi = await response.json<{ id: string }>();
  return { chargeId: pi.id };
}
```

---

## Anti-patterns

- **Storing `state` in a cookie or URL parameter without server-side validation** — The state must be validated server-side against a stored value to prevent CSRF attacks on the callback endpoint.
- **Using the connected account's `access_token` directly for platform charges** — Always use the platform's own secret key with the `Stripe-Account` header; the connected account's token is for their own API calls.
- **Not consuming (deleting) the state after use** — A state value that persists after the callback allows replay attacks within the TTL window.
- **Storing access tokens in plain text in D1** — In production, encrypt tokens at rest using a KMS-derived key or Cloudflare's `env.SECRET` binding.

---

## Gotchas

- The `redirect_uri` in `/connect/begin` must exactly match a URI registered in your Stripe Connect settings, including trailing slashes.
- Stripe returns `livemode: false` for test-mode connected accounts; ensure your D1 schema and queries filter by `livemode` when mixing test and live data.
- The `code` returned by Stripe is single-use and expires in 5 minutes — exchange it immediately in the callback.
- `ON CONFLICT (user_id) DO UPDATE` requires the `user_id` column to have a `UNIQUE` constraint; verify your migration applied before testing.
- Stripe Connect OAuth requires your platform to be approved for Standard Connect in the Dashboard before `client_id` is issued.

---

## Verification

```bash
# Apply migrations
npx wrangler d1 execute example project-db --file migrations/0002_connected_accounts.sql

# Run locally
npx wrangler dev

# Initiate connect flow (opens browser)
curl -L 'http://localhost:8787/connect/begin?user_id=user_abc123'

# After OAuth, verify connected account in D1
npx wrangler d1 execute example project-db --command \
  "SELECT user_id, stripe_user_id, livemode, connected_at FROM connected_accounts;"

# Verify state was cleaned up from KV
npx wrangler kv:key list --binding CONNECT_STATE_KV
```

---

## Related

- `stripe-webhooks-workers-d1-event-deduplication.md`
- `stripe-subscription-lifecycle-workers-kv.md`

---

## Sources

- Stripe Connect OAuth Reference — https://stripe.com/docs/connect/oauth-reference
- Stripe Connect Standard — https://stripe.com/docs/connect/standard-accounts
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare KV — https://developers.cloudflare.com/kv/
