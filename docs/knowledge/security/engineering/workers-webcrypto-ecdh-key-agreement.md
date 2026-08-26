# Workers WebCrypto ECDH Key Agreement Shared Secret

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to establish a shared secret between a Cloudflare Worker and a client (browser,
mobile app, or another service) without transmitting a raw secret over the wire. Classic
scenarios include end-to-end encryption handshakes, sealed envelope encryption for
user-owned data, and ephemeral forward-secret channels for WebSocket upgrades.

---

## Context

The Web Cryptography API (`crypto.subtle`) is available in every Workers runtime.
ECDH (Elliptic-Curve Diffie-Hellman) lets two parties each generate a key pair and
derive the same shared secret from their own private key and the counterpart's public key.
Neither party sends the shared secret; only the public keys travel over the wire.

Workers supports two ECDH curves:
- `P-256` (NIST prime256v1) — broadest client support
- `P-384` — stronger but ~30 % slower key generation in V8

The derived shared secret is **raw key material** — you must always pass it through a
KDF (HKDF) before use as an AES key. Using the raw bytes directly as a cipher key leaks
information about the Diffie-Hellman group order.

---

## Generating a Server-Side ECDH Key Pair

```typescript
// worker-key-setup.ts
export async function generateServerEcdhKeyPair(): Promise<CryptoKeyPair> {
  return crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,    // extractable — needed to export public key to clients
    ['deriveKey', 'deriveBits'],
  );
}

export async function exportPublicKeyJwk(publicKey: CryptoKey): Promise<JsonWebKey> {
  return crypto.subtle.exportKey('jwk', publicKey);
}
```

Store the server private key in a Workers Secret or Durable Object — never in KV (it is
replicated widely) and never hard-coded.

---

## Client Key Generation and Public Key Exchange (Browser)

```typescript
// client-side (browser, shown here for reference — not Workers code)
async function clientHandshake(serverPublicKeyJwk: JsonWebKey) {
  const clientKeyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    false,   // non-extractable: private key never leaves the browser
    ['deriveKey', 'deriveBits'],
  );

  const serverPublicKey = await crypto.subtle.importKey(
    'jwk',
    serverPublicKeyJwk,
    { name: 'ECDH', namedCurve: 'P-256' },
    false,
    [],     // ECDH public keys have no key usages on import
  );

  // Derive 256 bits of raw shared key material
  const sharedBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: serverPublicKey },
    clientKeyPair.privateKey,
    256,
  );

  // KDF: derive an AES-GCM key from the shared material
  const hkdfBase = await crypto.subtle.importKey(
    'raw', sharedBits, { name: 'HKDF' }, false, ['deriveKey'],
  );

  const aesKey = await crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new Uint8Array(32),  // exchange a random salt alongside public keys in production
      info: new TextEncoder().encode('ecdh-channel-v1'),
    },
    hkdfBase,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );

  // Send clientKeyPair.publicKey (exported as JWK) to the Worker
  const clientPublicKeyJwk = await crypto.subtle.exportKey('jwk', clientKeyPair.publicKey);
  return { aesKey, clientPublicKeyJwk };
}
```

---

## Server-Side Shared Secret Derivation (Workers)

```typescript
// src/ecdh-handler.ts
import type { Env } from './env';

interface HandshakeRequest {
  clientPublicKey: JsonWebKey;
  salt: string;  // base64-encoded 32-byte random salt from client
}

export async function handleEcdhHandshake(
  req: Request,
  serverPrivateKey: CryptoKey,
): Promise<Response> {
  const body = await req.json<HandshakeRequest>();

  // Import the client's public key
  const clientPublicKey = await crypto.subtle.importKey(
    'jwk',
    body.clientPublicKey,
    { name: 'ECDH', namedCurve: 'P-256' },
    false,
    [],
  );

  // Derive shared bits on the server side
  const sharedBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: clientPublicKey },
    serverPrivateKey,
    256,
  );

  // KDF with the client-supplied salt
  const salt = Uint8Array.from(atob(body.salt), c => c.charCodeAt(0));
  const hkdfBase = await crypto.subtle.importKey(
    'raw', sharedBits, { name: 'HKDF' }, false, ['deriveKey'],
  );
  const sessionKey = await crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt,
      info: new TextEncoder().encode('ecdh-channel-v1'),
    },
    hkdfBase,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );

  // The session key is now usable — store a fingerprint in KV keyed to the session ID
  const sessionId = crypto.randomUUID();
  // (store sessionId → key fingerprint mapping, not the key itself)

  return Response.json({ sessionId });
}
```

