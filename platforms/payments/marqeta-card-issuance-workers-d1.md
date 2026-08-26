# Marqeta Card Issuance and Spend Controls via Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to issue virtual or physical Visa/Mastercard cards to users or employees — for expense
management, earned-wage access, B2B vendor payments, or creator payouts — and control spend limits,
MCC categories, and merchant allowlists in real-time from a Cloudflare Worker without running a
persistent backend.

---

## Context

Marqeta is an open card issuing platform that lets programs create cards, fund them from a JIT
(Just-in-Time) funding source, and intercept every authorization with a real-time webhook decision.
The core model:

```
Card Program  →  Card Products  →  Cards (virtual/physical)
Card User  →  User Token  →  Card Token  →  Funding Source
Authorization  →  Marqeta JIT webhook  →  Worker approves/declines  →  Network response
```

On the example project platform Workers handle:
- **Card lifecycle** (create, suspend, terminate)
- **JIT funding webhooks** (approve/decline in <1 s)
- **Transaction event webhooks** (write to D1 for the spend ledger)
- **Velocity controls** via D1 counter queries

All card tokens and sensitive PAN data stay within Marqeta's PCI DSS-compliant vault. We only
store non-sensitive tokens and metadata in D1.

---

## D1 Schema

```sql
-- migrations/0021_marqeta_cards.sql
CREATE TABLE IF NOT EXISTS marqeta_cards (
  token         TEXT PRIMARY KEY,           -- Marqeta card token (uuid)
  user_token    TEXT NOT NULL,
  program_type  TEXT NOT NULL,              -- 'virtual' | 'physical'
  state         TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | SUSPENDED | TERMINATED
  last_four     TEXT,
  expiration    TEXT,                       -- MM/YY
  card_product  TEXT NOT NULL,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS marqeta_transactions (
  token           TEXT PRIMARY KEY,
  card_token      TEXT NOT NULL,
  user_token      TEXT NOT NULL,
  type            TEXT NOT NULL,            -- authorization | clearing | refund | dispute
  amount          INTEGER NOT NULL,         -- in cents
  currency        TEXT NOT NULL DEFAULT 'USD',
  merchant_name   TEXT,
  merchant_mcc    TEXT,
  state           TEXT NOT NULL,            -- PENDING | COMPLETION | DECLINED | REVERSED
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS marqeta_spend_controls (
  card_token      TEXT PRIMARY KEY,
  daily_limit     INTEGER,                  -- cents; NULL = no limit
  monthly_limit   INTEGER,
  allowed_mccs    TEXT,                     -- JSON array of allowed MCC codes
  blocked_mccs    TEXT,                     -- JSON array of blocked MCC codes
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_txn_card ON marqeta_transactions(card_token, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_txn_user ON marqeta_transactions(user_token, created_at DESC);
```

---

## Marqeta API Client

```typescript
// src/lib/marqeta.ts
import { Env } from '../types';

const MARQETA_BASE = 'https://sandbox-api.marqeta.com/v3'; // swap to api.marqeta.com in prod

function marqetaHeaders(env: Env): Headers {
  const credentials = btoa(`${env.MARQETA_APPLICATION_TOKEN}:${env.MARQETA_ADMIN_ACCESS_TOKEN}`);
  return new Headers({
    Authorization: `Basic ${credentials}`,
    'Content-Type': 'application/json',
    Accept: 'application/json',
  });
}

export interface MarqetaCard {
  token: string;
  user_token: string;
  card_product_token: string;
  state: string;
  last_four: string;
  expiration: string;
}

export async function createVirtualCard(
  userToken: string,
  cardProductToken: string,
  env: Env,
): Promise<MarqetaCard> {
  const body = {
    user_token: userToken,
    card_product_token: cardProductToken,
  };
  const resp = await fetch(`${MARQETA_BASE}/cards`, {
    method: 'POST',
    headers: marqetaHeaders(env),
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json<{ error_message: string }>();
    throw new Error(`Marqeta card create error: ${err.error_message}`);
  }
  return resp.json<MarqetaCard>();
}

export async function transitionCard(
  cardToken: string,
  state: 'ACTIVE' | 'SUSPENDED' | 'TERMINATED',
  env: Env,
): Promise<void> {
  const body = {
    card_token: cardToken,
    state,
    channel: 'API',
    reason_code: '00',
  };
  const resp = await fetch(`${MARQETA_BASE}/cardtransitions`, {
    method: 'POST',
    headers: marqetaHeaders(env),
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json<{ error_message: string }>();
    throw new Error(`Marqeta transition error: ${err.error_message}`);
  }
}

export async function revealPan(
  cardToken: string,
  env: Env,
): Promise<{ pan: string; cvv_number: string; expiration: string }> {
  // Returns full PAN — only use server-side, never pass to client
  const resp = await fetch(`${MARQETA_BASE}/cards/${cardToken}/showpan`, {
    headers: marqetaHeaders(env),
  });
  if (!resp.ok) throw new Error(`Marqeta showpan error: ${resp.status}`);
  return resp.json<{ pan: string; cvv_number: string; expiration: string }>();
}
```

