# Revolut Business API Payouts on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to programmatically initiate payouts to suppliers, contractors, or end-users from a Revolut Business account via a Cloudflare Worker, without running a dedicated server. The payout must be idempotent, auditable, and resilient to network failures.

## Context

Revolut Business exposes a REST API (v2) for initiating transfers between Revolut Business accounts, external bank accounts, and counterparties. Workers act as the payout orchestration layer: receiving payout requests, checking balance, creating counterparties if needed, initiating transfers, and persisting state to D1. Revolut uses OAuth 2.0 (JWT assertion) for machine-to-machine auth rather than long-lived API keys.

---

## 1. OAuth 2.0 JWT Bearer Token Acquisition

Revolut Business API v2 requires a signed JWT bearer token exchanged for an access token.

```typescript
// src/revolut-auth.ts
import { SignJWT, importPKCS8 } from 'jose';

interface Env {
  REVOLUT_CLIENT_ID: string;
  REVOLUT_PRIVATE_KEY: string; // PEM stored in Workers Secret
  REVOLUT_TOKEN_URL: string;   // https://auth.revolut.com/token
}

async function getRevolutAccessToken(env: Env): Promise<string> {
  const privateKey = await importPKCS8(env.REVOLUT_PRIVATE_KEY, 'RS256');

  const clientAssertion = await new SignJWT({})
    .setProtectedHeader({ alg: 'RS256' })
    .setIssuer(env.REVOLUT_CLIENT_ID)
    .setSubject(env.REVOLUT_CLIENT_ID)
    .setAudience(env.REVOLUT_TOKEN_URL)
    .setIssuedAt()
    .setExpirationTime('60s')
    .sign(privateKey);

  const body = new URLSearchParams({
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    client_assertion_type:
      'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
    client_assertion: clientAssertion,
  });

  const res = await fetch(env.REVOLUT_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) throw new Error(`Revolut token error: ${await res.text()}`);
  const { access_token } = await res.json<{ access_token: string }>();
  return access_token;
}

export { getRevolutAccessToken };
```

---

## 2. Creating or Fetching a Counterparty

Before sending a payout, the recipient must be a registered counterparty.

```typescript
// src/revolut-counterparty.ts
async function ensureCounterparty(
  token: string,
  recipient: { name: string; iban: string; bic: string }
): Promise<string> {
  const searchRes = await fetch(
    `https://b2b.revolut.com/api/2.0/counterparties?name=${encodeURIComponent(recipient.name)}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const list = await searchRes.json<Array<{ id: string; name: string }>>();
  const existing = list.find((c) => c.name === recipient.name);
  if (existing) return existing.id;

  const createRes = await fetch(
    'https://b2b.revolut.com/api/2.0/counterparty',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        company_name: recipient.name,
        bank_country: 'GB',
        currency: 'GBP',
        iban: recipient.iban,
        bic: recipient.bic,
      }),
    }
  );

  if (!createRes.ok)
    throw new Error(`Create counterparty failed: ${await createRes.text()}`);
  const { id } = await createRes.json<{ id: string }>();
  return id;
}

export { ensureCounterparty };
```

---

## 3. Initiating an Idempotent Payout Transfer

```typescript
// src/revolut-payout.ts
interface PayoutRequest {
  requestId: string; // used as Revolut request_id for idempotency
  counterpartyId: string;
  accountId: string; // Revolut source account UUID
  amount: number;    // in minor units (pence, cents)
  currency: string;  // ISO 4217
  reference: string;
}

interface TransferResponse {
  id: string;
  state: 'created' | 'pending' | 'completed' | 'failed' | 'declined' | 'reverted';
}

async function initiateTransfer(
  token: string,
  payout: PayoutRequest
): Promise<TransferResponse> {
  const res = await fetch('https://b2b.revolut.com/api/2.0/transfer', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': payout.requestId,
    },
    body: JSON.stringify({
      request_id: payout.requestId,
      source_account_id: payout.accountId,
      target_account_id: payout.counterpartyId,
      amount: payout.amount / 100, // Revolut v2 uses decimal amounts
      currency: payout.currency,
      reference: payout.reference,
    }),
  });

  if (!res.ok) throw new Error(`Transfer failed: ${await res.text()}`);
  return res.json<TransferResponse>();
}

export { initiateTransfer };
```

---

## 4. Worker Entry Point with D1 Audit Log

```typescript
// src/index.ts
import { getRevolutAccessToken } from './revolut-auth';
import { ensureCounterparty } from './revolut-counterparty';
import { initiateTransfer } from './revolut-payout';

