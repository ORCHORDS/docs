# Crypto Payment Settlement with USDC Stablecoin and Solana Webhooks

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You want to accept USDC payments on Solana (SPL token) and settle them to a business treasury wallet — without volatility risk (USDC is 1:1 USD), without a centralised crypto payment processor, and with webhook-driven order confirmation that integrates with your existing Cloudflare Workers API. The challenge: Solana transactions confirm in ~400 ms, but webhook delivery from indexers like Helius is at-least-once, block reorganisations can invalidate transactions, and USDC transfers are SPL token transfers — not native SOL transfers — requiring token account inspection.

---

## Context

**Why USDC on Solana:**
- Near-zero transaction fees ($0.00025 median as of 2026)
- ~400 ms block time, finality in ~2 slots under Tower BFT
- USDC is issued by Circle and always redeemable 1:1 for USD
- Circle provides an on-ramp API (CCTP v2) for cross-chain USDC transfers

**Settlement flow:**

```
Customer wallet (Phantom / Solflare)
        │
        │  SPL USDC transfer (Solana mainnet)
        ▼
Business deposit address
        │
        │  Helius enhanced webhook (transaction confirmed)
        ▼
Cloudflare Worker (webhook receiver)
  • verify transaction on-chain
  • match deposit to order
  • credit order in D1
        │
        ▼
Treasury sweep (scheduled: Worker + Cron)
  • aggregate deposits → sweep to cold wallet
```

---

## On-chain Setup: Generate a Deposit Address Per Order

Each order gets a unique deposit address derived from a master key using BIP44 path derivation. This allows you to map any incoming transfer to a specific order without watching a single shared address.

```typescript
// lib/solana/deposit-address.ts
import { Keypair, PublicKey } from '@solana/web3.js';
import { derivePath } from 'ed25519-hd-key';
import { encode as bs58encode } from 'bs58';

const USDC_MINT_MAINNET = new PublicKey('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v');

/**
 * Derive a deposit keypair for a given order index.
 * Master seed should be stored in Cloudflare Secrets (never in code).
 */
export function deriveDepositKeypair(masterSeedHex: string, orderIndex: number): Keypair {
  const seed = Buffer.from(masterSeedHex, 'hex');
  // BIP44 path: m/44'/501'/{orderIndex}'/0'
  const path = `m/44'/501'/${orderIndex}'/0'`;
  const { key } = derivePath(path, seed.toString('hex'));
  return Keypair.fromSeed(key);
}

/**
 * Get the associated token account for USDC on a given deposit keypair.
 * This is the address customers send USDC to.
 */
export async function getUsdcDepositAddress(
  masterSeedHex: string,
  orderIndex: number
): Promise<string> {
  const { getAssociatedTokenAddressSync } = await import('@solana/spl-token');
  const keypair = deriveDepositKeypair(masterSeedHex, orderIndex);
  const ata = getAssociatedTokenAddressSync(USDC_MINT_MAINNET, keypair.publicKey);
  return ata.toBase58();
}
```

---

## D1 Schema

```sql
-- migration: 0001_usdc_orders.sql
CREATE TABLE IF NOT EXISTS usdc_orders (
  id              TEXT PRIMARY KEY,          -- UUID
  order_index     INTEGER UNIQUE NOT NULL,   -- BIP44 path index
  deposit_address TEXT NOT NULL,             -- USDC ATA (base58)
  owner_address   TEXT NOT NULL,             -- deposit keypair pubkey
  amount_usd      TEXT NOT NULL,             -- e.g. "49.99"
  amount_usdc     INTEGER NOT NULL,          -- in micro-USDC (6 decimals): $49.99 = 49990000
  status          TEXT NOT NULL DEFAULT 'awaiting_payment',
  tx_signature    TEXT,                      -- confirmed Solana tx signature
  confirmed_at    TEXT,
  customer_id     TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_usdc_orders_deposit ON usdc_orders(deposit_address);
CREATE INDEX idx_usdc_orders_status  ON usdc_orders(status);

CREATE TABLE IF NOT EXISTS usdc_deposits (
  id              TEXT PRIMARY KEY,
  order_id        TEXT NOT NULL REFERENCES usdc_orders(id),
  tx_signature    TEXT NOT NULL UNIQUE,
  amount_usdc     INTEGER NOT NULL,
  sender_address  TEXT NOT NULL,
  slot            INTEGER NOT NULL,
  confirmed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Helius Webhook Configuration

Register a Cloudflare Worker URL as a Helius webhook watching the deposit addresses:

```typescript
// scripts/register-helius-webhook.ts
// Run once during deploy or when new addresses are created

