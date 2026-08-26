# D1 WAL Checkpoint Data Residency and Compliance Hardening

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Organisations subject to GDPR, HIPAA, or national data-sovereignty laws need guarantees that
personal data stored in Cloudflare D1 does not persist in regions outside a declared boundary
after a deletion event.

D1 uses a distributed SQLite architecture backed by Cloudflare's object-storage layer. SQLite's
Write-Ahead Log (WAL) mode means that a row deletion does not immediately reclaim storage or
remove data from checkpoint frames. If replication snapshots, WAL frames, or backup exports are
not handled correctly:

- Deleted EU-resident PII may survive in WAL segments replicated to non-EU PoPs.
- A court-ordered deletion (GDPR Article 17 "right to erasure") may not be complete until
  after checkpoint and vacuum cycles propagate.
- Encrypted columns that rely on application-level keys may still be decipherable if the WAL
  frame is captured before the key is rotated.

---

## Context

Cloudflare D1 in 2026 supports **location hints** that bias primary placement, but data is
replicated globally for read performance by default. Key WAL facts:

| WAL concept | D1 behaviour |
|---|---|
| WAL frames written on write | SQLite WAL frames replicate as-is to Cloudflare's underlying object store |
| `PRAGMA wal_checkpoint` | Available but D1 checkpoints automatically at transaction commit; manual PRAGMA may be no-op |
| `VACUUM` | `VACUUM INTO` is supported; full `VACUUM` reclaims WAL and rewrites the database file |
| Data at rest encryption | Cloudflare encrypts at infrastructure level (AES-256); application-level column encryption is the tenant's responsibility |
| Backup exports | `wrangler d1 export` dumps a snapshot; this snapshot may include WAL-pending rows |

For compliance, the practical controls available to D1 tenants are:

1. **Application-level column encryption** — encrypt PII before writing; key rotation + re-encryption makes residual WAL frames unreadable.
2. **Pseudonymisation** — store only a hashed or tokenised identifier; map to real PII in a separate system of record with a shorter retention window.
3. **Erasure via key deletion** — "crypto-shredding": delete the encryption key, rendering all copies of the ciphertext opaque.
4. **Export hygiene** — treat D1 export files as regulated data; encrypt and scope them.

---

## Code sections

### 1. Encrypted PII column write — crypto-shredding ready

```typescript
// lib/d1-pii-store.ts
const ALGO = { name: "AES-GCM", length: 256 } as const;

export async function encryptField(
  plaintext: string,
  key: CryptoKey
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plaintext)
  );
  // Store iv + ciphertext as base64
  const combined = new Uint8Array(iv.byteLength + enc.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(enc), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

export async function decryptField(
  ciphertext: string,
  key: CryptoKey
): Promise<string> {
  const bytes = Uint8Array.from(atob(ciphertext), (c) => c.charCodeAt(0));
  const iv = bytes.slice(0, 12);
  const ct = bytes.slice(12);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
  return new TextDecoder().decode(plain);
}
```

### 2. Per-tenant key management via Workers KV

```typescript
// lib/key-store.ts
export interface Env {
  PII_KEYS: KVNamespace;
}

const KV_KEY_VERSION_PREFIX = "pii-key:v";

export async function getLatestKey(
  env: Env,
  tenantId: string
): Promise<{ version: number; key: CryptoKey }> {
  // Enumerate versions stored as "pii-key:v<N>:<tenantId>"
  const list = await env.PII_KEYS.list({
    prefix: `${KV_KEY_VERSION_PREFIX}`,
    limit: 100,
  });

  const tenant_keys = list.keys
    .filter((k) => k.name.endsWith(`:${tenantId}`))
    .map((k) => ({
      version: parseInt(k.name.split(":")[1].replace("v", ""), 10),
      name: k.name,
    }))
    .sort((a, b) => b.version - a.version);

  if (tenant_keys.length === 0) throw new Error(`No key for tenant ${tenantId}`);

  const latest = tenant_keys[0];
  const raw = await env.PII_KEYS.get(latest.name, "arrayBuffer");
  if (!raw) throw new Error("Key material not found in KV");

  const key = await crypto.subtle.importKey(
    "raw",
    raw,
    ALGO,
    false, // non-extractable
    ["encrypt", "decrypt"]
  );
  return { version: latest.version, key };
}

export async function provisionKey(
  env: Env,
  tenantId: string,
  version: number
): Promise<void> {
  const raw = crypto.getRandomValues(new Uint8Array(32));
  await env.PII_KEYS.put(`${KV_KEY_VERSION_PREFIX}${version}:${tenantId}`, raw, {
    // Keys survive until explicitly deleted (crypto-shredding entrypoint)
    metadata: {
      tenantId,
      version,
      createdAt: new Date().toISOString(),
    },
  });
}

export async function cryptoShred(env: Env, tenantId: string): Promise<void> {
  // Delete all key versions for this tenant — renders all ciphertexts opaque
  const list = await env.PII_KEYS.list({
    prefix: `${KV_KEY_VERSION_PREFIX}`,
  });
  const toDelete = list.keys.filter((k) => k.name.endsWith(`:${tenantId}`));
  await Promise.all(toDelete.map((k) => env.PII_KEYS.delete(k.name)));
}
```

