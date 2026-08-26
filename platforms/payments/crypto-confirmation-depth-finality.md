# Crypto Payment Confirmation Depth and Finality

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A customer pays with cryptocurrency and the transaction appears on-chain almost immediately, but releasing the product or service after a single confirmation is risky. Different blockchains have different finality guarantees, attack costs, and reorganization probabilities. Waiting for 1 confirmation on Ethereum is very different from 1 confirmation on Bitcoin or 1 confirmation on Solana. Setting the wrong confirmation threshold leads either to fraud exposure (releasing too early on a chain with cheap reorganizations) or poor UX (making a Solana customer wait 5 minutes for "safety" that is mathematically unnecessary).

## Context

"Finality" in blockchains comes in two flavors:

1. **Probabilistic finality** (Bitcoin, Bitcoin Cash, Litecoin, pre-Merge Ethereum): A transaction becomes exponentially harder to reverse with each additional block. Attackers need to outpace the honest chain, which requires hash power proportional to block depth. The gold standard for probabilistic finality uses the 0.1% double-spend risk as the threshold.

2. **Economic / BFT finality** (Ethereum post-Merge, Solana, Avalanche): The protocol itself provides a checkpoint after a fixed number of slots/epochs, after which reversal would require slashing > 1/3 of staked ETH (Ethereum) or the network halting (Solana). These chains express finality as a discrete state, not a probability gradient.

For merchant payment confirmation, the practical question is: **at what confirmation depth is the probability of a double-spend attack economically irrational given the payment amount?**

The recommendation table in this article is calibrated for merchant payments up to $10,000. High-value transactions (>$50k) should use 2x these depths or wait for explicit protocol finality events.

## Confirmation Depth by Network

| Network         | Mechanism                | 0–$100     | $100–$1k   | $1k–$10k   | Notes                                         |
|-----------------|--------------------------|-----------|-----------|-----------|-----------------------------------------------|
| Bitcoin (BTC)   | Proof of Work            | 3 conf    | 3 conf    | 6 conf    | 6 confs ≈ 60 min; 0-conf only for micro-tips |
| Ethereum (ETH)  | PoS + Casper FFG         | 1 block   | 1 block   | 1 epoch   | Wait for finalized checkpoint (~13 min)        |
| Solana (SOL)    | PoH + Tower BFT          | finalized | finalized | finalized | Use `finalized` commitment, not `confirmed`    |
| Litecoin (LTC)  | PoW (lower hashrate)     | 6 conf    | 12 conf   | 24 conf   | Lower hashrate = cheaper to attack             |
| Bitcoin Cash    | PoW (lower hashrate)     | 10 conf   | 10 conf   | 15 conf   | Several 51% attacks occurred historically     |
| Polygon (MATIC) | PoS checkpoint to ETH    | 1 block   | 1 block   | ETH ckpt  | Full finality requires Ethereum checkpoint     |
| TRON (TRX)      | DPoS                     | 20 conf   | 20 conf   | 20 conf   | 27 validators; 19 blocks ≈ 60 seconds        |
| USDT (TRC-20)   | As per TRON              | 20 conf   | 20 conf   | 20 conf   | Same as TRON                                  |
| USDC (ERC-20)   | As per Ethereum          | 1 block   | 1 block   | finalized | Same as Ethereum                              |

## Polling Confirmation Depth via Workers

For blockchains without a finality event webhook, a Worker polls the relevant RPC endpoint on a schedule and updates D1 with the current confirmation count.

```typescript
// workers/btc-confirmation-poller.ts

interface PaymentRecord {
  id: string;
  txid: string;
  required_confirmations: number;
  current_confirmations: number;
  status: string;
}

export async function pollBitcoinConfirmations(
  db: D1Database,
  mempoolApiBase: string // e.g. "https://mempool.space/api"
): Promise<void> {
  // Fetch all pending BTC payments
  const pending = await db
    .prepare(
      `SELECT id, txid, required_confirmations, current_confirmations
       FROM crypto_payments
       WHERE network = 'bitcoin' AND status = 'pending'`
    )
    .all<PaymentRecord>();

  for (const payment of pending.results) {
    try {
      const resp = await fetch(
        `${mempoolApiBase}/tx/${payment.txid}/status`
      );
      if (!resp.ok) continue;

      const data = (await resp.json()) as {
        confirmed: boolean;
        block_height?: number;
      };

      if (!data.confirmed) {
        // Still in mempool — 0 confirmations
        continue;
      }

      // Get current tip height to compute confirmations
      const tipResp = await fetch(`${mempoolApiBase}/blocks/tip/height`);
      const tipHeight = await tipResp.json() as number;
      const confirmations = tipHeight - (data.block_height ?? tipHeight) + 1;

      const now = new Date().toISOString();
      const isConfirmed = confirmations >= payment.required_confirmations;

      await db
        .prepare(
          `UPDATE crypto_payments
           SET current_confirmations = ?,
               status = ?,
               confirmed_at = CASE WHEN ? THEN ? ELSE confirmed_at END,
               updated_at = ?
           WHERE id = ?`
        )
        .bind(
          confirmations,
          isConfirmed ? "confirmed" : "pending",
          isConfirmed ? 1 : 0,
          isConfirmed ? now : null,
          now,
          payment.id
        )
        .run();
    } catch (err) {
      console.error(`Error polling txid ${payment.txid}:`, err);
    }
  }
}

// Determine required confirmations at payment creation time
export function btcRequiredConfirmations(amountUsd: number): number {
  if (amountUsd <= 100) return 3;
  if (amountUsd <= 1000) return 3;
  return 6; // $1k–$10k
}
```