---

## Card Lifecycle Worker

```typescript
// src/handlers/marqeta-cards.ts
import { Env } from '../types';
import { createVirtualCard, transitionCard } from '../lib/marqeta';

export async function handleCreateCard(request: Request, env: Env, userId: string): Promise<Response> {
  const { cardProductToken } = await request.json<{ cardProductToken: string }>();

  // Map internal userId to Marqeta user token (assumed pre-created during onboarding)
  const userRow = await env.DB.prepare(
    'SELECT marqeta_user_token FROM users WHERE id = ?',
  )
    .bind(userId)
    .first<{ marqeta_user_token: string }>();

  if (!userRow?.marqeta_user_token) {
    return new Response('User not found in Marqeta', { status: 404 });
  }

  const card = await createVirtualCard(userRow.marqeta_user_token, cardProductToken, env);

  await env.DB.prepare(
    `INSERT INTO marqeta_cards
       (token, user_token, program_type, state, last_four, expiration, card_product)
     VALUES (?, ?, 'virtual', ?, ?, ?, ?)`,
  )
    .bind(card.token, card.user_token, card.state, card.last_four, card.expiration, cardProductToken)
    .run();

  // Insert default spend controls
  await env.DB.prepare(
    'INSERT OR IGNORE INTO marqeta_spend_controls (card_token, daily_limit, monthly_limit) VALUES (?, ?, ?)',
  )
    .bind(card.token, 10000, 100000) // $100/day, $1000/month default
    .run();

  return new Response(
    JSON.stringify({ token: card.token, lastFour: card.last_four, expiration: card.expiration }),
    { status: 201, headers: { 'Content-Type': 'application/json' } },
  );
}

export async function handleSuspendCard(
  cardToken: string,
  userId: string,
  env: Env,
): Promise<Response> {
  const ownership = await env.DB.prepare(
    'SELECT 1 FROM marqeta_cards WHERE token = ? AND user_token = (SELECT marqeta_user_token FROM users WHERE id = ?)',
  )
    .bind(cardToken, userId)
    .first();
  if (!ownership) return new Response('Forbidden', { status: 403 });

  await transitionCard(cardToken, 'SUSPENDED', env);
  await env.DB.prepare(
    'UPDATE marqeta_cards SET state = ?, updated_at = unixepoch() WHERE token = ?',
  )
    .bind('SUSPENDED', cardToken)
    .run();

  return new Response(JSON.stringify({ suspended: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## JIT Funding Webhook — Real-time Authorization

```typescript
// src/handlers/marqeta-jit.ts
import { Env } from '../types';

interface JITAuthorizationEvent {
  type: 'jit_funding';
  token: string;
  card_token: string;
  user_token: string;
  amount: number;
  currency_code: string;
  merchant: { mcc: string; name: string };
  jit_funding: { method: string; user_token: string; token: string };
}

export async function handleJITFunding(request: Request, env: Env): Promise<Response> {
  const body = await request.json<JITAuthorizationEvent>();
  const { card_token, user_token, amount, merchant } = body;

  // 1. Check spend controls
  const controls = await env.DB.prepare(
    'SELECT daily_limit, monthly_limit, allowed_mccs, blocked_mccs FROM marqeta_spend_controls WHERE card_token = ?',
  )
    .bind(card_token)
    .first<{ daily_limit: number; monthly_limit: number; allowed_mccs: string; blocked_mccs: string }>();

  // 2. MCC block check
  if (controls?.blocked_mccs) {
    const blocked: string[] = JSON.parse(controls.blocked_mccs);
    if (blocked.includes(merchant.mcc)) {
      return approvalResponse(body.token, false, 'INSUFFICIENT_FUNDS');
    }
  }

  // 3. Daily velocity check
  if (controls?.daily_limit != null) {
    const today = Math.floor(Date.now() / 1000) - 86400;
    const dailySpend = await env.DB.prepare(
      `SELECT COALESCE(SUM(amount), 0) AS total
       FROM marqeta_transactions
       WHERE card_token = ? AND state = 'PENDING' AND created_at > ?`,
    )
      .bind(card_token, today)
      .first<{ total: number }>();
    const used = dailySpend?.total ?? 0;
    if (used + amount > controls.daily_limit) {
      return approvalResponse(body.token, false, 'INSUFFICIENT_FUNDS');
    }
  }

  // 4. Approved — JIT funding must return synchronously within 1 second
  return approvalResponse(body.token, true);
}

