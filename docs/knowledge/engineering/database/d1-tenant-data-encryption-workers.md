# D1 Per-Tenant Data Encryption in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You store sensitive per-tenant data in D1 — PII fields, API credentials, health records,
financial data — and need encryption at the column level so that a D1 database export or
a compromised read path does not expose plaintext data for all tenants at once. Each
tenant's data must be encrypted with a key derived from or unique to that tenant, so that
revoking one tenant's key does not affect others.

## Context

D1 does not offer column-level encryption natively. SQLite's encryption extension (SEE) is
a paid commercial product not available in D1. The correct pattern for Cloudflare Workers
is **application-layer AES-256-GCM encryption** using the Web Crypto API (`crypto.subtle`),
which is available in the Workers runtime with no imports. Encryption keys are stored in
Cloudflare KV (or Workers Secrets for a single global key) and are never written to D1.

**Key derivation hierarchy**:
- A root key (Workers Secret, `ENCRYPTION_ROOT_KEY`) is stored as a hex string in the
  Worker environment — never in D1 or KV.
- Per-tenant derived keys are produced by HKDF from the root key and the tenant ID.
- Derived keys are cached in-memory per Worker invocation (not persisted to KV) to avoid
  a KV read on every encrypted column access.

---

## Key Derivation Utilities

```typescript
// src/lib/encryption.ts

/**
 * Derives a per-tenant AES-256-GCM key from the root key and tenant ID.
 * Uses HKDF-SHA-256. The derived key is stable: same root + same tenantId = same key.
 */
export async function deriveTenantKey(rootKeyHex: string, tenantId: string): Promise<CryptoKey> {
  const rootBytes = hexToBytes(rootKeyHex);

  // Import root key as HKDF key material
  const hkdfKey = await crypto.subtle.importKey(
    'raw',
    rootBytes,
    { name: 'HKDF' },
    false,
    ['deriveKey'],
  );

  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new TextEncoder().encode('d1-tenant-encryption-v1'),
      info: new TextEncoder().encode(tenantId),
    },
    hkdfKey,
    { name: 'AES-GCM', length: 256 },
    false,     // not extractable
    ['encrypt', 'decrypt'],
  );
}

export async function encryptField(key: CryptoKey, plaintext: string): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12)); // 96-bit IV for AES-GCM
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  // Store as base64(iv) + '.' + base64(ciphertext)
  return `${bytesToBase64(iv)}.${bytesToBase64(new Uint8Array(ciphertext))}`;
}

export async function decryptField(key: CryptoKey, encoded: string): Promise<string> {
  const [ivB64, ciphertextB64] = encoded.split('.');
  if (!ivB64 || !ciphertextB64) throw new Error('Invalid encrypted field format');
  const iv = base64ToBytes(ivB64);
  const ciphertext = base64ToBytes(ciphertextB64);
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
  return new TextDecoder().decode(plaintext);
}

// ── helpers ────────────────────────────────────────────────────────────────
function hexToBytes(hex: string): Uint8Array {
  const arr = new Uint8Array(hex.length / 2);
  for (let i = 0; i < arr.length; i++) arr[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return arr;
}
function bytesToBase64(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes));
}
function base64ToBytes(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}
```

---

## Schema Design

```sql
-- Encrypted columns store the opaque ciphertext string: "<iv_b64>.<ct_b64>"
-- Unencrypted metadata columns remain searchable in D1
CREATE TABLE tenant_profiles (
  id              TEXT PRIMARY KEY,
  tenant_id       TEXT NOT NULL,
  -- Unencrypted: indexed, searchable
  display_name    TEXT NOT NULL,
  tier            TEXT NOT NULL DEFAULT 'free',
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  -- Encrypted: opaque to D1, cannot be indexed or searched in SQL
  encrypted_email TEXT NOT NULL,    -- AES-GCM ciphertext
  encrypted_phone TEXT,
  encrypted_notes TEXT
);

CREATE INDEX idx_profiles_tenant ON tenant_profiles(tenant_id);
CREATE INDEX idx_profiles_tier   ON tenant_profiles(tenant_id, tier);
-- NOTE: encrypted columns are NOT indexed — ciphertext has no ordering semantics
```

---

## Write Path

```typescript
// src/services/profile-service.ts
import { D1Database } from '@cloudflare/workers-types';
import { deriveTenantKey, encryptField } from '../lib/encryption';

interface Env { DB: D1Database; ENCRYPTION_ROOT_KEY: string }

// In-request key cache: avoids re-running HKDF per column
const keyCache = new Map<string, CryptoKey>();

async function getTenantKey(env: Env, tenantId: string): Promise<CryptoKey> {
  if (!keyCache.has(tenantId)) {
    keyCache.set(tenantId, await deriveTenantKey(env.ENCRYPTION_ROOT_KEY, tenantId));
  }
  return keyCache.get(tenantId)!;
}

export async function createProfile(
  env: Env,
  profile: {
    id: string; tenantId: string; displayName: string;
    tier: string; email: string; phone?: string; notes?: string;
  },
): Promise<void> {
  const key = await getTenantKey(env, profile.tenantId);

  const [encEmail, encPhone, encNotes] = await Promise.all([
    encryptField(key, profile.email),
    profile.phone  ? encryptField(key, profile.phone)  : Promise.resolve(null),
    profile.notes  ? encryptField(key, profile.notes)  : Promise.resolve(null),
  ]);

  await env.DB.prepare(
    `INSERT INTO tenant_profiles
       (id, tenant_id, display_name, tier, encrypted_email, encrypted_phone, encrypted_notes)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`,
  ).bind(profile.id, profile.tenantId, profile.displayName, profile.tier,
    encEmail, encPhone, encNotes).run();
}
```

---

