# Crypto Wallet Address Validation on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user pastes a wallet address into your withdrawal or payout form. Before you pass it to your payment processor or on-chain transaction, you need to confirm it is structurally valid for the target chain, has the correct checksum, is not on your internal blocklist, and is not a known mixer or sanctioned address. Sending funds to a malformed or wrong-chain address is irreversible. All of this must happen in under 100 ms at the edge without shipping heavy crypto libraries in a Worker bundle.

## Context

Wallet address validation covers two distinct concerns: **format validity** (is this a plausible address for the declared chain?) and **risk screening** (should we allow payouts to this address at all?). Format validation is pure computation — checksums, Base58 decoding, bech32 encoding — and can run in a Worker using Web Crypto and lightweight pure-JS utilities kept well inside the 1 MB script size limit. Risk screening calls an external API (TRM Labs, Chainalysis, or Elliptic) or checks an internal D1 blocklist. Combine both in a single Worker endpoint so the form gets one clean response.

---

## 1. Ethereum Address Validation (EIP-55 Checksum)

```typescript
// src/validators/ethereum.ts

// Keccak-256 via subtle is not available; use a minimal pure-JS implementation
// bundled at <3 KB (e.g. 'ethereum-cryptography/keccak' tree-shaken for Workers)
import { keccak256 } from 'ethereum-cryptography/keccak';
import { utf8ToBytes, bytesToHex } from 'ethereum-cryptography/utils';

export function isValidEthAddress(address: string): boolean {
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) return false;
  return checksumMatches(address);
}

function checksumMatches(address: string): boolean {
  const stripped = address.slice(2).toLowerCase();
  const hash = bytesToHex(keccak256(utf8ToBytes(stripped)));

  for (let i = 0; i < stripped.length; i++) {
    const char = stripped[i];
    if (!/[a-f]/.test(char)) continue; // digit — skip
    const hashNibble = parseInt(hash[i], 16);
    const expectedUpper = hashNibble >= 8;
    if (expectedUpper !== (address[i + 2] === char.toUpperCase())) {
      return false; // checksum mismatch
    }
  }
  return true;
}

// Normalise: return checksummed form or throw
export function toChecksumAddress(address: string): string {
  if (!isValidEthAddress(address)) throw new Error('Invalid Ethereum address');
  const stripped = address.slice(2).toLowerCase();
  const hash = bytesToHex(keccak256(utf8ToBytes(stripped)));
  return '0x' + stripped
    .split('')
    .map((c, i) => (parseInt(hash[i], 16) >= 8 ? c.toUpperCase() : c))
    .join('');
}
```

## 2. Bitcoin Address Validation (Legacy, SegWit P2SH, Bech32)

```typescript
// src/validators/bitcoin.ts
// Uses 'scure-base' (tree-shaken) for Base58Check; bech32 from 'bech32' package

import { base58check } from '@scure/base';
import { bech32 } from 'bech32';

type Network = 'mainnet' | 'testnet';

const VERSION_BYTES: Record<Network, number[]> = {
  mainnet: [0x00, 0x05],    // P2PKH, P2SH
  testnet: [0x6f, 0xc4],
};

export function isValidBitcoinAddress(address: string, network: Network = 'mainnet'): boolean {
  // Bech32 / native SegWit
  if (address.toLowerCase().startsWith('bc1') || address.toLowerCase().startsWith('tb1')) {
    try {
      const hrp = network === 'mainnet' ? 'bc' : 'tb';
      const decoded = bech32.decode(address);
      return decoded.prefix === hrp && decoded.words.length > 0;
    } catch {
      return false;
    }
  }

  // Base58Check: P2PKH or P2SH
  try {
    const decoded = base58check(null).decode(address); // returns Uint8Array
    const version = decoded[0];
    return VERSION_BYTES[network].includes(version);
  } catch {
    return false;
  }
}
```

## 3. Solana Address Validation (Ed25519 Public Key)

```typescript
// src/validators/solana.ts
import { base58 } from '@scure/base';

export function isValidSolanaAddress(address: string): boolean {
  try {
    const bytes = base58.decode(address);
    // Solana public keys are 32-byte Ed25519 points
    return bytes.length === 32;
  } catch {
    return false;
  }
}
```

## 4. Worker: Unified Validation Endpoint

