# USDT TRC-20 Payment Verification on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to accept USDT (Tether) on the TRON network (TRC-20) as a payment method, verify incoming transfers to a deposit address, confirm finality, and credit user accounts — all from a Cloudflare Worker without a dedicated blockchain node.

## Context

TRON TRC-20 USDT is the highest-volume stablecoin transfer channel globally. Unlike EVM chains, TRON uses base58check addresses and the TronGrid REST API (or TronScan) as its RPC gateway. A Worker polls or webhook-receives TRC-20 token transfer events on a per-user deposit address, verifies the transaction ID, checks confirmation depth, and updates the ledger in D1. No WebSocket support is needed — HTTP polling via cron suffices for most use cases.

---

## 1. Generating a Unique Deposit Address per User

TRON addresses are derived from private keys using `secp256k1`. For a custodial flow, derive child addresses from an HD wallet seed stored in Workers Secrets.

```typescript
// src/tron-address.ts
// Uses TronWeb-equivalent logic; TronWeb is Node-only so we use tronweb-core primitives
// For Workers: use @noble/secp256k1 + tron base58check encoding

import { sha256 } from '@noble/hashes/sha256';
import { keccak_256 } from '@noble/hashes/sha3';
import * as secp from '@noble/secp256k1';
import { base58check } from '@scure/base';

function privateKeyToTronAddress(privateKeyHex: string): string {
  const privBytes = Uint8Array.from(Buffer.from(privateKeyHex, 'hex'));
  const pubKey = secp.getPublicKey(privBytes, false); // uncompressed, 65 bytes
  const pubKeyNoPrefix = pubKey.slice(1);             // drop 0x04 prefix
  const ethAddress = keccak_256(pubKeyNoPrefix).slice(12); // last 20 bytes
  const tronPrefixed = new Uint8Array(21);
  tronPrefixed[0] = 0x41; // TRON mainnet prefix
  tronPrefixed.set(ethAddress, 1);
  return base58check(sha256).encode(tronPrefixed);
}

export { privateKeyToTronAddress };
```

---

## 2. Querying TRC-20 Transfers via TronGrid

```typescript
// src/trongrid.ts
const TRON_USDT_CONTRACT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t';
const TRONGRID_BASE = 'https://api.trongrid.io';

interface TRC20Transfer {
  transaction_id: string;
  from: string;
  to: string;
  value: string; // raw amount (6 decimals for USDT TRC-20)
  block_timestamp: number;
  confirmed: boolean;
}

async function fetchIncomingTransfers(
  depositAddress: string,
  minTimestamp: number,
  apiKey: string
): Promise<TRC20Transfer[]> {
  const url = new URL(
    `/v1/accounts/${depositAddress}/transactions/trc20`,
    TRONGRID_BASE
  );
  url.searchParams.set('contract_address', TRON_USDT_CONTRACT);
  url.searchParams.set('min_timestamp', String(minTimestamp));
  url.searchParams.set('only_to', 'true');
  url.searchParams.set('limit', '20');

  const res = await fetch(url.toString(), {
    headers: {
      'TRON-PRO-API-KEY': apiKey,
      Accept: 'application/json',
    },
  });

  if (!res.ok) throw new Error(`TronGrid error: ${await res.text()}`);
  const { data } = await res.json<{ data: TRC20Transfer[] }>();
  return data ?? [];
}

async function getTransactionConfirmations(
  txId: string,
  apiKey: string
): Promise<number> {
  const res = await fetch(`${TRONGRID_BASE}/wallet/gettransactionbyid`, {
    method: 'POST',
    headers: {
      'TRON-PRO-API-KEY': apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ value: txId }),
  });
  const tx = await res.json<{ blockNumber?: number }>();
  if (!tx.blockNumber) return 0;

  const nowBlock = await fetch(`${TRONGRID_BASE}/wallet/getnowblock`, {
    headers: { 'TRON-PRO-API-KEY': apiKey },
  }).then((r) => r.json<{ block_header: { raw_data: { number: number } } }>());

  return nowBlock.block_header.raw_data.number - tx.blockNumber;
}

export { fetchIncomingTransfers, getTransactionConfirmations };
```

---

## 3. Cron Worker — Poll, Confirm, and Credit

