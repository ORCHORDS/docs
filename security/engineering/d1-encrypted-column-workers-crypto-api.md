# D1 Encrypted Column Storage via Workers Crypto API

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An anonymous social platform stores sensitive user data — device fingerprints, phone numbers used for SMS verification, or moderation notes — in Cloudflare D1. A D1 database breach would expose these fields in plaintext. Application-layer column encryption ensures data is unintelligible without the key even if the raw SQLite file is extracted.

## Context

Cloudflare Workers expose the Web Crypto API (`crypto.subtle`) natively at the edge with no cold-start cost. D1 stores data as UTF-8 text or blobs; ciphertext can be stored as Base64 strings in `TEXT` columns or as raw bytes in `BLOB` columns. The encryption key must never live in the database itself — it is injected via a Workers Secret.

## Threat Model

Column encryption defends against:
- **Database-level breach** — a leaked D1 snapshot contains only ciphertext.
- **SQL injection read** — even a successful `SELECT *` returns encrypted blobs.
- **Insider read** — DB admins cannot read sensitive fields without the KMS key.

It does NOT defend against:
- A compromised Worker runtime that already holds the decrypted key.
- Queries that filter or sort on encrypted columns (those must be hashed separately).

```typescript
// threat-model.ts — enumerate what is and is not protected
type ProtectedField = "phone_e164" | "device_fingerprint" | "mod_note";
type UnprotectedField = "user_id" | "created_at" | "post_count";

// Encrypted columns are opaque to D1; searching requires a blind index
interface UserRow {
  user_id: string;           // plaintext — used as PK
  phone_enc: string;         // AES-GCM ciphertext, base64
  phone_hmac: string;        // HMAC-SHA256 blind index for equality lookup
  device_fp_enc: string;     // AES-GCM ciphertext
  created_at: number;        // plaintext epoch ms
}
```

## Key Derivation and Import

The root secret is a 32-byte hex value stored as a Workers Secret (`COLUMN_ENC_KEY`). Each column uses a derived key via HKDF so a single root secret produces independent per-column keys, limiting blast radius if one key is ever used incorrectly.

```typescript
// crypto-keys.ts
const enc = new TextEncoder();

async function importRootKey(hex: string): Promise<CryptoKey> {
  const raw = Uint8Array.from(hex.match(/.{2}/g)!.map(b => parseInt(b, 16)));
  return crypto.subtle.importKey("raw", raw, "HKDF", false, ["deriveKey"]);
}

async function deriveColumnKey(
  rootKey: CryptoKey,
  column: string
): Promise<CryptoKey> {
  return crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: enc.encode("example project-d1-column-v1"),
      info: enc.encode(column),
    },
    rootKey,
    { name: "AES-GCM", length: 256 },
    false,  // non-extractable — key never leaves SubtleCrypto
    ["encrypt", "decrypt"]
  );
}

async function deriveHmacKey(
  rootKey: CryptoKey,
  column: string
): Promise<CryptoKey> {
  return crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: enc.encode("example project-d1-hmac-v1"),
      info: enc.encode(column),
    },
    rootKey,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
}
```

## Encrypt / Decrypt Implementation

AES-GCM with a random 12-byte IV per encryption. The IV is prepended to the ciphertext before Base64 encoding so each row is self-contained. The tag (16 bytes) is appended automatically by SubtleCrypto.

```typescript
// column-crypto.ts
const IV_BYTES = 12;

export async function encryptColumn(
  key: CryptoKey,
  plaintext: string
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    enc.encode(plaintext)
  );
  const blob = new Uint8Array(IV_BYTES + ct.byteLength);
  blob.set(iv, 0);
  blob.set(new Uint8Array(ct), IV_BYTES);
  return btoa(String.fromCharCode(...blob));
}

export async function decryptColumn(
  key: CryptoKey,
  b64: string
): Promise<string> {
  const blob = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const iv = blob.slice(0, IV_BYTES);
  const ct = blob.slice(IV_BYTES);
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
  return new TextDecoder().decrypt(pt); // throws on tag mismatch
}

export async function blindIndex(
  hmacKey: CryptoKey,
  value: string
): Promise<string> {
  const sig = await crypto.subtle.sign("HMAC", hmacKey, enc.encode(value));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}
```

