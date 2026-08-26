# Crypto Payment Address Reuse Prevention with D1 on Cloudflare Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Two customers submit payments to the same crypto deposit address. Both payments are credited to the first order that reserved the address, or worse, the second payment is permanently lost because the first order already closed. The root cause is address reuse: a naive integration generates one static wallet address per merchant account and routes all payments there, making per-order attribution impossible.

---

## Context

Crypto payment processors (NOWPayments, CoinPayments, BitPay, self-hosted HD wallets) support per-invoice address generation. Each payment order must receive a unique, never-reused deposit address. The address is derived from an HD wallet at a per-order BIP32 derivation index stored in D1. Cloudflare Workers handles order creation, address assignment, and payment webhook processing. D1 enforces the uniqueness constraint with a `UNIQUE` index and an atomic counter row.

Key invariants:
1. Each D1 row maps exactly one address to one order.
2. The derivation index only increments; it is never recycled.
3. Addresses are locked at order creation; payment webhooks look up by address, not by order ID passed from the client.

---

## 1. D1 Schema

```sql
-- migrations/0001_crypto_addresses.sql
CREATE TABLE IF NOT EXISTS hd_wallet_counters (
  wallet_id   TEXT PRIMARY KEY,
  next_index  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS crypto_payment_addresses (
  address          TEXT PRIMARY KEY,
  order_id         TEXT NOT NULL UNIQUE,
  derivation_index INTEGER NOT NULL,
  coin             TEXT NOT NULL,
  amount_crypto    TEXT NOT NULL,
  amount_usd_cents INTEGER NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',
  created_at       INTEGER NOT NULL,
  expires_at       INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cpa_order
  ON crypto_payment_addresses (order_id);

CREATE INDEX IF NOT EXISTS idx_cpa_status_expires
  ON crypto_payment_addresses (status, expires_at);

-- Seed the counter for your HD wallet ID
INSERT OR IGNORE INTO hd_wallet_counters (wallet_id, next_index)
VALUES ('main', 0);
```

---

## 2. Atomic Index Claim in D1

D1 does not support `SELECT ... FOR UPDATE`, so the claim must use a CAS (compare-and-swap) UPDATE pattern. The counter row is incremented atomically; if two Workers race, only one wins the given index.

```typescript
// src/lib/address-counter.ts
export interface Env {
  DB: D1Database;
}

/** Claims the next derivation index and returns it. Never returns the same index twice. */
export async function claimNextIndex(db: D1Database, walletId = 'main'): Promise<number> {
  const result = await db
    .prepare(
      `UPDATE hd_wallet_counters
          SET next_index = next_index + 1
        WHERE wallet_id = ?
        RETURNING next_index - 1 AS claimed_index`
    )
    .bind(walletId)
    .first<{ claimed_index: number }>();

  if (!result) throw new Error(`Wallet counter '${walletId}' not initialised`);
  return result.claimed_index;
}
```

---

## 3. HD Wallet Address Derivation

Use the `@scure/bip32` + `@scure/bip39` stack (pure JS, runs in Workers). The derivation path follows BIP44: `m/44'/coin_type'/0'/0/index`.

```typescript
// src/lib/hd-derive.ts
import { HDKey } from '@scure/bip32';
import { payments, networks } from 'bitcoinjs-lib'; // or equivalent per coin

const COIN_TYPE: Record<string, number> = { BTC: 0, LTC: 2, ETH: 60 };

export function deriveAddress(
  xpub: string,
  coin: string,
  index: number
): string {
  const coinType = COIN_TYPE[coin];
  if (coinType === undefined) throw new Error(`Unknown coin: ${coin}`);

  const master = HDKey.fromExtendedKey(xpub);
  // External chain: m/44'/coin_type'/0'/0/index
  const child = master
    .deriveChild(44 + 0x80000000)  // purpose, hardened
    .deriveChild(coinType + 0x80000000)
    .deriveChild(0x80000000)       // account 0, hardened
    .deriveChild(0)                // external chain
    .deriveChild(index);           // address index

  if (!child.publicKey) throw new Error('Derivation failed');

  // P2PKH for BTC/LTC; for ETH use a different encoder
  const { address } = payments.p2pkh({
    pubkey: Buffer.from(child.publicKey),
    network: coin === 'LTC' ? networks.testnet : networks.bitcoin,
  });

  if (!address) throw new Error('Address encoding failed');
  return address;
}
```

---

## 4. Order Creation Handler

