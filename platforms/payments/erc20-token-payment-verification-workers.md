# ERC-20 Token Payment Verification with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A customer sends USDC, USDT, or another ERC-20 token to your Ethereum wallet address. You need to verify the transfer on-chain without running a node: confirm the correct token contract, amount, and recipient address from within a Cloudflare Worker, then update order state in D1 once the transaction reaches sufficient confirmations.

## Context

ERC-20 `Transfer` events are indexed by every Ethereum JSON-RPC provider. Workers can query Alchemy, Infura, or QuickNode's HTTPS endpoints to fetch transaction receipts and decode the `Transfer(address indexed from, address indexed to, uint256 value)` log. No Node.js ethers.js or web3.js required — log decoding is pure string manipulation on the ABI-encoded hex data. A Durable Object or Queues consumer can poll for confirmations without blocking a request.

---

## Environment (wrangler.toml)

```toml
[vars]
ETH_CHAIN_ID = "1"   # 1 = Ethereum mainnet, 11155111 = Sepolia

[[d1_databases]]
binding       = "DB"
database_name = "payments"
database_id   = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[queues.producers]]
binding = "CONFIRM_QUEUE"
queue   = "erc20-confirmations"
```

## Token Registry (D1)

```sql
-- migrations/0001_erc20_tokens.sql
CREATE TABLE IF NOT EXISTS erc20_tokens (
  symbol       TEXT PRIMARY KEY,
  contract     TEXT NOT NULL,   -- checksummed ERC-20 contract address
  decimals     INTEGER NOT NULL
);
INSERT OR IGNORE INTO erc20_tokens VALUES
  ('USDC', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 6),
  ('USDT', '0xdAC17F958D2ee523a2206206994597C13D831ec7', 6);
```

## Ethereum JSON-RPC Helper

```typescript
// src/lib/eth-rpc.ts

interface Env {
  ETH_RPC_URL: string;   // e.g. https://eth-mainnet.g.alchemy.com/v2/KEY
}

type RpcResult<T> = { result: T; error?: { code: number; message: string } };

export async function ethRpc<T>(
  env: Env,
  method: string,
  params: unknown[]
): Promise<T> {
  const res = await fetch(env.ETH_RPC_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const json = (await res.json()) as RpcResult<T>;
  if (json.error) throw new Error(`RPC ${method}: ${json.error.message}`);
  return json.result;
}

export async function getBlockNumber(env: Env): Promise<number> {
  const hex = await ethRpc<string>(env, "eth_blockNumber", []);
  return parseInt(hex, 16);
}

export async function getTransactionReceipt(
  env: Env,
  txHash: string
): Promise<EthReceipt | null> {
  return ethRpc<EthReceipt | null>(env, "eth_getTransactionReceipt", [txHash]);
}

export interface EthReceipt {
  blockNumber: string;      // hex
  status: string;           // "0x1" = success
  logs: EthLog[];
}

export interface EthLog {
  address: string;          // contract address (lowercase)
  topics: string[];         // [eventSig, from (padded), to (padded)]
  data: string;             // ABI-encoded uint256 value
}
```

## Decode ERC-20 Transfer Log

```typescript
// src/lib/erc20.ts
import { EthLog } from "./eth-rpc";

// keccak256("Transfer(address,address,uint256)")
const TRANSFER_SIG =
  "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";

export interface Erc20Transfer {
  from: string;
  to: string;
  valueRaw: bigint;   // raw integer (divide by 10^decimals for human amount)
  contract: string;
}

export function decodeTransferLog(log: EthLog): Erc20Transfer | null {
  if (log.topics[0]?.toLowerCase() !== TRANSFER_SIG) return null;
  if (log.topics.length < 3) return null;

  // Topics 1 & 2 are ABI-encoded addresses (padded to 32 bytes)
  const from     = "0x" + log.topics[1].slice(26).toLowerCase();
  const to       = "0x" + log.topics[2].slice(26).toLowerCase();
  const valueRaw = BigInt(log.data);

  return { from, to, valueRaw, contract: log.address.toLowerCase() };
}
```

## Verify a Payment Transaction