---

## Ephemeral vs. Static Server Keys

| Mode | Forward secrecy | Key management cost |
|------|----------------|---------------------|
| Static server key pair | None — compromised server key breaks all past sessions | Low — one key pair |
| Per-session ephemeral key pair | Full — each handshake is independent | High — key generated per request |
| Short-lived rotating key pair | Partial — limited to the rotation window | Medium |

For forward secrecy, generate a **new server key pair per handshake** instead of reusing
a long-lived secret:

<redacted-secret>
export async function ephemeralHandshake(clientPublicKeyJwk: JsonWebKey): Promise<{
  serverPublicKeyJwk: JsonWebKey;
  sessionId: string;
}> {
  const ephemeralPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    ['deriveBits'],
  );
  const serverPublicKeyJwk = await crypto.subtle.exportKey('jwk', ephemeralPair.publicKey);
  // ... derive and store session key as above using ephemeralPair.privateKey
  return { serverPublicKeyJwk, sessionId: crypto.randomUUID() };
}
```

---

## Anti-patterns

- **Using `deriveBits` output directly as a cipher key.** Always pass through HKDF with a
  domain-separation `info` string so the key is bound to its purpose.
- **Reusing the HKDF salt across sessions.** A fixed salt degrades HKDF to a PRF with
  reduced security margin. Generate 32 random bytes per session.
- **Storing the derived AES key in KV or D1.** The derived key is session material; store
  only a session token referencing it. The key lives in the Durable Object or is
  re-derived on each request from the session token.
- **Not validating the curve on import.** Always specify `namedCurve: 'P-256'` in the
  import algorithm; omitting it may allow a curve-confusion attack.
- **Exporting the server private key to the response.** The private key must never leave
  the Worker. Only the public key (`exportKey('jwk', pair.publicKey)`) is sent.

---

## Gotchas

- `crypto.subtle.deriveBits` in Workers returns an `ArrayBuffer`, not a `Uint8Array`.
  Wrap it: `new Uint8Array(sharedBits)` before further use.
- P-256 key generation is synchronous in V8's implementation but the API is always
  Promise-based — always `await`.
- The `keyUsages` array for an ECDH **public** key on import must be `[]` (empty).
  Passing `['deriveKey']` throws `InvalidAccessError` in the Workers runtime.
- `SubtleCrypto` does not distinguish P-256 from P-384 at the type level — pass the wrong
  curve name and the error surfaces only at import time.
- Workers subrequests share the same `crypto.subtle` instance; there is no isolation
  between concurrent requests beyond normal JavaScript variable scoping.

---

## Verification

```typescript
// Smoke-test: both sides must derive identical shared bits
async function selfTest() {
  const alice = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const bob   = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);

  const bitsAlice = await crypto.subtle.deriveBits({ name: 'ECDH', public: bob.publicKey },   alice.privateKey, 256);
  const bitsBob   = await crypto.subtle.deriveBits({ name: 'ECDH', public: alice.publicKey }, bob.privateKey,   256);

  const hexAlice = [...new Uint8Array(bitsAlice)].map(b => b.toString(16).padStart(2,'0')).join('');
  const hexBob   = [...new Uint8Array(bitsBob)  ].map(b => b.toString(16).padStart(2,'0')).join('');

  console.assert(hexAlice === hexBob, 'ECDH shared secret mismatch!');
  console.log('ECDH self-test passed');
}
```

---

## Related

- `workers-crypto-subtle-key-extraction-prevention.md`
- `cryptographic-agility-workers-subtlecrypto-migration.md`
- `workers-hkdf-key-derivation-hierarchical-secrets.md`
- `d1-encrypted-column-workers-crypto-api.md`
- `ed25519-webcrypto-jwt-signature-workers.md`

---

## Sources

- W3C Web Cryptography API spec — https://www.w3.org/TR/WebCryptoAPI/
- Cloudflare Workers Web Crypto — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- RFC 5869 HKDF — https://datatracker.ietf.org/doc/html/rfc5869
- NIST SP 800-56A Rev 3 — https://csrc.nist.gov/publications/detail/sp/800-56a/rev-3/final