const HELIUS_API_KEY = process.env.HELIUS_API_KEY!;
const WORKER_URL    = 'https://payment-api.yourapp.workers.dev/webhooks/solana';

async function registerWebhook(depositAddresses: string[]) {
  const response = await fetch(
    `https://api.helius.xyz/v0/webhooks?api-key=<redacted-secret>
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        webhookURL: WORKER_URL,
        transactionTypes: ['TRANSFER'],
        accountAddresses: depositAddresses,
        webhookType: 'enhanced',
        authHeader: `Bearer ${process.env.HELIUS_WEBHOOK_SECRET}`,
      }),
    }
  );
  const data = await response.json();
  console.log('Registered webhook:', data.webhookID);
}
```

---

## Webhook Receiver Worker

```typescript
// workers/solana-webhook-receiver.ts
import { Connection, PublicKey } from '@solana/web3.js';
import type { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  HELIUS_WEBHOOK_SECRET: string;
  HELIUS_RPC_URL: string; // e.g. https://mainnet.helius-rpc.com/?api-key=XXX
  MASTER_SEED_HEX: string;
}

const USDC_MINT = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
const USDC_DECIMALS = 6;

interface HeliusEnhancedEvent {
  signature: string;
  slot: number;
  type: string;
  tokenTransfers?: Array<{
    mint: string;
    toUserAccount: string;
    fromUserAccount: string;
    tokenAmount: number;
  }>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('', { status: 405 });

    // Verify Helius auth header
    const auth = request.headers.get('authorization') ?? '';
    if (auth !== `Bearer ${env.HELIUS_WEBHOOK_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    const events: HeliusEnhancedEvent[] = await request.json();

    for (const event of events) {
      await processEvent(event, env);
    }

    return new Response('ok', { status: 200 });
  },
};

async function processEvent(event: HeliusEnhancedEvent, env: Env): Promise<void> {
  // Only process USDC token transfers
  const usdcTransfers = (event.tokenTransfers ?? []).filter(
    t => t.mint === USDC_MINT && t.tokenAmount > 0
  );
  if (usdcTransfers.length === 0) return;

  for (const transfer of usdcTransfers) {
    await processUsdcTransfer(event, transfer, env);
  }
}

async function processUsdcTransfer(
  event: HeliusEnhancedEvent,
  transfer: { toUserAccount: string; fromUserAccount: string; tokenAmount: number },
  env: Env
): Promise<void> {
  // Find the order for this deposit address
  const order = await env.DB.prepare(
    'SELECT * FROM usdc_orders WHERE deposit_address = ? AND status = ?'
  ).bind(transfer.toUserAccount, 'awaiting_payment')
   .first<{
     id: string; amount_usdc: number; order_index: number;
     customer_id: string; deposit_address: string;
   }>();

  if (!order) return; // Not one of our deposit addresses or already paid

  // Verify on-chain (protection against replayed/forged Helius events)
  const verified = await verifyOnChain(
    event.signature,
    transfer.toUserAccount,
    transfer.tokenAmount,
    env.HELIUS_RPC_URL
  );
  if (!verified) return;

  // Convert tokenAmount (Helius sends as float with full precision) to micro-USDC
  const receivedMicroUsdc = Math.round(transfer.tokenAmount * 10 ** USDC_DECIMALS);

  // Allow 1% tolerance for wallet rounding errors
  const expectedMicroUsdc = order.amount_usdc;
  const tolerance = Math.round(expectedMicroUsdc * 0.01);
  if (receivedMicroUsdc < expectedMicroUsdc - tolerance) {
    // Underpayment — log but do not confirm
    await env.DB.prepare(
      `INSERT OR IGNORE INTO usdc_deposits
         (id, order_id, tx_signature, amount_usdc, sender_address, slot)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      crypto.randomUUID(), order.id, event.signature,
      receivedMicroUsdc, transfer.fromUserAccount, event.slot
    ).run();
    return;
  }

  // Confirm order (idempotent via tx_signature UNIQUE constraint)
  await env.DB.batch([
    env.DB.prepare(
      `INSERT OR IGNORE INTO usdc_deposits
         (id, order_id, tx_signature, amount_usdc, sender_address, slot)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      crypto.randomUUID(), order.id, event.signature,
      receivedMicroUsdc, transfer.fromUserAccount, event.slot
    ),
    env.DB.prepare(
      `UPDATE usdc_orders
       SET status = 'confirmed', tx_signature = ?, confirmed_at = datetime('now'),
           updated_at = datetime('now')
       WHERE id = ? AND status = 'awaiting_payment'`
    ).bind(event.signature, order.id),
  ]);
}

