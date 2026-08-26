# encryption-at-rest-detail

**Issue:** Encryption at rest — keys, algorithms, patterns
**Date:** 2026-08-09
**Status:** documented

## Symptom
You store user PII in the DB. A security breach exposes
the DB. The user emails are in plain text. The
attacker harvests them. GDPR fines. The users sue.

## Root cause
**Data at rest is unencrypted.** A breach exposes
everything.

**Source:** NIST — Encryption at Rest:
https://csrc.nist.gov/publications/detail/sp/800-175b/final

> "Encryption at rest is the cryptographic transformation
> of data when it is stored."

## The "data classification" pattern

Classify data by sensitivity:
- **Public:** Marketing copy, open source code
- **Internal:** Employee handbooks, internal docs
- **Confidential:** User PII (email, name, phone)
- **Restricted:** Credit cards, health data, passwords

Different classifications need different protections.

## The "encryption" choice

For data at rest, use AES-256-GCM:
- **Symmetric:** Same key for encrypt + decrypt
- **AEAD:** Authenticated; detects tampering
- **256-bit key:** Industry standard

```ts
async function encrypt(plaintext: string, key: CryptoKey): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));  // 96-bit IV for GCM
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  return `${base64(iv)}:${base64(new Uint8Array(ciphertext))}`;
}

async function decrypt(ciphertext: string, key: CryptoKey): Promise<string> {
  const [ivStr, ctStr] = ciphertext.split(':');
  const iv = base64Decode(ivStr);
  const ct = base64Decode(ctStr);
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ct,
  );
  return new TextDecoder().decode(plaintext);
}
```

The IV is random; the ciphertext is base64-encoded.

## The "key" pattern

The encryption key should:
- **Be 256 bits (32 bytes)**
- **Be generated from a CSPRNG**
- **Be stored in a KMS / HSM** (not in code)
- **Be rotated periodically** (every 90 days)
- **Be different per environment** (dev vs prod)

```ts
// Generate a key (do this once per environment)
const key = await crypto.subtle.generateKey(
  { name: 'AES-GCM', length: 256 },
  true,  // extractable
  ['encrypt', 'decrypt'],
);

// Export for storage (in KMS)
const exportedKey = await crypto.subtle.exportKey('raw', key);
// Store in KMS, Vault, or env
```

The key is generated once; stored in a KMS.

## The "KMS" pattern

For key management, use a KMS:
- **AWS KMS:** aws.amazon.com/kms
- **Cloudflare Workers Secrets:** built-in
- **HashiCorp Vault:** vaultproject.io
- **Google Cloud KMS:** cloud.google.com/kms

The KMS holds the key; the app uses it.

## The "envelope encryption" pattern

For large data, encrypt with a data key; encrypt the data
key with a master key:
```ts
// 1. Generate a data key
const dataKey = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
const exportedDataKey = await crypto.subtle.exportKey('raw', dataKey);

// 2. Encrypt the data with the data key
const ciphertext = await encryptWithKey(plaintext, dataKey);

// 3. Encrypt the data key with the master key (in KMS)
const encryptedDataKey = await kmsEncrypt(exportedDataKey, env.MASTER_KEY_ID);

// 4. Store { ciphertext, encryptedDataKey }
```

The master key never leaves the KMS; the data key is per
record.

## The "field-level encryption" pattern

For specific fields (PII), encrypt at the field level:
```ts
interface User {
  id: string;
  email: string;          // Public (used for login)
  email_hash: string;     // For search
  email_encrypted: string; // For decryption when needed
  ssn_encrypted: string;  // Sensitive
}
```

Some fields are encrypted; others are not (for search
performance).

## The "searchable encryption" pattern

For searching encrypted data, use:
- **Deterministic encryption:** Same plaintext = same
  ciphertext (for equality search)
- **Homomorphic encryption:** Search on encrypted data
- **Tokenization:** Replace the data with a token; store
  the token + the real value