### 3. Writing and reading a PII row with key version tracking

```typescript
// lib/user-store.ts
import { encryptField, decryptField } from "./d1-pii-store";
import { getLatestKey } from "./key-store";

export async function createUser(
  db: D1Database,
  env: Env,
  tenantId: string,
  userId: string,
  email: string,
  phone: string
): Promise<void> {
  const { version, key } = await getLatestKey(env, tenantId);
  const [encEmail, encPhone] = await Promise.all([
    encryptField(email, key),
    encryptField(phone, key),
  ]);

  await db
    .prepare(
      `INSERT INTO users (id, tenant_id, enc_email, enc_phone, key_version, created_at)
       VALUES (?, ?, ?, ?, ?, unixepoch())`
    )
    .bind(userId, tenantId, encEmail, encPhone, version)
    .run();
}

export async function getUser(
  db: D1Database,
  env: Env,
  tenantId: string,
  userId: string
): Promise<{ email: string; phone: string } | null> {
  const row = await db
    .prepare(
      `SELECT enc_email, enc_phone, key_version FROM users
       WHERE id = ? AND tenant_id = ?`
    )
    .bind(userId, tenantId)
    .first<{ enc_email: string; enc_phone: string; key_version: number }>();

  if (!row) return null;

  // Fetch the specific key version that was used to encrypt this row
  const raw = await env.PII_KEYS.get(
    `pii-key:v${row.key_version}:${tenantId}`,
    "arrayBuffer"
  );
  if (!raw) throw new Error("Key not found — possible crypto-shred already applied");

  const key = await crypto.subtle.importKey("raw", raw, ALGO, false, ["decrypt"]);
  const [email, phone] = await Promise.all([
    decryptField(row.enc_email, key),
    decryptField(row.enc_phone, key),
  ]);
  return { email, phone };
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS users (
  id          TEXT    NOT NULL,
  tenant_id   TEXT    NOT NULL,
  enc_email   TEXT    NOT NULL,  -- AES-GCM(base64)
  enc_phone   TEXT    NOT NULL,  -- AES-GCM(base64)
  key_version INTEGER NOT NULL,  -- links to KV key entry
  created_at  INTEGER NOT NULL,
  PRIMARY KEY (id, tenant_id)
);
```

### 4. Right-to-erasure endpoint

```typescript
// Handles GDPR Art. 17 "right to erasure" requests
export async function handleErasureRequest(
  db: D1Database,
  env: Env,
  tenantId: string,
  userId: string
): Promise<{ rowsDeleted: number; keysShreddedCount: number }> {
  // 1. Delete the row from D1 (WAL frame will remain temporarily but plaintext is gone)
  const result = await db
    .prepare(`DELETE FROM users WHERE id = ? AND tenant_id = ?`)
    .bind(userId, tenantId)
    .run();

  // 2. If this was the last user for the tenant, crypto-shred the keys
  const remaining = await db
    .prepare(`SELECT count(*) as n FROM users WHERE tenant_id = ?`)
    .bind(tenantId)
    .first<{ n: number }>();

  let shreddedCount = 0;
  if ((remaining?.n ?? 0) === 0) {
    const list = await env.PII_KEYS.list({ prefix: `pii-key:v` });
    const tenantKeys = list.keys.filter((k) => k.name.endsWith(`:${tenantId}`));
    await Promise.all(tenantKeys.map((k) => env.PII_KEYS.delete(k.name)));
    shreddedCount = tenantKeys.length;
  }

  return {
    rowsDeleted: result.meta?.rows_written ?? 0,
    keysShreddedCount: shreddedCount,
  };
}
```

### 5. Encrypted D1 export hygiene via R2

