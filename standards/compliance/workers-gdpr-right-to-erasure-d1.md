# GDPR Article 17 Right-to-Erasure in Cloudflare Workers with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SaaS product must honour GDPR "right to be forgotten" requests within 30 days. Users submit a deletion request, the Worker must cascade-delete their rows from multiple D1 tables, remove R2 uploads, clear KV cache entries, and issue a durable `erasure_reference` UUID for the audit trail.

---

## Context

GDPR Article 17 grants data subjects the right to have their personal data erased without undue delay. Cloudflare Workers with D1 can handle this transactionally because D1 supports multi-statement SQL. R2 object listing and `DeleteObjects` handle stored files. A single audit record persisted in D1 satisfies the 30-day tracking window required by DPAs. All operations should be idempotent so duplicate erasure requests do not produce errors.

---

## Section 1 — D1 Schema

```sql
-- Core user table
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL,
  created_at  INTEGER NOT NULL
);

-- Child tables that must cascade
CREATE TABLE IF NOT EXISTS user_profiles (
  user_id     TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT,
  avatar_key  TEXT   -- R2 object key
);

CREATE TABLE IF NOT EXISTS user_sessions (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  INTEGER NOT NULL
);

-- Erasure audit log (immutable, never deleted)
CREATE TABLE IF NOT EXISTS erasure_audit (
  erasure_reference TEXT PRIMARY KEY,  -- UUID v4
  user_id           TEXT NOT NULL,
  requested_at      INTEGER NOT NULL,
  completed_at      INTEGER,
  status            TEXT NOT NULL DEFAULT 'pending',  -- pending | complete | failed
  r2_objects_deleted INTEGER DEFAULT 0,
  kv_keys_deleted    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_erasure_user ON erasure_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_erasure_status ON erasure_audit(status, requested_at);
```

---

## Section 2 — Worker Implementation

```typescript
interface Env {
  DB: D1Database;
  USER_UPLOADS: R2Bucket;
  SESSION_CACHE: KVNamespace;
  ERASURE_SECRET: string; // HMAC secret to verify internal callbacks
}

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'DELETE' && url.pathname === '/v1/me/erasure') {
      return handleErasureRequest(request, env);
    }

    if (request.method === 'GET' && url.pathname.startsWith('/v1/erasure/status/')) {
      const ref = url.pathname.split('/').pop() ?? '';
      return handleErasureStatus(ref, env);
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function handleErasureRequest(request: Request, env: Env): Promise<Response> {
  // 1. Authenticate — expect Bearer JWT (implementation omitted for brevity)
  const userId = await resolveUserId(request);
  if (!userId) return new Response('Unauthorized', { status: 401 });

  // 2. Confirm user exists
  const userRow = await env.DB
    .prepare('SELECT id FROM users WHERE id = ?')
    .bind(userId)
    .first<{ id: string }>();
  if (!userRow) return new Response('Not Found', { status: 404 });

  // 3. Create erasure reference
  const erasureReference = crypto.randomUUID();
  const now = Date.now();
  const deadline = now + THIRTY_DAYS_MS;

  await env.DB
    .prepare(
      `INSERT INTO erasure_audit (erasure_reference, user_id, requested_at, status)
       VALUES (?, ?, ?, 'pending')
       ON CONFLICT (erasure_reference) DO NOTHING`
    )
    .bind(erasureReference, userId, now)
    .run();

  // 4. Collect R2 keys before deletion
  const profile = await env.DB
    .prepare('SELECT avatar_key FROM user_profiles WHERE user_id = ?')
    .bind(userId)
    .first<{ avatar_key: string | null }>();

  const r2Keys: string[] = [];
  if (profile?.avatar_key) r2Keys.push(profile.avatar_key);

  // List any additional user uploads
  let cursor: string | undefined;
  do {
    const listed = await env.USER_UPLOADS.list({
      prefix: `uploads/${userId}/`,
      cursor,
      limit: 1000,
    });
    r2Keys.push(...listed.objects.map((o) => o.key));
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);

  // 5. Delete R2 objects
  await Promise.all(r2Keys.map((key) => env.USER_UPLOADS.delete(key)));

  // 6. Cascade-delete from D1 (FK ON DELETE CASCADE handles children)
  await env.DB
    .prepare('DELETE FROM users WHERE id = ?')
    .bind(userId)
    .run();

  // 7. Purge KV session cache
  const kvKey = `session:user:${userId}`;
  await env.SESSION_CACHE.delete(kvKey);
  const kvKeysDeleted = 1;

  // 8. Mark audit record complete
  await env.DB
    .prepare(
      `UPDATE erasure_audit
       SET completed_at = ?, status = 'complete',
           r2_objects_deleted = ?, kv_keys_deleted = ?
       WHERE erasure_reference = ?`
    )
    .bind(Date.now(), r2Keys.length, kvKeysDeleted, erasureReference)
    .run();

  return Response.json(
    {
      erasure_reference: erasureReference,
      status: 'complete',
      deadline_iso: new Date(deadline).toISOString(),
      r2_objects_deleted: r2Keys.length,
    },
    { status: 200 }
  );
}

async function handleErasureStatus(ref: string, env: Env): Promise<Response> {
  const row = await env.DB
    .prepare(
      `SELECT erasure_reference, status, requested_at, completed_at,
              r2_objects_deleted, kv_keys_deleted
       FROM erasure_audit WHERE erasure_reference = ?`
    )
    .bind(ref)
    .first();

  if (!row) return new Response('Not Found', { status: 404 });
  return Response.json(row);
}

// Stub — replace with your auth library
async function resolveUserId(_req: Request): Promise<string | null> {
  return 'user-123';
}
```