## Read Path with Selective Decryption

```typescript
// src/services/profile-service.ts (continued)
import { decryptField } from '../lib/encryption';

interface ProfileRow {
  id: string; tenant_id: string; display_name: string; tier: string;
  encrypted_email: string; encrypted_phone: string | null; encrypted_notes: string | null;
}

export async function getProfile(
  env: Env,
  tenantId: string,
  profileId: string,
): Promise<{ id: string; displayName: string; email: string; phone?: string } | null> {
  const row = await env.DB
    .prepare(`SELECT * FROM tenant_profiles WHERE id = ?1 AND tenant_id = ?2`)
    .bind(profileId, tenantId)
    .first<ProfileRow>();

  if (!row) return null;

  const key = await getTenantKey(env, tenantId);

  const [email, phone] = await Promise.all([
    decryptField(key, row.encrypted_email),
    row.encrypted_phone ? decryptField(key, row.encrypted_phone) : Promise.resolve(undefined),
  ]);

  return { id: row.id, displayName: row.display_name, email, phone };
}
```

---

## Key Rotation Strategy

```typescript
// src/lib/key-rotation.ts
// Re-encrypt all rows for a tenant under a new root key
export async function rotateTenantEncryption(
  db: D1Database,
  tenantId: string,
  oldRootKeyHex: string,
  newRootKeyHex: string,
): Promise<number> {
  const oldKey = await deriveTenantKey(oldRootKeyHex, tenantId);
  const newKey = await deriveTenantKey(newRootKeyHex, tenantId);

  const rows = await db
    .prepare(`SELECT id, encrypted_email, encrypted_phone, encrypted_notes
              FROM tenant_profiles WHERE tenant_id = ?`)
    .bind(tenantId)
    .all<{ id: string; encrypted_email: string; encrypted_phone: string | null; encrypted_notes: string | null }>();

  const stmts = await Promise.all(
    rows.results.map(async (row) => {
      const email = await decryptField(oldKey, row.encrypted_email).then((p) => encryptField(newKey, p));
      const phone = row.encrypted_phone
        ? await decryptField(oldKey, row.encrypted_phone).then((p) => encryptField(newKey, p))
        : null;
      const notes = row.encrypted_notes
        ? await decryptField(oldKey, row.encrypted_notes).then((p) => encryptField(newKey, p))
        : null;
      return db.prepare(
        `UPDATE tenant_profiles SET encrypted_email=?2, encrypted_phone=?3, encrypted_notes=?4 WHERE id=?1`,
      ).bind(row.id, email, phone, notes);
    }),
  );

  await db.batch(stmts);
  return rows.results.length;
}
```

---

## Anti-patterns

- **Storing the encryption key in D1 alongside the ciphertext**: The key must never live in
  the same storage as the ciphertext. Store it in Workers Secrets or derive it from a secret.
- **Reusing the same IV across encryptions**: AES-GCM is catastrophically broken when two
  ciphertexts use the same key+IV. Always call `crypto.getRandomValues(new Uint8Array(12))`
  per encryption call.
- **Encrypting columns that must be filtered or sorted in SQL**: Ciphertext cannot be indexed
  or compared semantically. For searchable fields, store a deterministic HMAC of the plaintext
  in a separate indexed column used only for equality lookup — never the raw value.
- **Using a global key for all tenants**: A single compromised key exposes all tenants. Derive
  per-tenant keys so that key revocation is scoped.

## Gotchas

- `crypto.subtle` operations are async. Encrypting/decrypting multiple columns requires
  `Promise.all()` to avoid serial await overhead, especially for batch reads.
- The Workers in-memory key cache (`keyCache = new Map(...)`) is scoped to a single
  isolate invocation. It is not shared across requests or Workers instances — this is
  desirable for security isolation.
- D1 has no concept of column masking. Encrypted values are returned in plaintext `SELECT *`
  results as opaque strings. Access control must be enforced at the Worker layer, not in SQL.
- Key rotation requires re-encrypting every row for the tenant. For large datasets, paginate
  with LIMIT/OFFSET and run via a Cron Trigger to stay within the 30-second CPU limit.

## Verification

```typescript
// Round-trip test
async function verifyEncryption(rootKeyHex: string, tenantId: string): Promise<void> {
  const key = await deriveTenantKey(rootKeyHex, tenantId);
  const plaintext = 'test@example.com';
  const ciphertext = await encryptField(key, plaintext);
  const decrypted = await decryptField(key, ciphertext);
  console.assert(decrypted === plaintext, 'Decryption mismatch');
  // Verify two encryptions of the same value produce different ciphertexts (unique IV)
  const ciphertext2 = await encryptField(key, plaintext);
  console.assert(ciphertext !== ciphertext2, 'IV reuse detected');
  console.log('Encryption round-trip OK');
}
```

```sql
-- Confirm no plaintext emails accidentally stored (should all start with base64 chars)
SELECT id, encrypted_email
FROM   tenant_profiles
WHERE  encrypted_email NOT LIKE '%=.%'
  AND  encrypted_email NOT GLOB '*[A-Za-z0-9+/]*.*[A-Za-z0-9+/]*';
-- Any rows returned here may have been stored without encryption
```

## Related

- `database-encryption-at-rest.md` — generic encryption-at-rest patterns
- `d1-row-level-security-tenant-id.md` — tenant isolation at the query layer
- `d1-multi-tenant-schema-isolation.md` — database-per-tenant topology
- `column-level-security.md` — Postgres column masking alternative
- `d1-audit-event-log.md` — audit who decrypted sensitive fields

## Sources

- Web Crypto API (Workers): https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- HKDF specification: https://www.rfc-editor.org/rfc/rfc5869
- AES-GCM nonce guidance: https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
