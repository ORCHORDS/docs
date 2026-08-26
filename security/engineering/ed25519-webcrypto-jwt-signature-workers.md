# Ed25519 JWT and Signature Verification with Web Crypto API in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to verify cryptographic signatures inside a Cloudflare Worker — either bare Ed25519 signatures on webhook payloads or JWT tokens signed with the EdDSA algorithm. The Node.js `crypto` module is unavailable, and pulling in a full npm cryptography library adds unnecessary bundle weight and supply-chain surface area.

The Web Crypto API (`SubtleCrypto`) is available in every Workers runtime and supports Ed25519 natively since the V8 10.x engine. Using it correctly avoids the subtle mistakes that plague custom implementations: wrong key formats, synchronous comparisons, and missing algorithm identifiers.

## Context

Cloudflare Workers run in a V8 isolate that exposes the `crypto.subtle` global conforming to the W3C Web Cryptography API specification. Ed25519 (EdDSA on Curve25519) is defined in RFC 8032 and has been added to the Web Crypto spec under the `"Ed25519"` algorithm identifier. Because Ed25519 is deterministic (no random nonce during signing), replay attacks must be prevented at the application layer — the signature alone does not prove freshness.

Workers cannot import raw `.pem` files directly; keys must be imported as JWK (JSON Web Key) objects or as raw 32-byte public key buffers. Storing the public key as a Worker secret in base64url or JWK format is the recommended approach so it never appears in source code.

## Importing an Ed25519 Public Key

Ed25519 public keys are 32 bytes. They can be stored as base64url strings in Worker secrets and imported at runtime. Import once per isolate lifetime using a module-level variable to avoid re-parsing on every request.

```typescript
// src/crypto.ts

let cachedPublicKey: CryptoKey | null = null;

/**
 * Import an Ed25519 public key from a base64url-encoded 32-byte string.
 * The key is cached in module scope so it is imported once per isolate.
 */
export async function getPublicKey(base64urlKey: string): Promise<CryptoKey> {
  if (cachedPublicKey) return cachedPublicKey;

  const raw = base64UrlDecode(base64urlKey);
  if (raw.byteLength !== 32) {
    throw new Error(`Ed25519 public key must be 32 bytes, got ${raw.byteLength}`);
  }

  cachedPublicKey = await crypto.subtle.importKey(
    "raw",
    raw,
    { name: "Ed25519" },
    false,   // not extractable
    ["verify"]
  );

  return cachedPublicKey;
}

function base64UrlDecode(input: string): ArrayBuffer {
  // Pad to multiple of 4
  const padded = input.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? 0 : 4 - (padded.length % 4);
  const base64 = padded + "=".repeat(pad);
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
```

## Verifying a Raw Ed25519 Signature

Webhook providers like GitHub or Discord send a raw 64-byte signature in a request header, usually hex or base64-encoded. Verify it against the raw request body bytes, not a parsed string.

```typescript
// src/webhook-verify.ts
import { getPublicKey } from "./crypto";

interface Env {
  WEBHOOK_PUBLIC_KEY: string; // base64url 32-byte Ed25519 public key in secret
}

export async function verifyWebhookSignature(
  request: Request,
  env: Env
): Promise<boolean> {
  const signatureHex = request.headers.get("X-Signature-Ed25519");
  const timestamp = request.headers.get("X-Signature-Timestamp");

  if (!signatureHex || !timestamp) return false;

  // Reject stale timestamps (±5 minutes)
  const ts = parseInt(timestamp, 10);
  if (isNaN(ts) || Math.abs(Date.now() / 1000 - ts) > 300) {
    return false;
  }

  const body = await request.text();
  const message = new TextEncoder().encode(timestamp + body);

  // Decode hex signature to bytes
  if (signatureHex.length !== 128) return false; // 64 bytes = 128 hex chars
  const sigBytes = new Uint8Array(64);
  for (let i = 0; i < 64; i++) {
    sigBytes[i] = parseInt(signatureHex.slice(i * 2, i * 2 + 2), 16);
  }

  const publicKey = await getPublicKey(env.WEBHOOK_PUBLIC_KEY);

  return crypto.subtle.verify(
    "Ed25519",
    publicKey,
    sigBytes.buffer,
    message
  );
}
```

## Verifying EdDSA JWTs (jose-compatible)

JWTs signed with `alg: "EdDSA"` carry the signature as base64url in the third segment. A minimal verifier that avoids full library overhead:

```typescript
// src/jwt-verify.ts
import { getPublicKey } from "./crypto";

interface JWTPayload {
  sub: string;
  iat: number;
  exp: number;

}

export async function verifyEdDSAJWT(
  token: string,
  publicKeyBase64url: string,
  expectedAudience?: string
): Promise<JWTPayload> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Malformed JWT");

  const [headerB64, payloadB64, sigB64] = parts;

  // Verify header declares EdDSA
  const header = JSON.parse(
    new TextDecoder().decode(base64UrlDecodeToBytes(headerB64))
  );
  if (header.alg !== "EdDSA") {
    throw new Error(`Expected EdDSA, got ${header.alg}`);
  }

  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = base64UrlDecodeToBytes(sigB64);

  const publicKey = await getPublicKey(publicKeyBase64url);

  const valid = await crypto.subtle.verify(
    "Ed25519",
    publicKey,
    signature,
    signingInput
  );

  if (!valid) throw new Error("JWT signature verification failed");

  const payload: JWTPayload = JSON.parse(
    new TextDecoder().decode(base64UrlDecodeToBytes(payloadB64))
  );

  const now = Math.floor(Date.now() / 1000);
  if (payload.exp && payload.exp < now) throw new Error("JWT expired");
  if (payload.iat && payload.iat > now + 60) throw new Error("JWT issued in the future");

  if (expectedAudience) {
    const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
    if (!aud.includes(expectedAudience)) {
      throw new Error(`Audience mismatch: expected ${expectedAudience}`);
    }
  }

  return payload;
}

function base64UrlDecodeToBytes(input: string): Uint8Array {
  const padded = input.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? 0 : 4 - (padded.length % 4);
  const binary = atob(padded + "=".repeat(pad));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
```

## Generating a Signing Keypair (offline / CI)

Key generation happens offline or in a CI step. Never generate keys inside a Worker.

```typescript
// scripts/generate-ed25519-keypair.ts  (run with: npx ts-node scripts/generate-ed25519-keypair.ts)
// Run in Node.js 20+ (also has Web Crypto)

const { subtle } = globalThis.crypto;

const keypair = await subtle.generateKey(
  { name: "Ed25519" },
  true,  // extractable for export
  ["sign", "verify"]
);

const privateJwk = await subtle.exportKey("jwk", keypair.privateKey);
const publicJwk = await subtle.exportKey("jwk", keypair.publicKey);

// Export public key as raw base64url for Worker secret
const rawPublic = await subtle.exportKey("raw", keypair.publicKey);
const publicBase64url = btoa(String.fromCharCode(...new Uint8Array(rawPublic)))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

console.log("Public key (base64url, store as WEBHOOK_PUBLIC_KEY secret):");
console.log(publicBase64url);
console.log("\nPrivate key JWK (store in your signing service, never in Workers):");
console.log(JSON.stringify(privateJwk, null, 2));
```

Store the public key with `wrangler secret put WEBHOOK_PUBLIC_KEY` and keep the private JWK in Vault or a dedicated signing service.

## Anti-patterns

- Comparing signatures with `===` string equality — use `crypto.subtle.verify` which is constant-time
- Importing the private key into a Worker — Workers should only verify, never sign production secrets
- Skipping the timestamp/nonce check — Ed25519 is deterministic so replayed requests have valid signatures
- Using `"RSASSA-PKCS1-v1_5"` or HMAC when the upstream provides Ed25519 — algorithm confusion leads to bypass
- Re-importing the `CryptoKey` on every request — cache at module scope to avoid the import overhead
- Accepting `alg: "none"` or allowing algorithm negotiation from the token itself

## Gotchas

- The `"Ed25519"` algorithm name is case-sensitive; `"ed25519"` throws `NotSupportedError`
- Raw key format exports 32 bytes; DER/SPKI format adds an 12-byte ASN.1 prefix — ensure you use the same format on both ends
- Workers running in compatibility date before 2023-03-01 may not support `"Ed25519"` in `importKey("raw", ...)` — set `compatibility_date = "2023-08-01"` or later in `wrangler.toml`
- `crypto.subtle.verify` returns `false` for invalid signatures rather than throwing — always check the boolean return value explicitly
- JWKs for Ed25519 use `crv: "Ed25519"` and `kty: "OKP"`, not `kty: "EC"`

## Verification

```bash
# 1. Generate a test keypair and sign a payload offline
node -e "
const {subtle} = crypto;
(async () => {
  const kp = await subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
  const msg = new TextEncoder().encode('hello');
  const sig = await subtle.sign('Ed25519', kp.privateKey, msg);
  const raw = await subtle.exportKey('raw', kp.publicKey);
  console.log('pub:', Buffer.from(raw).toString('base64url'));
  console.log('sig:', Buffer.from(sig).toString('hex'));
})();
"

# 2. Hit your Worker endpoint with the test signature and observe a 200
# 3. Flip one byte of the signature hex and confirm a 401
# 4. Replay a valid request 10 minutes later and confirm timestamp rejection
```

## Related

- `timing-safe-compare.md` — constant-time comparison patterns in Workers
- `cryptographic-agility-workers-subtlecrypto-migration.md` — migrating between algorithm identifiers
- `webhook-signature-verification-hmac.md` — HMAC-SHA256 webhook verification pattern
- `jwt-best-practices.md` — JWT validation checklist

## Sources

- W3C Web Cryptography API Specification — https://www.w3.org/TR/WebCryptoAPI/
- RFC 8032: Edwards-Curve Digital Signature Algorithm (EdDSA) — https://www.rfc-editor.org/rfc/rfc8032
- Cloudflare Workers Web Crypto API docs — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