```typescript
// src/tron-poller.ts
interface Env {
  DB: D1Database;
  TRONGRID_API_KEY: string;
  MIN_CONFIRMATIONS: string; // e.g. "20"
}

const USDT_DECIMALS = 6;
const MIN_CONF = 20; // TRON block time ~3s; 20 blocks ≈ 60s finality

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const minConf = parseInt(env.MIN_CONFIRMATIONS ?? String(MIN_CONF), 10);
    const { fetchIncomingTransfers, getTransactionConfirmations } =
      await import('./trongrid');

    const addresses = await env.DB.prepare(
      `SELECT id AS user_id, deposit_address, last_checked_ts
       FROM user_tron_deposits WHERE active = 1 LIMIT 200`
    ).all<{ user_id: string; deposit_address: string; last_checked_ts: number }>();

    for (const row of addresses.results) {
      const transfers = await fetchIncomingTransfers(
        row.deposit_address,
        row.last_checked_ts,
        env.TRONGRID_API_KEY
      );

      for (const tx of transfers) {
        const already = await env.DB.prepare(
          'SELECT 1 FROM tron_transactions WHERE tx_id = ?'
        ).bind(tx.transaction_id).first();
        if (already) continue;

        const confs = await getTransactionConfirmations(
          tx.transaction_id,
          env.TRONGRID_API_KEY
        );
        if (confs < minConf) continue; // wait for finality

        const usdtAmount = Number(tx.value) / 10 ** USDT_DECIMALS;

        await env.DB.batch([
          env.DB.prepare(
            `INSERT INTO tron_transactions (tx_id, user_id, amount_usdt, confirmations, created_at)
             VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)`
          ).bind(tx.transaction_id, row.user_id, usdtAmount, confs),
          env.DB.prepare(
            'UPDATE user_balances SET usdt_balance = usdt_balance + ? WHERE user_id = ?'
          ).bind(usdtAmount, row.user_id),
        ]);
      }

      await env.DB.prepare(
        'UPDATE user_tron_deposits SET last_checked_ts = ? WHERE deposit_address = ?'
      ).bind(Date.now(), row.deposit_address).run();
    }
  },
};
```

---

## 4. On-Demand Deposit Status Endpoint

```typescript
// src/deposit-status.ts
export async function handleDepositStatus(
  request: Request,
  env: { DB: D1Database }
): Promise<Response> {
  const userId = new URL(request.url).searchParams.get('userId');
  if (!userId) return new Response('Missing userId', { status: 400 });

  const [deposit, transactions] = await Promise.all([
    env.DB.prepare(
      'SELECT deposit_address FROM user_tron_deposits WHERE id = ?'
    ).bind(userId).first<{ deposit_address: string }>(),

    env.DB.prepare(
      `SELECT tx_id, amount_usdt, confirmations, created_at
       FROM tron_transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 10`
    ).bind(userId).all(),
  ]);

  return Response.json({
    depositAddress: deposit?.deposit_address,
    recentTransactions: transactions.results,
  });
}
```

---

## 5. Webhook Alternative via TronGrid Event Subscription

TronGrid supports webhook delivery for contract events. Register via their dashboard and verify origin by checking that the source IP belongs to TronGrid's published CIDR ranges in the Worker.

```typescript
// src/tron-webhook.ts
const TRONGRID_IPS = ['34.36.104.131', '35.199.36.153']; // verify current list

export async function handleTronWebhook(
  request: Request,
  env: { DB: D1Database; TRONGRID_API_KEY: string }
): Promise<Response> {
  const sourceIp = request.headers.get('CF-Connecting-IP') ?? '';
  if (!TRONGRID_IPS.includes(sourceIp))
    return new Response('Forbidden', { status: 403 });

  const event = await request.json<{
    transaction_id: string;
    result: { to: string; value: string };
    block_number: number;
  }>();

  // Queue for confirmation polling rather than crediting immediately
  await env.DB.prepare(
    `INSERT OR IGNORE INTO tron_pending (tx_id, to_address, raw_value, block_number, received_at)
     VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(
      event.transaction_id,
      event.result.to,
      event.result.value,
      event.block_number
    )
    .run();

  return new Response('OK');
}
```

---

## Anti-patterns

- **Crediting on zero confirmations** — TRON has rare but documented reorgs; always enforce at least 20 confirmations before crediting.
- **Sharing one deposit address across users** — Without per-user addresses you cannot attribute payments; use HD wallet derivation or a KV-mapped address pool.
- **Parsing USDT amounts as integers without decimal handling** — TRC-20 USDT has 6 decimals; a raw value of `1000000` = `1.00 USDT`.
- **Calling TronGrid without an API key** — Free-tier rate limits are 15 req/s; authenticated keys get 1000 req/s.

## Gotchas

- TRON's energy/bandwidth model means TRC-20 transfers require TRON (TRX) in the recipient address to pay for energy; zero-TRX addresses may fail to receive.
- TronGrid's `confirmed` flag is eventually consistent — use block-depth confirmation counting for production.
- TRON mainnet addresses start with `T`; testnet Shasta/Nile addresses start with `T` too but use different genesis — test keys are incompatible.
- The `value` field in TRC-20 event logs is a hex string in some endpoints and a decimal string in others; always parse with `BigInt`.

## Verification

```bash
# Check a known USDT TRC-20 transfer on mainnet
curl "https://api.trongrid.io/v1/accounts/TYour...Address/transactions/trc20?contract_address=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t&limit=5" \
  -H "TRON-PRO-API-KEY: <key>"

# Confirm D1 credit after cron
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
wrangler d1 execute <DB> --command "SELECT * FROM tron_transactions ORDER BY created_at DESC LIMIT 5"
```

## Related

- `usdc-stablecoin-settlement-solana-webhooks.md`
- `crypto-payments-integration.md`
- `crypto-confirmation-depth-finality.md`
- `crypto-price-volatility-handling.md`

## Sources

- https://developers.tron.network/docs/trongrid
- https://developers.tron.network/reference/get-trc20-transaction-info-by-account-address
- https://tronscan.org/#/tools/trc20
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
