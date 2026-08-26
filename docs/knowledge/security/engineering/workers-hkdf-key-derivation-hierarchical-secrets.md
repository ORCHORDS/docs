# HKDF Key Derivation and Hierarchical Secrets in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You store one master secret in Workers Secrets, but your platform needs dozens of distinct cryptographic
keys: per-feature HMAC keys, per-tenant encryption keys, ephemeral session keys, vote-token signing
keys, and content-moderation signing keys. Storing each key as a separate Secret becomes unmanageable
and rotation requires coordinating many independent values. You need a single root secret from which
all operational keys are deterministically derived, so rotating one value rotates everything.

---

## Context

HKDF (HMAC-based Key Derivation Function, RFC 5869) is the standard for this pattern. Given a single
Input Keying Material (IKM), HKDF produces cryptographically independent derived keys via:

1. **Extract**: `PRK = HMAC-Hash(salt, IKM)` — condenses entropy.
2. **Expand**: `OKM = HKDF-Expand(PRK, info, length)` — stretches into distinct keys per `info` label.

The `info` field (a context string) ensures that keys derived for different purposes are independent
even if an attacker compromises one derived key. The Web Crypto API (`SubtleCrypto`) supports HKDF
natively in Workers — no external libraries required.

For an anonymous social platform, this means one `MASTER_SECRET` env var funds: session signing,
vote-token HMAC, field-level encryption for sensitive D1 columns, webhook signing, and more.

---

## 1. HKDF Extract — Importing the Master Key

The master key must be imported as an `HKDF` key, not as `HMAC` or `AES`, because `SubtleCrypto`
enforces key-algorithm pairing.

```typescript
// src/crypto/hkdf.ts

/** Import raw secret bytes as an HKDF key. Call once at module load; cache the result. */
export async function importMasterKey(
  rawSecret: string // from env.MASTER_SECRET — base64-encoded 32-byte value
): Promise<CryptoKey> {
  const keyBytes = Uint8Array.from(atob(rawSecret), c => c.charCodeAt(0));

  return crypto.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'HKDF' },
    false,        // non-extractable — derived keys cannot be exported from the runtime
    ['deriveKey', 'deriveBits']
  );
}
```

Cache this at module scope so it is computed once per isolate warm-up:

```typescript
// src/crypto/master.ts
import { importMasterKey } from './hkdf';

let cachedMasterKey: CryptoKey | null = null;

export async function getMasterKey(env: Env): Promise<CryptoKey> {
  if (!cachedMasterKey) {
    cachedMasterKey = await importMasterKey(env.MASTER_SECRET);
  }
  return cachedMasterKey;
}
```

---

## 2. HKDF Expand — Deriving Purpose-Specific Keys

The `info` parameter is what makes derived keys independent. Use a structured label scheme:
`{application}:{version}:{purpose}`.

```typescript
// src/crypto/hkdf.ts (continued)

const ENC = new TextEncoder();

/**
 * Derive a purpose-specific AES-GCM key from the master key.
 * @param masterKey  — imported HKDF CryptoKey
 * @param purpose    — e.g. "v1:field-encryption:content-body"
 * @param salt       — optional random or fixed salt; use fixed per-purpose salt for determinism
 */
export async function deriveAesKey(
  masterKey: CryptoKey,
  purpose: string,
  salt?: Uint8Array
): Promise<CryptoKey> {
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      info: ENC.encode(purpose),
      salt: salt ?? new Uint8Array(32), // zero salt is valid; non-zero salt adds entropy
    },
    masterKey,
    { name: 'AES-GCM', length: 256 },
    false,    // non-extractable
    ['encrypt', 'decrypt']
  );
}

/**
 * Derive a purpose-specific HMAC-SHA256 key from the master key.
 */
export async function deriveHmacKey(
  masterKey: CryptoKey,
  purpose: string,
  salt?: Uint8Array
): Promise<CryptoKey> {
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      info: ENC.encode(purpose),
      salt: salt ?? new Uint8Array(32),
    },
    masterKey,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

/**
 * Derive raw bytes — useful when you need a symmetric key for a non-Web-Crypto algorithm,
 * or when generating a fixed-length random-looking value (e.g. a CSRF token seed).
 */
export async function deriveBits(
  masterKey: CryptoKey,
  purpose: string,
  bits = 256,
  salt?: Uint8Array
): Promise<ArrayBuffer> {
  return crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      info: ENC.encode(purpose),
      salt: salt ?? new Uint8Array(32),
    },
    masterKey,
    bits
  );
}
```

