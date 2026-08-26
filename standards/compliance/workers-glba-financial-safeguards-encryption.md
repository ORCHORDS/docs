# GLBA Safeguards Rule: Encrypting Financial PII in D1 with AES-GCM and Key Rotation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The FTC Safeguards Rule (16 CFR Part 314), updated in 2023, requires financial institutions covered by GLBA to encrypt customer financial information both in transit and at rest. When customer PII (account numbers, SSNs, income figures) is stored in Cloudflare D1, you must encrypt sensitive columns before inserting them, store the encryption keys outside the database, and rotate keys periodically without downtime — all achievable using the Workers WebCrypto API and KV for key management.

## Context

- Runtime: Cloudflare Workers (TypeScript)
- Storage: Cloudflare D1 (ciphertext blobs stored as TEXT)
- Key store: Cloudflare KV (versioned AES-GCM keys)
- Crypto: Web Crypto API (`crypto.subtle`), available natively in Workers
- GLBA Safeguards Rule sections: §314.4(e) encryption, §314.4(f) access controls

---

## Section 1: Key Management in KV

Store AES-GCM keys as JWK JSON. Use a version counter so old versions can decrypt while new versions encrypt.

```typescript
// src/crypto/keyManager.ts
import { Env } from '../types';

const KEY_PREFIX  = 'glba:key:';
const META_KEY    = 'glba:key:meta';

export interface KeyMeta {
  currentVersion: number;
  createdAt: string;
}

export async function generateAndStoreKey(
  env: Env
): Promise<number> {
  const meta: KeyMeta = JSON.parse(
    (await env.KEY_KV.get(META_KEY)) ?? '{"currentVersion":0,"createdAt":""}'
  );
  const nextVersion = meta.currentVersion + 1;

  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    true,  // extractable so we can export to JWK
    ['encrypt', 'decrypt']
  );
  const jwk = await crypto.subtle.exportKey('jwk', key);

  await env.KEY_KV.put(
    `${KEY_PREFIX}${nextVersion}`,
    JSON.stringify(jwk)
  );
  await env.KEY_KV.put(
    META_KEY,
    JSON.stringify({ currentVersion: nextVersion, createdAt: new Date().toISOString() })
  );
  return nextVersion;
}

export async function loadKey(
  env: Env,
  version: number
): Promise<CryptoKey> {
  const raw = await env.KEY_KV.get(`${KEY_PREFIX}${version}`);
  if (!raw) throw new Error(`Key version ${version} not found`);
  const jwk = JSON.parse(raw) as JsonWebKey;
  return crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'AES-GCM' },
    false,
    ['encrypt', 'decrypt']
  );
}

export async function currentKeyVersion(env: Env): Promise<number> {
  const raw = await env.KEY_KV.get(META_KEY);
  if (!raw) throw new Error('No key meta found — run generateAndStoreKey first');
  return (JSON.parse(raw) as KeyMeta).currentVersion;
}
```

---

## Section 2: Encrypt / Decrypt Helpers

```typescript
// src/crypto/aesGcm.ts

// Returns base64url( iv || ciphertext ), prefixed with key version
export async function encryptField(
  key: CryptoKey,
  keyVersion: number,
  plaintext: string
): Promise<string> {
  const iv  = crypto.getRandomValues(new Uint8Array(12));  // 96-bit IV for AES-GCM
  const enc = new TextEncoder();
  const ct  = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    enc.encode(plaintext)
  );

  // Concatenate iv + ciphertext and base64url-encode
  const combined = new Uint8Array(iv.byteLength + ct.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ct), iv.byteLength);

  const b64 = btoa(String.fromCharCode(...combined))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

  return `v${keyVersion}:${b64}`;
}

export async function decryptField(
  env: { KEY_KV: KVNamespace },  // accept env or just KEY_KV
  ciphertext: string
): Promise<string> {
  const colonIdx = ciphertext.indexOf(':');
  const versionStr = ciphertext.slice(1, colonIdx);  // strip leading 'v'
  const version = parseInt(versionStr, 10);
  const b64     = ciphertext.slice(colonIdx + 1);

  // Restore padding and decode base64url
  const padded  = b64.replace(/-/g, '+').replace(/_/g, '/')
                     .padEnd(b64.length + (4 - b64.length % 4) % 4, '=');
  const bytes   = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
  const iv      = bytes.slice(0, 12);
  const ct      = bytes.slice(12);

  const { loadKey } = await import('./keyManager');
  const key = await loadKey(env as Env, version);
  const pt  = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new TextDecoder().decode(pt);
}
```

---

## Section 3: D1 Schema and Encrypted Insert

```sql
-- migrations/0004_financial_records.sql
CREATE TABLE IF NOT EXISTS financial_records (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id    TEXT NOT NULL,
  account_enc    TEXT NOT NULL,  -- encrypted account number
  ssn_enc        TEXT NOT NULL,  -- encrypted SSN
  income_enc     TEXT NOT NULL,  -- encrypted annual income
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

```typescript
// src/routes/financialRecord.ts
import { Env }            from '../types';
import { encryptField, decryptField } from '../crypto/aesGcm';
import { currentKeyVersion, loadKey } from '../crypto/keyManager';

