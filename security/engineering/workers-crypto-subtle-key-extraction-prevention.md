# Workers CryptoSubtle Key Extraction Prevention

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Worker that handles cryptographic keys via the Web Crypto API (`crypto.subtle`) can inadvertently export raw key material through improper `extractable` flag usage, insecure key serialization, or by exposing key bytes in error messages, logs, or response bodies.

## Context
The Workers runtime exposes the W3C Web Cryptography API (`crypto.subtle`). Keys created with `extractable: true` can be serialized back to raw bytes via `crypto.subtle.exportKey()`. If key material is logged, included in error responses, stored in KV without encryption, or passed through service bindings without care, it can leak. The correct model is to mark all production keys `extractable: false` and rely on the `CryptoKey` object handle for all operations without ever materializing raw bytes in application code.

---

## Section 1 — Always Import Keys as Non-Extractable

When loading a secret (from a Workers secret, environment variable, or KV) into a `CryptoKey`, always set `extractable: false`. This is enforced by the runtime—any subsequent call to `exportKey()` on such a key will throw.

```typescript
interface Env {
  SIGNING_KEY_HEX: string; // 32-byte hex secret from Workers secrets
}

let _signingKey: CryptoKey | null = null;

async function getSigningKey(env: Env): Promise<CryptoKey> {
  if (_signingKey) return _signingKey;

  const rawBytes = hexToBytes(env.SIGNING_KEY_HEX);

  // extractable: false — the key bytes can never be exported
  _signingKey = await crypto.subtle.importKey(
    'raw',
    rawBytes,
    { name: 'HMAC', hash: 'SHA-256' },
    false, // <-- NON-EXTRACTABLE
    ['sign', 'verify']
  );

  // Zero out the raw bytes array immediately after import
  rawBytes.fill(0);

  return _signingKey;
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

export async function signPayload(env: Env, data: string): Promise<string> {
  const key = await getSigningKey(env);
  const sig = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(data)
  );
  return bufferToBase64Url(sig);
}

function bufferToBase64Url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}
```

---

## Section 2 — Generating Keys: Non-Extractable by Default

When generating ephemeral or long-lived keys (e.g., for ECDH, AES-GCM), set `extractable: false` unless you explicitly need to export the key for storage or transmission. For keys that must be persisted, export once, store securely, then re-import as non-extractable on every Worker instantiation.

```typescript
// GOOD: generate non-extractable key for signing
const signingKey = await crypto.subtle.generateKey(
  { name: 'HMAC', hash: 'SHA-256', length: 256 },
  false, // non-extractable
  ['sign', 'verify']
);

// GOOD: generate extractable key pair, export public key only, store private as non-extractable
async function generateAndStoreKeyPair(env: Env): Promise<string> {
  const keyPair = await crypto.subtle.generateKey(
    { name: 'ECDSA', namedCurve: 'P-256' },
    true, // extractable — needed only for initial storage
    ['sign', 'verify']
  );

  // Export private key material for secure storage (Workers secrets / KV encrypted)
  const privateJwk = await crypto.subtle.exportKey('jwk', keyPair.privateKey);
  const privateKeyJson = JSON.stringify(privateJwk);

  // Zero sensitive fields from the exported JWK after use
  privateJwk.d = ''; // d is the private scalar

  // Store securely; in production use Workers secrets or an encrypted KV value
  await env.KV.put('keypair:private', privateKeyJson, { expirationTtl: 90 * 86400 });

  // Export public key (safe to distribute)
  const publicJwk = await crypto.subtle.exportKey('jwk', keyPair.publicKey);
  return JSON.stringify(publicJwk);
}

// On subsequent requests: re-import private key as NON-EXTRACTABLE
async function loadPrivateKey(env: Env): Promise<CryptoKey> {
  const stored = await env.KV.get('keypair:private');
  if (!stored) throw new Error('Private key not found');
  const jwk = JSON.parse(stored) as JsonWebKey;
  const key = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false, // <-- NON-EXTRACTABLE after loading from storage
    ['sign']
  );
  // Overwrite the parsed JWK d value
  jwk.d = '';
  return key;
}
```

---

## Section 3 — Prevent Key Material from Leaking via Errors or Logs

Raw key bytes must never appear in error messages, console output, or HTTP responses. Wrap crypto operations so that caught errors are sanitized before propagation.

```typescript
class CryptoError extends Error {
  constructor(message: string) {
    // Never include key material, hex strings, or base64 blobs in the message
    super(message);
    this.name = 'CryptoError';
  }
}

async function safeSign(key: CryptoKey, data: ArrayBuffer): Promise<ArrayBuffer> {
  try {
    return await crypto.subtle.sign('HMAC', key, data);
  } catch (e) {
    // Do NOT log the original error — it may contain key context in some runtimes
    throw new CryptoError('Signing operation failed');
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const key = await getSigningKey(env);
      const body = await request.arrayBuffer();
      const sig = await safeSign(key, body);
      return new Response(bufferToBase64Url(sig));
    } catch (e) {
      if (e instanceof CryptoError) {
        // Safe to surface generic message
        return new Response('Crypto operation failed', { status: 500 });
      }
      // Unknown errors: log internally (to Tail Worker), never return to client
      console.error('Unexpected error in crypto handler');
      return new Response('Internal Server Error', { status: 500 });
    }
  }
};
```

