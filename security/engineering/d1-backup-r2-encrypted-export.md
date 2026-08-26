# D1 Database Backup Encryption and Secure Export to R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Teams export D1 databases to R2 for disaster recovery or compliance archiving. Cloudflare's built-in D1 export writes a raw SQLite dump — unencrypted SQL text containing PII, API keys hashed with bcrypt, and financial records. An inadvertent R2 bucket policy misconfiguration would expose the entire dataset. Encrypting the backup with AES-GCM before writing to R2 limits the blast radius to the encryption key.

## Context

Cloudflare D1 does not natively encrypt exports. The export API (`/client/v4/accounts/{account_id}/d1/database/{database_id}/export`) produces a signed download URL for a raw SQLite file or SQL dump. A Workers cron job can fetch this dump, encrypt it in-memory with `SubtleCrypto.encrypt`, then write the ciphertext to R2 with key metadata. The encryption key lives in Workers Secrets Store — never in environment variables or the R2 object itself.

---

## 1. Triggering the D1 Export via REST API

```typescript
// src/d1-export.ts

export interface D1ExportResult {
  signedUrl: string;     // short-lived URL to download the SQL dump
  filename: string;
}

export async function requestD1Export(
  accountId: string,
  databaseId: string,
  cfApiToken: string,
): Promise<D1ExportResult> {
  // Initiate export — Cloudflare creates an export task
  const initResp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/export`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${cfApiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ output_format: 'polling' }),
    },
  );
  if (!initResp.ok) {
    throw new Error(`D1 export initiation failed: ${initResp.status} ${await initResp.text()}`);
  }
  const init = await initResp.json<{ result: { at_bookmark: string } }>();

  // Poll until the export is ready (may take seconds for large databases)
  for (let attempt = 0; attempt < 30; attempt++) {
    const pollResp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/export`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${cfApiToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          output_format: 'polling',
          current_bookmark: init.result.at_bookmark,
        }),
      },
    );
    const poll = await pollResp.json<any>();
    if (poll.result?.status === 'complete') {
      return {
        signedUrl: poll.result.signed_url,
        filename: poll.result.filename,
      };
    }
    if (poll.result?.status === 'error') {
      throw new Error(`D1 export error: ${JSON.stringify(poll.result)}`);
    }
    // Wait between polls — Workers cannot use setTimeout; use a busy loop approximation
    // In practice, use a Durable Object alarm for large databases
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error('D1 export polling timeout');
}
```

---

## 2. Streaming Encryption with AES-GCM

Encrypt the entire dump in-memory (suitable for databases up to ~50MB; use streaming for larger).

```typescript
// src/encrypt.ts

export interface EncryptedBundle {
  iv: Uint8Array;           // 12-byte random IV
  ciphertext: ArrayBuffer;  // AES-GCM encrypted payload
  keyVersion: string;       // key rotation identifier
}

export async function encryptDump(
  plaintext: ArrayBuffer,
  aesKey: CryptoKey,
  keyVersion: string,
): Promise<EncryptedBundle> {
  const iv = crypto.getRandomValues(new Uint8Array(12)); // 96-bit IV for AES-GCM

  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, tagLength: 128 },
    aesKey,
    plaintext,
  );

  return { iv, ciphertext, keyVersion };
}

export async function decryptDump(
  bundle: EncryptedBundle,
  aesKey: CryptoKey,
): Promise<ArrayBuffer> {
  return crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: bundle.iv, tagLength: 128 },
    aesKey,
    bundle.ciphertext,
  );
}

export async function importBackupKey(rawKeyBase64: string): Promise<CryptoKey> {
  const rawKey = Uint8Array.from(atob(rawKeyBase64), c => c.charCodeAt(0));
  if (rawKey.length !== 32) throw new Error('AES-256 key must be 32 bytes');
  return crypto.subtle.importKey('raw', rawKey, 'AES-GCM', false, ['encrypt', 'decrypt']);
}
```

---

## 3. Writing Encrypted Backup to R2 with Metadata

Store the IV and key version as R2 object custom metadata — the IV is not secret (public), but the key version is needed for decryption routing.

```typescript
// src/backup-writer.ts
import { EncryptedBundle } from './encrypt';

export interface BackupMetadata {
  sourceDatabase: string;
  exportTimestamp: string;
  keyVersion: string;
  ivHex: string;
  plaintextSha256?: string;   // hex hash of plaintext for integrity check after decryption
}

export async function writeEncryptedBackupToR2(
  bucket: R2Bucket,
  bundle: EncryptedBundle,
  dbId: string,
  plaintextBuffer: ArrayBuffer,
): Promise<string> {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const objectKey = `backups/${dbId}/${timestamp}.db.aes`;

  // Compute plaintext SHA-256 for post-decryption integrity verification
  const hashBuffer = await crypto.subtle.digest('SHA-256', plaintextBuffer);
  const plaintextSha256 = Array.from(new Uint8Array(hashBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  const metadata: BackupMetadata = {
    sourceDatabase: dbId,
    exportTimestamp: timestamp,
    keyVersion: bundle.keyVersion,
    ivHex: Array.from(bundle.iv).map(b => b.toString(16).padStart(2, '0')).join(''),
    plaintextSha256,
  };

  await bucket.put(objectKey, bundle.ciphertext, {
    httpMetadata: { contentType: 'application/octet-stream' },
    customMetadata: metadata as unknown as Record<string, string>,
  });

  return objectKey;
}
```

---

## 4. Orchestrating the Backup Worker

```typescript
// src/index.ts
import { requestD1Export } from './d1-export';
import { encryptDump, importBackupKey } from './encrypt';
import { writeEncryptedBackupToR2 } from './backup-writer';

export interface Env {
  CF_API_TOKEN: string;         // Cloudflare API token with D1:Read permission
  CF_ACCOUNT_ID: string;
  D1_DATABASE_ID: string;
  BACKUP_ENCRYPTION_KEY: string;   // Base64 AES-256 key from Secrets Store
  BACKUP_KEY_VERSION: string;      // e.g. "2026-Q3" — bump on key rotation
  BACKUP_BUCKET: R2Bucket;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runBackup(env));
  },
};

async function runBackup(env: Env): Promise<void> {
  console.log('Starting D1 backup...');

  const { signedUrl } = await requestD1Export(env.CF_ACCOUNT_ID, env.D1_DATABASE_ID, env.CF_API_TOKEN);

  const dumpResp = await fetch(signedUrl);
  if (!dumpResp.ok) throw new Error(`Failed to download D1 dump: ${dumpResp.status}`);
  const plaintext = await dumpResp.arrayBuffer();

  const aesKey = await importBackupKey(env.BACKUP_ENCRYPTION_KEY);
  const bundle = await encryptDump(plaintext, aesKey, env.BACKUP_KEY_VERSION);

  const objectKey = await writeEncryptedBackupToR2(
    env.BACKUP_BUCKET, bundle, env.D1_DATABASE_ID, plaintext,
  );

  console.log(`Backup written to R2: ${objectKey} (${bundle.ciphertext.byteLength} bytes encrypted)`);
}
```

---

## 5. Decryption and Restoration Pattern

```typescript
// scripts/restore.ts — run locally with Wrangler dev or a trusted Worker
async function restoreFromBackup(
  bucket: R2Bucket,
  objectKey: string,
  aesKey: CryptoKey,
): Promise<ArrayBuffer> {
  const obj = await bucket.get(objectKey);
  if (!obj) throw new Error(`Object not found: ${objectKey}`);

  const meta = obj.customMetadata as { ivHex: string; plaintextSha256: string };
  const iv = Uint8Array.from(meta.ivHex.match(/.{2}/g)!.map(h => parseInt(h, 16)));

  const ciphertext = await obj.arrayBuffer();
  const { decryptDump } = await import('./encrypt');
  const plaintext = await decryptDump({ iv, ciphertext, keyVersion: meta.keyVersion }, aesKey);

  // Verify integrity
  const hashBuffer = await crypto.subtle.digest('SHA-256', plaintext);
  const actualHash = Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');
  if (actualHash !== meta.plaintextSha256) {
    throw new Error('Plaintext integrity check failed — backup may be corrupted or tampered');
  }
  return plaintext;
}
```

---

## Anti-patterns

- Storing the `BACKUP_ENCRYPTION_KEY` in `wrangler.toml` `[vars]` — plaintext secrets committed to version control.
- Using AES-ECB mode — produces deterministic ciphertext; identical SQL blocks produce identical encrypted blocks, leaking schema structure.
- Reusing the same IV across multiple backups — AES-GCM with a reused IV for the same key breaks confidentiality.
- Writing the IV into the ciphertext stream without metadata — makes decryption impossible after key rotation if the IV is lost.
- Skipping the post-decryption SHA-256 integrity check — silent corruption goes undetected until restoration.
- Granting the backup Worker `D1:Write` permission — the backup job only needs `D1:Read`; follow least privilege.

## Gotchas

- D1 export polling uses `current_bookmark` from the initiation response — omitting it causes the API to re-initiate a new export.
- Workers cannot use `setTimeout` reliably inside `fetch` handlers; for large databases that take minutes to export, use a Durable Object alarm to poll asynchronously.
- AES-GCM with a 128-bit tag (`tagLength: 128`) provides authenticated encryption — the tag is appended to the ciphertext by SubtleCrypto; the total `ciphertext.byteLength` is `plaintext.byteLength + 16`.
- R2 `customMetadata` values must be strings; encode `ivHex` as a hex string, not a Uint8Array.
- The signed D1 export URL has a short TTL (minutes); download the dump immediately after receiving it.

## Verification

```bash
# List encrypted backups in R2
wrangler r2 object list backup-bucket --prefix "backups/${D1_DATABASE_ID}/" | jq '.[].key'

# Inspect metadata (IV and key version) of a specific backup
wrangler r2 object get backup-bucket "backups/${D1_DATABASE_ID}/2026-08-23.db.aes" --remote 2>&1 \
  | grep -E "(keyVersion|ivHex|plaintextSha256)"

# Verify ciphertext is not plaintext SQLite (should NOT start with "SQLite format 3")
wrangler r2 object get backup-bucket "backups/${D1_DATABASE_ID}/latest.db.aes" -o /tmp/backup.bin
xxd /tmp/backup.bin | head -2
# Expected: random bytes (no "53 51 4c 69 74 65" SQLite magic)
```

## Related

- `d1-encrypted-column-workers-crypto-api.md` — Encrypting individual D1 columns with AES-GCM
- `r2-bucket-public-exposure-audit.md` — Ensuring backup R2 bucket is not publicly accessible
- `workers-hkdf-key-derivation-hierarchical-secrets.md` — HKDF for deriving per-database keys from a master secret
- `workers-audit-log-immutable-r2-worm-pattern.md` — Immutable R2 objects for audit trails

## Sources

- [Cloudflare D1 Export API](https://developers.cloudflare.com/d1/platform/export-import-data/)
- [SubtleCrypto AES-GCM — MDN](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt#aes-gcm)
- [R2 PutObject customMetadata](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [Workers Secrets Store](https://developers.cloudflare.com/workers/configuration/secrets/)