export async function createFinancialRecord(
  env: Env,
  customerId: string,
  account: string,
  ssn: string,
  income: string
): Promise<number> {
  const version = await currentKeyVersion(env);
  const key     = await loadKey(env, version);

  const [accountEnc, ssnEnc, incomeEnc] = await Promise.all([
    encryptField(key, version, account),
    encryptField(key, version, ssn),
    encryptField(key, version, income),
  ]);

  const result = await env.FINANCIAL_DB
    .prepare(
      `INSERT INTO financial_records (customer_id, account_enc, ssn_enc, income_enc)
       VALUES (?, ?, ?, ?)`
    )
    .bind(customerId, accountEnc, ssnEnc, incomeEnc)
    .run();

  return result.meta.last_row_id as number;
}

export async function getFinancialRecord(
  env: Env,
  customerId: string
): Promise<{ account: string; ssn: string; income: string } | null> {
  const row = await env.FINANCIAL_DB
    .prepare('SELECT * FROM financial_records WHERE customer_id = ? LIMIT 1')
    .bind(customerId)
    .first<{ account_enc: string; ssn_enc: string; income_enc: string }>();

  if (!row) return null;

  const [account, ssn, income] = await Promise.all([
    decryptField(env, row.account_enc),
    decryptField(env, row.ssn_enc),
    decryptField(env, row.income_enc),
  ]);

  return { account, ssn, income };
}
```

---

## Section 4: Key Rotation Cron

```typescript
// src/cron/keyRotation.ts
import { Env } from '../types';
import { generateAndStoreKey } from '../crypto/keyManager';

// Called from scheduled handler; generates a new key version.
// Existing ciphertext keeps its version prefix and decrypts with the old key.
// Only new writes use the new key version.
export async function runKeyRotation(env: Env): Promise<void> {
  const newVersion = await generateAndStoreKey(env);
  console.log(`[key-rotation] new key version: ${newVersion}`);

  // Optionally: re-encrypt all rows with the new key (re-encryption job)
  // For simplicity this example uses lazy re-encryption on read.
}
```

```toml
# wrangler.toml additions
[[kv_namespaces]]
binding      = "KEY_KV"
id           = "<your-kv-id>"

[[d1_databases]]
binding       = "FINANCIAL_DB"
database_name = "financial-records"
database_id   = "<your-d1-id>"

[triggers]
crons = ["0 3 1 * *"]  # rotate keys on 1st of each month at 03:00 UTC
```

---

## Anti-patterns

- Storing encryption keys in the same D1 database as the ciphertext — if the DB is compromised so are the keys.
- Using ECB mode or a fixed IV — AES-GCM requires a unique 96-bit random IV per encryption call.
- Base64-encoding plaintext and calling it "encryption" — this provides zero confidentiality.
- Rotating keys without preserving the version prefix on ciphertext — you lose the ability to decrypt old rows.
- Logging plaintext PII values during debugging — scrub logs before enabling verbose mode in production.

## Gotchas

- `crypto.subtle` is async; always `await` encrypt/decrypt — returning a Promise where a string is expected causes silent failures.
- AES-GCM authentication tag is appended to the ciphertext by WebCrypto; your byte layout must account for `ct.byteLength = plaintext.length + 16`.
- KV values have a 25 MiB size limit — well above JWK size, but keep metadata payloads slim.
- GLBA requires access logs for PII — combine this article with `workers-iso-27001-access-log-d1.md`.

---

## Verification

```bash
# Bootstrap: generate first key
npx wrangler dev &
curl -X POST https://api.example.com/admin/rotate-key

# Insert a test record
curl -X POST https://api.example.com/financial \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"C001","account":"1234-5678","ssn":"123-45-6789","income":"75000"}'

# Verify ciphertext in D1 (should NOT show plaintext)
npx wrangler d1 execute FINANCIAL_DB --remote \
  --command "SELECT account_enc FROM financial_records WHERE customer_id='C001';"

# Decrypt via API
curl https://api.example.com/financial/C001 | jq .

# Rotate key and verify old records still decrypt
npx wrangler d1 execute FINANCIAL_DB --remote \
  --command "SELECT substr(account_enc,1,5) as key_ver FROM financial_records;"
```

---

## Related

- `documentation/categories/compliance/workers-iso-27001-access-log-d1.md`
- `documentation/categories/compliance/workers-nist-csf-incident-response-d1.md`
- `documentation/workers/webcrypto-patterns.md`

## Sources

- https://www.ftc.gov/business-guidance/resources/ftc-safeguards-rule-what-your-business-needs-know (FTC GLBA Safeguards Rule)
- https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314 (16 CFR Part 314)
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
