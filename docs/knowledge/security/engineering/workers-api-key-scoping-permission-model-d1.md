# Workers API Key Scoping and Permission Model with D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A single flat API key either can do everything or nothing. You need keys that carry
explicit, auditable scopes — `ledger:read`, `payments:write`, `admin:*` — so that a
leaked integration key cannot reach endpoints outside its intended surface.

## Context

Model API key permissions as a bitmask or scope-set stored in D1. Each incoming
request presents a key; the Worker fetches the key's scope set from a KV cache backed
by D1, then checks whether the required scope is present before routing. Keys can be
revoked, expiry-scoped, and narrowed without reissuing credentials.

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id           TEXT    PRIMARY KEY,         -- ULID or UUID
  tenant_id    TEXT    NOT NULL,
  key_hash     TEXT    NOT NULL UNIQUE,     -- SHA-256 of the raw key
  name         TEXT    NOT NULL,
  scopes       TEXT    NOT NULL,            -- JSON array: ["ledger:read","payments:write"]
  expires_at   INTEGER,                     -- Unix ms; NULL = never
  revoked_at   INTEGER,
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER
);

CREATE INDEX idx_api_keys_tenant ON api_keys (tenant_id);
CREATE INDEX idx_api_keys_hash   ON api_keys (key_hash);
```

---

## Issuing a scoped key

```typescript
import { ulid } from 'ulidx';  // npm package, zero-dep ULID

const ALLOWED_SCOPES = new Set([
  'ledger:read', 'ledger:write',
  'payments:read', 'payments:write',
  'users:read', 'users:write',
  'admin:*',
]);

export async function issueApiKey(
  db: D1Database,
  tenantId: string,
  name: string,
  scopes: string[],
  ttlDays?: number,
): Promise<{ id: string; rawKey: string }> {
  // Validate requested scopes
  for (const s of scopes) {
    if (!ALLOWED_SCOPES.has(s)) throw new Error(`Unknown scope: ${s}`);
  }

  const id = ulid();
  const rawKey = `sk_${tenantId}_${ulid()}`;  // human-readable prefix
  const keyHash = await sha256Hex(rawKey);
  const now = Date.now();
  const expiresAt = ttlDays ? now + ttlDays * 86_400_000 : null;

  await db
    .prepare(
      `INSERT INTO api_keys (id, tenant_id, key_hash, name, scopes, expires_at, revoked_at, created_at)
       VALUES (?, ?, ?, ?, ?, ?, NULL, ?)`,
    )
    .bind(id, tenantId, keyHash, name, JSON.stringify(scopes), expiresAt, now)
    .run();

  return { id, rawKey };  // rawKey shown once; never stored in plaintext
}

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Resolving a key and checking a scope

```typescript
interface KeyRecord {
  id: string;
  tenantId: string;
  scopes: string[];
  expiresAt: number | null;
  revokedAt: number | null;
}

export async function resolveKey(
  rawKey: string,
  db: D1Database,
  kv: KVNamespace,
): Promise<KeyRecord | null> {
  const hash = await sha256Hex(rawKey);
  const cacheKey = `apikey:${hash}`;

  // Cache hit
  const cached = await kv.get(cacheKey, 'json') as KeyRecord | null;
  if (cached) return cached;

  // Cache miss — query D1
  const row = await db
    .prepare(
      `SELECT id, tenant_id, scopes, expires_at, revoked_at
       FROM api_keys WHERE key_hash = ?`,
    )
    .bind(hash)
    .first<{ id: string; tenant_id: string; scopes: string; expires_at: number | null; revoked_at: number | null }>();

  if (!row) return null;

  const record: KeyRecord = {
    id: row.id,
    tenantId: row.tenant_id,
    scopes: JSON.parse(row.scopes),
    expiresAt: row.expires_at,
    revokedAt: row.revoked_at,
  };

  // Short TTL so revocations propagate quickly
  await kv.put(cacheKey, JSON.stringify(record), { expirationTtl: 60 });
  return record;
}

export function hasScope(key: KeyRecord, required: string): boolean {
  const now = Date.now();
  if (key.revokedAt !== null) return false;
  if (key.expiresAt !== null && now > key.expiresAt) return false;

  // Wildcard: admin:* grants everything under admin namespace
  return key.scopes.some(s => {
    if (s === required) return true;
    if (s.endsWith(':*')) {
      const ns = s.slice(0, -2);
      return required === ns || required.startsWith(`${ns}:`);
    }
    return false;
  });
}
```

