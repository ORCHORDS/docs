# API Key Hash Storage in Workers D1 — Bcrypt-Alternative Patterns

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You issue long-lived API keys to customers and store them in D1.  You cannot store keys
in plaintext, but the Cloudflare Workers runtime has no native bcrypt implementation and
the WASM-compiled bcrypt libraries add significant bundle size and latency.  You need a
secure, verifiable storage scheme using only the Web Crypto API that is available in the
Workers runtime (`crypto.subtle`).

---

## Context

bcrypt's purpose in password storage is its tunable work factor that keeps brute-force
expensive even as hardware improves.  API keys are different from passwords:

- API keys are **long** (≥128 bits of entropy) and **randomly generated**, so they
  resist offline brute-force by virtue of their length.
- The primary threat is **database breach** revealing the stored value.
- The secondary threat is **timing attacks** on comparison.

Given these constraints, the preferred scheme for Cloudflare Workers is:
1. **Generate** a 32-byte (256-bit) random key, encode it as base64url.
2. **Derive** a storage hash using HKDF-SHA-256 with a per-deployment secret as the IKM
   and the key itself as info (so the stored value is a keyed hash — a MAC over the key).
3. **Store** only the HKDF output in D1; never the plaintext key.
4. **Verify** by re-deriving the HKDF output and comparing with a timing-safe equals.

This is comparable to the "keyed hash" approach used by GitHub's personal access token
storage.

---

## 1. Generating an API Key

```typescript
// src/keygen.ts
export const KEY_PREFIX = 'sk_live_';
const KEY_BYTES = 32; // 256 bits

export function generateApiKey(): string {
  const raw = new Uint8Array(KEY_BYTES);
  crypto.getRandomValues(raw);
  const b64 = btoa(String.fromCharCode(...raw))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
  return `${KEY_PREFIX}${b64}`;
}
```

The prefix (`sk_live_`) lets secret-scanning tools detect accidentally leaked keys in
logs, source code, and GitHub commits.

---

## 2. Importing the HKDF Key from the Deployment Secret

```typescript
// src/hkdf.ts
export async function importHkdfKey(secret: string): Promise<CryptoKey> {
  const raw = new TextEncoder().encode(secret);
  return crypto.subtle.importKey(
    'raw',
    raw,
    { name: 'HKDF' },
    false,          // non-extractable
    ['deriveBits'],
  );
}

export async function deriveKeyHash(
  hkdfKey: CryptoKey,
  apiKey: string,
): Promise<string> {
  const info = new TextEncoder().encode(apiKey);
  // Use a fixed, domain-separated salt
  const salt = new TextEncoder().encode('api-key-hash-v1');

  const bits = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt,
      info,
    },
    hkdfKey,
    256, // output bits
  );

  return Array.from(new Uint8Array(bits))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

---

## 3. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id           TEXT PRIMARY KEY,         -- UUID, returned to the client
  key_hash     TEXT NOT NULL UNIQUE,     -- HKDF output, hex-encoded
  owner_id     TEXT NOT NULL,
  name         TEXT NOT NULL DEFAULT '',
  scopes       TEXT NOT NULL DEFAULT '[]', -- JSON array of scope strings
  created_at   INTEGER NOT NULL,
  last_used_at INTEGER,
  expires_at   INTEGER,                  -- NULL = never expires
  revoked      INTEGER NOT NULL DEFAULT 0  -- 0 | 1
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash     ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_owner    ON api_keys (owner_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_expires  ON api_keys (expires_at) WHERE expires_at IS NOT NULL;
```

---

## 4. Issuing a Key

```typescript
// src/issue.ts
import { generateApiKey } from './keygen';
import { importHkdfKey, deriveKeyHash } from './hkdf';
import { randomUUID } from 'crypto'; // available in Workers via globalThis

export interface IssueResult {
  id: string;
  plaintext: string; // shown to the user exactly once
}

export async function issueApiKey(
  db: D1Database,
  hkdfSecret: string,
  ownerId: string,
  name: string,
  scopes: string[],
  ttlDays?: number,
): Promise<IssueResult> {
  const plaintext = generateApiKey();
  const hkdfKey = await importHkdfKey(hkdfSecret);
  const keyHash = await deriveKeyHash(hkdfKey, plaintext);

  const id = crypto.randomUUID();
  const now = Date.now();
  const expiresAt = ttlDays ? now + ttlDays * 86_400_000 : null;

  await db
    .prepare(
      `INSERT INTO api_keys
         (id, key_hash, owner_id, name, scopes, created_at, expires_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(id, keyHash, ownerId, name, JSON.stringify(scopes), now, expiresAt)
    .run();

  return { id, plaintext };
}
```

Return `plaintext` to the user in the response body **once** and never log it.

---

## 5. Verifying an Incoming Key

```typescript
// src/verify.ts
import { importHkdfKey, deriveKeyHash } from './hkdf';

export interface KeyRecord {
  id: string;
  owner_id: string;
  scopes: string[];
  expires_at: number | null;
  revoked: number;
}

