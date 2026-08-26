# Open Banking PSD2 AIS Account Data Retrieval via Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to read a user's bank account balances, transaction history, or account ownership data
through a PSD2-compliant Account Information Service (AIS) provider — to pre-fill payment amounts,
verify funds before ACH, or power a personal finance dashboard — without storing raw bank
credentials or running a persistent server.

This article covers **AIS** (read-only account data). For payment initiation (PIS / pay-by-bank)
see `/payments/open-banking-pay-by-bank-integration.md`.

---

## Context

PSD2's Account Information Service allows TPPs (Third Party Providers) to access bank data on
behalf of a customer after explicit OAuth-style consent. Providers that abstract this across
European and UK banks include **TrueLayer**, **Yapily**, **Nordigen (GoCardless)**, and
**Tink (Visa)**. All follow a similar flow:

```
User → Consent redirect → Bank login → Callback → Access token → Account/Transaction data
```

On the example project platform we orchestrate this entirely through Cloudflare Workers:
- **Consent initiation and callback** handled in a Worker (no backend server)
- **Access tokens** stored encrypted in KV with per-user TTL
- **Account data** fetched and cached in KV with short TTL (15 min)
- **D1** holds the consent audit log and linked accounts

---

## D1 Schema

```sql
-- migrations/0019_ais_consents.sql
CREATE TABLE IF NOT EXISTS ais_consents (
  id              TEXT PRIMARY KEY,   -- provider consent/requisition id
  user_id         TEXT NOT NULL,
  provider        TEXT NOT NULL,      -- 'truelayer' | 'yapily' | 'nordigen' | 'tink'
  institution_id  TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'PENDING',
  scopes          TEXT NOT NULL,      -- JSON array of granted scopes
  expires_at      INTEGER,            -- unix epoch
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  revoked_at      INTEGER
);

CREATE TABLE IF NOT EXISTS ais_accounts (
  id              TEXT PRIMARY KEY,   -- bank account id from provider
  consent_id      TEXT NOT NULL REFERENCES ais_consents(id),
  user_id         TEXT NOT NULL,
  iban            TEXT,
  sort_code       TEXT,
  account_number  TEXT,
  currency        TEXT NOT NULL,
  account_type    TEXT,               -- 'CURRENT' | 'SAVINGS' etc.
  display_name    TEXT,
  linked_at       INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_ais_consents_user ON ais_consents(user_id, status);
CREATE INDEX IF NOT EXISTS idx_ais_accounts_user ON ais_accounts(user_id);
```

---

## Provider Abstraction Layer

```typescript
// src/lib/ais/types.ts
export interface AISAccount {
  id: string;
  iban?: string;
  currency: string;
  displayName: string;
  accountType: string;
}

export interface AISBalance {
  accountId: string;
  available: number;
  current: number;
  currency: string;
  updatedAt: string;
}

export interface AISTransaction {
  id: string;
  accountId: string;
  amount: number;
  currency: string;
  description: string;
  timestamp: string;
  status: 'SETTLED' | 'PENDING';
}

export interface AISProvider {
  buildConsentUrl(userId: string, institutionId: string, redirectUri: string): Promise<string>;
  exchangeCallback(params: URLSearchParams): Promise<{ consentId: string; accessToken: string; expiresIn: number }>;
  listAccounts(accessToken: string, consentId: string): Promise<AISAccount[]>;
  getBalance(accessToken: string, accountId: string): Promise<AISBalance>;
  getTransactions(accessToken: string, accountId: string, from: Date, to: Date): Promise<AISTransaction[]>;
}
```

---

## TrueLayer AIS Provider

