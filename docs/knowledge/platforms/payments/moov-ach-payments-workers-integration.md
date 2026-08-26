# Moov ACH Payments Integration with Cloudflare Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

You need ACH push payments (disbursements) or ACH pull payments (collections) to US bank accounts without the overhead of a full banking-as-a-service licence, Dwolla's deprecated Veem integration, or Stripe's ACH debit which requires a separate NACHA authorisation flow. Moov.io provides a developer-first ACH and card-issuing API that runs on modern REST/JSON. Cloudflare Workers is the integration layer for creating accounts, linking bank accounts, initiating transfers, and handling webhook events.

---

## Context

Moov is a regulated financial institution (licensed MSB and BaaS provider) that exposes ACH origination, card acceptance, and instant payouts through a REST API. The core objects are:

- **Account** — a Moov representation of a business or individual (maps to a Dwolla "Customer" or Stripe "Customer").
- **Bank Account** — a linked US bank account, verified via micro-deposits or Plaid instant verification.
- **Transfer** — an ACH debit (pull) or ACH credit (push) between two Moov accounts.
- **Webhook** — event delivery for transfer status changes (`transfer.created`, `transfer.completed`, `transfer.failed`).

Workers handles the API calls, stores transfer state in D1, and verifies Moov webhook signatures (HMAC-SHA256 over the raw body with a shared secret).

Moov uses OAuth2 client credentials for API authentication. Tokens expire; Workers must cache and refresh them in KV.

---

## 1. OAuth2 Token Management in KV

```typescript
// src/lib/moov-auth.ts
export interface Env {
  KV: KVNamespace;
  MOOV_CLIENT_ID: string;
  MOOV_CLIENT_SECRET: string;
  MOOV_ACCOUNT_ID: string; // your facilitator account ID
}

const TOKEN_KEY = 'moov:access_token';
const MOOV_TOKEN_URL = 'https://api.moov.io/oauth2/token';

export async function getMoovToken(env: Env): Promise<string> {
  const cached = await env.KV.get(TOKEN_KEY);
  if (cached) return cached;

  const body = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: env.MOOV_CLIENT_ID,
    client_secret: env.MOOV_CLIENT_SECRET,
    scope: '/accounts.write /transfers.write /bank-accounts.write',
  });

  const resp = await fetch(MOOV_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!resp.ok) throw new Error(`Moov token error: ${resp.status} ${await resp.text()}`);

  const data = await resp.json<{ access_token: string; expires_in: number }>();

  // Cache with 60 s buffer before expiry
  await env.KV.put(TOKEN_KEY, data.access_token, {
    expirationTtl: Math.max(data.expires_in - 60, 60),
  });

  return data.access_token;
}

export function moovHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'X-Account-ID': '', // set per-request if scoped to a connected account
  };
}
```

---

## 2. Creating a Moov Account for a Payee

```typescript
// src/lib/moov-accounts.ts
import { getMoovToken } from './moov-auth';
import type { Env } from '../types';

const MOOV_API = 'https://api.moov.io';

export interface MoovAccountInput {
  email: string;
  displayName: string;
  taxID?: string; // EIN or SSN for business / individual
}

export interface MoovAccount {
  accountID: string;
  accountType: string;
  displayName: string;
}

export async function createMoovAccount(env: Env, input: MoovAccountInput): Promise<MoovAccount> {
  const token = await getMoovToken(env);

  const resp = await fetch(`${MOOV_API}/accounts`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      accountType: 'individual',
      profile: {
        individual: {
          name: { firstName: input.displayName.split(' ')[0], lastName: input.displayName.split(' ').slice(1).join(' ') || 'Unknown' },
          email: input.email,
        },
      },
      capabilities: ['transfers'],
    }),
  });

  if (!resp.ok) throw new Error(`Moov create account error: ${resp.status} ${await resp.text()}`);
  return resp.json<MoovAccount>();
}
```

---

## 3. Linking a Bank Account via Plaid Token Exchange

