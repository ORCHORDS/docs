# Circle USDC Programmable Payments on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to accept, send, or convert USDC stablecoin payments through Circle's Programmable
Wallets or Payments API from a Cloudflare Workers edge backend — including generating
deposit addresses, verifying on-chain settlement, initiating USDC payouts to end-users,
and converting USDC to fiat via Circle's API — without running a dedicated server.

## Context

Circle's USDC infrastructure spans multiple blockchains (Ethereum, Solana, Polygon, Arbitrum,
Base). Circle provides two relevant API surfaces for payments:

- **Payments API** — accepts card payments and settles in USDC. Covered here only briefly
  since card-to-USDC is mostly a B2B flow.
- **Programmable Wallets API** — creates custodial wallets per user, generates deposit
  addresses, tracks balances, and initiates transfers. This is the primary focus.

Circle webhooks use a notification structure similar to AWS SNS (wrapped in a JSON envelope
with a `notificationType` field). Verification uses the Circle-provided public key to verify
an RSA or ECDSA signature on the envelope; in practice most implementations verify the
`subscriptionConfirmation` challenge and then check `message.status` fields for finality.

Workers serve as the custodian backend, D1 stores wallet metadata, and KV caches the
Circle public key used for webhook verification.

---

## 1. Creating a Programmable Wallet for a User

```typescript
// src/circle/wallet-create.ts
interface CircleWalletResponse {
  data: {
    wallets: Array<{
      walletId: string;
      entityId: string;
      type: string;
      name: string;
    }>;
  };
}

export async function createUserWallet(
  userId: string,
  env: Env
): Promise<string> {
  const idempotencyKey = crypto.randomUUID();

  const res = await fetch('https://api.circle.com/v1/w3s/wallets', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CIRCLE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      idempotencyKey,
      entitySecretCiphertext: env.CIRCLE_ENTITY_SECRET_CIPHERTEXT,
      wallets: [
        {
          userId,
          name: `user-${userId}`,
          refId: userId,
          metadata: [{ name: 'userId', value: userId }],
        },
      ],
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Circle wallet create failed: ${res.status} ${err}`);
  }

  const data = await res.json<CircleWalletResponse>();
  const walletId = data.data.wallets[0].walletId;

  await env.DB.prepare(
    `INSERT INTO circle_wallets (user_id, wallet_id, created_at)
     VALUES (?1, ?2, ?3)
     ON CONFLICT(user_id) DO NOTHING`
  )
    .bind(userId, walletId, new Date().toISOString())
    .run();

  return walletId;
}
```

---

## 2. Generating a USDC Deposit Address

```typescript
// src/circle/deposit-address.ts
type Blockchain = 'ETH' | 'SOL' | 'MATIC' | 'ARB' | 'BASE';

interface CircleAddressResponse {
  data: {
    address: string;
    blockchain: Blockchain;
    currency: string;
  };
}

export async function getOrCreateDepositAddress(
  walletId: string,
  blockchain: Blockchain,
  env: Env
): Promise<string> {
  // Check cache first
  const cacheKey = `circle_addr:${walletId}:${blockchain}`;
  const cached = await env.KV.get(cacheKey);
  if (cached) return cached;

  const idempotencyKey = crypto.randomUUID();

  const res = await fetch(
    `https://api.circle.com/v1/w3s/wallets/${walletId}/addresses`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CIRCLE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        idempotencyKey,
        entitySecretCiphertext: env.CIRCLE_ENTITY_SECRET_CIPHERTEXT,
        blockchain,
        currency: 'USDC',
      }),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Circle address create failed: ${res.status} ${err}`);
  }

  const data = await res.json<CircleAddressResponse>();
  const address = data.data.address;

  // Cache indefinitely — addresses are reusable
  await env.KV.put(cacheKey, address);

  await env.DB.prepare(
    `INSERT INTO circle_addresses (wallet_id, address, blockchain, created_at)
     VALUES (?1, ?2, ?3, ?4) ON CONFLICT(wallet_id, blockchain) DO NOTHING`
  )
    .bind(walletId, address, blockchain, new Date().toISOString())
    .run();

  return address;
}
```

---

## 3. Processing Circle Webhook Notifications