async function verifyOnChain(
  signature: string,
  expectedRecipient: string,
  expectedAmount: number,
  rpcUrl: string
): Promise<boolean> {
  const connection = new Connection(rpcUrl, 'confirmed');
  try {
    const tx = await connection.getParsedTransaction(signature, {
      commitment: 'confirmed',
      maxSupportedTransactionVersion: 0,
    });
    if (!tx) return false;

    // Check transaction is not failed
    if (tx.meta?.err) return false;

    // Find a USDC transfer instruction to expectedRecipient
    const instructions = tx.transaction.message.instructions;
    for (const ix of instructions) {
      if ('parsed' in ix && ix.program === 'spl-token' && ix.parsed?.type === 'transferChecked') {
        const info = ix.parsed.info;
        if (
          info.mint === USDC_MINT &&
          info.destination === expectedRecipient &&
          Math.abs(parseFloat(info.tokenAmount.uiAmountString) - expectedAmount) < 0.0001
        ) {
          return true;
        }
      }
    }
    return false;
  } catch {
    return false;
  }
}
```

---

## Treasury Sweep Worker (Cron Trigger)

```typescript
// workers/treasury-sweep.ts
// Runs every hour: consolidates confirmed deposits to cold wallet

import {
  Connection, Keypair, PublicKey, Transaction,
  sendAndConfirmTransaction,
} from '@solana/web3.js';
import {
  createTransferCheckedInstruction,
  getAssociatedTokenAddressSync,
  getAccount,
  TOKEN_PROGRAM_ID,
} from '@solana/spl-token';
import { deriveDepositKeypair } from '../lib/solana/deposit-address';

export interface Env {
  DB: D1Database;
  MASTER_SEED_HEX: string;
  TREASURY_WALLET: string;      // cold wallet base58 pubkey
  HELIUS_RPC_URL: string;
}

const USDC_MINT = new PublicKey('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v');
const USDC_DECIMALS = 6;
const MIN_SWEEP_USDC = 1_000_000; // $1.00 minimum before sweeping

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const connection = new Connection(env.HELIUS_RPC_URL, 'confirmed');
    const treasury = new PublicKey(env.TREASURY_WALLET);
    const treasuryAta = getAssociatedTokenAddressSync(USDC_MINT, treasury);

    // Find confirmed but unswept orders
    const orders = await env.DB.prepare(
      `SELECT id, order_index, deposit_address
       FROM usdc_orders
       WHERE status = 'confirmed'
       ORDER BY confirmed_at
       LIMIT 20`
    ).all<{ id: string; order_index: number; deposit_address: string }>();

    for (const order of orders.results) {
      await sweepOrder(order, treasuryAta, connection, env);
    }
  },
};