```typescript
// src/index.ts
import { Env } from './types';
import { isValidEthAddress, toChecksumAddress } from './validators/ethereum';
import { isValidBitcoinAddress } from './validators/bitcoin';
import { isValidSolanaAddress } from './validators/solana';

type Chain = 'ethereum' | 'bitcoin' | 'solana' | 'polygon' | 'bnb';

const ETH_COMPATIBLE: Chain[] = ['ethereum', 'polygon', 'bnb'];

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { address, chain }: { address: string; chain: Chain } = await req.json();

    // 1. Format validation
    let formatValid = false;
    let normalised = address.trim();

    if (ETH_COMPATIBLE.includes(chain)) {
      formatValid = isValidEthAddress(normalised);
      if (formatValid) normalised = toChecksumAddress(normalised);
    } else if (chain === 'bitcoin') {
      formatValid = isValidBitcoinAddress(normalised, 'mainnet');
    } else if (chain === 'solana') {
      formatValid = isValidSolanaAddress(normalised);
    }

    if (!formatValid) {
      return Response.json({
        valid: false,
        error: `Invalid ${chain} address format.`,
      }, { status: 400 });
    }

    // 2. Internal blocklist (D1)
    const blocked = await env.DB.prepare(
      'SELECT reason FROM blocked_addresses WHERE address = ? AND chain = ?'
    ).bind(normalised.toLowerCase(), chain).first<{ reason: string }>();

    if (blocked) {
      return Response.json({
        valid: false,
        error: 'This address is not eligible to receive payouts.',
        reason: blocked.reason, // log server-side; strip before returning to client if needed
      }, { status: 403 });
    }

    // 3. Optional: external risk API (TRM Labs, etc.)
    if (env.TRM_API_KEY) {
      const risk = await screenWithTrm(normalised, chain, env.TRM_API_KEY);
      if (risk.blocked) {
        return Response.json({
          valid: false,
          error: 'Address flagged by risk screening. Contact support.',
        }, { status: 403 });
      }
    }

    return Response.json({ valid: true, address: normalised });
  },
};

async function screenWithTrm(
  address: string,
  chain: Chain,
  apiKey: string
): Promise<{ blocked: boolean }> {
  const res = await fetch('https://api.trmlabs.com/public/v1/sanctions/screening', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Basic ${btoa(apiKey + ':')}`,
    },
    body: JSON.stringify([{ address, chain }]),
  });
  if (!res.ok) return { blocked: false }; // fail open — log and alert separately
  const data: Array<{ isSanctioned: boolean }> = await res.json();
  return { blocked: data[0]?.isSanctioned ?? false };
}
```

## 5. D1 Blocklist Schema

```sql
-- migrations/0011_blocked_addresses.sql
CREATE TABLE IF NOT EXISTS blocked_addresses (
  address   TEXT NOT NULL,         -- lowercase
  chain     TEXT NOT NULL,
  reason    TEXT NOT NULL,         -- 'ofac' | 'mixer' | 'internal'
  added_at  INTEGER NOT NULL,
  added_by  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_blocked_addr_chain
  ON blocked_addresses (address, chain);
```

---

## Anti-patterns

- **Validating only with a regex** — a 42-character hex string passes a naive ETH regex but may have a wrong checksum, indicating a transcription error; always verify EIP-55 checksum.
- **Accepting a valid format as proof the address is reachable** — a valid Bitcoin address on mainnet will silently accept funds sent to it even if nobody controls the private key. Format validity is necessary but not sufficient.
- **Running heavy crypto libraries (e.g. full bitcoinjs-lib) in a Worker** — they exceed 1 MB gzipped. Use tree-shaken packages: `@scure/base`, `bech32`, `ethereum-cryptography`.
- **Blocking on the external risk API** — if TRM or Chainalysis times out, fail open and queue the address for async screening rather than blocking the user.
- **Storing addresses case-sensitively in blocklists** — normalise to lowercase before storage and lookup; EVM checksummed and non-checksummed forms must match the same row.

## Gotchas

- EVM chains (Ethereum, Polygon, BNB) share the same address format. The chain parameter you accept does not change format validation, but it matters for the risk API call.
- Bech32m (taproot `bc1p…`) requires `bech32.decodeUnsafe` from the `bech32` package v2+; the older `bech32.decode` rejects it silently.
- Solana `SystemProgram.programId` (`1111…`) is a valid 32-byte key. If you want to reject known burn/program addresses, maintain an explicit list.
- TRM Labs' API returns HTTP 200 even for sanctioned addresses — you must inspect the `isSanctioned` field, not the status code.
- Web Crypto's `SubtleCrypto` does not expose Keccak-256 (it is SHA-3, which differs). You must bundle a pure-JS Keccak implementation for Ethereum checksum validation.

## Verification

```bash
# Valid checksummed ETH address
curl -X POST https://your-worker.workers.dev/validate-address \
  -H 'Content-Type: application/json' \
  -d '{"address":"0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed","chain":"ethereum"}'
# expect {"valid":true,"address":"0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"}

# Wrong checksum (lowercase e should be uppercase E at position 9)
curl -X POST https://your-worker.workers.dev/validate-address \
  -H 'Content-Type: application/json' \
  -d '{"address":"0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed","chain":"ethereum"}'
# expect {"valid":false,"error":"Invalid ethereum address format."}

# Solana
curl -X POST https://your-worker.workers.dev/validate-address \
  -H 'Content-Type: application/json' \
  -d '{"address":"9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM","chain":"solana"}'
```

## Related

- `crypto-wallet-signature-verification-web-crypto-workers.md`
- `ofac-sanctions-screening-workers.md`
- `erc20-token-payment-verification-workers.md`
- `crypto-payment-address-reuse-prevention-d1.md`
- `usdt-trc20-payment-verification-workers.md`

## Sources

- https://eips.ethereum.org/EIPS/eip-55
- https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki
- https://docs.trmlabs.com/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://github.com/paulmillr/scure-base
