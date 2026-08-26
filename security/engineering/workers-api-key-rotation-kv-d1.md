# API Key Rotation Without Downtime: KV + D1 Strategy

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to rotate API keys for external clients without invalidating existing sessions or causing 4xx errors during the cutover window. Keys must transition through `active → rotating → revoked` states with overlap TTLs so both the old and new key are accepted simultaneously.

---

## Context
Cloudflare Workers have no persistent in-process state, so all key state lives in KV (for fast per-request lookup) and D1 (as the authoritative record). A Cron Trigger drives automatic rotation on schedule. KV entries carry a TTL matching the overlap window so expired keys self-delete. The D1 `api_keys` table is the audit trail and source of truth for revocation checks.

---

## D1 Schema
```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  key_hash    TEXT NOT NULL UNIQUE,
  client_id   TEXT NOT NULL,
  status      TEXT NOT NULL CHECK(status IN ('active','rotating','revoked')) DEFAULT 'active',
  family_id   TEXT NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  expires_at  INTEGER,
  revoked_at  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_api_keys_client ON api_keys(client_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_family ON api_keys(family_id);
```

---

## Worker: Key Validation
```typescript
// src/validate.ts
import type { Env } from './env';

const OVERLAP_TTL_SECONDS = 3600; // 1 hour overlap

async function hashKey(raw: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(raw)
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

export async function validateApiKey(
  raw: string,
  env: Env
): Promise<{ valid: boolean; clientId?: string; status?: string }> {
  // 1. Fast path: check KV cache first
  const kvEntry = await env.API_KEYS_KV.get(`key:${raw}`, 'json') as
    | { clientId: string; status: string }
    | null;

  if (kvEntry) {
    if (kvEntry.status === 'revoked') return { valid: false };
    return { valid: true, clientId: kvEntry.clientId, status: kvEntry.status };
  }

  // 2. Slow path: check D1
  const hash = await hashKey(raw);
  const row = await env.DB.prepare(
    `SELECT client_id, status, expires_at
     FROM api_keys
     WHERE key_hash = ? AND status != 'revoked'`
  ).bind(hash).first<{ client_id: string; status: string; expires_at: number | null }>();

  if (!row) return { valid: false };

  const now = Math.floor(Date.now() / 1000);
  if (row.expires_at && row.expires_at < now) return { valid: false };

  // 3. Backfill KV cache with short TTL
  await env.API_KEYS_KV.put(
    `key:${raw}`,
    JSON.stringify({ clientId: row.client_id, status: row.status }),
    { expirationTtl: OVERLAP_TTL_SECONDS }
  );

  return { valid: true, clientId: row.client_id, status: row.status };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authHeader = request.headers.get('Authorization') ?? '';
    const raw = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';

    if (!raw) return new Response('Unauthorized', { status: 401 });

    const result = await validateApiKey(raw, env);
    if (!result.valid) return new Response('Forbidden', { status: 403 });

    return new Response(
      JSON.stringify({ clientId: result.clientId, status: result.status }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  },
};
```

---

## Worker: Rotation Cron
```typescript
// src/rotate.ts
import type { Env } from './env';

const OVERLAP_TTL_SECONDS = 3600;

async function hashKey(raw: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(raw)
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

async function rotateKeysForClient(clientId: string, env: Env): Promise<string> {
  // Generate new key
  const newRaw = crypto.randomUUID() + '-' + crypto.randomUUID();
  const newHash = await hashKey(newRaw);
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + 7 * 86400; // new key valid 7 days

  // Mark existing active keys as 'rotating'
  await env.DB.prepare(
    `UPDATE api_keys
     SET status = 'rotating', expires_at = ?
     WHERE client_id = ? AND status = 'active'`
  ).bind(now + OVERLAP_TTL_SECONDS, clientId).run();

  // Insert new active key, same family
  const family = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO api_keys (key_hash, client_id, status, family_id, created_at, expires_at)
     VALUES (?, ?, 'active', ?, ?, ?)`
  ).bind(newHash, clientId, family, now, expiresAt).run();

  // Cache new key in KV
  await env.API_KEYS_KV.put(
    `key:${newRaw}`,
    JSON.stringify({ clientId, status: 'active' }),
    { expirationTtl: 7 * 86400 }
  );

  return newRaw; // return to caller / notify client via webhook
}

export async function handleRotationCron(env: Env): Promise<void> {
  // Find clients whose active key is older than 30 days
  const rows = await env.DB.prepare(
    `SELECT DISTINCT client_id FROM api_keys
     WHERE status = 'active' AND created_at < ?`
  ).bind(Math.floor(Date.now() / 1000) - 30 * 86400).all<{ client_id: string }>();

  for (const row of rows.results) {
    const newKey = await rotateKeysForClient(row.client_id, env);
    console.log(`Rotated key for client ${row.client_id}, new key prefix: ${newKey.slice(0, 8)}...`);
  }

  // Hard-revoke 'rotating' keys past their expiry
  await env.DB.prepare(
    `UPDATE api_keys SET status = 'revoked', revoked_at = ?
     WHERE status = 'rotating' AND expires_at < ?`
  ).bind(Math.floor(Date.now() / 1000), Math.floor(Date.now() / 1000)).run();
}
```

---

## wrangler.toml
```toml
[triggers]
crons = ["0 3 * * *"]  # daily at 03:00 UTC

[[kv_namespaces]]
binding = "API_KEYS_KV"
id     = "<KV_NAMESPACE_ID>"

[[d1_databases]]
binding  = "DB"
database_name = "my-db"
database_id   = "<D1_DATABASE_ID>"
```

---

## Anti-patterns
- **Storing raw keys in D1** — always store a SHA-256 hash; raw keys belong only in KV during the overlap window.
- **Skipping the KV fast path** — hitting D1 on every request adds 5-20 ms; KV lookup is sub-millisecond from the edge.
- **Revoking immediately on rotation** — without an overlap window, in-flight requests using the old key return 403.
- **No family_id** — without grouping keys into families you cannot revoke all keys for a client on a breach.

---

## Gotchas
- KV `expirationTtl` is in **seconds**, not milliseconds.
- `crypto.randomUUID()` is available globally in Workers runtime; no import needed.
- D1 `unixepoch()` returns seconds; `Date.now()` returns milliseconds — always divide by 1000 before storing.
- The Cron handler must be exported under `scheduled` in the default export, not `fetch`.

---

## Verification
```bash
# Apply schema
wrangler d1 execute my-db --file schema.sql

# Insert a test key
KEY=$(node -e "console.log(require('crypto').randomUUID()+'-'+require('crypto').randomUUID())")
HASH=$(echo -n "$KEY" | sha256sum | awk '{print $1}')
wrangler d1 execute my-db \
  --command "INSERT INTO api_keys (key_hash,client_id,family_id) VALUES ('$HASH','client-1','fam-1')"

# Validate via Worker
curl -H "Authorization: Bearer $KEY" https://<worker>.workers.dev/

# Force rotation cron
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"
```

---

## Related
- `workers-jwt-refresh-token-rotation.md`
- `workers-encrypted-kv-store-aes-gcm.md`

---

## Sources
- Cloudflare Workers KV Docs — https://developers.cloudflare.com/kv/
- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- Web Crypto API (Workers) — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