async function sweepOrder(
  order: { id: string; order_index: number; deposit_address: string },
  treasuryAta: PublicKey,
  connection: Connection,
  env: Env
): Promise<void> {
  const keypair = deriveDepositKeypair(env.MASTER_SEED_HEX, order.order_index);
  const sourceAta = new PublicKey(order.deposit_address);

  let balance: bigint;
  try {
    const account = await getAccount(connection, sourceAta);
    balance = account.amount;
  } catch {
    // Account may not exist yet (no deposit received) — skip
    await env.DB.prepare(
      `UPDATE usdc_orders SET status = 'sweep_skipped' WHERE id = ?`
    ).bind(order.id).run();
    return;
  }

  if (balance < BigInt(MIN_SWEEP_USDC)) return;

  const ix = createTransferCheckedInstruction(
    sourceAta,
    USDC_MINT,
    treasuryAta,
    keypair.publicKey,
    balance,
    USDC_DECIMALS,
    [],
    TOKEN_PROGRAM_ID
  );

  const tx = new Transaction().add(ix);
  const sig = await sendAndConfirmTransaction(connection, tx, [keypair]);

  await env.DB.prepare(
    `UPDATE usdc_orders
     SET status = 'swept', updated_at = datetime('now')
     WHERE id = ?`
  ).bind(order.id).run();

  console.log(`Swept ${balance} micro-USDC from order ${order.id}: ${sig}`);
}
```

---

## Order Creation API

```typescript
// workers/create-order.ts
import { deriveDepositKeypair, getUsdcDepositAddress } from '../lib/solana/deposit-address';