interface Env {
  DB: D1Database;
  REVOLUT_CLIENT_ID: string;
  REVOLUT_PRIVATE_KEY: string;
  REVOLUT_TOKEN_URL: string;
  REVOLUT_ACCOUNT_ID: string;
  PAYOUT_SIGNING_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/payout')
      return new Response('Not found', { status: 404 });

    const sig = request.headers.get('X-Payout-Signature');
    if (!sig || sig !== env.PAYOUT_SIGNING_SECRET)
      return new Response('Unauthorized', { status: 401 });

    const body = await request.json<{
      requestId: string;
      amount: number;
      currency: string;
      reference: string;
      recipient: { name: string; iban: string; bic: string };
    }>();

    // Deduplication check
    const existing = await env.DB.prepare(
      'SELECT state FROM revolut_payouts WHERE request_id = ?'
    ).bind(body.requestId).first<{ state: string }>();

    if (existing) return Response.json({ status: existing.state });

    const token = await getRevolutAccessToken(env);
    const counterpartyId = await ensureCounterparty(token, body.recipient);
    const transfer = await initiateTransfer(token, {
      requestId: body.requestId,
      counterpartyId,
      accountId: env.REVOLUT_ACCOUNT_ID,
      amount: body.amount,
      currency: body.currency,
      reference: body.reference,
    });

    await env.DB.prepare(
      `INSERT INTO revolut_payouts (request_id, transfer_id, state, created_at)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP)`
    ).bind(body.requestId, transfer.id, transfer.state).run();

    return Response.json({ transferId: transfer.id, state: transfer.state });
  },
};
```

---

## 5. Polling Transfer State via Scheduled Worker

```typescript
// src/poller.ts (cron trigger)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const pending = await env.DB.prepare(
      `SELECT request_id, transfer_id FROM revolut_payouts
       WHERE state IN ('created','pending') LIMIT 50`
    ).all<{ request_id: string; transfer_id: string }>();

    const token = await getRevolutAccessToken(env);

    for (const row of pending.results) {
      const res = await fetch(
        `https://b2b.revolut.com/api/2.0/transaction/${row.transfer_id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const { state } = await res.json<{ state: string }>();
      await env.DB.prepare(
        'UPDATE revolut_payouts SET state = ? WHERE transfer_id = ?'
      ).bind(state, row.transfer_id).run();
    }
  },
};
```

---

## Anti-patterns

- **Storing the access token in KV without TTL** — Revolut tokens are short-lived (40 min); cache with `expirationTtl: 2200` or re-fetch per invocation for low-volume Workers.
- **Sending decimal amounts directly** — Revolut v2 uses decimal currency values (e.g., `10.50`), not minor units. Dividing by 100 before sending is required.
- **Skipping `Idempotency-Key` header** — Without it, duplicate network retries create double payouts.
- **Creating counterparties on every request** — Always search for an existing counterparty first; Revolut enforces uniqueness constraints and returns 422 on duplicates.

## Gotchas

- Revolut sandbox (`sandbox-b2b.revolut.com`) uses a separate OAuth endpoint; the client ID and keys differ from production.
- Transfer `state: 'pending'` is not terminal — always poll or handle the `TransactionStateChanged` webhook before marking a payout done.
- JWT `aud` must match the token endpoint URL exactly, including the scheme.
- The `source_account_id` must be the UUID of your Revolut Business account, not the IBAN.

## Verification

```bash
# Smoke-test the payout Worker locally with Miniflare
wrangler dev --local

curl -X POST http://localhost:8787/payout \
  -H 'Content-Type: application/json' \
  -H 'X-Payout-Signature: <secret>' \
  -d '{"requestId":"test-001","amount":1000,"currency":"GBP","reference":"INV-001","recipient":{"name":"Acme Ltd","iban":"GB29NWBK60161331926819","bic":"NWBKGB2L"}}'

# Confirm D1 row was written
wrangler d1 execute <DB_NAME> --command "SELECT * FROM revolut_payouts WHERE request_id='test-001'"
```

## Related

- `wise-payouts-api-mass-payouts-workers.md`
- `payment-retry-exponential-backoff-cloudflare-queues.md`
- `idempotency-keys-payment-apis.md`
- `payment-audit-logging.md`

## Sources

- https://developer.revolut.com/docs/business/business-api
- https://developer.revolut.com/docs/business/transfers
- https://developer.revolut.com/docs/business/authentication
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-events/