---

## 3. Purpose Label Registry

Maintain a central registry so labels never collide. A collision between two purposes would produce the
same key for different uses, defeating isolation.

```typescript
// src/crypto/purposes.ts
export const KEY_PURPOSES = {
  // Field-level encryption in D1
  D1_CONTENT_BODY:    'example project:v1:d1-encrypt:content-body',
  D1_CONTENT_META:    'example project:v1:d1-encrypt:content-meta',
  D1_USER_SETTINGS:   'example project:v1:d1-encrypt:user-settings',

  // HMAC signing
  VOTE_TOKEN:         'example project:v1:hmac:vote-token',
  SESSION_JWT:        'example project:v1:hmac:session-jwt',
  WEBHOOK_OUTBOUND:   'example project:v1:hmac:webhook-outbound',
  MODERATION_PAYLOAD: 'example project:v1:hmac:moderation-payload',

  // Ephemeral / per-tenant
  TENANT_PREFIX:      'example project:v1:tenant:', // append tenant ID
} as const;
```

For per-tenant keys, append the tenant identifier to a prefix:

```typescript
export function tenantPurpose(base: string, tenantId: string): string {
  return `${base}${tenantId}`;
}
// e.g. tenantPurpose(KEY_PURPOSES.TENANT_PREFIX + 'd1-encrypt:', 'tenant-abc')
// => "example project:v1:tenant:d1-encrypt:tenant-abc"
```

---

## 4. Field-Level Encryption with a Derived AES-GCM Key

Using a derived key for field-level D1 column encryption — each column class gets its own key so a
breach of the encrypted `content_body` key cannot decrypt `user_settings`.

```typescript
// src/crypto/field-encrypt.ts
import { getMasterKey, deriveAesKey, deriveBits } from './hkdf';
import { KEY_PURPOSES } from './purposes';

export async function encryptField(
  env: Env,
  purpose: keyof typeof KEY_PURPOSES,
  plaintext: string
): Promise<string> {
  const masterKey = await getMasterKey(env);
  const aesKey = await deriveAesKey(masterKey, KEY_PURPOSES[purpose]);

  const iv = crypto.getRandomValues(new Uint8Array(12)); // 96-bit GCM IV
  const enc = new TextEncoder();
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    enc.encode(plaintext)
  );

  // Pack: base64(iv) "." base64(ciphertext)
  const toB64 = (buf: ArrayBuffer | Uint8Array) =>
    btoa(String.fromCharCode(...new Uint8Array(buf instanceof ArrayBuffer ? buf : buf)));

  return `${toB64(iv)}.${toB64(ciphertext)}`;
}

export async function decryptField(
  env: Env,
  purpose: keyof typeof KEY_PURPOSES,
  packed: string
): Promise<string> {
  const [ivB64, ctB64] = packed.split('.');
  const fromB64 = (s: string) =>
    Uint8Array.from(atob(s), c => c.charCodeAt(0));

  const masterKey = await getMasterKey(env);
  const aesKey = await deriveAesKey(masterKey, KEY_PURPOSES[purpose]);

  const plainBuf = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: fromB64(ivB64) },
    aesKey,
    fromB64(ctB64)
  );

  return new TextDecoder().decode(plainBuf);
}
```

---

## 5. Key Rotation Strategy

HKDF is deterministic — the same master key + purpose always produces the same derived key. Rotation
means changing the master secret and re-encrypting stored data. Do this in three phases:

```typescript
// src/crypto/rotation.ts

/**
 * Phase 1: Add MASTER_SECRET_NEXT alongside MASTER_SECRET.
 * Phase 2: Re-encrypt all D1 rows using NEXT as the new key.
 * Phase 3: Promote NEXT to MASTER_SECRET and remove MASTER_SECRET_NEXT.
 */
export async function reEncryptField(
  env: Env,
  purpose: keyof typeof KEY_PURPOSES,
  packed: string
): Promise<string> {
  // Decrypt with current master
  const plaintext = await decryptField(env, purpose, packed);

  // If rotation is in progress, re-encrypt with the new master
  if (env.MASTER_SECRET_NEXT) {
    const nextMaster = await importMasterKey(env.MASTER_SECRET_NEXT);
    const aesKey = await deriveAesKey(nextMaster, KEY_PURPOSES[purpose]);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv },
      aesKey,
      new TextEncoder().encode(plaintext)
    );
    const toB64 = (b: ArrayBuffer | Uint8Array) =>
      btoa(String.fromCharCode(...new Uint8Array(b instanceof ArrayBuffer ? b : b)));
    return `next.${toB64(iv)}.${toB64(ciphertext)}`;
  }

  return packed; // no rotation in progress
}
```