```typescript
// src/lib/verify-payment.ts
import { getTransactionReceipt, getBlockNumber } from "./eth-rpc";
import { decodeTransferLog } from "./erc20";

const MIN_CONFIRMATIONS = 12; // ~2.4 min on mainnet

interface Env {
  ETH_RPC_URL: string;
  DB: D1Database;
  MERCHANT_ETH_ADDRESS: string; // lowercase
}

export interface VerifyResult {
  status: "pending" | "confirmed" | "failed" | "not_found";
  confirmations?: number;
  transfer?: { from: string; valueRaw: bigint; symbol: string };
}

export async function verifyErc20Payment(
  env: Env,
  txHash: string,
  expectedSymbol: string,
  expectedAmountRaw: bigint   // in token's smallest unit
): Promise<VerifyResult> {
  const receipt = await getTransactionReceipt(env, txHash);
  if (!receipt) return { status: "not_found" };
  if (receipt.status !== "0x1") return { status: "failed" };

  // Fetch token contract address from D1
  const token = await env.DB.prepare(
    "SELECT contract, decimals FROM erc20_tokens WHERE symbol = ?"
  ).bind(expectedSymbol).first<{ contract: string; decimals: number }>();

  if (!token) throw new Error(`Unknown token symbol: ${expectedSymbol}`);

  // Find a matching Transfer log in receipt
  const merchant = env.MERCHANT_ETH_ADDRESS.toLowerCase();
  const transfer = receipt.logs
    .map(decodeTransferLog)
    .find(
      (t) =>
        t &&
        t.contract === token.contract.toLowerCase() &&
        t.to === merchant &&
        t.valueRaw >= expectedAmountRaw   // allow overpayment
    );

  if (!transfer) return { status: "failed" }; // no matching transfer

  const currentBlock = await getBlockNumber(env);
  const txBlock      = parseInt(receipt.blockNumber, 16);
  const confirmations = currentBlock - txBlock;

  if (confirmations < MIN_CONFIRMATIONS) {
    return { status: "pending", confirmations };
  }

  return {
    status: "confirmed",
    confirmations,
    transfer: { from: transfer.from, valueRaw: transfer.valueRaw, symbol: expectedSymbol },
  };
}
```

## Polling Consumer via Queues

```typescript
// src/consumers/erc20-confirm.ts
import { verifyErc20Payment } from "../lib/verify-payment";

interface ConfirmMsg {
  txHash: string;
  orderId: string;
  symbol: string;
  expectedAmountRaw: string;  // serialized bigint
  attempt: number;
}

export default {
  async queue(batch: MessageBatch<ConfirmMsg>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { txHash, orderId, symbol, expectedAmountRaw, attempt } = msg.body;

      const result = await verifyErc20Payment(
        env, txHash, symbol, BigInt(expectedAmountRaw)
      );

      if (result.status === "confirmed") {
        await env.DB.prepare(
          "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?"
        ).bind(Date.now(), orderId).run();
        msg.ack();
      } else if (result.status === "failed" || attempt >= 30) {
        await env.DB.prepare(
          "UPDATE orders SET status = 'payment_failed' WHERE id = ?"
        ).bind(orderId).run();
        msg.ack();
      } else {
        // Re-enqueue with delay — poll again in 30 s
        await env.CONFIRM_QUEUE.send(
          { ...msg.body, attempt: attempt + 1 },
          { delaySeconds: 30 }
        );
        msg.ack(); // ack original; successor carries state
      }
    }
  },
};
```

---

## Anti-patterns

- Trusting `eth_getTransactionByHash` alone — it returns data before mining; always use `eth_getTransactionReceipt` which is only available post-inclusion.
- Matching only on transaction `to` — for ERC-20 transfers, the transaction recipient is the *contract*, not your wallet; you must decode the `Transfer` log's `to` topic.
- Checking a single confirmation for high-value payments — use at least 12 blocks (~2.4 min) for amounts over $1,000, 64 blocks for finalized safety.
- Storing raw `bigint` in D1 as a number — JavaScript `number` loses precision for large uint256; store as TEXT and re-parse as `BigInt`.

## Gotchas

- Log addresses returned by JSON-RPC are lowercase without checksum; always `.toLowerCase()` before comparison.
- `data` field for a transfer is 32 bytes (66 hex chars including `0x`) representing the `uint256` value — parse with `BigInt(data)`.
- Alchemy and Infura rate-limit by compute units; a polling loop that fires every second will exhaust a free-tier key quickly.
- Stablecoin decimals differ: USDC and USDT use 6, DAI uses 18 — always look up from your token registry, never hardcode.
- `BigInt` is not JSON-serializable; convert to `.toString()` when storing in Queue messages or D1.

## Verification

```bash
# Query a known USDC transfer on Sepolia testnet
curl -X POST $ETH_RPC_URL \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getTransactionReceipt","params":["0x<txhash>"],"id":1}' \
  | jq '.result.logs[] | select(.topics[0] == "0xddf252ad...")'
```

## Related

- `usdt-trc20-payment-verification-workers.md`
- `crypto-wallet-signature-verification-web-crypto-workers.md`
- `crypto-confirmation-depth-finality.md`
- `crypto-payment-address-reuse-prevention-d1.md`
- `circle-usdc-programmable-payments-workers.md`

## Sources

- https://eips.ethereum.org/EIPS/eip-20
- https://docs.alchemy.com/reference/eth-gettransactionreceipt
- https://developers.cloudflare.com/queues/reference/delay-messages/
