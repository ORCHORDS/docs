# API Key Management System in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers platform needs to issue, validate, scope, track, and revoke API keys for external clients. Keys must be recognizable by prefix (`sk_live_`), never stored in plaintext, queryable by their prefix, scoped to specific operations, and auditable via usage tracking in Analytics Engine. A rotation workflow allows seamless rollover without downtime.

---

## Context

Self-hosted API key management is preferable to third-party services when keys must be validated at the edge with sub-millisecond latency. D1 stores the key hash and metadata (prefix, scopes, created date, expiry, revocation flag). Analytics Engine logs each key usage event without blocking the response path. The key is shown to the client only once at creation time; thereafter, only the `SHA-256` hash is retained.

Base58 encoding (Bitcoin alphabet) avoids visually ambiguous characters (`0`, `O`, `I`, `l`) that cause transcription errors when keys are copied manually.

---

## Solution

```typescript
// api-key-management.ts
// Secure API key lifecycle management for Cloudflare Workers + D1.

const BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

// ── Base58 encoding ───────────────────────────────────────────────────────────

function base58Encode(bytes: Uint8Array): string {
  let num = BigInt(0);
  for (const byte of bytes) {
    num = num * BigInt(256) + BigInt(byte);
  }

  let encoded = '';
  while (num > BigInt(0)) {
    encoded = BASE58_ALPHABET[Number(num % BigInt(58))] + encoded;
    num = num / BigInt(58);
  }

  // Preserve leading zero bytes.
  for (const byte of bytes) {
    if (byte !== 0) break;
    encoded = '1' + encoded;
  }

  return encoded;
}

// ── Key generation ────────────────────────────────────────────────────────────

export type KeyEnvironment = 'live' | 'test';

export interface ApiKeyGenerationResult {
  /** Full key shown to the user exactly once. */
  rawKey: string;
  /** Short prefix used to identify the key in listings (e.g. sk_live_Ab3x). */
  prefix: string;
  /** SHA-256 hex hash stored in D1. */
  keyHash: string;
}

export async function generateApiKey(
  environment: KeyEnvironment
): Promise<ApiKeyGenerationResult> {
  // 32 random bytes → 43–44 base58 characters.
  const randomBytes = crypto.getRandomValues(new Uint8Array(32));
  const encoded = base58Encode(randomBytes);

  const envPrefix = environment === 'live' ? 'sk_live_' : 'sk_test_';
  const rawKey = `${envPrefix}${encoded}`;

  // Public prefix = first 12 chars of the full key (safe to store/display).
  const prefix = rawKey.slice(0, 12);

  // Hash for storage.
  const hashBuf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(rawKey)
  );
  const keyHash = Array.from(new Uint8Array(hashBuf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  return { rawKey, prefix, keyHash };
}

// ── D1 schema ─────────────────────────────────────────────────────────────────
// CREATE TABLE IF NOT EXISTS api_keys (
//   id          TEXT PRIMARY KEY,         -- UUID
//   key_hash    TEXT NOT NULL UNIQUE,     -- SHA-256 hex
//   prefix      TEXT NOT NULL,            -- sk_live_Ab3x (first 12 chars)
//   owner_id    TEXT NOT NULL,
//   scopes      TEXT NOT NULL,            -- JSON array
//   environment TEXT NOT NULL,            -- 'live' | 'test'
//   created_at  TEXT NOT NULL,
//   expires_at  TEXT,                     -- nullable ISO timestamp
//   revoked_at  TEXT                      -- nullable, set on revocation
// );

export interface ApiKeyRecord {
  id: string;
  keyHash: string;
  prefix: string;
  ownerId: string;
  scopes: string[];
  environment: KeyEnvironment;
  createdAt: string;
  expiresAt: string | null;
  revokedAt: string | null;
}

// ── Key creation endpoint ─────────────────────────────────────────────────────

export async function createApiKey(
  ownerId: string,
  scopes: string[],
  environment: KeyEnvironment,
  expiresInDays: number | null,
  db: D1Database
): Promise<{ record: ApiKeyRecord; rawKey: string }> {
  const { rawKey, prefix, keyHash } = await generateApiKey(environment);
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  const expiresAt = expiresInDays
    ? new Date(Date.now() + expiresInDays * 86_400_000).toISOString()
    : null;

  await db
    .prepare(
      `INSERT INTO api_keys
         (id, key_hash, prefix, owner_id, scopes, environment, created_at, expires_at, revoked_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)`
    )
    .bind(id, keyHash, prefix, ownerId, JSON.stringify(scopes), environment, now, expiresAt)
    .run();

  const record: ApiKeyRecord = {
    id,
    keyHash,
    prefix,
    ownerId,
    scopes,
    environment,
    createdAt: now,
    expiresAt,
    revokedAt: null,
  };

  return { record, rawKey };
}

// ── Key validation ────────────────────────────────────────────────────────────

export interface ValidationResult {
  valid: boolean;
  reason?: string;
  record?: ApiKeyRecord;
}

export async function validateApiKey(
  rawKey: string,
  requiredScope: string,
  db: D1Database
): Promise<ValidationResult> {
  if (!rawKey.startsWith('sk_live_') && !rawKey.startsWith('sk_test_')) {
    return { valid: false, reason: 'invalid_format' };
  }

  const hashBuf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(rawKey)
  );
  const keyHash = Array.from(new Uint8Array(hashBuf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  const row = await db
    .prepare('SELECT * FROM api_keys WHERE key_hash = ?')
    .bind(keyHash)
    .first<Record<string, string>>();

  if (!row) return { valid: false, reason: 'not_found' };

  if (row.revoked_at) return { valid: false, reason: 'revoked' };

  if (row.expires_at && new Date(row.expires_at) < new Date()) {
    return { valid: false, reason: 'expired' };
  }

  const scopes: string[] = JSON.parse(row.scopes);
  if (!scopes.includes(requiredScope) && !scopes.includes('*')) {
    return { valid: false, reason: 'insufficient_scope' };
  }

  return {
    valid: true,
    record: {
      id: row.id,
      keyHash: row.key_hash,
      prefix: row.prefix,
      ownerId: row.owner_id,
      scopes,
      environment: row.environment as KeyEnvironment,
      createdAt: row.created_at,
      expiresAt: row.expires_at ?? null,
      revokedAt: null,
    },
  };
}

// ── Usage tracking via Analytics Engine ──────────────────────────────────────

export function trackKeyUsage(
  record: ApiKeyRecord,
  request: Request,
  dataset: AnalyticsEngineDataset
): void {
  dataset.writeDataPoint({
    blobs: [
      record.prefix,
      record.ownerId,
      new URL(request.url).pathname,
      request.method,
    ],
    doubles: [1],
    indexes: [record.prefix],
  });
}

// ── Revocation endpoint ───────────────────────────────────────────────────────

export async function revokeApiKey(
  keyId: string,
  ownerId: string,
  db: D1Database
): Promise<{ revoked: boolean }> {
  const result = await db
    .prepare(
      `UPDATE api_keys
       SET revoked_at = ?
       WHERE id = ? AND owner_id = ? AND revoked_at IS NULL`
    )
    .bind(new Date().toISOString(), keyId, ownerId)
    .run();

  return { revoked: (result.meta.changes ?? 0) > 0 };
}

// ── Rotation workflow ─────────────────────────────────────────────────────────
// 1. Create a new key (client receives the new raw key).
// 2. Client updates their systems to use the new key.
// 3. After a grace period, revoke the old key.

export async function rotateApiKey(
  oldKeyId: string,
  ownerId: string,
  scopes: string[],
  environment: KeyEnvironment,
  db: D1Database
): Promise<{ newRecord: ApiKeyRecord; newRawKey: string }> {
  // Step 1: create replacement (old key remains valid during grace period).
  const { record: newRecord, rawKey: newRawKey } = await createApiKey(
    ownerId,
    scopes,
    environment,
    null, // inherit expiry policy from caller
    db
  );

  // Step 2: mark the old key as scheduled for revocation via a soft flag.
  // Full revocation is a separate call after the client confirms migration.
  await db
    .prepare(
      `UPDATE api_keys SET expires_at = datetime('now', '+7 days')
       WHERE id = ? AND owner_id = ?`
    )
    .bind(oldKeyId, ownerId)
    .run();

  return { newRecord, newRawKey };
}

// ── Worker entry point ────────────────────────────────────────────────────────

interface Env {
  DB: D1Database;
  USAGE: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const rawKey = request.headers.get('x-api-key') ?? '';

    if (url.pathname === '/keys' && request.method === 'POST') {
      const body = await request.json<{ ownerId: string; scopes: string[]; expiresInDays?: number }>();
      const { record, rawKey: key } = await createApiKey(
        body.ownerId,
        body.scopes,
        'live',
        body.expiresInDays ?? null,
        env.DB
      );
      // Raw key is shown once — never stored.
      return new Response(JSON.stringify({ ...record, rawKey: key }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname.startsWith('/keys/') && request.method === 'DELETE') {
      const keyId = url.pathname.split('/')[2];
      const ownerId = request.headers.get('x-owner-id') ?? '';
      const result = await revokeApiKey(keyId, ownerId, env.DB);
      return new Response(JSON.stringify(result), { headers: { 'content-type': 'application/json' } });
    }

    // All other routes: validate key and track usage.
    const validation = await validateApiKey(rawKey, url.pathname.split('/')[1], env.DB);
    if (!validation.valid) {
      return new Response(JSON.stringify({ error: validation.reason }), { status: 401 });
    }

    trackKeyUsage(validation.record!, request, env.USAGE);

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'content-type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

- Base58 encoding uses `BigInt` arithmetic to convert raw bytes to a base-58 string, avoiding ambiguous characters. For 32 random bytes, output length is consistently 43–44 characters.
- `prefix` is the first 12 characters of the full key, which is safe to store and display in listings without exposing the secret portion.
- `SHA-256` hashing ensures that even if the D1 database is leaked, raw keys cannot be recovered.
- `AnalyticsEngineDataset.writeDataPoint` is non-blocking — it does not add latency to the request path.
- The rotation workflow gives the client a 7-day window (via `expires_at`) to migrate before the old key becomes invalid, avoiding hard cutoffs.
- `scopes.includes('*')` acts as a wildcard for admin keys that bypass individual scope checks.

---

## Anti-patterns

- Do not store raw API keys anywhere — not in D1, not in KV, not in logs.
- Do not use `Math.random()` for key generation — it is not cryptographically secure.
- Do not skip the expiry check in `validateApiKey` — an unexpired but revoked key is also invalid; check both.
- Do not return the raw key in any subsequent API response; it must be shown once and discarded server-side.
- Do not use sequential integers as key IDs — they allow enumeration attacks.

---

## Gotchas

- `D1Database.first()` returns `null` when no row matches — always null-check before accessing row properties.
- `AnalyticsEngineDataset` is bound in `wrangler.toml` under `[[analytics_engine_datasets]]`; it is not available in local `wrangler dev` without `--remote`.
- `result.meta.changes` can be `undefined` if the D1 binding is in a preview environment; guard with `?? 0`.
- Base58 encoding with `BigInt` is slower than base64 for large byte arrays — acceptable for key generation (infrequent) but not for hot paths.
- SQLite (D1) does not enforce `JSON` column types — always `JSON.parse` / `JSON.stringify` manually.

---

## Verification

```bash
# 1. Create a key.
curl -X POST https://your-worker.example.com/keys \
  -H 'content-type: application/json' \
  -d '{"ownerId":"user_123","scopes":["read","write"],"expiresInDays":90}'
# Expected: {"id":"...","prefix":"sk_live_Ab3x","rawKey":"sk_live_...", ...}

# 2. Use the key.
curl https://your-worker.example.com/read \
  -H 'x-api-key: sk_live_<your-key>'
# Expected: {"ok":true}

# 3. Revoke the key.
curl -X DELETE https://your-worker.example.com/keys/<key-id> \
  -H 'x-owner-id: user_123'
# Expected: {"revoked":true}

# 4. Verify revoked key is rejected.
curl https://your-worker.example.com/read \
  -H 'x-api-key: sk_live_<your-key>'
# Expected: 401 {"error":"revoked"}
```

---

## Related

- `documentation/categories/security/workers-secret-scanning-prevention.md`
- `documentation/categories/security/workers-dependency-vulnerability-scanner.md`
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/

---

## Sources

- Cloudflare D1: https://developers.cloudflare.com/d1/
- OWASP API Security Top 10 — API2: Broken Authentication: https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/
- Bitcoin Base58Check encoding: https://en.bitcoin.it/wiki/Base58Check_encoding