```typescript
// src/circle/webhook-handler.ts
// Circle sends notifications wrapped in an SNS-style envelope.
// Verify by fetching the SigningCertURL and checking the RSA signature,
// or use Circle's simpler webhook secret (available for Programmable Wallets v2).

interface CircleNotification {
  Type: string;
  MessageId: string;
  Message: string; // JSON string — parse separately
  SubscribeURL?: string;
}

interface CircleTransactionMessage {
  clientId: string;
  notificationType: string;
  transaction: {
    id: string;
    walletId: string;
    amounts: Array<{ amount: string; currency: string }>;
    txHash: string;
    state: 'INITIATED' | 'PENDING' | 'COMPLETE' | 'FAILED';
    transactionType: 'INBOUND' | 'OUTBOUND';
  };
}

export async function handleCircleWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<CircleNotification>();

  // Handle SNS subscription confirmation
  if (body.Type === 'SubscriptionConfirmation' && body.SubscribeURL) {
    await fetch(body.SubscribeURL);
    return new Response('OK', { status: 200 });
  }

  if (body.Type !== 'Notification') {
    return new Response('Ignored', { status: 200 });
  }

  const msg = JSON.parse(body.Message) as CircleTransactionMessage;

  if (msg.notificationType === 'transactions.inbound.complete') {
    const tx = msg.transaction;
    const usdcAmount = tx.amounts.find(a => a.currency === 'USDC');
    if (!usdcAmount) return new Response('OK', { status: 200 });

    await env.DB.prepare(
      `INSERT INTO circle_transactions
         (id, wallet_id, tx_hash, amount_usdc, state, type, settled_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
       ON CONFLICT(id) DO UPDATE SET state = excluded.state, settled_at = excluded.settled_at`
    )
      .bind(
        tx.id,
        tx.walletId,
        tx.txHash,
        usdcAmount.amount,
        tx.state,
        tx.transactionType,
        new Date().toISOString()
      )
      .run();

    // Credit user's internal balance
    await env.DB.prepare(
      `UPDATE circle_wallets
       SET balance_usdc = balance_usdc + ?1
       WHERE wallet_id = ?2`
    )
      .bind(parseFloat(usdcAmount.amount), tx.walletId)
      .run();
  }

  return new Response('OK', { status: 200 });
}
```

---

## 4. Initiating a USDC Payout to an External Address

```typescript
// src/circle/payout.ts
export async function sendUSDC(params: {
  fromWalletId: string;
  destinationAddress: string;
  blockchain: string;
  amountUsdc: string; // decimal string, e.g. "100.00"
  idempotencyKey: string;
  env: Env;
}): Promise<string> {
  const { fromWalletId, destinationAddress, blockchain, amountUsdc, idempotencyKey, env } = params;

  const res = await fetch('https://api.circle.com/v1/w3s/transactions/transfer', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CIRCLE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      idempotencyKey,
      entitySecretCiphertext: env.CIRCLE_ENTITY_SECRET_CIPHERTEXT,
      walletId: fromWalletId,
      amounts: [{ amount: amountUsdc, currency: 'USDC' }],
      destinationAddress,
      blockchain,
      feeLevel: 'MEDIUM',
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Circle transfer failed: ${res.status} ${err}`);
  }

  const data = await res.json<{ data: { id: string } }>();
  return data.data.id;
}
```

---

## Anti-patterns

- **Reusing idempotency keys across different transfers** — Circle deduplicates on
  `idempotencyKey`; reusing a key for a different amount/destination silently returns the
  original response without creating a new transfer.
- **Treating `PENDING` state as final** — on-chain transactions require a configurable
  number of block confirmations; only `COMPLETE` state is final and safe to credit.
- **Storing `CIRCLE_ENTITY_SECRET_CIPHERTEXT` in source code** — this ciphertext, combined
  with the entity secret, controls all wallet operations; treat it as a credential.
- **Not caching deposit addresses** — calling the address creation endpoint repeatedly for
  the same wallet wastes quota; addresses are deterministic and reusable.

## Gotchas

- Circle's Programmable Wallets use an `entitySecretCiphertext` that must be regenerated
  each API session using the raw entity secret and Circle's public key; the ciphertext
  changes per request in some SDK flows — read the API docs for your SDK version carefully.
- Circle sandbox (`api-sandbox.circle.com`) requires separate API keys from production
  (`api.circle.com`); the base URL is also different.
- USDC has 6 decimal places on Ethereum/Solana; Circle's API returns amounts as decimal
  strings (e.g. `"100.000000"`), not minor units. Do not multiply by 100 before storing.
- Circle SNS webhook envelopes set `Content-Type: text/plain` even though the body is JSON;
  parse with `request.text()` then `JSON.parse()`, not `request.json()`, to avoid decoding
  errors on some runtimes.
- Gas fee estimation for outbound transfers uses `feeLevel` (LOW/MEDIUM/HIGH); always pass
  `MEDIUM` or higher for time-sensitive operations to avoid stuck transactions.

## Verification

```bash
# Check wallet balance in D1
wrangler d1 execute DB --command \
  "SELECT wallet_id, balance_usdc, created_at FROM circle_wallets ORDER BY created_at DESC LIMIT 5"

# Check recent inbound transactions
wrangler d1 execute DB --command \
  "SELECT id, wallet_id, amount_usdc, state, settled_at FROM circle_transactions
   WHERE type = 'INBOUND' ORDER BY settled_at DESC LIMIT 10"
```

## Related

- `usdc-stablecoin-settlement-solana-webhooks.md`
- `crypto-payments-integration.md`
- `crypto-confirmation-depth-finality.md`
- `wallet-balance-patterns.md`

## Sources

- https://developers.circle.com/w3s/docs/programmable-wallets-overview
- https://developers.circle.com/w3s/reference/createwallet
- https://developers.circle.com/w3s/docs/notifications-quickstart
- https://developers.cloudflare.com/workers/