export async function createUsdcOrder(
  env: { DB: D1Database; MASTER_SEED_HEX: string },
  params: { amountUsd: string; customerId: string }
): Promise<{ orderId: string; depositAddress: string; amountUsdc: number; expiresAt: string }> {
  // Get next order index (auto-increment)
  const row = await env.DB.prepare(
    'SELECT COALESCE(MAX(order_index), -1) + 1 AS next_index FROM usdc_orders'
  ).first<{ next_index: number }>();
  const orderIndex = row?.next_index ?? 0;

  const depositAddress = await getUsdcDepositAddress(env.MASTER_SEED_HEX, orderIndex);
  const amountUsdc = Math.round(parseFloat(params.amountUsd) * 10 ** 6);
  const orderId = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + 30 * 60 * 1000).toISOString(); // 30 min window

  const keypair = deriveDepositKeypair(env.MASTER_SEED_HEX, orderIndex);

  await env.DB.prepare(
    `INSERT INTO usdc_orders
       (id, order_index, deposit_address, owner_address, amount_usd, amount_usdc, customer_id)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    orderId, orderIndex, depositAddress, keypair.publicKey.toBase58(),
    params.amountUsd, amountUsdc, params.customerId
  ).run();

  return { orderId, depositAddress, amountUsdc, expiresAt };
}
```

---

## Anti-patterns

- **Watching a single shared deposit address**: Makes order matching impossible without memo instructions. Unique per-order addresses via BIP44 derivation are the correct pattern.

- **Trusting Helius webhook payload without on-chain verification**: Helius is a trusted indexer but webhooks can be replayed or spoofed if the auth header is leaked. Always verify with `getParsedTransaction`.

- **Accepting the tokenAmount float directly without rounding**: Helius returns token amounts as floats (e.g. `49.99`). Converting to micro-USDC with `* 10^6` without `Math.round` causes off-by-one errors for values like `$49.99 → 49989999` vs `49990000`.

- **Not accounting for transaction fees when sweeping**: On Solana, the fee payer is the signer — your deposit keypair. Ensure each deposit wallet holds a small SOL balance (~0.002 SOL) for fees, funded during ATA creation.

- **Sweeping immediately in the webhook handler**: If the sweep transaction fails, you've already confirmed the order. Separate confirmation from sweep via status machine (`confirmed` → `swept`).

- **Using `finalized` commitment for webhook receipt**: Finalized takes ~32 slots (~13s). For UX, accept at `confirmed` (2 slots, ~800ms) but note a <0.01% chance of rollback.

---

## Gotchas

1. **USDC ATA may not exist** for the deposit keypair until the customer sends USDC. Solana requires an ATA creation transaction (cost ~0.002 SOL). You can pre-create ATAs during order creation or let Phantom create it on first send.

2. **Helius `accountAddresses` limit**: Helius enhanced webhooks support up to 100,000 addresses per webhook. For large scale, group addresses by batch and register multiple webhooks.

3. **`tokenAmount` in Helius events uses the UI amount** (not raw lamports). For USDC with 6 decimals, `tokenAmount: 49.99` means 49,990,000 micro-USDC.

4. **BIP44 path for Solana is `m/44'/501'/index'/0'`** (not `m/44'/60'` like Ethereum). Phantom uses this path.

5. **D1 does not support `INTEGER` for amounts > 2^53** — use `TEXT` for very large USDC amounts, or keep values in micro-USDC (6 decimals) which fits in a 53-bit JS integer up to ~$9 trillion.

6. **Cloudflare Workers cannot use Node.js crypto** for ed25519 key derivation. Use the Web Crypto API or import `ed25519-hd-key` (Wasm-compatible).

7. **Helius webhook deduplication**: Helius may deliver the same event multiple times (at-least-once). The `UNIQUE(tx_signature)` constraint on `usdc_deposits` and `INSERT OR IGNORE` handle this safely.

---

## Verification

```bash
# 1. Deploy workers
wrangler deploy --config wrangler.toml

# 2. Create a test order
curl -X POST https://payment-api.yourapp.workers.dev/orders/usdc \
  -H "Content-Type: application/json" \
  -d '{"amountUsd": "1.00", "customerId": "cust_test"}'

# 3. Send USDC on devnet (using Solana CLI)
# First switch to devnet: solana config set --url devnet
solana transfer --fee-payer ~/.config/solana/id.json \
  <deposit_address> 1 --allow-unfunded-recipient

# 4. Watch D1 for confirmation
wrangler d1 execute payments \
  --command "SELECT id, status, tx_signature, confirmed_at FROM usdc_orders ORDER BY created_at DESC LIMIT 5"

# 5. Simulate Helius webhook locally
curl -X POST http://localhost:8787/webhooks/solana \
  -H "Authorization: Bearer test_secret" \
  -H "Content-Type: application/json" \
  -d '[{"signature":"test","slot":123,"type":"TRANSFER","tokenTransfers":[{"mint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","toUserAccount":"<deposit_address>","fromUserAccount":"<sender>","tokenAmount":1.00}]}]'
```

---

## Related

- `solana-helius-webhook-payment-verification.md` — Helius webhook HMAC verification
- `crypto-payments-integration.md` — Multi-chain crypto payment overview
- `crypto-price-volatility-handling.md` — Volatility hedging strategies
- `payment-state-machine-design.md` — Order state transitions
- `deferred-revenue-waterfall-d1.md` — Revenue recognition after USDC settlement

---

## Sources

- [Helius documentation — Enhanced webhooks](https://docs.helius.dev/webhooks-and-websockets/webhooks)
- [Solana SPL Token — Associated Token Accounts](https://spl.solana.com/associated-token-account)
- [Circle USDC on Solana](https://www.circle.com/en/usdc-multichain/solana)
- [Solana Web3.js — getParsedTransaction](https://solana-labs.github.io/solana-web3.js/)
- [BIP44 — Multi-Account Hierarchy](https://github.com/bitcoin/bips/blob/master/bip-0044.mediawiki)
- [ed25519-hd-key npm package](https://www.npmjs.com/package/ed25519-hd-key)
