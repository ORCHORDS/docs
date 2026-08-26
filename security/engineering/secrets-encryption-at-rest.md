# secrets-encryption-at-rest

**Issue:** Encrypt PII in D1 + R2 + KV
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your DB has 100k user records with emails, phone numbers, and
addresses. A backup of the DB is leaked. The PII is in
plaintext. You're in violation of GDPR + CCPA.

## Root cause
**At-rest encryption is not the same as in-transit encryption.**
D1, R2, and KV encrypt at rest on the CF platform. But the
DATA is plaintext. Anyone with read access (a leaked backup, a
compromised API key, a malicious employee) can read the PII.

**Source:** CF security:
https://developers.cloudflare.com/fundamentals/security/

> "Cloudflare encrypts data at rest using AES-256. ... However,
> encryption-at-rest by the cloud provider is not a substitute
> for application-level encryption of sensitive data."

## Fix
**Application-level encryption** for PII fields. Encrypt the
field with a key the application manages. The DB only sees
ciphertext.

### What to encrypt
- **PII:** email, phone, address, full name, government ID
- **Tokens:** API keys, OAuth tokens, session tokens (if
  stored in the DB)
- **Financial:** bank account, card number (use Stripe's vault
  instead — never store card data)
- **Health:** any health-related data
- **Children's data:** always (per GDPR-K + COPPA)

### What NOT to encrypt
- **Display name:** already public (in the user's profile)
- **Public content:** posts, comments
- **Audit log metadata:** the audit log is itself sensitive;
  encrypt the metadata, not the row structure
- **Booleans + small numbers:** the overhead isn't worth it

### Pattern: column-level encryption

```ts
// On the application side
import { encryptPII, decryptPII } from './crypto';

class EncryptedUserRepository {
  async create(data: NewUser): Promise<User> {
    const encrypted = {
      id: data.id,
      tenantId: data.tenantId,
      email_encrypted: await encryptPII(data.email, this.env),
      phone_encrypted: data.phone ? await encryptPII(data.phone, this.env) : null,
      displayName: data.displayName,  // not encrypted (public)
      role: data.role,
      createdAt: Date.now(),
    };
    await this.db.prepare(
      `INSERT INTO users (id, tenant_id, email_encrypted, phone_encrypted, display_name, role, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(encrypted.id, encrypted.tenantId, encrypted.email_encrypted, encrypted.phone_encrypted, encrypted.displayName, encrypted.role, encrypted.createdAt).run();
  }

  async getById(id: string): Promise<User | null> {
    const row = await this.db.prepare(
      `SELECT * FROM users WHERE id = ?`
    ).bind(id).first<UserRow>();
    if (!row) return null;
    return {
      ...row,
      email: await decryptPII(row.email_encrypted, this.env),
      phone: row.phone_encrypted ? await decryptPII(row.phone_encrypted, this.env) : null,
    };
  }
}
```

### Key management

The encryption key is the most sensitive secret. Store it:
- **In CF Workers Secrets** (`wrangler secret put PII_ENCRYPTION_KEY`)
- **OR in a dedicated KMS** (CF doesn't have one, so use
  AWS KMS, GCP KMS, HashiCorp Vault, etc.)
- **NEVER in `wrangler.toml`**
- **NEVER in git**

For key rotation, see `secrets-rotation-runbook.md`.

### The crypto details

```ts
// AES-GCM with a 256-bit key + 96-bit IV per encryption
async function encryptPII(plaintext: string, env: Env): Promise<string> {
  const key = await getKey(env.PII_ENCRYPTION_KEY);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext)
  );
  // Format: base64(iv) + '.' + base64(ciphertext)
  return btoa(String.fromCharCode(...iv)) + '.' + btoa(String.fromCharCode(...new Uint8Array(ciphertext)));
}
```

### Search on encrypted fields

You **cannot** search on encrypted fields directly. If you need
to look up by email, you have 2 options:

1. **Hash for lookup:** Store `email_hash` alongside the
   encrypted email. Use the hash for lookups. (Like
   `bcrypt(password)` for password verification.)
2. **Deterministic encryption:** Use the same IV per email (BAD
   — leaks structure). Don't.

For most apps, option 1 (hash + encrypt) is the right answer.
The hash doesn't need to be reversible; the encrypted value
does.

## Verification
- **Test:** `test/encryption.test.ts` — encrypt + decrypt
  round-trip; ciphertext is different for same plaintext
  (different IVs)
- **Audit:** A leaked DB shows encrypted blobs, not plaintext
- **Pen test:** Annual review of encryption implementation

## Gotchas
- **Encryption doesn't make a DB query fast.** The query
  `WHERE email = 'alice@example.com'` can't be optimized if
  `email` is encrypted. Use the hash for lookups.
- **Encrypted fields don't support LIKE or prefix queries.**
  If you need "starts with A," you can't.
- **Sorting on encrypted fields is meaningless.** The sort
  order is on the ciphertext, not the plaintext.
- **The IV (initialization vector) must be unique per
  encryption.** Reusing an IV leaks structure. Use
  `crypto.getRandomValues(new Uint8Array(12))` for each
  encryption.
- **Authenticated encryption (AES-GCM) is mandatory.** AES-CBC
  without a MAC is vulnerable to padding oracle attacks.
- **Decryption errors should be silent** (return null or a
  generic error). Don't leak whether the ciphertext was
  invalid vs the key was wrong.

## Related
- `secrets-rotation-runbook.md` (key rotation)
- `gdpr-article-17-erasure.md` (encryption + erasure interaction)
- `pbkdf2-max-100k-iterations.md` (for password hashing, not
  for PII encryption — use a different KDF)
- NIST: https://csrc.nist.gov/publications/detail/sp/800-38d/final (AES-GCM)
