# Stripe Connect OAuth Flow in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You are building a multi-sided marketplace and need to onboard merchant accounts via Stripe Connect. Each merchant must grant your platform permission to create charges on their behalf. The OAuth redirect flow must be stateless at the edge — no sticky sessions, no origin round-trips.

## Context

Stripe Connect supports two integration patterns:
- **Standard**: merchant signs up for a full Stripe account; your platform gets delegated access.
- **Express / Custom**: your platform owns the UX but still uses OAuth tokens under the hood.

Cloudflare Workers sit in front of your origin and can own the entire OAuth handshake using KV for ephemeral state and D1 for durable account storage.

## Solution

### 1. Generate the Authorization URL

```typescript
// src/handlers/connect/authorize.ts
import { Env } from '../../types';

const STRIPE_CONNECT_BASE = 'https://connect.stripe.com/oauth/authorize';

export async function handleAuthorize(
  request: Request,
  env: Env
): Promise<Response> {
  const merchantId = new URL(request.url).searchParams.get('merchant_id');
  if (!merchantId) {
    return new Response('Missing merchant_id', { status: 400 });
  }

  // Generate a cryptographically random state token
  const stateBytes = crypto.getRandomValues(new Uint8Array(32));
  const state = btoa(String.fromCharCode(...stateBytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');

  // Store state -> merchantId mapping in KV with 10-minute TTL
  await env.CONNECT_STATE_KV.put(
    `oauth_state:${state}`,
    JSON.stringify({ merchantId, createdAt: Date.now() }),
    { expirationTtl: 600 }
  );

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: env.STRIPE_CLIENT_ID,
    scope: 'read_write',
    redirect_uri: `${env.BASE_URL}/connect/callback`,
    state,
    // Pre-fill merchant details if available
    'stripe_user[email]': '',
    'stripe_user[business_type]': 'company',
  });

  return Response.redirect(
    `${STRIPE_CONNECT_BASE}?${params.toString()}`,
    302
  );
}
```

### 2. Handle the OAuth Callback

```typescript
// src/handlers/connect/callback.ts
import { Env } from '../../types';
import { storeConnectedAccount } from '../../db/accounts';

export async function handleCallback(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  if (error) {
    const desc = url.searchParams.get('error_description') ?? error;
    return Response.redirect(
      `${env.BASE_URL}/dashboard?connect_error=${encodeURIComponent(desc)}`,
      302
    );
  }

  if (!code || !state) {
    return new Response('Invalid callback parameters', { status: 400 });
  }

  // Validate state from KV
  const stateData = await env.CONNECT_STATE_KV.get(
    `oauth_state:${state}`,
    'json'
  ) as { merchantId: string; createdAt: number } | null;

  if (!stateData) {
    return new Response('Invalid or expired state', { status: 400 });
  }

  // Consume state immediately (prevent replay)
  await env.CONNECT_STATE_KV.delete(`oauth_state:${state}`);

  // Exchange code for access token
  const tokenResponse = await exchangeCodeForToken(code, env);
  if (!tokenResponse.ok) {
    const body = await tokenResponse.json();
    console.error('Token exchange failed', body);
    return new Response('Token exchange failed', { status: 502 });
  }

  const token = await tokenResponse.json() as StripeConnectToken;

  // Persist connected account to D1
  await storeConnectedAccount(env.DB, {
    merchantId: stateData.merchantId,
    stripeAccountId: token.stripe_user_id,
    accessToken: <redacted-secret>
    refreshToken: token.refresh_token ?? null,
    scope: token.scope,
    tokenType: token.token_type,
    connectedAt: new Date().toISOString(),
  });

  return Response.redirect(
    `${env.BASE_URL}/dashboard?connect_success=1`,
    302
  );
}

async function exchangeCodeForToken(
  code: string,
  env: Env
): Promise<Response> {
  return fetch('https://connect.stripe.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      client_secret: env.STRIPE_SECRET_KEY,
    }),
  });
}

interface StripeConnectToken {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  stripe_user_id: string;
  scope: string;
}
```

### 3. D1 Schema for Connected Accounts

```sql
-- migrations/001_connected_accounts.sql
CREATE TABLE IF NOT EXISTS connected_accounts (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  merchant_id     TEXT NOT NULL,
  stripe_account_id TEXT NOT NULL UNIQUE,
  access_token    TEXT NOT NULL,
  refresh_token   TEXT,
  scope           TEXT NOT NULL,
  token_type      TEXT NOT NULL DEFAULT 'bearer',
  connected_at    TEXT NOT NULL,
  deauthorized_at TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_connected_accounts_merchant
  ON connected_accounts (merchant_id);
CREATE INDEX idx_connected_accounts_stripe
  ON connected_accounts (stripe_account_id);
```

### 4. D1 Account Storage Helper

