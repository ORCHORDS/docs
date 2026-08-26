# Crypto Wallet Signature Verification with Workers Web Crypto

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your application needs to prove that the user who initiates a payment or signs a transaction actually controls the stated on-chain address — without a backend database of passwords or OAuth tokens. Wallet signature verification (sign-in-with-Ethereum / SIWS, or Solana wallet signing) lets you gate API calls by cryptographic proof of key ownership, all enforced at the Cloudflare Workers edge using the native `SubtleCrypto` API.

---

## Context

EVM wallets (MetaMask, Coinbase Wallet) sign an EIP-191 personal message using secp256k1 ECDSA. The resulting 65-byte signature encodes `r`, `s`, and a recovery id (`v`) that lets you reconstruct the signer's public key and therefore derive their Ethereum address without knowing the key in advance. Solana wallets use Ed25519, which Workers `SubtleCrypto` supports natively since compatibility date `2024-09-23`.

Neither the user's private key nor their seed phrase ever leaves the client — the Workers endpoint only receives the message, the signature, and the claimed address/public key, then rejects requests that do not match.

---

## 1. Nonce-based Challenge Generation (Replay Prevention)

```typescript
// src/auth/challenge.ts

export interface Challenge {
  nonce: string;
  issuedAt: string;
  expiresAt: string;
}

export function buildChallenge(address: string): { message: string; challenge: Challenge } {
  const nonce = crypto.randomUUID();
  const issuedAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();

  const message =
    `Sign this message to authenticate with example.com\n` +
    `Address: ${address}\n` +
    `Nonce: ${nonce}\n` +
    `Issued: ${issuedAt}\n` +
    `Expires: ${expiresAt}`;

  return { message, challenge: { nonce, issuedAt, expiresAt } };
}

export function isChallengeExpired(challenge: Challenge): boolean {
  return Date.now() > new Date(challenge.expiresAt).getTime();
}
```

---

## 2. Solana Ed25519 Signature Verification

```typescript
// src/auth/solana.ts

export async function verifySolanaSignature(
  message: string,
  signatureBase64: string,
  publicKeyBase58: string
): Promise<boolean> {
  // Decode base58 public key to raw bytes
  const pubKeyBytes = base58Decode(publicKeyBase58);
  const sigBytes = Uint8Array.from(atob(signatureBase64), c => c.charCodeAt(0));
  const msgBytes = new TextEncoder().encode(message);

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    pubKeyBytes,
    { name: 'Ed25519' },
    false,
    ['verify']
  );

  return crypto.subtle.verify('Ed25519', cryptoKey, sigBytes, msgBytes);
}

// Minimal base58 decoder (alphabet: Bitcoin/Solana variant)
const BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

function base58Decode(input: string): Uint8Array {
  let result = 0n;
  for (const char of input) {
    const index = BASE58_ALPHABET.indexOf(char);
    if (index < 0) throw new Error(`Invalid base58 char: ${char}`);
    result = result * 58n + BigInt(index);
  }
  const hex = result.toString(16).padStart(64, '0');
  return Uint8Array.from(hex.match(/.{2}/g)!.map(b => parseInt(b, 16)));
}
```

---

## 3. Ethereum EIP-191 Signature Verification

Cloudflare Workers do not expose secp256k1 natively, but you can implement ecrecover using a compact pure-JS library bundled at build time, or use the following pattern with a wasm bundle:

```typescript
// src/auth/ethereum.ts
// Requires: npm install @noble/secp256k1 @noble/hashes
import { secp256k1 } from '@noble/secp256k1';
import { keccak_256 } from '@noble/hashes/sha3';

function toEthereumSignedMessage(message: string): Uint8Array {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return new TextEncoder().encode(prefix + message);
}

export function recoverEthAddress(message: string, signatureHex: string): string {
  const msgHash = keccak_256(toEthereumSignedMessage(message));
  const sigBytes = hexToBytes(signatureHex.replace('0x', ''));

  const r = sigBytes.slice(0, 32);
  const s = sigBytes.slice(32, 64);
  let v = sigBytes[64];
  if (v >= 27) v -= 27; // normalize

  const sig = secp256k1.Signature.fromCompact(
    [...r, ...s].map(b => b.toString(16).padStart(2, '0')).join('')
  ).addRecoveryBit(v);

  const pubKey = sig.recoverPublicKey(msgHash);
  const pubKeyBytes = pubKey.toRawBytes(false).slice(1); // drop 0x04 prefix
  const addressHash = keccak_256(pubKeyBytes);
  return '0x' + bytesToHex(addressHash.slice(12));
}

function hexToBytes(hex: string): Uint8Array {
  return Uint8Array.from(hex.match(/.{2}/g)!.map(b => parseInt(b, 16)));
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## 4. Worker Endpoint: Verify and Issue Session Token

```typescript
// src/index.ts