For most apps, **deterministic encryption + hash**:
```ts
// For unique constraints
const emailHash = await sha256(email + env.PEPPER);
await env.DB!.prepare(
  `INSERT INTO users (email_hash, email_encrypted) VALUES (?, ?)`
).bind(emailHash, encrypt(email, env.ENCRYPTION_KEY)).run();

// For lookup
const user = await env.DB!.prepare(
  `SELECT * FROM users WHERE email_hash = ?`
).bind(await sha256(inputEmail + env.PEPPER)).first();
```

The hash is for lookup; the ciphertext is for display.

## The "encryption" anti-patterns

### 1. Encryption in the client
- **Issue:** The key is in the client; an attacker can
  extract it
- **Fix:** Encrypt on the server only

### 2. Key in code
- **Issue:** A breach exposes the key
- **Fix:** Use a KMS

### 3. ECB mode
- **Issue:** Same plaintext = same ciphertext (pattern
  leaks)
- **Fix:** Use GCM mode

### 4. No IV
- **Issue:** Same key + same plaintext = same ciphertext
- **Fix:** Use a random IV

### 5. Same key for everything
- **Issue:** A breach exposes all data
- **Fix:** Per-environment keys; rotate regularly

### 6. Encrypted data without backup
- **Issue:** Lose the key, lose the data
- **Fix:** Backup the key securely

## The "CF Workers + encryption" pattern

For CF Workers, use the Web Crypto API:
```ts
// In a Worker
const key = await crypto.subtle.importKey(
  'raw',
  base64Decode(env.ENCRYPTION_KEY),
  { name: 'AES-GCM', length: 256 },
  false,
  ['encrypt', 'decrypt'],
);
```

CF Workers has Web Crypto built-in.

## The "data at rest" table

| Data | Encrypted? | Why |
|---|---|---|
| User email | Yes (if PII) | GDPR |
| User password | Hash (Argon2id) | Cannot decrypt |
| User SSN | Yes (mandatory) | PCI |
| Credit card | Yes (PCI-DSS) | PCI |
| Health data | Yes (HIPAA) | HIPAA |
| Public content | No | Public |
| Audit log | Yes (some fields) | Compliance |

## The "key rotation" pattern

For key rotation, support multiple keys:
```ts
const KEYS = {
  'v1': key1,
  'v2': key2,  // New key
};

// Decrypt
async function decrypt(ciphertext: string, keyVersion: string): Promise<string> {
  const key = KEYS[keyVersion as keyof typeof KEYS];
  if (!key) throw new Error('Unknown key version');
  return decryptWithKey(ciphertext, key);
}

// Rotate
// 1. Generate a new key
// 2. Update the KEYS map
// 3. Re-encrypt all data with the new key (background job)
// 4. Remove the old key
```

The old key is kept until all data is re-encrypted.

## The "compliance" requirement

| Standard | Encryption requirement |
|---|---|
| **GDPR** | "Appropriate" technical measures (encryption recommended) |
| **PCI-DSS** | Strong cryptography for cardholder data |
| **HIPAA** | Addressable: encryption is one option |
| **SOC 2** | Encryption at rest is a common control |
| **CCPA** | "Reasonable security" (encryption recommended) |

For most regulated data, encryption is required or strongly
recommended.

## Verification
- **Test:** Encrypt + decrypt round-trip
- **Test:** Wrong key fails
- **Test:** Tampered ciphertext is rejected
- **Audit:** Annual key rotation
- **Pen test:** Annual security review

## Gotchas
- **The "encryption without key management" anti-pattern.**
  The key is the most valuable thing; secure it.
- **The "encryption in the client" anti-pattern.** The
  key is exposed.
- **The "deterministic encryption for uniqueness" anti-
  pattern.** Deterministic encryption leaks duplicates.
- **The "encrypt everything" anti-pattern.** Encryption
  has a performance cost. Encrypt only what's needed.
- **The "no backup" anti-pattern.** Lose the key, lose
  the data.

## Related
- `secrets-encryption-at-rest.md`
- `secrets-management-detail.md`
- `secrets-rotation-runbook.md`
- `gdpr-article-17-erasure.md` (encrypted data can be hard
  to erase)
- Web Crypto: https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API
- NIST: https://csrc.nist.gov/publications/detail/sp/800-175b/final