## Solana Finality via WebSocket

Solana distinguishes three commitment levels: `processed` (latest block, not yet voted on), `confirmed` (voted on by supermajority), and `finalized` (rooted, cannot be rolled back). Always use `finalized` for payments.

```typescript
// workers/solana-finality-check.ts

interface SolanaSignatureStatus {
  confirmationStatus: "processed" | "confirmed" | "finalized" | null;
  err: object | null;
  confirmations: number | null;
}

export async function waitForSolanaFinality(
  signature: string,
  rpcUrl: string,
  timeoutMs = 120_000
): Promise<{ finalized: boolean; error: string | null }> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const resp = await fetch(rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "getSignatureStatuses",
        params: [[signature], { searchTransactionHistory: true }],
      }),
    });

    const json = (await resp.json()) as {
      result: { value: (SolanaSignatureStatus | null)[] };
    };

    const status = json.result?.value?.[0];

    if (!status) {
      // Not yet known to node — wait and retry
      await sleep(2000);
      continue;
    }

    if (status.err !== null) {
      return { finalized: false, error: JSON.stringify(status.err) };
    }

    if (status.confirmationStatus === "finalized") {
      return { finalized: true, error: null };
    }

    await sleep(2000);
  }

  return { finalized: false, error: "timeout waiting for finality" };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
```

## Ethereum Finality via Beacon Chain Checkpoint

Post-Merge Ethereum uses Casper FFG checkpoints. A checkpoint is finalized once it has been justified by two consecutive epochs of 2/3+ validator attestations. The Beacon Chain API exposes the finalized slot directly.

```typescript
// workers/eth-finality-check.ts

interface BeaconFinalityResponse {
  data: {
    finalized: { epoch: string; root: string };
    current_justified: { epoch: string; root: string };
  };
}

export async function isEthTransactionFinalized(
  txBlockNumber: number,
  beaconRpcUrl: string, // e.g. https://beaconcha.in/api/v1 or local node
  executionRpcUrl: string
): Promise<boolean> {
  // Step 1: Get the finalized checkpoint epoch from the Beacon API
  const checkpointResp = await fetch(
    `${beaconRpcUrl}/eth/v1/beacon/states/head/finality_checkpoints`
  );
  const checkpoint = (await checkpointResp.json()) as BeaconFinalityResponse;
  const finalizedEpoch = parseInt(checkpoint.data.finalized.epoch, 10);

  // Step 2: Convert epoch to slot to block number
  // 1 epoch = 32 slots; 1 slot = 12 seconds
  const finalizedSlot = finalizedEpoch * 32;
  // Approximate: mainnet genesis timestamp is 1606824023, slot 0
  const GENESIS_TIMESTAMP = 1_606_824_023;
  const SECONDS_PER_SLOT = 12;
  const finalizedTimestamp = GENESIS_TIMESTAMP + finalizedSlot * SECONDS_PER_SLOT;

  // Step 3: Find the block closest to the finalized slot timestamp
  const blockResp = await fetch(executionRpcUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "eth_getBlockByNumber",
      params: ["finalized", false],
    }),
  });
  const blockData = (await blockResp.json()) as {
    result: { number: string };
  };
  const finalizedBlockNumber = parseInt(blockData.result.number, 16);

  return txBlockNumber <= finalizedBlockNumber;
}
```

## D1 Payment Status Tracking

Store confirmation state in D1 alongside the blockchain-specific metadata:

```sql
-- migrations/0011_crypto_payments.sql
CREATE TABLE IF NOT EXISTS crypto_payments (
  id                     TEXT PRIMARY KEY,
  order_id               TEXT NOT NULL,
  network                TEXT NOT NULL,   -- bitcoin | ethereum | solana | ...
  txid                   TEXT NOT NULL,
  amount_crypto          TEXT NOT NULL,   -- stored as string to avoid float loss
  amount_usd_cents       INTEGER NOT NULL,
  required_confirmations INTEGER NOT NULL,
  current_confirmations  INTEGER NOT NULL DEFAULT 0,
  status                 TEXT NOT NULL DEFAULT 'pending',
  -- pending | confirming | confirmed | failed | expired
  block_height           INTEGER,
  confirmed_at           TEXT,
  expires_at             TEXT NOT NULL,  -- payments expire after 15–60 min
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL,
  UNIQUE (network, txid)
);

CREATE INDEX idx_cp_order  ON crypto_payments (order_id);
CREATE INDEX idx_cp_status ON crypto_payments (status, network);
```

## Anti-patterns

- **Using 0-confirmations ("0-conf") for anything above micro-transactions**: 0-conf is appropriate only for low-value in-person transactions with trusted parties. For online payments, a single mempool broadcast is trivially replaceable with RBF (Replace-By-Fee) on Bitcoin.
- **Applying Bitcoin confirmation thresholds to proof-of-stake chains**: PoS chains with economic finality do not share PoW's probabilistic model. Waiting 6 confirmations on Ethereum post-Merge is unnecessary (each block finalizes within ~13 minutes via checkpoints).
- **Treating `confirmed` as finalized on Solana**: Solana's `confirmed` status means a supermajority voted, but the slot is not yet permanently rooted. A validator outage could cause a short fork at this level. Always use `finalized` for payments.
- **Ignoring chain reorganizations after "confirmed"**: Store the `block_height` and re-verify on each poll. If a block height changes after "confirmed", the transaction has been reorganized and should revert to `pending`.
- **Hardcoding confirmation thresholds in business logic**: Store `required_confirmations` per payment row. This allows tuning per-order risk without redeployment.

## Gotchas

- Bitcoin's average block time is 10 minutes but has high variance (occasionally 30+ minutes between blocks due to proof-of-work randomness). Display a live estimate ("~3 blocks remaining, ~25 min") rather than a fixed countdown.
- Ethereum's slot time is 12 seconds but a missed slot (no block produced) shifts subsequent block numbers. Do not assume `block_number + 64 blocks = finalized`; always query the Beacon API directly.
- Solana's `getSignatureStatuses` only searches recent history by default. Pass `searchTransactionHistory: true` for transactions older than ~5 minutes or your node's retention window.
- ERC-20 token transfers (USDT, USDC) are embedded inside Ethereum transaction logs, not the transaction value field. Confirm using `eth_getLogs` filtered by the ERC-20 `Transfer` event topic, not the transaction's `value` field (which will be 0 ETH).
- The TRON network has experienced periods of validator centralization. For high-value TRON payments, consider waiting for 27 confirmations (one full Super Representative rotation).
- Mempool RPC providers rate-limit polling. Use exponential backoff and cache the chain tip height between payment polls to reduce API calls.

## Verification

```bash
# Check confirmation count for a Bitcoin txid via mempool.space
curl -s "https://mempool.space/api/tx/TXID/status" | jq .

# Get current Bitcoin tip height
curl -s "https://mempool.space/api/blocks/tip/height"

# Check Solana signature status
curl -s https://api.mainnet-beta.solana.com \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"getSignatureStatuses",
    "params":[["SIGNATURE"], {"searchTransactionHistory":true}]
  }' | jq .result.value[0].confirmationStatus

# Ethereum finalized block
curl -s https://YOUR_ETH_RPC \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_getBlockByNumber","params":["finalized",false]}' \
  | jq .result.number
```

```typescript
// Unit-test BTC confirmation thresholds
const cases: [number, number][] = [
  [10, 3],
  [100, 3],
  [500, 3],
  [1001, 6],
  [9999, 6],
];
for (const [usd, expected] of cases) {
  const got = btcRequiredConfirmations(usd);
  console.assert(got === expected, `$${usd} → ${got} (expected ${expected})`);
}
```

## Related

- `crypto-payments-integration.md` — general crypto payment gateway integration
- `crypto-payments-nowpayments-settlement.md` — settlement flow with NowPayments
- `crypto-price-volatility-handling.md` — handling price movement during confirmation wait
- `payment-state-machine-design.md` — modeling payment states in D1
- `payment-audit-logging.md` — audit trail for crypto payment events

## Sources

- https://developer.bitcoin.org/devguide/p2p_network.html#transaction-broadcasting
- https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/finality/
- https://docs.solana.com/developing/clients/jsonrpc-api#configuring-state-commitment
- https://mempool.space/api
- https://beaconcha.in/api/v1
- https://nicehash.com/profitability-calculator (hashrate cost reference for 51% attack estimation)