import { buildChallenge, isChallengeExpired } from './auth/challenge';
import { verifySolanaSignature } from './auth/solana';
import { recoverEthAddress } from './auth/ethereum';

interface Env {
  KV: KVNamespace;
  JWT_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Step 1: issue challenge
    if (url.pathname === '/auth/challenge' && request.method === 'POST') {
      const { address, chain } = await request.json<{ address: string; chain: 'solana' | 'evm' }>();
      const { message, challenge } = buildChallenge(address);

      // Store nonce keyed by address; TTL matches expiry
      await env.KV.put(`nonce:${address}`, JSON.stringify(challenge), { expirationTtl: 300 });

      return Response.json({ message });
    }

    // Step 2: verify signature and issue JWT
    if (url.pathname === '/auth/verify' && request.method === 'POST') {
      const { address, signature, chain, message } =
        await request.json<{ address: string; signature: string; chain: string; message: string }>();

      const raw = await env.KV.get(`nonce:${address}`);
      if (!raw) return new Response('Challenge not found or expired', { status: 401 });

      const challenge = JSON.parse(raw);
      if (isChallengeExpired(challenge)) {
        await env.KV.delete(`nonce:${address}`);
        return new Response('Challenge expired', { status: 401 });
      }

      let verified = false;
      if (chain === 'solana') {
        verified = await verifySolanaSignature(message, signature, address);
      } else {
        const recovered = recoverEthAddress(message, signature);
        verified = recovered.toLowerCase() === address.toLowerCase();
      }

      if (!verified) return new Response('Invalid signature', { status: 401 });

      // Delete nonce — single-use
      await env.KV.delete(`nonce:${address}`);

      const token = await issueJwt(address, chain, env.JWT_SECRET);
      return Response.json({ token });
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function issueJwt(address: string, chain: string, secret: string): Promise<string> {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ sub: address, chain, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600 }));
  const data = `${header}.${payload}`;
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${data}.${sigB64}`;
}
```

---

## 5. KV Namespace Binding

```toml
# wrangler.toml
name = "wallet-auth"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding  = "KV"
id       = "<your-kv-namespace-id>"

# wrangler secret put JWT_SECRET
```

---

## Anti-patterns

- **Reusing nonces** — nonces must be deleted after a single successful verification to prevent replay; a used challenge stored permanently is equivalent to no nonce at all.
- **Case-sensitive Ethereum address comparison** — EVM addresses are checksummed (EIP-55) but case-insensitive for identity; always compare `.toLowerCase()`.
- **Verifying before storing the challenge** — if you verify the signature without first retrieving a stored nonce, an attacker can craft any valid message offline and submit it.
- **Long challenge TTL** — five minutes is the standard; longer windows give attackers more time to intercept and reuse a signed message.

---

## Gotchas

- Cloudflare Workers support Ed25519 natively as of compatibility date `2024-09-23`; earlier dates will throw on `importKey` with algorithm `Ed25519`.
- `@noble/secp256k1` must be bundled at build time — Workers cannot `require()` node built-ins.
- Solana Phantom signs messages as UTF-8 bytes; Ledger hardware wallets may sign `MessageV0` transactions instead of raw text — validate message format server-side.
- EIP-4361 (Sign-In with Ethereum) mandates additional fields (domain, URI, version); parse and validate these if you need SIWE standard compliance.
- Ed25519 public keys on Solana are 32 bytes; the base58-decoded key must be exactly 32 bytes or `importKey` throws `DataError`.

---

## Verification

```bash
# Test Solana signature (use Solana CLI):
# solana-keygen sign-file /path/to/keypair.json <(echo -n "your challenge message")
# Then POST to /auth/verify with the resulting base64 signature

# Test EVM signature (use cast from Foundry):
# cast wallet sign --private-key 0xYOUR_KEY "your challenge message"
curl -X POST https://wallet-auth.workers.dev/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"address":"0xABC...","signature":"0x...","chain":"evm","message":"Sign this message..."}'
# Expected: {"token":"eyJ..."}
```

---

## Related

- `crypto-payments-integration.md`
- `circle-usdc-programmable-payments-workers.md`
- `solana-helius-webhook-payment-verification.md`
- `idempotency-keys-payment-apis.md`

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://eips.ethereum.org/EIPS/eip-191
- https://eips.ethereum.org/EIPS/eip-4361
- https://docs.solana.com/developing/clients/javascript-reference#signing-messages
- https://paulmillr.com/noble/