```typescript
// src/lib/moov-bank-accounts.ts
import { getMoovToken } from './moov-auth';
import type { Env } from '../types';

const MOOV_API = 'https://api.moov.io';

/**
 * Links a bank account to a Moov account using a Plaid public token
 * (Moov supports the Plaid token exchange natively).
 */
export async function linkBankAccountPlaid(
  env: Env,
  moovAccountId: string,
  plaidPublicToken: string,
  plaidAccountId: string
): Promise<{ bankAccountID: string; status: string }> {
  const token = await getMoovToken(env);

  const resp = await fetch(`${MOOV_API}/accounts/${moovAccountId}/bank-accounts`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      plaid: {
        publicToken: plaidPublicToken,
        accountId: plaidAccountId,
      },
    }),
  });

  if (!resp.ok) throw new Error(`Moov link bank error: ${resp.status} ${await resp.text()}`);
  return resp.json<{ bankAccountID: string; status: string }>();
}
```

---

## 4. Initiating an ACH Transfer

```typescript
// src/lib/moov-transfers.ts
import { getMoovToken } from './moov-auth';
import type { Env } from '../types';

const MOOV_API = 'https://api.moov.io';

export interface TransferResult {
  transferID: string;
  status: 'created' | 'pending' | 'completed' | 'failed' | 'reversed';
  createdOn: string;
}

/**
 * Initiates an ACH credit (push) from your platform account to a payee's bank account.
 * Use ACH debit (pull) for collections by swapping source/destination.
 */
export async function initiateAchCredit(
  env: Env,
  opts: {
    sourceAccountId: string;   // your facilitator Moov account
    sourceBankAccountId: string;
    destinationAccountId: string; // payee Moov account
    destinationBankAccountId: string;
    amountCents: number;
    currency: string;
    description: string;       // NACHA company entry description (max 10 chars)
    idempotencyKey: string;
  }
): Promise<TransferResult> {
  const token = await getMoovToken(env);

  const resp = await fetch(`${MOOV_API}/transfers`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-Idempotency-Key': opts.idempotencyKey,
    },
    body: JSON.stringify({
      source: {
        accountID: opts.sourceAccountId,
        bankAccountID: opts.sourceBankAccountId,
        paymentMethodType: 'ach-debit-collect', // debit source to push funds
      },
      destination: {
        accountID: opts.destinationAccountId,
        bankAccountID: opts.destinationBankAccountId,
        paymentMethodType: 'ach-credit-standard',
      },
      amount: { value: opts.amountCents, currency: opts.currency.toUpperCase() },
      description: opts.description.slice(0, 10),
    }),
  });

  if (!resp.ok) throw new Error(`Moov transfer error: ${resp.status} ${await resp.text()}`);
  return resp.json<TransferResult>();
}
```

---

## 5. Webhook Signature Verification and D1 State Persistence

```typescript
// src/handlers/moov-webhook.ts
import type { Env } from '../types';

export async function handleMoovWebhook(request: Request, env: Env): Promise<Response> {
  const rawBody = await request.text();
  const signature = request.headers.get('Moov-Signature') ?? '';

  // HMAC-SHA256 verification
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.MOOV_WEBHOOK_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify']
  );

  const sigBytes = hexToBytes(signature);
  const bodyBytes = new TextEncoder().encode(rawBody);
  const valid = await crypto.subtle.verify('HMAC', key, sigBytes, bodyBytes);
  if (!valid) return new Response('Invalid signature', { status: 401 });

  const event = JSON.parse(rawBody) as {
    eventID: string;
    eventType: string;
    data: { transfer?: { transferID: string; status: string } };
  };

  // Idempotency check
  const already = await env.DB
    .prepare(`SELECT id FROM moov_webhook_events WHERE event_id = ?`)
    .bind(event.eventID)
    .first();
  if (already) return new Response('already_processed', { status: 200 });

  await env.DB
    .prepare(`INSERT INTO moov_webhook_events (event_id, event_type, raw_payload) VALUES (?, ?, ?)`)
    .bind(event.eventID, event.eventType, rawBody)
    .run();

  if (event.eventType === 'transfer.completed' && event.data.transfer) {
    await env.DB
      .prepare(`UPDATE moov_transfers SET status = 'completed' WHERE transfer_id = ?`)
      .bind(event.data.transfer.transferID)
      .run();
  }

  if (event.eventType === 'transfer.failed' && event.data.transfer) {
    await env.DB
      .prepare(`UPDATE moov_transfers SET status = 'failed' WHERE transfer_id = ?`)
      .bind(event.data.transfer.transferID)
      .run();
  }

  return new Response('ok');
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}
```