Prefix rotated ciphertext with `next.` so the decrypt function knows which master to use:

```typescript
export async function decryptFieldAny(
  env: Env,
  purpose: keyof typeof KEY_PURPOSES,
  packed: string
): Promise<string> {
  if (packed.startsWith('next.') && env.MASTER_SECRET_NEXT) {
    const stripped = packed.slice('next.'.length);
    // Temporarily swap to use MASTER_SECRET_NEXT for decryption
    const nextMaster = await importMasterKey(env.MASTER_SECRET_NEXT);
    // ... (same decrypt logic, using nextMaster)
    void nextMaster; // implementation elided for brevity
  }
  return decryptField(env, purpose, packed);
}
```

---

## Anti-patterns

- **Using the master key directly for encryption** — bypasses the purpose isolation that HKDF provides.
  A compromised encryption operation cannot then attack other key usages.
- **Hardcoding `info` strings inline** — a typo in one call site produces a silently different key.
  Always reference the central `KEY_PURPOSES` registry.
- **Using a zero-length salt** — valid but eliminates the salt's entropy contribution. Use at least a
  fixed 32-byte application-specific salt so even if the same IKM is reused across apps, keys differ.
- **Caching derived keys in KV** — KV is a data store, not a HSM. Keep all `CryptoKey` objects in
  module-level memory (per-isolate), where they remain non-extractable.
- **Rotating by changing only one derived key** — if you change the VOTE_TOKEN purpose string, old
  tokens immediately become invalid. Rotation requires both old and new keys active simultaneously.

---

## Gotchas

- `importKey` with `extractable: false` prevents `exportKey` from succeeding — this is intentional.
  The key material never leaves the Workers runtime.
- HKDF `deriveKey` with `extractable: false` on the output key means you cannot serialize it. If you
  need to pass a derived key across service binding calls, re-derive it in the receiving Worker using
  the same master and purpose.
- Workers isolates are not persistent — the module-level cache (`cachedMasterKey`) is rebuilt on each
  cold start. Each `importKey` call takes ~0.1 ms; this is acceptable overhead.
- AES-GCM with a 12-byte random IV has a 2^32 message limit per key before IV collision probability
  becomes non-negligible. For high-volume encryption, derive a new key per-session or use a counter IV.
- The `salt` in HKDF extract is NOT a per-message nonce. It is a fixed, purpose-level value. The
  per-message randomness lives in AES-GCM's IV.

---

## Verification

```typescript
// Verify two different purposes produce different keys
const master = await importMasterKey(env.MASTER_SECRET);
const key1Bits = await deriveBits(master, 'test:purpose-a', 256);
const key2Bits = await deriveBits(master, 'test:purpose-b', 256);

const a = new Uint8Array(key1Bits);
const b = new Uint8Array(key2Bits);
let same = true;
for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) { same = false; break; }
console.assert(!same, 'Different purposes must produce different keys');

// Verify determinism — same master + same purpose = same bits
const key1Again = await deriveBits(master, 'test:purpose-a', 256);
const c = new Uint8Array(key1Again);
let equal = true;
for (let i = 0; i < a.length; i++) if (a[i] !== c[i]) { equal = false; break; }
console.assert(equal, 'Same inputs must produce same key');
```

---

## Related

- `d1-encrypted-column-workers-crypto-api.md`
- `durable-objects-storage-encryption-patterns.md`
- `cryptographic-agility-workers-subtlecrypto-migration.md`
- `workers-secrets-store-scoped-binding.md`
- `api-key-rotation-workers-kv-secrets.md`

---

## Sources

- RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)
- Web Crypto API — SubtleCrypto.deriveKey — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveKey
- Web Crypto API — SubtleCrypto.deriveBits — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveBits
- Cloudflare Workers Crypto — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- NIST SP 800-108 Rev 1 — Recommendation for Key Derivation Using Pseudorandom Functions
- AES-GCM IV collision analysis — Nonce-Disrespecting Adversaries (Joux, 2006)