---

## Middleware integration in a Worker

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const rawKey = request.headers.get('X-Api-Key') ?? '';
    if (!rawKey) return new Response('Unauthorized', { status: 401 });

    const key = await resolveKey(rawKey, env.DB, env.KV);
    if (!key) return new Response('Unauthorized', { status: 401 });

    const url = new URL(request.url);
    const requiredScope = routeToScope(url.pathname, request.method);

    if (!hasScope(key, requiredScope)) {
      return new Response('Forbidden', { status: 403 });
    }

    // Attach resolved key to request context for downstream handlers
    return handleRequest(request, env, key);
  },
};

function routeToScope(pathname: string, method: string): string {
  const verb = method === 'GET' ? 'read' : 'write';
  if (pathname.startsWith('/ledger'))   return `ledger:${verb}`;
  if (pathname.startsWith('/payments')) return `payments:${verb}`;
  if (pathname.startsWith('/users'))    return `users:${verb}`;
  if (pathname.startsWith('/admin'))    return 'admin:*';
  return 'unknown';
}
```

---

## Revoking a key and purging the cache

```typescript
export async function revokeKey(
  id: string,
  db: D1Database,
  kv: KVNamespace,
): Promise<void> {
  const row = await db
    .prepare('SELECT key_hash FROM api_keys WHERE id = ?')
    .bind(id)
    .first<{ key_hash: string }>();
  if (!row) throw new Error('Key not found');

  await db
    .prepare('UPDATE api_keys SET revoked_at = ? WHERE id = ?')
    .bind(Date.now(), id)
    .run();

  // Eagerly evict KV cache entry so revocation takes effect within seconds
  await kv.delete(`apikey:${row.key_hash}`);
}
```

---

## Anti-patterns

- **Embedding scopes inside the API key itself (unsigned)**: anyone who holds the key can self-escalate by crafting a different scope string.
- **Using exact string matching without wildcard logic**: forces issuance of many keys when a single `admin:*` key would suffice and is auditable.
- **Long KV TTL (> 5 min) for key cache**: a revoked key remains valid until cache expiry; 60 seconds is a practical maximum.
- **Storing the raw key in the database**: only the hash should persist. The raw key is handed to the caller once and discarded.

## Gotchas

- D1 `key_hash` uniqueness constraint means two tenants cannot accidentally share a hash — good — but the index must be on `key_hash`, not `(tenant_id, key_hash)`, for the lookup to be O(log n).
- Scope comparison is case-sensitive. Normalise to lowercase at issuance and at resolution time.
- If you use KV as the authoritative store (not D1), you lose the ability to enumerate all keys for a tenant without a secondary index namespace.

## Verification

```bash
# List all active (non-revoked, non-expired) keys for a tenant
wrangler d1 execute <DB_NAME> --command \
  "SELECT id, name, scopes, expires_at FROM api_keys
   WHERE tenant_id = 'acme' AND revoked_at IS NULL
   AND (expires_at IS NULL OR expires_at > unixepoch() * 1000)"
```

## Related

- `api-key-authentication.md`
- `api-key-hash-storage-workers-d1-bcrypt-alternative.md`
- `api-key-rotation-zero-downtime.md`
- `workers-kv-ttl-token-revocation-expiry.md`
- `multi-tenancy-isolation-workers-kv-d1.md`

## Sources

- OWASP API Security Top 10 2023 — API1 Broken Object Level Authorization
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