function approvalResponse(
  token: string,
  approved: boolean,
  declineReason?: string,
): Response {
  const body = approved
    ? { jit_funding: { token, method: 'pgfs.authorization', acting_user_token: token } }
    : { jit_funding: { token, method: 'pgfs.authorization', acting_user_token: token }, is_declined: true, decline_reason: declineReason };

  return new Response(JSON.stringify(body), {
    status: approved ? 200 : 402,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## Transaction Event Webhook

```typescript
// src/handlers/marqeta-transactions.ts
import { Env } from '../types';

interface TransactionEvent {
  type: string; // authorization | clearing | refund
  token: string;
  card_token: string;
  user_token: string;
  amount: number;
  currency_code: string;
  merchant: { name: string; mcc: string };
  state: string;
}

export async function handleTransactionWebhook(request: Request, env: Env): Promise<Response> {
  // Marqeta signs webhooks with Basic Auth on the incoming request
  const authHeader = request.headers.get('Authorization') ?? '';
  const expectedAuth = `Basic ${btoa(`${env.MARQETA_WEBHOOK_USERNAME}:${env.MARQETA_WEBHOOK_PASSWORD}`)}`;
  if (authHeader !== expectedAuth) return new Response('Unauthorized', { status: 401 });

  const events = await request.json<TransactionEvent[]>();

  const stmts = events.map((e) =>
    env.DB.prepare(
      `INSERT INTO marqeta_transactions
         (token, card_token, user_token, type, amount, currency, merchant_name, merchant_mcc, state)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(token) DO UPDATE SET state = excluded.state`,
    ).bind(e.token, e.card_token, e.user_token, e.type, e.amount, e.currency_code, e.merchant.name, e.merchant.mcc, e.state),
  );

  await env.DB.batch(stmts);
  return new Response('OK', { status: 200 });
}
```

---

## Anti-patterns

- **Performing async D1 writes inside the JIT funding handler before responding**: Marqeta requires
  a JIT response within 1 second (hard SLA). Write to D1 *after* returning the approval response
  using `ctx.waitUntil(writeToD1(...))`.
- **Storing full PAN or CVV in D1**: Marqeta's `showpan` API returns the PAN for display to the
  user. Never store it in D1 or KV. Only store non-sensitive tokens and last four digits.
- **Creating Marqeta users on every card request**: Marqeta user tokens are persistent per real
  user. Create the Marqeta user once at onboarding and store the token in your users table.
- **Ignoring the `clearing` event**: The initial `authorization` is a hold. The actual debit is
  the `clearing` event. Both must be tracked to maintain an accurate spend ledger.
- **Setting daily limits only in D1 without mirroring to Marqeta velocity controls**: D1 controls
  work only when every authorization passes through your JIT endpoint. If Marqeta routes around
  your JIT (e.g., offline transactions), the D1 check is bypassed. Use Marqeta's built-in velocity
  controls as an additional safety layer.

---

## Gotchas

- **JIT timeout = hard decline**: If your Worker exceeds Marqeta's authorization timeout (~1 s),
  the transaction is declined automatically. Keep JIT handlers lean; offload D1 writes to
  `ctx.waitUntil`.
- **Sandbox vs production credential format**: Sandbox uses `sandbox-api.marqeta.com/v3`;
  production uses `api.marqeta.com/v3`. The credential format (Basic auth with application token
  and admin access token) is the same in both environments.
- **Marqeta webhooks send arrays**: The transaction webhook posts a JSON array of events, not a
  single object. Always parse as `TransactionEvent[]`.
- **Card product must be pre-configured in Marqeta Dashboard**: You cannot create a card product
  via API; it must be set up by your Marqeta implementation manager. Store the card product token
  as an environment secret.
- **Tokenization for Apple Pay/Google Pay**: Marqeta supports push provisioning to wallets, but
  this requires an additional SDK (iOS/Android) and Marqeta support enablement. Not available by
  default on new programs.

---

## Verification

```bash
# 1. Create a test card via API
curl -X POST https://sandbox-api.marqeta.com/v3/cards \
  -u "$MARQETA_APPLICATION_TOKEN:$MARQETA_ADMIN_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_token":"user_test_001","card_product_token":"my_card_product"}'

# 2. Simulate a JIT authorization
curl -X POST https://sandbox-api.marqeta.com/v3/simulate/authorization \
  -u "$MARQETA_APPLICATION_TOKEN:$MARQETA_ADMIN_ACCESS_TOKEN" \
  -d '{"card_token":"$CARD_TOKEN","amount":1000,"mid":"merchant_001"}'

# 3. Verify transaction in D1
wrangler d1 execute example project-db \
  --command "SELECT * FROM marqeta_transactions WHERE card_token='$CARD_TOKEN' ORDER BY created_at DESC LIMIT 5"

# 4. Check spend controls
wrangler d1 execute example project-db \
  --command "SELECT * FROM marqeta_spend_controls WHERE card_token='$CARD_TOKEN'"
```

---

## Related

- `/payments/stripe-issuing-card-spend-controls-workers.md`
- `/payments/stripe-issuing-real-time-authorization-webhooks.md`
- `/payments/network-tokenization-visa-mastercard.md`
- `/payments/payment-fraud-detection-velocity-checks.md`
- `/payments/pci-dss-scope-reduction-tokenization.md`

---

## Sources

- Marqeta Core API Reference: https://www.marqeta.com/docs/core-api
- Marqeta JIT Funding Guide: https://www.marqeta.com/docs/core-api/just-in-time-funding
- Marqeta Card Lifecycle: https://www.marqeta.com/docs/core-api/card-transitions
- Marqeta Webhooks: https://www.marqeta.com/docs/core-api/event-types
- Cloudflare Workers D1: https://developers.cloudflare.com/d1/