---

## 6. D1 Transfer State Schema

```sql
-- migrations/0003_moov_transfers.sql
CREATE TABLE IF NOT EXISTS moov_transfers (
  transfer_id   TEXT PRIMARY KEY,
  order_id      TEXT NOT NULL,
  amount_cents  INTEGER NOT NULL,
  currency      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'created',
  created_at    INTEGER NOT NULL DEFAULT (UNIXEPOCH()),
  completed_at  INTEGER
);

CREATE TABLE IF NOT EXISTS moov_webhook_events (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  event_id     TEXT NOT NULL UNIQUE,
  event_type   TEXT NOT NULL,
  raw_payload  TEXT NOT NULL,
  received_at  INTEGER NOT NULL DEFAULT (UNIXEPOCH())
);
```

---

## Anti-patterns

- **Hardcoding the OAuth2 token** — Moov tokens expire (typically 1 hour). Always cache in KV with TTL and refresh on expiry.
- **Omitting the idempotency key on transfer creation** — ACH transfers are high-value; a retry without an idempotency key can result in duplicate disbursements.
- **Using `ach-credit-same-day` for all transfers** — Same-Day ACH carries a surcharge and is not always necessary. Default to `ach-credit-standard` (1–2 business days) unless the use case requires it.
- **Processing webhook events without idempotency** — Moov retries unacknowledged webhooks; the D1 `event_id` unique index prevents double-processing.

---

## Gotchas

- Moov's `description` field (company entry description in the NACHA file) is capped at 10 characters. Values longer than 10 are silently truncated by some receiving banks, causing reconciliation confusion.
- ACH returns (R01–R29) arrive as `transfer.failed` webhook events 2–5 business days after settlement. Your D1 schema must handle late status reversals.
- Moov sandbox (`sandbox.moov.io`) uses a different base URL than production (`api.moov.io`). Keep it in an env var, never hardcoded.
- `X-Idempotency-Key` on the Moov API is required for transfers and is a string up to 100 characters. A UUID v4 per transfer attempt is the safe default.
- Bank account verification via micro-deposits takes 1–2 business days. If your flow requires immediate transfer capability, use Plaid instant verification instead.

---

## Verification

```bash
# Create a sandbox account
curl -X POST https://sandbox.moov.io/accounts \
  -H "Authorization: Bearer $MOOV_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"accountType":"individual","profile":{"individual":{"name":{"firstName":"Test","lastName":"User"},"email":"test@example.com"}},"capabilities":["transfers"]}'

# Initiate a test transfer (sandbox auto-completes)
curl -X POST https://sandbox.moov.io/transfers \
  -H "Authorization: Bearer $MOOV_TOKEN" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -d '{...}'

# Check D1 for status updates after webhook delivery
wrangler d1 execute YOUR_DB --command \
  "SELECT transfer_id, status FROM moov_transfers ORDER BY created_at DESC LIMIT 10"
```

---

## Related

- `dwolla-ach-transfer-api-workers-d1.md`
- `ach-debit-pull-payment-orchestration-workers-d1.md`
- `plaid-link-ach-payment-initiation-workers.md`
- `idempotency-keys-payment-apis.md`
- `fednow-instant-payments-integration.md`

---

## Sources

- Moov API reference: https://docs.moov.io/api/
- Moov ACH transfers guide: https://docs.moov.io/guides/money-movement/ach/
- Moov OAuth2 authentication: https://docs.moov.io/guides/get-started/authentication/
- NACHA ACH return codes: https://www.nacha.org/content/ach-return-codes
