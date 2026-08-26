# Crypto Gas Fee Estimation Workers Real-Time

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need to show users an accurate gas fee estimate before they submit an on-chain transaction (ETH, Polygon, Arbitrum, or Solana) and want to serve those estimates from the Cloudflare edge with sub-50 ms latency and freshness within one block.

## Context
Gas prices are block-scoped and volatile; a stale estimate silently under-funds a transaction, causing it to hang. Workers fetch estimates from RPC providers (Alchemy, Infura, Helius) and cache results in KV with a short TTL (5–15 seconds). EIP-1559 networks expose `eth_feeHistory` for accurate base-fee + priority-fee decomposition; legacy networks use `eth_gasPrice`. Solana uses a different priority-fee model via `getRecentPrioritizationFees`.

## EIP-1559 Fee Estimation (Ethereum / Polygon / Arbitrum)

```typescript
// src/evm-gas.ts
export interface Env {
  GAS_CACHE: KVNamespace;
  ALCHEMY_API_KEY: string;
  ALCHEMY_ETH_URL: string;   // e.g. https://eth-mainnet.g.alchemy.com/v2/
  ALCHEMY_POLY_URL: string;
  ALCHEMY_ARB_URL: string;
}

export interface EvmGasEstimate {
  baseFeeWei: bigint;
  priorityFeeWei: bigint;     // 50th-percentile tip
  fastPriorityFeeWei: bigint; // 90th-percentile tip
  maxFeeWei: bigint;          // baseFee * 1.25 + priorityFee (EIP-1559 cap)
  fetchedAt: number;
  blockNumber: number;
}

const NETWORKS: Record<string, string> = {
  eth: 'ALCHEMY_ETH_URL',
  polygon: 'ALCHEMY_POLY_URL',
  arbitrum: 'ALCHEMY_ARB_URL',
};

async function jsonRpc(url: string, method: string, params: unknown[]): Promise<unknown> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  const json = await res.json<{ result: unknown; error?: { message: string } }>();
  if (json.error) throw new Error(`RPC error: ${json.error.message}`);
  return json.result;
}

export async function getEvmGasEstimate(
  env: Env,
  network: 'eth' | 'polygon' | 'arbitrum'
): Promise<EvmGasEstimate> {
  const cacheKey = `gas:evm:${network}`;
  const cached = await env.GAS_CACHE.get(cacheKey, 'json') as EvmGasEstimate | null;
  if (cached) {
    // Return with bigint fields restored from JSON strings
    return {
      ...cached,
      baseFeeWei: BigInt(cached.baseFeeWei),
      priorityFeeWei: BigInt(cached.priorityFeeWei),
      fastPriorityFeeWei: BigInt(cached.fastPriorityFeeWei),
      maxFeeWei: BigInt(cached.maxFeeWei),
    };
  }

  const urlKey = NETWORKS[network] as keyof Env;
  const rpcUrl = (env[urlKey] as string) + env.ALCHEMY_API_KEY;

  // Fetch last 5 blocks of fee history with 25th and 75th percentile rewards
  const feeHistory = await jsonRpc(rpcUrl, 'eth_feeHistory', [
    '0x5',       // 5 blocks
    'latest',
    [25, 50, 90], // reward percentiles
  ]) as {
    baseFeePerGas: string[];
    reward: string[][];
    oldestBlock: string;
  };

  // Latest pending base fee is the last entry
  const baseFeeWei = BigInt(feeHistory.baseFeePerGas.at(-1) ?? '0x0');

  // Median across blocks for each percentile
  const p50Rewards = feeHistory.reward.map((r) => BigInt(r[1] ?? '0x0'));
  const p90Rewards = feeHistory.reward.map((r) => BigInt(r[2] ?? '0x0'));
  const priorityFeeWei = median(p50Rewards);
  const fastPriorityFeeWei = median(p90Rewards);

  // EIP-1559: maxFeePerGas = baseFee * 1.25 + maxPriorityFee
  const maxFeeWei = (baseFeeWei * 125n) / 100n + fastPriorityFeeWei;

  const blockNumberHex = await jsonRpc(rpcUrl, 'eth_blockNumber', []) as string;
  const blockNumber = parseInt(blockNumberHex, 16);

  const estimate: EvmGasEstimate = {
    baseFeeWei,
    priorityFeeWei,
    fastPriorityFeeWei,
    maxFeeWei,
    fetchedAt: Date.now(),
    blockNumber,
  };

  // Cache 10 seconds — Ethereum block time is 12 s; Polygon/Arbitrum faster
  await env.GAS_CACHE.put(cacheKey, JSON.stringify({
    ...estimate,
    baseFeeWei: estimate.baseFeeWei.toString(),
    priorityFeeWei: estimate.priorityFeeWei.toString(),
    fastPriorityFeeWei: estimate.fastPriorityFeeWei.toString(),
    maxFeeWei: estimate.maxFeeWei.toString(),
  }), { expirationTtl: 10 });

  return estimate;
}

function median(values: bigint[]): bigint {
  const sorted = [...values].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2n
    : sorted[mid];
}
```

