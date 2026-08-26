# D1 Column Encryption AES-GCM Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to store sensitive per-row fields — SSNs, API keys, payment tokens, health data — in D1 such that a database dump or a compromised read-only credential does not expose plaintext values. Whole-database encryption at rest is not sufficient when different tenants or access levels should only decrypt their own rows.

## Context

D1 has no native column encryption. Encryption must happen in the Worker before any write and decryption after any read. The Web Crypto API is available in the Workers runtime with zero cold-start cost. AES-256-GCM is the correct choice: it provides authenticated encryption (integrity + confidentiality), produces a standard 12-byte IV + 16-byte auth tag, and is natively supported by `crypto.subtle`. Store `iv` + `ciphertext` together as a single base64-encoded blob so the column remains a plain `TEXT` type.

## Key Derivation

Never hard-code a raw key. Derive a per-purpose AES key from a secret stored in a Workers secret or KV namespace.

```typescript
// src/crypto.ts
const KEY_USAGE: KeyUsage[] = ['encrypt', 'decrypt'];

export async function deriveColumnKey(
  masterSecret: string,
  columnLabel: string        // e.g. "ssn", "api_key" — domain-separates keys
): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    'raw',
    enc.encode(masterSecret),
    { name: 'HKDF' },
    false,
    ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: enc.encode('d1-column-encryption-v1'),
      info: enc.encode(columnLabel),
    },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    KEY_USAGE
  );
}
```

## Encrypt / Decrypt Helpers

```typescript
// src/crypto.ts (continued)
function toBase64(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}

function fromBase64(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

export async function encryptColumn(
  key: CryptoKey,
  plaintext: string
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder();
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    enc.encode(plaintext)
  );
  // Stored format: base64(iv) + "." + base64(ciphertext+tag)
  return `${toBase64(iv)}.${toBase64(ciphertext)}`;
}

export async function decryptColumn(
  key: CryptoKey,
  blob: string
): Promise<string> {
  const [ivB64, ctB64] = blob.split('.');
  if (!ivB64 || !ctB64) throw new Error('Invalid encrypted blob format');
  const iv = fromBase64(ivB64);
  const ciphertext = fromBase64(ctB64);
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ciphertext
  );
  return new TextDecoder().decode(plain);
}
```

## Writing Encrypted Rows

```typescript
// src/users.ts
interface Env {
  DB: D1Database;
  COLUMN_MASTER_SECRET: string;   // set via `wrangler secret put COLUMN_MASTER_SECRET`
}

export async function createUser(
  env: Env,
  userId: string,
  email: string,
  ssn: string
): Promise<void> {
  const key = await deriveColumnKey(env.COLUMN_MASTER_SECRET, 'ssn');
  const encryptedSsn = await encryptColumn(key, ssn);

  await env.DB.prepare(
    'INSERT INTO users (id, email, ssn_enc) VALUES (?, ?, ?)'
  )
    .bind(userId, email, encryptedSsn)
    .run();
}
```

## Reading and Decrypting Rows

```typescript
interface UserRow {
  id: string;
  email: string;
  ssn_enc: string;
}

export async function getUserSsn(
  env: Env,
  userId: string
): Promise<string | null> {
  const row = await env.DB.prepare(
    'SELECT ssn_enc FROM users WHERE id = ?'
  )
    .bind(userId)
    .first<UserRow>();

  if (!row) return null;

  const key = await deriveColumnKey(env.COLUMN_MASTER_SECRET, 'ssn');
  return decryptColumn(key, row.ssn_enc);
}

// Bulk decrypt — use Promise.all since Workers runs crypto in parallel
export async function listUsersDecrypted(
  env: Env
): Promise<Array<{ id: string; email: string; ssn: string }>> {
  const { results } = await env.DB.prepare(
    'SELECT id, email, ssn_enc FROM users'
  ).all<UserRow>();

  const key = await deriveColumnKey(env.COLUMN_MASTER_SECRET, 'ssn');
  return Promise.all(
    results.map(async (row) => ({
      id: row.id,
      email: row.email,
      ssn: await decryptColumn(key, row.ssn_enc),
    }))
  );
}
```