---

## Section 3 — Testing / Verification

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { env, createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';
import worker from './index';

describe('GDPR erasure endpoint', () => {
  beforeEach(async () => {
    // Seed a user row
    await env.DB.prepare(
      `INSERT OR REPLACE INTO users (id, email, created_at) VALUES ('user-123', 'test@example.com', 0)`
    ).run();
    await env.DB.prepare(
      `INSERT OR REPLACE INTO user_profiles (user_id, display_name, avatar_key)
       VALUES ('user-123', 'Test', 'uploads/user-123/avatar.jpg')`
    ).run();
    await env.USER_UPLOADS.put('uploads/user-123/avatar.jpg', 'imgdata');
  });

  it('returns 200 with erasure_reference and deletes user row', async () => {
    const ctx = createExecutionContext();
    const req = new Request('https://api.example.com/v1/me/erasure', { method: 'DELETE' });
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(200);
    const body = await res.json<{ erasure_reference: string; status: string }>();
    expect(body.status).toBe('complete');
    expect(body.erasure_reference).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );

    const userGone = await env.DB.prepare('SELECT id FROM users WHERE id = ?').bind('user-123').first();
    expect(userGone).toBeNull();

    const r2Gone = await env.USER_UPLOADS.get('uploads/user-123/avatar.jpg');
    expect(r2Gone).toBeNull();
  });
});
```

---

## Anti-patterns

- **Soft-delete only** — Marking `deleted = true` does NOT satisfy Article 17; data must be physically removed from storage.
- **Skipping child tables** — Forgetting to cascade-delete related tables leaves orphaned PII which is still a GDPR violation.
- **Logging PAN or email in the erasure response** — The confirmation JSON must not echo back personal data.
- **Single-row DELETE without a transaction guard** — If the Worker crashes mid-erasure, partial deletion leaves the audit in an inconsistent state; use status tracking to allow resume.

---

## Gotchas

- D1 `ON DELETE CASCADE` only fires if the parent row is deleted AND the FK constraint was declared at table creation time; `PRAGMA foreign_keys = ON` is enabled by default in D1.
- R2 `list()` is paginated with a default limit of 1000 — always check `truncated` and loop.
- KV `delete()` is eventually consistent; a brief window exists where stale session data may still be served from edge caches.
- Store the `erasure_reference` UUID in D1 *before* deleting data — if R2 deletion fails, you can resume using the audit row.
- The 30-day GDPR window is a maximum, not a target; aim to complete within minutes.

---

## Verification

```bash
# Trigger erasure (replace TOKEN with a valid Bearer)
curl -X DELETE https://api.example.com/v1/me/erasure \
  -H "Authorization: Bearer $TOKEN"

# Poll status
curl https://api.example.com/v1/erasure/status/<erasure_reference>

# Confirm row deleted in D1 (Wrangler)
npx wrangler d1 execute MY_DB --command "SELECT * FROM users WHERE id='user-123'"

# Confirm R2 object gone
npx wrangler r2 object get USER_UPLOADS uploads/user-123/avatar.jpg

# View audit log
npx wrangler d1 execute MY_DB --command "SELECT * FROM erasure_audit ORDER BY requested_at DESC LIMIT 5"
```

---

## Related

- `workers-gdpr-data-portability-r2.md`
- `workers-ccpa-opt-out-gpc-header.md`
- `workers-hipaa-audit-log-d1.md`

---

## Sources

- GDPR Article 17 — https://gdpr-info.eu/art-17-gdpr/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare R2 — https://developers.cloudflare.com/r2/
- Cloudflare KV — https://developers.cloudflare.com/kv/