## Total Transaction Cost Calculator

Translate raw gas estimates into human-readable USD costs using a cached ETH price.

```typescript
// src/gas-cost.ts
export async function estimateTransactionCostUsd(
  env: Env,
  gasUnits: bigint,
  estimate: EvmGasEstimate,
  ethPriceUsd: number
): Promise<{ standardUsd: number; fastUsd: number; maxFeeUsd: number }> {
  const WEI_PER_ETH = 10n ** 18n;

  const standardCostWei = gasUnits * (estimate.baseFeeWei + estimate.priorityFeeWei);
  const fastCostWei = gasUnits * (estimate.baseFeeWei + estimate.fastPriorityFeeWei);
  const maxCostWei = gasUnits * estimate.maxFeeWei;

  const toUsd = (wei: bigint): number =>
    (Number(wei) / Number(WEI_PER_ETH)) * ethPriceUsd;

  return {
    standardUsd: toUsd(standardCostWei),
    fastUsd: toUsd(fastCostWei),
    maxFeeUsd: toUsd(maxCostWei),
  };
}
```

## Solana Priority Fee Estimation

Solana uses compute-unit pricing distinct from Ethereum. Fetch recent prioritization fees from a validator RPC and compute the 75th percentile.

```typescript
// src/solana-gas.ts
export interface SolanaFeeEstimate {
  minPriorityFee: number;   // microlamports per compute unit
  medianPriorityFee: number;
  highPriorityFee: number;  // 75th percentile
  fetchedAt: number;
}

export async function getSolanaFeeEstimate(
  env: Env & { HELIUS_API_KEY: string },
  accountKeys?: string[]  // optional: filter by program accounts for relevance
): Promise<SolanaFeeEstimate> {
  const cacheKey = 'gas:solana:priority';
  const cached = await env.GAS_CACHE.get(cacheKey, 'json') as SolanaFeeEstimate | null;
  if (cached) return cached;

  const rpcUrl = `https://mainnet.helius-rpc.com/?api-key=<redacted-secret>

  const result = await jsonRpc(rpcUrl, 'getRecentPrioritizationFees', [
    accountKeys ?? [],
  ]) as { slot: number; prioritizationFee: number }[];

  const fees = result.map((r) => r.prioritizationFee).sort((a, b) => a - b);
  const p50 = fees[Math.floor(fees.length * 0.50)] ?? 0;
  const p75 = fees[Math.floor(fees.length * 0.75)] ?? 0;

  const estimate: SolanaFeeEstimate = {
    minPriorityFee: fees[0] ?? 0,
    medianPriorityFee: p50,
    highPriorityFee: p75,
    fetchedAt: Date.now(),
  };

  await env.GAS_CACHE.put(cacheKey, JSON.stringify(estimate), { expirationTtl: 5 });
  return estimate;
}
```

## Worker API Handler

```typescript
// src/index.ts
import type { Env } from './evm-gas';
import { getEvmGasEstimate } from './evm-gas';
import { getSolanaFeeEstimate } from './solana-gas';
import { estimateTransactionCostUsd } from './gas-cost';