## Key Rotation

Store a `key_version` column alongside the encrypted blob. On rotation, re-encrypt rows in a background cron Worker reading the old version and writing with the new key.

```typescript
// Rotation worker (runs as a scheduled cron)
export async function rotateColumnKey(
  env: Env,
  oldSecret: string,
  newSecret: string,
  batchSize = 100
): Promise<void> {
  const oldKey = await deriveColumnKey(oldSecret, 'ssn');
  const newKey = await deriveColumnKey(newSecret, 'ssn');

  let cursor = 0;
  while (true) {
    const { results } = await env.DB.prepare(
      'SELECT id, ssn_enc FROM users WHERE key_version = 1 LIMIT ?'
    )
      .bind(batchSize)
      .all<{ id: string; ssn_enc: string }>();

    if (results.length === 0) break;

    const statements = await Promise.all(
      results.map(async ({ id, ssn_enc }) => {
        const plain = await decryptColumn(oldKey, ssn_enc);
        const reEncrypted = await encryptColumn(newKey, plain);
        return env.DB.prepare(
          'UPDATE users SET ssn_enc = ?, key_version = 2 WHERE id = ?'
        ).bind(reEncrypted, id);
      })
    );
    await env.DB.batch(statements);
    cursor += results.length;
  }
}
```

## Anti-patterns

- **Reusing the IV**: never pass a fixed IV to `AES-GCM`. Each encryption call must generate a fresh random 12 bytes. Reusing an IV with the same key breaks AES-GCM's confidentiality guarantee catastrophically.
- **Encrypting indexed search columns**: you cannot query encrypted ciphertext with `WHERE ssn_enc = ?` and get a meaningful result. Either store a separate deterministic HMAC of the value for exact-match lookups, or keep plaintext in a non-sensitive search field and encrypt only the sensitive display value.
- **Storing the key in D1 itself**: the key must live outside the database (Workers secret, KV with separate IAM, or an external KMS). A key in the same store as the ciphertext provides no protection.

## Gotchas

- `crypto.subtle` is always available in the Workers runtime — no import needed.
- `btoa`/`atob` operate on Latin-1, not UTF-8. The `toBase64` helper above serializes the raw `Uint8Array` via `String.fromCharCode`; this is correct for arbitrary binary. Do not pass a UTF-8 string directly to `btoa`.
- AES-GCM ciphertext is `plaintext.length + 16` bytes (auth tag) — factor this into your column storage estimates.
- `deriveKey` with `extractable: false` prevents the key material from being serialized out of the runtime, adding a small defence-in-depth layer.

## Verification

```typescript
const secret = 'test-master-secret-32-bytes-long!!';
const key = await deriveColumnKey(secret, 'ssn');
const original = '123-45-6789';
const blob = await encryptColumn(key, original);

console.assert(blob.includes('.'), 'blob should contain IV separator');
const decrypted = await decryptColumn(key, blob);
console.assert(decrypted === original, 'round-trip must match');

// Tamper test — should throw
try {
  const tampered = blob.slice(0, -4) + 'XXXX';
  await decryptColumn(key, tampered);
  console.error('FAIL: should have thrown on tampered ciphertext');
} catch {
  console.log('PASS: tamper detection works');
}
```

## Related

- `d1-tenant-data-encryption-workers.md` — whole-tenant encryption strategy
- `d1-row-level-security-tenant-id.md`
- `d1-strict-tables-type-enforcement-workers.md`

## Sources

- Web Crypto API in Workers: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- AES-GCM spec: https://www.w3.org/TR/WebCryptoAPI/#aes-gcm
- HKDF RFC 5869: https://www.rfc-editor.org/rfc/rfc5869