```typescript
// src/db/accounts.ts
import { Env } from '../types';

export interface ConnectedAccountRecord {
  merchantId: string;
  stripeAccountId: string;
  accessToken: string;
  refreshToken: string | null;
  scope: string;
  tokenType: string;
  connectedAt: string;
}

export async function storeConnectedAccount(
  db: D1Database,
  record: ConnectedAccountRecord
): Promise<void> {
  await db
    .prepare(`
      INSERT INTO connected_accounts
        (merchant_id, stripe_account_id, access_token, refresh_token,
         scope, token_type, connected_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (stripe_account_id) DO UPDATE SET
        access_token   = <redacted-secret>
        refresh_token  = excluded.refresh_token,
        scope          = excluded.scope,
        updated_at     = datetime('now'),
        deauthorized_at = NULL
    `)
    .bind(
      record.merchantId,
      record.stripeAccountId,
      record.accessToken,
      record.refreshToken,
      record.scope,
      record.tokenType,
      record.connectedAt
    )
    .run();
}

export async function getConnectedAccount(
  db: D1Database,
  merchantId: string
): Promise<ConnectedAccountRecord | null> {
  const row = await db
    .prepare(`
      SELECT * FROM connected_accounts
      WHERE merchant_id = ? AND deauthorized_at IS NULL
      LIMIT 1
    `)
    .bind(merchantId)
    .first();

  if (!row) return null;
  return row as unknown as ConnectedAccountRecord;
}
```

### 5. Deauthorization Webhook Handler

```typescript
// src/handlers/connect/deauthorize.ts
import { Stripe } from 'stripe';
import { Env } from '../../types';

export async function handleDeauthorizeWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const rawBody = await request.text();
  const signature = request.headers.get('stripe-signature') ?? '';

  let event: Stripe.Event;
  try {
    // Verify webhook signature
    const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
    event = stripe.webhooks.constructEvent(
      rawBody,
      signature,
      env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err) {
    return new Response(`Webhook signature verification failed: ${err}`, {
      status: 400,
    });
  }

  if (event.type === 'account.application.deauthorized') {
    const stripeAccountId = (event.account as string);
    await env.DB.prepare(`
      UPDATE connected_accounts
      SET deauthorized_at = datetime('now'), updated_at = datetime('now')
      WHERE stripe_account_id = ?
    `)
      .bind(stripeAccountId)
      .run();

    console.log(`Deauthorized Stripe account: ${stripeAccountId}`);
  }

  return new Response(JSON.stringify({ received: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

### 6. Router Wiring

```typescript
// src/index.ts
import { handleAuthorize } from './handlers/connect/authorize';
import { handleCallback } from './handlers/connect/callback';
import { handleDeauthorizeWebhook } from './handlers/connect/deauthorize';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/connect/authorize' && request.method === 'GET')
      return handleAuthorize(request, env);
    if (pathname === '/connect/callback' && request.method === 'GET')
      return handleCallback(request, env);
    if (pathname === '/webhooks/connect' && request.method === 'POST')
      return handleDeauthorizeWebhook(request, env);

    return new Response('Not Found', { status: 404 });
  },
};
```

### 7. wrangler.toml Bindings

```toml
# wrangler.toml
name = "stripe-connect-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "CONNECT_STATE_KV"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id = "<your-d1-database-id>"

[vars]
BASE_URL = "https://api.yourplatform.com"
STRIPE_CLIENT_ID = "ca_xxx"

# Secrets (set via `wrangler secret put`)
# STRIPE_SECRET_KEY
# STRIPE_WEBHOOK_SECRET
```

## Implementation Details

**State parameter lifespan**: KV TTL is set to 600 seconds (10 minutes). If the merchant takes longer than that to complete Stripe's onboarding, the state will expire and they receive a fresh "Invalid or expired state" error — harmless; they just restart the flow.

**Token storage**: Access tokens are stored in plaintext in D1 in this example. In production, encrypt them with a KV-backed DEK (data-encryption key) or use Cloudflare's `secrets` binding for the encryption key.

**Idempotency**: The `ON CONFLICT … DO UPDATE` clause means re-connecting the same Stripe account simply refreshes the token rather than inserting a duplicate row.

**Scopes**: `read_write` grants your platform the ability to create charges, refunds, and payouts on behalf of the connected account. Use `read_only` if you only need reporting access.

## Anti-patterns

- **Storing state in a cookie**: Cookies are per-browser; a merchant opening the flow on mobile and completing on desktop will fail. KV is the correct cross-device store.
- **Skipping state validation**: Without CSRF state verification an attacker can inject their own `code` and connect your platform to their account.
- **Reusing access tokens across workers**: Each Worker invocation should read the latest token from D1; never cache it in a module-level variable because the token can be revoked asynchronously.
- **Logging full access tokens**: Emit only the last 4 characters for tracing.

## Gotchas

- Stripe's `redirect_uri` must match **exactly** what is registered in your Connect settings dashboard — trailing slashes matter.
- `event.account` on a deauthorization webhook is the connected account ID (e.g. `acct_xxx`), not your platform account.
- `refresh_token` is only present for Standard accounts; Express/Custom accounts use rotating access tokens.
- The Workers `crypto.getRandomValues` API is synchronous and available in the global scope — no need to import Node's `crypto`.

## Verification

```bash
# 1. Trigger the authorize redirect
curl -I "https://your-worker.workers.dev/connect/authorize?merchant_id=merch_123"
# Expect: 302 to connect.stripe.com

# 2. Simulate callback (Stripe test mode)
curl "https://your-worker.workers.dev/connect/callback\
?code=ac_test_xxx&state=<state-from-kv>"
# Expect: 302 to /dashboard?connect_success=1

# 3. Confirm D1 row
wrangler d1 execute payments \
  --command "SELECT stripe_account_id, connected_at FROM connected_accounts LIMIT 5;"
```

## Related

- `documentation/categories/payments/workers-pci-dss-scope-reduction.md`
- `documentation/categories/payments/workers-payment-retry-exponential-backoff.md`

## Sources

- https://stripe.com/docs/connect/oauth-reference
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
