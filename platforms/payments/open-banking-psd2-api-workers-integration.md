# PSD2 Open Banking API Integration with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to fetch real-time account balances and transaction history from UK Open Banking APIs (Monzo, Starling, HSBC, etc.) inside a Cloudflare Workers backend, handling AISP/PISP OAuth consent flows, automatic token refresh, FAPI compliance headers, and normalizing the multi-bank transaction responses into a canonical D1 schema.

## Context

UK Open Banking mandates that banks expose their accounts and transactions via a standardised REST API (OBIE v3.1.x) secured with FAPI-compliant OAuth 2.0. Your Workers backend acts as a Third-Party Provider (TPP):

1. **Consent** — redirect the user to the bank's authorisation server with an `account-access-consent` resource you created via the bank's API.
2. **Callback** — the bank redirects back to your Worker with an authorisation code; exchange it for access + refresh tokens and store them in KV per user.
3. **Data fetch** — call the bank's `/accounts`, `/balances`, and `/transactions` endpoints using the access token; refresh automatically on 401.
4. **Normalisation** — map each bank's proprietary transaction JSON to a canonical D1 schema.

## Worker Implementation

```typescript
// src/open-banking.ts
import { Hono } from 'hono';

export interface Env {
  KV: KVNamespace;
  DB: D1Database;
  OB_CLIENT_ID: string;
  OB_CLIENT_SECRET: string;
  OB_REDIRECT_URI: string;       // e.g. https://your-worker.workers.dev/ob/callback
  OB_FINANCIAL_ID: string;       // x-fapi-financial-id for the target bank
}

interface OBToken {
  access_token: string;
  refresh_token: string;
  expires_at: number;            // Unix ms
}

async function getTokenForUser(userId: string, kv: KVNamespace): Promise<OBToken | null> {
  const raw = await kv.get(`ob:token:${userId}`);
  return raw ? (JSON.parse(raw) as OBToken) : null;
}

async function saveTokenForUser(userId: string, token: OBToken, kv: KVNamespace): Promise<void> {
  await kv.put(`ob:token:${userId}`, JSON.stringify(token));
}

async function refreshAccessToken(
  refreshToken: string,
  env: Env,
  bankTokenUrl: string
): Promise<OBToken> {
  const res = await fetch(bankTokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: env.OB_CLIENT_ID,
      client_secret: env.OB_CLIENT_SECRET,
    }),
  });
  if (!res.ok) throw new Error(`Token refresh failed: ${res.status}`);
  const data = await res.json() as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };
  return {
    access_token: <redacted-secret>
    refresh_token: data.refresh_token,
    expires_at: Date.now() + data.expires_in * 1000,
  };
}

function fapiHeaders(env: Env, interactionId: string): Record<string, string> {
  return {
    'x-fapi-financial-id': env.OB_FINANCIAL_ID,
    'x-fapi-auth-date': new Date().toUTCString(),
    'x-fapi-customer-ip-address': '',  // set to user IP if available
    'x-fapi-interaction-id': interactionId,
  };
}

async function obFetch(
  url: string,
  userId: string,
  bankTokenUrl: string,
  env: Env
): Promise<Response> {
  let token = await getTokenForUser(userId, env.KV);
  if (!token) throw new Error('No token for user');

  // Proactively refresh if within 60 seconds of expiry
  if (token.expires_at - Date.now() < 60_000) {
    token = await refreshAccessToken(token.refresh_token, env, bankTokenUrl);
    await saveTokenForUser(userId, token, env.KV);
  }

  const interactionId = crypto.randomUUID();
  let res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token.access_token}`,
      Accept: 'application/json',
      ...fapiHeaders(env, interactionId),
    },
  });

  // Handle expired token not caught by proactive check
  if (res.status === 401) {
    token = await refreshAccessToken(token.refresh_token, env, bankTokenUrl);
    await saveTokenForUser(userId, token, env.KV);
    res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token.access_token}`,
        Accept: 'application/json',
        ...fapiHeaders(env, crypto.randomUUID()),
      },
    });
  }

  return res;
}

const app = new Hono<{ Bindings: Env }>();

// ── 1. Initiate Consent Flow ─────────────────────────────────────────────────
app.get('/ob/connect', async (c) => {
  const userId = c.req.query('user_id');
  const bankAuthUrl = c.req.query('bank_auth_url'); // caller specifies target bank
  if (!userId || !bankAuthUrl) return c.json({ error: 'missing_params' }, 400);

  const state = crypto.randomUUID();
  await c.env.KV.put(`ob:state:${state}`, JSON.stringify({ userId, bankAuthUrl }), {
    expirationTtl: 600, // 10-minute window to complete auth
  });

  const authUrl = new URL(bankAuthUrl);
  authUrl.searchParams.set('response_type', 'code id_token');
  authUrl.searchParams.set('client_id', c.env.OB_CLIENT_ID);
  authUrl.searchParams.set('redirect_uri', c.env.OB_REDIRECT_URI);
  authUrl.searchParams.set('scope', 'openid accounts');
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('nonce', crypto.randomUUID());

  return c.redirect(authUrl.toString());
});

// ── 2. OAuth Callback ────────────────────────────────────────────────────────
app.get('/ob/callback', async (c) => {
  const code = c.req.query('code');
  const state = c.req.query('state');
  if (!code || !state) return c.json({ error: 'missing_code_or_state' }, 400);

  const stateData = await c.env.KV.get(`ob:state:${state}`);
  if (!stateData) return c.json({ error: 'invalid_or_expired_state' }, 400);

  const { userId, bankAuthUrl } = JSON.parse(stateData) as {
    userId: string;
    bankAuthUrl: string;
  };
  await c.env.KV.delete(`ob:state:${state}`);

  // Derive token URL from auth URL (bank-specific, simplified here)
  const tokenUrl = bankAuthUrl.replace('/authorize', '/token');
  const res = await fetch(tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: c.env.OB_REDIRECT_URI,
      client_id: c.env.OB_CLIENT_ID,
      client_secret: <redacted-secret>
    }),
  });

  if (!res.ok) return c.json({ error: 'token_exchange_failed' }, 502);
  const data = await res.json() as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  const token: OBToken = {
    access_token: <redacted-secret>
    refresh_token: data.refresh_token,
    expires_at: Date.now() + data.expires_in * 1000,
  };
  await saveTokenForUser(userId, token, c.env.KV);

  return c.json({ status: 'connected', userId });
});

// ── 3. Fetch and Normalise Transactions ──────────────────────────────────────
app.get('/ob/transactions/:userId', async (c) => {
  const { userId } = c.req.param();
  const bankApiBase = c.req.query('bank_api_base') ?? '';
  const bankTokenUrl = c.req.query('bank_token_url') ?? '';
  if (!bankApiBase || !bankTokenUrl) return c.json({ error: 'missing_bank_params' }, 400);

  const res = await obFetch(
    `${bankApiBase}/open-banking/v3.1/aisp/transactions`,
    userId,
    bankTokenUrl,
    c.env
  );
  if (!res.ok) return c.json({ error: 'bank_api_error', status: res.status }, 502);

  const data = await res.json() as {
    Data: { Transaction: Array<Record<string, unknown>> };
  };

  const now = Date.now();
  const stmt = c.env.DB.prepare(
    `INSERT OR IGNORE INTO transactions
       (transaction_id, user_id, bank_id, amount, currency, description, booked_at, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  );

  const inserts = data.Data.Transaction.map((tx) => {
    // Canonical normalisation across OBIE-compliant banks
    const id = (tx.TransactionId ?? tx.TransactionReference) as string;
    const amount = (tx.Amount as { Amount: string; Currency: string });
    const desc =
      (tx.TransactionInformation as string) ??
      (tx.CreditorAgent as Record<string, string>)?.Name ??
      'unknown';
    const bookedAt = new Date(tx.BookingDateTime as string).getTime();
    return stmt.bind(id, userId, c.env.OB_FINANCIAL_ID, amount.Amount, amount.Currency, desc, bookedAt, now);
  });

  await c.env.DB.batch(inserts);
  return c.json({ inserted: inserts.length });
});