## Hardening — Key Lifecycle

Per-column key derivation means rotating one column's key does not require re-encrypting other columns. A version prefix in the stored blob enables online rotation without downtime.

```typescript
// versioned-crypto.ts
const CURRENT_VERSION = 1;

interface VersionedCiphertext {
  v: number;
  data: string;  // base64 AES-GCM blob
}

export async function encryptVersioned(
  key: CryptoKey,
  plaintext: string
): Promise<string> {
  const data = await encryptColumn(key, plaintext);
  return JSON.stringify({ v: CURRENT_VERSION, data } satisfies VersionedCiphertext);
}

export async function decryptVersioned(
  keys: Map<number, CryptoKey>,
  stored: string
): Promise<string> {
  const { v, data } = JSON.parse(stored) as VersionedCiphertext;
  const key = keys.get(v);
  if (!key) throw new Error(`No key for version ${v}`);
  return decryptColumn(key, data);
}

// During rotation: write new version, lazy-migrate on read
export async function migrateRow(
  db: D1Database,
  userId: string,
  oldKeys: Map<number, CryptoKey>,
  newKey: CryptoKey,
  column: string
): Promise<void> {
  const row = await db.prepare(`SELECT ${column} FROM users WHERE user_id=?`)
    .bind(userId).first<{ [k: string]: string }>();
  if (!row) return;
  const pt = await decryptVersioned(oldKeys, row[column]);
  const newCt = await encryptVersioned(newKey, pt);
  await db.prepare(`UPDATE users SET ${column}=? WHERE user_id=?`)
    .bind(newCt, userId).run();
}
```

## Monitoring

Track decryption failures as a signal for tampered rows or wrong-key attempts.

```typescript
// monitoring.ts
export async function safeDecrypt(
  key: CryptoKey,
  b64: string,
  userId: string,
  column: string,
  ctx: ExecutionContext
): Promise<string | null> {
  try {
    return await decryptColumn(key, b64);
  } catch (err) {
    // AES-GCM tag failure = data tampering or wrong key
    ctx.waitUntil(
      fetch("https://logs.internal/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event: "column_decrypt_failure",
          user_id: userId,
          column,
          ts: Date.now(),
        }),
      })
    );
    return null;
  }
}
```

## Anti-patterns

- Storing the encryption key in D1 or KV alongside the data it encrypts.
- Using ECB mode or a static IV — both leak repeated plaintexts.
- Encrypting the primary key or any indexed column without a separate blind index.
- Using `crypto.getRandomValues` outside Workers (not available in all runtimes) — always test in `wrangler dev`.
- Re-using the same derived key for both encryption and HMAC blind indexes.

## Gotchas

- `crypto.subtle.decrypt` throws a `DOMException` on authentication tag failure, not a typed error — catch it broadly.
- Base64 output grows ~33 % over plaintext; account for D1's TEXT column size when planning migrations.
- HKDF `info` must be unique per column and per usage (enc vs HMAC) — a collision silently reuses the same key material.
- Non-extractable keys cannot be serialised; derive them fresh per request from the Workers Secret.
- D1 does not support column-level access controls — encryption is the only enforcement boundary.

## Verification

```bash
# 1. Insert a row via wrangler and confirm the DB shows ciphertext
wrangler d1 execute example project-db --command "SELECT phone_enc FROM users LIMIT 1;"
# Output should be base64 gibberish, never an E.164 number.

# 2. Verify equality lookup works via blind index
wrangler d1 execute example project-db --command \
  "SELECT user_id FROM users WHERE phone_hmac='<expected-hmac>';"

# 3. Corrupt a ciphertext byte and confirm decryption throws
# In a local test: flip one byte in phone_enc, call decrypt, expect DOMException.
```

## Related

- /documentation/categories/security/secrets-encryption-at-rest.md
- /documentation/categories/security/cryptographic-agility-workers-subtlecrypto-migration.md
- /documentation/categories/security/d1-row-level-security-tenant-isolation.md
- /documentation/categories/security/sql-injection-prevention-d1-workers.md
- /documentation/categories/security/workers-secrets-store-scoped-binding.md

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt
- https://developers.cloudflare.com/d1/
- https://www.w3.org/TR/WebCryptoAPI/#dfn-SubtleCrypto-method-deriveKey
- https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