const ETH_PRICE_USD = 3500; // Replace with a live price fetch from your preferred oracle

export default {
  async fetch(request: Request, env: Env & { HELIUS_API_KEY: string }): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/gas/evm') {
      const network = (url.searchParams.get('network') ?? 'eth') as 'eth' | 'polygon' | 'arbitrum';
      const gasUnits = BigInt(url.searchParams.get('units') ?? '21000');
      const estimate = await getEvmGasEstimate(env, network);
      const costs = await estimateTransactionCostUsd(env, gasUnits, estimate, ETH_PRICE_USD);

      return Response.json({
        network,
        blockNumber: estimate.blockNumber,
        baseFeeGwei: Number(estimate.baseFeeWei) / 1e9,
        priorityFeeGwei: Number(estimate.priorityFeeWei) / 1e9,
        fastPriorityFeeGwei: Number(estimate.fastPriorityFeeWei) / 1e9,
        maxFeeGwei: Number(estimate.maxFeeWei) / 1e9,
        estimatedCostUsd: costs,
        fetchedAt: estimate.fetchedAt,
      });
    }

    if (url.pathname === '/gas/solana') {
      const estimate = await getSolanaFeeEstimate(env);
      return Response.json(estimate);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Anti-patterns
- Do not use `eth_gasPrice` for EIP-1559 networks — it returns a blended value that over-estimates base fee and ignores priority fee decomposition.
- Never cache gas estimates for more than 15 seconds on high-throughput chains like Polygon (2-second blocks); staleness leads to under-funded transactions.
- Avoid fetching gas inside the transaction-signing path on the client — the estimate can be stale by the time the user confirms; always fetch fresh at submit time.
- Do not use a single percentile from a single block; multi-block median across reward percentiles smooths out anomalous blocks and MEV spikes.
- Never expose raw RPC API keys in client responses — proxy through Workers only.

## Gotchas
- `eth_feeHistory` returns `baseFeePerGas` with one extra entry (the next pending block); always use `.at(-1)` for the current estimate.
- Arbitrum's gas model differs from Ethereum mainnet — L2 gas prices include an L1 data fee component; `eth_feeHistory` on Arbitrum reflects L2 execution only.
- Solana `getRecentPrioritizationFees` returns microlamports per compute unit, not per transaction; multiply by the compute unit budget (default 200,000) for total fee.
- BigInt values cannot be serialized with `JSON.stringify` directly — always convert to strings before KV storage and parse back on read.
- Workers KV has eventual consistency; edge nodes in different PoPs may serve slightly different cached values during the TTL window.

## Verification
1. Call `GET /gas/evm?network=eth&units=21000` and confirm `baseFeeGwei` is non-zero and changes between calls separated by 12+ seconds.
2. Call with `?network=polygon` and verify the base fee is substantially lower than Ethereum mainnet.
3. Set KV TTL to 1 second in dev, make two rapid requests, and confirm both return identical `fetchedAt` within the same second (cache hit).
4. Call `GET /gas/solana` and confirm `highPriorityFee` is a positive integer in microlamports.
5. Verify `estimatedCostUsd.standardUsd` is in a plausible range for the current ETH price.

## Related
- `crypto-payments-integration.md`
- `usdc-stablecoin-settlement-solana-webhooks.md`
- `solana-helius-webhook-payment-verification.md`
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md`
- `crypto-wallet-signature-verification-web-crypto-workers.md`

## Sources
- https://eips.ethereum.org/EIPS/eip-1559
- https://docs.alchemy.com/reference/eth-feehistory
- https://docs.helius.dev/solana-rpc-nodes/alpha-priority-fee-api