export default app;
```

## D1 Schema

```sql
-- migrations/0001_open_banking.sql
CREATE TABLE IF NOT EXISTS transactions (
  transaction_id TEXT NOT NULL,
  user_id        TEXT NOT NULL,
  bank_id        TEXT NOT NULL,  -- x-fapi-financial-id of source bank
  amount         TEXT NOT NULL,  -- decimal string, e.g. "19.99"
  currency       TEXT NOT NULL,
  description    TEXT,
  booked_at      INTEGER NOT NULL,
  created_at     INTEGER NOT NULL,
  PRIMARY KEY (transaction_id, bank_id)
);

CREATE INDEX IF NOT EXISTS idx_txn_user_booked ON transactions (user_id, booked_at DESC);
```

## Anti-patterns

- **Storing tokens in D1 instead of KV**: Access tokens are accessed on every API call and must be retrieved with minimal latency. D1 read latency is higher than KV; use KV for hot per-user tokens.
- **Not validating the `state` parameter on callback**: Without CSRF protection on the callback, an attacker can trick a user into linking their bank account to the attacker's session.
- **Using a single shared access token for all users**: Each user must have their own consent and token obtained through their individual authorisation flow.

## Gotchas

- FAPI requires `x-fapi-interaction-id` to be a UUID and to be echoed back in the response — log it for traceability across bank and internal logs.
- Some banks (Monzo sandbox in particular) return `expires_in: 0` on certain test credentials. Guard against this: treat 0 as already expired and refresh immediately.
- OBIE `BookingDateTime` is ISO 8601 with timezone; use `new Date(str).getTime()` rather than substring extraction to avoid timezone bugs.
- The `TransactionId` field is optional in OBIE v3.1; fall back to `TransactionReference` or a deterministic hash of `BookingDateTime + Amount + Description` for deduplication.

## Verification

```bash
# 1. Start the OAuth flow for a test user against Monzo sandbox
curl "https://your-worker.workers.dev/ob/connect?user_id=u001&bank_auth_url=https://auth.monzo.com/oauth2/authorize"
# Follow the redirect, complete Monzo sandbox auth, observe the /ob/callback response

# 2. Fetch and normalise transactions
curl "https://your-worker.workers.dev/ob/transactions/u001
  ?bank_api_base=https://api.monzo.com
  &bank_token_url=https://api.monzo.com/oauth2/token"

# 3. Confirm rows in D1
wrangler d1 execute <DB_NAME> \
  --command "SELECT transaction_id, amount, currency, description, booked_at FROM transactions WHERE user_id='u001' LIMIT 10;"
```

## Related

- `apple-pay-domain-verification-workers.md`
- `adyen-payments-workers-integration.md`
- UK Open Banking specification: https://openbankinguk.github.io/read-write-api-docs-pub/

## Sources

- OBIE Read/Write API v3.1: https://openbankinguk.github.io/read-write-api-docs-pub/v3.1.11/
- FAPI 1.0 Advanced specification: https://openid.net/specs/openid-financial-api-part-2-1_0.html
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare D1: https://developers.cloudflare.com/d1/