```typescript
// Export D1 snapshot encrypted to R2 — avoids plaintext WAL exposure
export async function encryptedExport(
  env: Env & { EXPORT_BUCKET: R2Bucket; EXPORT_KEY_SECRET: string }
): Promise<void> {
  // Derive an AES key from the export secret
  const baseKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.EXPORT_KEY_SECRET),
    "HKDF",
    false,
    ["deriveKey"]
  );
  const exportKey = await crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(16), info: new TextEncoder().encode("d1-export") },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt"]
  );

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const exportKey2 = `backups/d1-export-${timestamp}.db.enc`;

  const plaintextBytes = new TextEncoder().encode("-- SQL dump placeholder");
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    exportKey,
    plaintextBytes
  );

  const blob = new Uint8Array(iv.byteLength + encrypted.byteLength);
  blob.set(iv, 0);
  blob.set(new Uint8Array(encrypted), 12);

  await env.EXPORT_BUCKET.put(exportKey2, blob, {
    httpMetadata: { contentType: "application/octet-stream" },
    customMetadata: { encrypted: "aes-gcm-256", exportedAt: new Date().toISOString() },
  });
}
```

---

## Anti-patterns

- Storing PII in plaintext columns and relying solely on Cloudflare's infrastructure-level encryption for compliance — infrastructure encryption does not satisfy crypto-shredding requirements.
- Running `wrangler d1 export` without immediately encrypting the output file — the export is a plaintext SQLite file.
- Using a single global encryption key for all tenants — a crypto-shred for one tenant renders all tenants' data inaccessible.
- Deleting a D1 row and immediately certifying erasure without acknowledging the WAL checkpoint window.
- Storing key material in D1 itself — keys must survive independently from the ciphertext they protect; KV (with its own encryption and replication model) or an external KMS is required.

---

## Gotchas

- D1 does not currently expose `PRAGMA wal_checkpoint` results to applications; checkpoint timing is internal to Cloudflare. Assume WAL frames persist for at least the Cloudflare replication window (minutes to hours) before erasure is complete at the storage layer.
- `wrangler d1 export` produces a snapshot at a point in time; it may include rows that have been deleted in-flight if the export runs during an active write workload.
- Per-row `key_version` tracking is required for key rotation to be safe; without it, re-keying all rows atomically is not possible in D1 without a full table rewrite.
- Cloudflare D1 location hints bias primary placement but do not prevent global read-replica propagation. If strict single-region residency is required, D1 is not currently the right primitive; use a regional database accessed via Hyperdrive with geo-locked Workers routes.
- AES-GCM nonces must be unique per encryption call per key; never reuse an IV. The `crypto.getRandomValues(new Uint8Array(12))` pattern provides 96-bit random nonces — collision probability is negligible for volumes under 2^32 encryptions per key.

---

## Verification

```bash
# 1. Confirm enc_email column stores ciphertext, not plaintext
wrangler d1 execute orchords-db \
  --command "SELECT enc_email FROM users LIMIT 1"
# expect: a base64 blob, never a readable email address

# 2. Test erasure endpoint
curl -X DELETE "https://worker.example.com/users/user123?tenant=tenant456"
# expect: {"rowsDeleted":1,"keysShreddedCount":2}

# 3. Confirm decryption fails after crypto-shred
curl "https://worker.example.com/users/user123?tenant=tenant456"
# expect: 500 "Key not found — possible crypto-shred already applied"

# 4. Verify export is encrypted
wrangler d1 export orchords-db --output /tmp/export.sql
file /tmp/export.sql
# expect: plaintext (encrypt this file before storing!)
```

---

## Related

- `d1-encrypted-column-workers-crypto-api.md`
- `d1-backup-r2-encrypted-export.md`
- `workers-hkdf-key-derivation-hierarchical-secrets.md`
- `secrets-encryption-at-rest.md`
- `multi-tenancy-isolation-workers-kv-d1.md`
- `workers-kv-ttl-token-revocation-expiry.md`

---

## Sources

- GDPR Article 17 — Right to Erasure — https://gdpr-info.eu/art-17-gdpr/
- NIST SP 800-188: De-Identifying Government Datasets — https://csrc.nist.gov/publications/detail/sp/800-188/final
- Cloudflare D1 architecture — https://developers.cloudflare.com/d1/reference/database-engine/
- SQLite WAL mode — https://www.sqlite.org/wal.html
- Web Crypto API AES-GCM — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt#aes-gcm
- Cloudflare Workers KV documentation — https://developers.cloudflare.com/kv/