export async function verifyApiKey(
  db: D1Database,
  hkdfSecret: string,
  raw: string,
): Promise<KeyRecord | null> {
  const hkdfKey = await importHkdfKey(hkdfSecret);
  const hash = await deriveKeyHash(hkdfKey, raw);

  const row = await db
    .prepare(
      `SELECT id, owner_id, scopes, expires_at, revoked
         FROM api_keys
        WHERE key_hash = ?
        LIMIT 1`,
    )
    .bind(hash)
    .first<KeyRecord>();

  if (!row) return null;
  if (row.revoked) return null;
  if (row.expires_at && row.expires_at < Date.now()) return null;

  // Update last_used_at asynchronously — do not block verification
  // (caller must wrap in ctx.waitUntil)
  db.prepare(`UPDATE api_keys SET last_used_at = ? WHERE id = ?`)
    .bind(Date.now(), row.id)
    .run()
    .catch(() => {}); // fire-and-forget; audit log separately if needed

  return { ...row, scopes: JSON.parse(row.scopes as unknown as string) };
}
```

The hash lookup provides timing-safety at the DB level: the query returns a row or null
in constant time from the Workers perspective (network RTT dominates).  No additional
constant-time compare is required because you are comparing hash-of-key, not key itself.

---

## 6. Worker Entry Point

```typescript
// src/index.ts
import { verifyApiKey } from './verify';

export interface Env {
  DB: D1Database;
  HKDF_SECRET: string;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const authHeader = req.headers.get('Authorization') ?? '';
    const raw = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';

    if (!raw) {
      return new Response('Unauthorized', {
        status: 401,
        headers: { 'WWW-Authenticate': 'Bearer realm="api"' },
      });
    }

    const record = await verifyApiKey(env.DB, env.HKDF_SECRET, raw);
    if (!record) {
      return new Response('Unauthorized', { status: 401 });
    }

    // Attach verified identity to the downstream request
    const downstream = new Request(req, {
      headers: new Headers({
        ...Object.fromEntries(req.headers),
        'X-Authenticated-Owner': record.owner_id,
        'X-Scopes': record.scopes.join(' '),
      }),
    });

    return fetch(downstream);
  },
};
```

---

## Anti-patterns

- **Storing the plaintext key in D1** — a database breach exposes all keys immediately.
- **Using SHA-256 directly without a secret IKM** — a simple hash of the key is
  vulnerable to offline dictionary attack if the attacker knows your key format; HKDF
  with a secret IKM turns it into a MAC.
- **Logging the raw key in Wrangler tail output** — add a `NEVER_LOG_KEYS=true` env var
  as a lint-time reminder and filter tail workers.
- **Using a single global HKDF_SECRET across all environments** — rotate per-environment
  (`staging`, `production`) and store via `wrangler secret put`.
- **Not rotating the HKDF secret after a suspected compromise** — old keys remain valid
  if the attacker captured the HKDF output and you only rotate the IKM.  On compromise,
  revoke all keys in D1 and reissue.
- **Comparing raw hashes with `===`** — in Workers the HKDF output is computed, not
  stored externally, so `===` is fine; but if you ever accept an externally-provided
  hash for comparison, use a timing-safe function.

---

## Gotchas

- `crypto.subtle.deriveBits` is async in Workers; do not call it in a `for` loop without
  `await` — you will create a race condition on the `hkdfKey` object.
- HKDF `info` is meant to be context-specific binding, not a secret.  The security comes
  from the `salt` + `IKM` pair, not from making `info` secret.
- D1's `UNIQUE` constraint on `key_hash` protects against collision (negligible for
  256-bit output) but also means a duplicate key insert throws; wrap in try/catch.
- The `last_used_at` update inside `verifyApiKey` is fire-and-forget; if the Worker
  crashes after returning the response, the update may be lost — acceptable for an
  informational field.
- Key format detection: if your API accepts keys from multiple generations (v1 SHA-256,
  v2 HKDF), check the prefix (`sk_live_v1_` vs `sk_live_v2_`) to select the verification
  path — never try both and return success on either match.

---

## Verification

```bash
# Issue a key
curl -X POST https://api.<account>.workers.dev/keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-jwt>" \
  -d '{"name":"ci-runner","scopes":["read:data"]}'
# Returns: {"id":"...","plaintext":"sk_live_..."}

# Verify the key works
curl -I https://api.<account>.workers.dev/data \
  -H "Authorization: Bearer sk_live_..."
# Expect: 200

# Verify tampered key is rejected
curl -I https://api.<account>.workers.dev/data \
  -H "Authorization: Bearer sk_live_AAAAAAAA"
# Expect: 401

# Confirm hash stored (not plaintext)
wrangler d1 execute api-keys-db \
  --command "SELECT id, key_hash, owner_id FROM api_keys LIMIT 3"
# key_hash should be 64 hex chars, never starting with 'sk_live_'
```

---

## Related

- `api-key-rotation-workers-kv-secrets.md`
- `api-key-rotation-zero-downtime.md`
- `workers-hkdf-key-derivation-hierarchical-secrets.md`
- `timing-safe-compare.md`
- `secrets-encryption-at-rest.md`

---

## Sources

- GitHub token storage design (keyed hash): https://github.blog/engineering/engineering-principles/behind-githubs-new-authentication-token-formats/
- RFC 5869 — HKDF: https://www.rfc-editor.org/rfc/rfc5869
- Web Crypto API — `deriveBits`: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveBits
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