```typescript
// src/handlers/create-order.ts
import { claimNextIndex } from '../lib/address-counter';
import { deriveAddress } from '../lib/hd-derive';
import type { Env } from '../types';

export async function handleCreateOrder(request: Request, env: Env): Promise<Response> {
  const { coin, amount_usd_cents, order_id } = await request.json<{
    coin: string;
    amount_usd_cents: number;
    order_id: string;
  }>();

  const xpub = env.HD_WALLET_XPUB; // set in Workers secret
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + 60 * 60; // 1 hour window

  // Claim an index atomically
  const index = await claimNextIndex(env.DB);

  // Derive the unique deposit address
  const address = deriveAddress(xpub, coin, index);

  // Record in D1 — UNIQUE on address + order_id prevents double-insert
  try {
    await env.DB
      .prepare(
        `INSERT INTO crypto_payment_addresses
           (address, order_id, derivation_index, coin, amount_crypto, amount_usd_cents,
            status, created_at, expires_at)
         VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)`
      )
      .bind(address, order_id, index, coin, '0', amount_usd_cents, now, expiresAt)
      .run();
  } catch (e: any) {
    if (e.message?.includes('UNIQUE')) {
      return Response.json({ error: 'order_id already assigned an address' }, { status: 409 });
    }
    throw e;
  }

  return Response.json({ address, expires_at: expiresAt });
}
```

---

## 5. Payment Webhook Attribution by Address

The webhook carries the deposit address (not the order ID), which is the authoritative lookup key.

```typescript
// src/handlers/payment-webhook.ts
import type { Env } from '../types';

export async function handleCryptoWebhook(request: Request, env: Env): Promise<Response> {
  const payload = await request.json<{
    address: string;
    tx_hash: string;
    amount: string;
    confirmations: number;
  }>();

  if (payload.confirmations < 3) {
    return new Response('waiting_confirmations', { status: 200 });
  }

  const row = await env.DB
    .prepare(
      `SELECT order_id, amount_usd_cents, status
         FROM crypto_payment_addresses
        WHERE address = ?`
    )
    .bind(payload.address)
    .first<{ order_id: string; amount_usd_cents: number; status: string }>();

  if (!row) return Response.json({ error: 'unknown_address' }, { status: 404 });
  if (row.status === 'paid') return new Response('already_processed', { status: 200 });

  await env.DB
    .prepare(
      `UPDATE crypto_payment_addresses
          SET status = 'paid'
        WHERE address = ? AND status = 'pending'`
    )
    .bind(payload.address)
    .run();

  // Fulfil the order via your business logic
  await fulfillOrder(row.order_id, env);

  return new Response('ok', { status: 200 });
}

async function fulfillOrder(orderId: string, env: Env): Promise<void> {
  // call internal order service, send email, etc.
}
```

---

## 6. Expiry Sweep (Cron Trigger)

```typescript
// src/cron/expire-addresses.ts
import type { Env } from '../types';

export async function sweepExpiredAddresses(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  await env.DB
    .prepare(
      `UPDATE crypto_payment_addresses
          SET status = 'expired'
        WHERE status = 'pending' AND expires_at < ?`
    )
    .bind(now)
    .run();
}
```

```toml
# wrangler.toml
[triggers]
crons = ["*/15 * * * *"]
```

---

## Anti-patterns

- **One static address per merchant** — makes order attribution impossible; never do this.
- **Reusing expired address indexes** — an expired order's address could receive a late payment; the index must be permanently retired, not recycled.
- **Storing index in KV** — KV is eventually consistent; two concurrent Workers can read the same counter and issue duplicate addresses. D1's atomic `UPDATE … RETURNING` is the correct primitive.
- **Trusting client-supplied order IDs in webhook** — always look up by address; a malicious client can claim any order_id.

---

## Gotchas

- `@scure/bip32` does not support hardened derivation from a public xpub (by design). Use an xpub already at the account level (`m/44'/coin'/0'`), so Workers only needs to derive `0/index` (non-hardened).
- ETH addresses require checksummed hex encoding (`getAddress` from `ethers/address`), not the BTC P2PKH format.
- D1's `RETURNING` clause requires SQLite ≥ 3.35; D1 supports it.
- Address expiry does not cancel the blockchain payment — late payments arriving after expiry still land at the derived address. The sweep marks the DB row expired, but your webhook handler must still credit the order (or issue a refund).

---

## Verification

```bash
# Insert a test order and verify unique address assignment
curl -X POST https://your-worker.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"coin":"BTC","amount_usd_cents":2999,"order_id":"ord_test_001"}'

# Attempt duplicate order_id — must return 409
curl -X POST https://your-worker.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"coin":"BTC","amount_usd_cents":2999,"order_id":"ord_test_001"}'

# Inspect D1 directly
wrangler d1 execute YOUR_DB --command \
  "SELECT address, order_id, derivation_index, status FROM crypto_payment_addresses LIMIT 10"
```

---

## Related

- `crypto-payment-channel-state-durable-objects.md`
- `crypto-wallet-signature-verification-web-crypto-workers.md`
- `nowpayments-invoice-lifecycle-and-late-deposits.md`
- `idempotency-keys-payment-apis.md`

---

## Sources

- BIP32 HD Wallet specification: https://github.com/bitcoin/bips/blob/master/bip-0032.mediawiki
- BIP44 multi-coin derivation paths: https://github.com/bitcoin/bips/blob/master/bip-0044.mediawiki
- `@scure/bip32` library: https://github.com/paulmillr/scure-bip32
- Cloudflare D1 `RETURNING` clause: https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