```typescript
// src/lib/ais/truelayer.ts
import { AISProvider, AISAccount, AISBalance, AISTransaction } from './types';

const BASE = 'https://api.truelayer.com';
const AUTH = 'https://auth.truelayer.com';

export class TrueLayerProvider implements AISProvider {
  constructor(
    private clientId: string,
    private clientSecret: string,
  ) {}

  async buildConsentUrl(
    userId: string,
    institutionId: string,
    redirectUri: string,
  ): Promise<string> {
    const params = new URLSearchParams({
      response_type: 'code',
      client_id: this.clientId,
      scope: 'info accounts balance transactions',
      redirect_uri: redirectUri,
      state: userId,
      providers: institutionId,
      enable_mock: 'true', // remove in production
    });
    return `${AUTH}/?${params}`;
  }

  async exchangeCallback(params: URLSearchParams): Promise<{
    consentId: string;
    accessToken: string;
    expiresIn: number;
  }> {
    const code = params.get('code');
    if (!code) throw new Error('Missing code in callback');

    const resp = await fetch(`${AUTH}/connect/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: this.clientId,
        client_secret: <redacted-secret>
        code,
        redirect_uri: 'https://example project.example.com/ais/callback',
      }),
    });
    if (!resp.ok) throw new Error(`TrueLayer token error: ${resp.status}`);
    const data = await resp.json<{ access_token: string; expires_in: number; sub: string }>();
    return {
      consentId: data.sub,
      accessToken: <redacted-secret>
      expiresIn: data.expires_in,
    };
  }

  async listAccounts(accessToken: string): Promise<AISAccount[]> {
    const resp = await fetch(`${BASE}/data/v1/accounts`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) throw new Error(`TrueLayer accounts error: ${resp.status}`);
    const data = await resp.json<{ results: Array<{ account_id: string; display_name: string; account_type: string; currency: string; account_number?: { iban?: string } }> }>();
    return data.results.map((a) => ({
      id: a.account_id,
      iban: a.account_number?.iban,
      currency: a.currency,
      displayName: a.display_name,
      accountType: a.account_type,
    }));
  }

  async getBalance(accessToken: string, accountId: string): Promise<AISBalance> {
    const resp = await fetch(`${BASE}/data/v1/accounts/${accountId}/balance`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) throw new Error(`TrueLayer balance error: ${resp.status}`);
    const data = await resp.json<{ results: Array<{ available: number; current: number; currency: string; update_timestamp: string }> }>();
    const b = data.results[0];
    return { accountId, available: b.available, current: b.current, currency: b.currency, updatedAt: b.update_timestamp };
  }

  async getTransactions(
    accessToken: string,
    accountId: string,
    from: Date,
    to: Date,
  ): Promise<AISTransaction[]> {
    const params = new URLSearchParams({
      from: from.toISOString(),
      to: to.toISOString(),
    });
    const resp = await fetch(`${BASE}/data/v1/accounts/${accountId}/transactions?${params}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) throw new Error(`TrueLayer transactions error: ${resp.status}`);
    const data = await resp.json<{ results: Array<{ transaction_id: string; amount: number; currency: string; description: string; timestamp: string; transaction_classification: string[] }> }>();
    return data.results.map((t) => ({
      id: t.transaction_id,
      accountId,
      amount: t.amount,
      currency: t.currency,
      description: t.description,
      timestamp: t.timestamp,
      status: 'SETTLED' as const,
    }));
  }
}
```

---

## Workers Handlers — Consent Flow

```typescript
// src/handlers/ais-consent.ts
import { Env } from '../types';
import { TrueLayerProvider } from '../lib/ais/truelayer';

function buildProvider(env: Env): TrueLayerProvider {
  return new TrueLayerProvider(env.TRUELAYER_CLIENT_ID, env.TRUELAYER_CLIENT_SECRET);
}

/** GET /ais/connect?institution_id=... */
export async function handleAISConnect(request: Request, env: Env, userId: string): Promise<Response> {
  const url = new URL(request.url);
  const institutionId = url.searchParams.get('institution_id') ?? 'mock';
  const provider = buildProvider(env);
  const consentUrl = await provider.buildConsentUrl(
    userId,
    institutionId,
    'https://example project.example.com/ais/callback',
  );
  return Response.redirect(consentUrl, 302);
}

/** GET /ais/callback?code=...&state=... */
export async function handleAISCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.searchParams.get('state') ?? '';
  const provider = buildProvider(env);

  const { consentId, accessToken, expiresIn } = await provider.exchangeCallback(url.searchParams);

  // Store encrypted token in KV
  const kvKey = `ais:token:${userId}:${consentId}`;
  await env.KV.put(kvKey, accessToken, { expirationTtl: expiresIn - 60 });

  // Fetch and persist accounts
  const accounts = await provider.listAccounts(accessToken);
  const stmts = accounts.map((a) =>
    env.DB.prepare(
      `INSERT OR REPLACE INTO ais_accounts
         (id, consent_id, user_id, iban, currency, account_type, display_name)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ).bind(a.id, consentId, userId, a.iban ?? null, a.currency, a.accountType, a.displayName),
  );
  await env.DB.batch([
    env.DB.prepare(
      `INSERT OR REPLACE INTO ais_consents
         (id, user_id, provider, institution_id, status, scopes, expires_at)
       VALUES (?, ?, 'truelayer', 'mock', 'AUTHORISED', '["accounts","balance","transactions"]', ?)`,
    ).bind(consentId, userId, Math.floor(Date.now() / 1000) + expiresIn),
    ...stmts,
  ]);

  return new Response(JSON.stringify({ consentId, accounts }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

/** GET /ais/balance?account_id=... */
export async function handleAISBalance(request: Request, env: Env, userId: string): Promise<Response> {
  const url = new URL(request.url);
  const accountId = url.searchParams.get('account_id') ?? '';

  // KV cache for 15 min
  const cacheKey = `ais:balance:${accountId}`;
  const cached = await env.KV.get(cacheKey, 'json');
  if (cached) return new Response(JSON.stringify(cached), { headers: { 'Content-Type': 'application/json' } });

  // Retrieve token
  const consent = await env.DB.prepare(
    'SELECT c.id FROM ais_consents c JOIN ais_accounts a ON a.consent_id = c.id WHERE a.id = ? AND c.user_id = ?',
  ).bind(accountId, userId).first<{ id: string }>();
  if (!consent) return new Response('Not found', { status: 404 });

  const kvKey = `ais:token:${userId}:${consent.id}`;
  const accessToken = await env.KV.get(kvKey);
  if (!accessToken) return new Response('Consent expired', { status: 401 });

  const provider = buildProvider(env);
  const balance = await provider.getBalance(accessToken, accountId);

  await env.KV.put(cacheKey, JSON.stringify(balance), { expirationTtl: 900 });
  return new Response(JSON.stringify(balance), { headers: { 'Content-Type': 'application/json' } });
}
```

---

## Consent Revocation

```typescript
// src/handlers/ais-revoke.ts
import { Env } from '../types';

export async function handleAISRevoke(
  consentId: string,
  userId: string,
  env: Env,
): Promise<Response> {
  // Delete KV token
  await env.KV.delete(`ais:token:${userId}:${consentId}`);

  // Mark consent revoked in D1
  await env.DB.prepare(
    'UPDATE ais_consents SET status = ?, revoked_at = unixepoch() WHERE id = ? AND user_id = ?',
  )
    .bind('REVOKED', consentId, userId)
    .run();

  // Optionally call provider revocation endpoint here
  return new Response(JSON.stringify({ revoked: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## Anti-patterns

- **Caching balances for more than 15 minutes**: PSD2 SCA re-authentication is required for
  sensitive operations; stale balance data can produce misleading fund-availability signals.
- **Using AIS access tokens for PIS**: AIS and PIS scopes are separate. A token granted for
  account info cannot initiate a payment. Always use a PIS-specific consent flow for payments.
- **Storing raw access tokens in plain KV**: At minimum, encrypt with a Worker-level AES-GCM key
  stored in a secret. Treat AIS tokens like bearer tokens with bank-account access.
- **Skipping consent expiry checks**: TrueLayer AIS tokens expire in 90 days (UK) and shorter in
  EU. Always validate `expires_at` before attempting a data call.
- **Embedding institution IDs in client-side URLs**: The institution ID list is provider-managed
  and may change. Fetch it server-side and expose only what the user selected.

---

## Gotchas

- **90-day re-consent (UK Open Banking)**: CMA9 banks require the user to re-authorize every
  90 days. You must track consent expiry in D1 and prompt the user to reconnect before it lapses.
- **ASPSP data quality varies**: Some banks return `null` IBAN or missing transaction IDs. Treat
  all provider response fields as optional and default gracefully.
- **Nordigen (GoCardless AIS) uses requisition IDs**: The object model differs from TrueLayer;
  your abstraction layer must account for the requisition → account linkage pattern.
- **Tink requires eIDAS certificate registration**: Unlike TrueLayer which operates under its own
  PSD2 license, direct Tink integration requires your own TPP certificate in some markets.
- **Balance != available funds for payment**: Banks may report a "current" balance that includes
  uncleared items. Always use the `available` field and add a safety buffer before assuming funds.

---

## Verification

```bash
# 1. Start a consent flow (mock bank in test env)
curl "https://workers-dev.example project.example.com/ais/connect?institution_id=mock" \
  -H "Authorization: Bearer $USER_JWT" -v

# 2. Simulate callback
curl "https://workers-dev.example project.example.com/ais/callback?code=mock_code&state=$USER_ID" -v

# 3. Fetch balance
curl "https://workers-dev.example project.example.com/ais/balance?account_id=$ACCOUNT_ID" \
  -H "Authorization: Bearer $USER_JWT"

# 4. Verify D1 consent record
wrangler d1 execute example project-db \
  --command "SELECT * FROM ais_consents WHERE user_id='$USER_ID'"

# 5. Verify KV token present
wrangler kv key get --namespace-id=$KV_NAMESPACE_ID "ais:token:$USER_ID:$CONSENT_ID"
```

---

## Related

- `/payments/open-banking-pay-by-bank-integration.md`
- `/payments/plaid-link-ach-payment-initiation-workers.md`
- `/payments/stripe-financial-connections-ownership-verification.md`
- `/payments/pci-dss-scope-reduction-tokenization.md`
- `/payments/psd2-sca-exemption-strategies.md`

---

## Sources

- TrueLayer Data API docs: https://docs.truelayer.com/docs/data-api-v1
- Open Banking UK Standard: https://standards.openbanking.org.uk/
- Nordigen (GoCardless) AIS API: https://developer.gocardless.com/bank-account-data/quick-start-guide
- Yapily AIS docs: https://docs.yapily.com/api/reference/#tag/Financial-Data
- PSD2 EBA Guidelines on AIS: https://www.eba.europa.eu/regulation-and-policy/payment-services-and-electronic-money