---

## Section 4 — Key Derivation to Avoid Storing Multiple Raw Keys

Use HKDF to derive purpose-specific subkeys from a single master key. Store only the master secret; the subkeys are derived per-operation and never persist in memory longer than the request.

```typescript
async function deriveSubkey(
  masterKeyBytes: Uint8Array,
  purpose: string,
  algorithm: AesKeyGenParams | HmacKeyGenParams
): Promise<CryptoKey> {
  const masterKey = await crypto.subtle.importKey(
    'raw',
    masterKeyBytes,
    'HKDF',
    false, // non-extractable
    ['deriveKey']
  );

  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new TextEncoder().encode('example project-v1'),
      info: new TextEncoder().encode(purpose),
    },
    masterKey,
    algorithm,
    false, // derived subkey also non-extractable
    algorithm.name === 'HMAC' ? ['sign', 'verify'] : ['encrypt', 'decrypt']
  );
}

// Usage:
const encKey = await deriveSubkey(
  hexToBytes(env.MASTER_KEY_HEX),
  'encryption-v1',
  { name: 'AES-GCM', length: 256 }
);

const sigKey = await deriveSubkey(
  hexToBytes(env.MASTER_KEY_HEX),
  'signing-v1',
  { name: 'HMAC', hash: 'SHA-256' }
);
```

---

## Anti-patterns

- Importing keys with `extractable: true` when export is not needed — this is the most common mistake and offers no benefit.
- Logging the `env.SIGNING_KEY_HEX` value or interpolating it into error strings during debugging.
- Storing derived `CryptoKey` objects in `globalThis` or module-level variables as `JsonWebKey` objects — store the `CryptoKey` handle, not the serialized bytes.
- Passing raw key bytes through `Response.json()` or `KV.put()` without encryption.
- Using `JSON.stringify(cryptoKey)` — this does not serialize key material (it returns `{}`) but the attempt suggests a misunderstanding of the API that may lead to unsafe workarounds.
- Creating a key via `crypto.getRandomValues()` in a loop to avoid importing — this does not integrate with `crypto.subtle` and means managing raw bytes in application code.

---

## Gotchas

- `extractable: false` is enforced by the runtime: calling `crypto.subtle.exportKey()` on a non-extractable key throws `DOMException: key is not extractable`. This exception message does not expose key material but does indicate an attempted export—monitor for this in Tail Workers.
- Module-level caching of `CryptoKey` objects (as done in Section 1) is safe and recommended. The `CryptoKey` handle is opaque and cannot be serialized or extracted from outside `crypto.subtle`.
- `crypto.subtle.wrapKey()` (wrapping a key with another key) still requires the inner key to be extractable. If you need to transport a key, use `wrapKey` with an appropriate wrapping key—never export raw bytes manually.
- HKDF-derived keys require the `info` parameter to be unique per purpose. Reusing the same `info` for different contexts defeats the purpose isolation.
- Workers secrets (`env.MY_SECRET`) are strings. Always convert to `Uint8Array` via `hexToBytes()` or `new TextEncoder().encode()` before importing into `crypto.subtle`; do not pass the string directly.

---

## Verification

1. Attempt `crypto.subtle.exportKey('raw', signingKey)` in a test and confirm it throws `DOMException`.
2. Review all `importKey` and `generateKey` calls with `grep -r 'extractable: true'` in the codebase and audit each one for necessity.
3. Enable Tail Workers to stream console logs to a logging endpoint and confirm no hex strings or base64 key blobs appear in logs during normal operation.
4. Use Cloudflare's Workers Secrets dashboard to confirm that `SIGNING_KEY_HEX` is stored as a secret, not an environment variable (secrets are not visible in wrangler.toml or in the Cloudflare dashboard value field after creation).

```bash
# Audit extractable keys in source
grep -rn 'extractable: true' /path/to/project project/src/
# Should return only intentional export-required key generations
```

---

## Related

- `cryptographic-agility-workers-subtlecrypto-migration.md`
- `workers-hkdf-key-derivation-hierarchical-secrets.md`
- `workers-environment-variable-hygiene.md`
- `secrets-encryption-at-rest.md`
- `workers-secrets-store-scoped-binding.md`

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://www.w3.org/TR/WebCryptoAPI/#dfn-CryptoKey-extractable
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/importKey
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveKey
- https://developers.cloudflare.com/workers/configuration/secrets/
