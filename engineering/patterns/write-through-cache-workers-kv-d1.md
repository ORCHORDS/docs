# Write-Through Cache — Workers KV + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers API serves user profile reads at high volume. The existing pattern writes directly to D1 and reads through KV — but the KV copy becomes stale whenever a write occurs, causing clients to see outdated data until the cache expires. The write-through pattern fixes this: every write hits D1 *and* KV atomically (within the same request), so the cache is always current immediately after a write succeeds.

Write-through trades slightly higher write latency (two operations instead of one) for zero stale reads — exactly right for data that is read far more than it is written and where users must see their own writes immediately.

---

## Context

KV is eventually consistent across Cloudflare's global network but is strongly consistent *within the same colo* on the same PoP. D1 is the system of record; KV is the read cache. The write-through pattern writes D1 first (the authoritative store), then updates KV as the last step. If the KV write fails, the system degrades gracefully to read-through fallback — it never leaves the cache with *incorrect* data, only *missing* data.

Compare with write-behind (write KV first, flush to D1 asynchronously): write-behind has lower write latency but risks data loss if D1 flush fails. Write-through is the safer default.

---

## Repository Interface

```typescript
// src/profiles/repository.ts
export interface UserProfile {
  id: string;
  displayName: string;
  email: string;
  avatarUrl: string | null;
  updatedAt: string;
}

export interface ProfileRepository {
  get(id: string): Promise<UserProfile | null>;
  upsert(profile: UserProfile): Promise<void>;
  delete(id: string): Promise<void>;
}
```

---

## Write-Through Repository Implementation

```typescript
// src/profiles/write-through-repository.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';
import type { UserProfile, ProfileRepository } from './repository';

const TTL_SECONDS = 300; // 5-minute KV TTL
const KV_PREFIX = 'profile:';

export class WriteThroughProfileRepository implements ProfileRepository {
  constructor(
    private readonly db: D1Database,
    private readonly kv: KVNamespace,
  ) {}

  async get(id: string): Promise<UserProfile | null> {
    // 1. Check KV first (fast path)
    const cached = await this.kv.get<UserProfile>(KV_PREFIX + id, 'json');
    if (cached) return cached;

    // 2. Miss: read from D1 and backfill KV
    const row = await this.db
      .prepare('SELECT * FROM user_profiles WHERE id = ?')
      .bind(id)
      .first<UserProfile>();

    if (row) {
      // Backfill — don't await; a KV write failure here only delays caching
      this.kv
        .put(KV_PREFIX + id, JSON.stringify(row), { expirationTtl: TTL_SECONDS })
        .catch(err => console.error('KV backfill failed', err));
    }

    return row ?? null;
  }

  async upsert(profile: UserProfile): Promise<void> {
    const updatedProfile = { ...profile, updatedAt: new Date().toISOString() };

    // 1. Write to D1 first — the system of record
    await this.db
      .prepare(`
        INSERT INTO user_profiles (id, display_name, email, avatar_url, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
          display_name = excluded.display_name,
          email        = excluded.email,
          avatar_url   = excluded.avatar_url,
          updated_at   = excluded.updated_at
      `)
      .bind(
        updatedProfile.id,
        updatedProfile.displayName,
        updatedProfile.email,
        updatedProfile.avatarUrl,
        updatedProfile.updatedAt,
      )
      .run();

    // 2. Update KV synchronously — write-through guarantee
    // If this throws, the caller gets a 500 but D1 is correct; next read will backfill.
    await this.kv.put(
      KV_PREFIX + updatedProfile.id,
      JSON.stringify(updatedProfile),
      { expirationTtl: TTL_SECONDS },
    );
  }

  async delete(id: string): Promise<void> {
    // 1. Delete from D1
    await this.db
      .prepare('DELETE FROM user_profiles WHERE id = ?')
      .bind(id)
      .run();

    // 2. Invalidate KV — also synchronous so reads don't see deleted data
    await this.kv.delete(KV_PREFIX + id);
  }
}
```

---

## Worker Handler

```typescript
// src/index.ts
import { WriteThroughProfileRepository } from './profiles/write-through-repository';
import type { UserProfile } from './profiles/repository';

interface Env {
  DB: D1Database;
  PROFILE_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const repo = new WriteThroughProfileRepository(env.DB, env.PROFILE_CACHE);
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/profiles\/([^/]+)$/);
    if (!match) return new Response('Not Found', { status: 404 });
    const id = match[1];

    if (request.method === 'GET') {
      const profile = await repo.get(id);
      if (!profile) return new Response('Not Found', { status: 404 });
      return Response.json(profile, {
        headers: { 'Cache-Control': 'private, max-age=60' },
      });
    }

    if (request.method === 'PUT') {
      const body = await request.json<Partial<UserProfile>>();
      if (!body.displayName || !body.email) {
        return Response.json({ error: 'displayName and email required' }, { status: 400 });
      }
      await repo.upsert({ id, displayName: body.displayName, email: body.email, avatarUrl: body.avatarUrl ?? null, updatedAt: '' });
      return new Response(null, { status: 204 });
    }

    if (request.method === 'DELETE') {
      await repo.delete(id);
      return new Response(null, { status: 204 });
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};
```

---

## Handling KV Write Failures Gracefully

KV is highly available but not infallible. Decide upfront whether KV failure should be a client-visible error or a silent degradation.

```typescript
async upsertWithFallback(profile: UserProfile): Promise<{ kvOk: boolean }> {
  // D1 write is always required
  await this.writeToD1(profile);

  // KV write failure: degrade, do not fail the request
  try {
    await this.kv.put(KV_PREFIX + profile.id, JSON.stringify(profile), {
      expirationTtl: TTL_SECONDS,
    });
    return { kvOk: true };
  } catch (err) {
    console.error('Write-through KV update failed — degraded to read-through', err);
    return { kvOk: false };
  }
}
```

Log `kvOk: false` to Analytics Engine or Logpush so cache write failures are observable without surfacing them to the client.

---

## Cache Key Versioning for Schema Migrations

When D1 schema changes (renaming a column, adding a non-nullable field), stale KV entries with the old shape will cause parse errors.

```typescript
const CACHE_VERSION = 'v2';
const KV_PREFIX = `profile:${CACHE_VERSION}:`;

// On schema migration, bump CACHE_VERSION.
// Old KV entries expire naturally via TTL; no manual purge needed.
```

---

## Anti-patterns

- **Writing KV before D1**: if D1 fails after KV is already updated, the cache holds data that was never persisted — ghost state. Always write the system of record first.
- **Using KV as the system of record**: KV is eventually consistent globally; two Workers in different colos may read different values. D1 is the single source of truth.
- **Long TTLs on mutable data**: a 24-hour TTL on user profile data means a write-through bypass (direct D1 write from a background job) could leave the cache stale for a day. Keep TTLs short (5–15 min) or purge explicitly.
- **Not awaiting the KV write in `upsert`**: fire-and-forget on the KV write converts write-through into write-behind with loss risk. Await it (and handle failures explicitly).
- **One KV key per field**: storing `profile:email:id`, `profile:name:id`, etc. requires multiple KV reads. Store the full serialised object under one key.

---

## Gotchas

- KV `get` with `'json'` type calls `JSON.parse` internally and returns `null` on parse error, not a throw — useful but easy to miss in type signatures.
- KV `put` has a maximum value size of 25 MB; for very large profile blobs consider R2 instead.
- Workers KV list operations (`kv.list()`) are eventually consistent and should not be relied on to enumerate all recently-written keys.
- D1's `ON CONFLICT ... DO UPDATE` (UPSERT) requires SQLite 3.24+; Cloudflare's D1 runtime supports it as of 2024.
- In Vitest with `@cloudflare/vitest-pool-workers`, mock KV as an in-memory map to test write-through ordering without a live binding.

---

## Verification

```bash
# Write a profile
curl -X PUT https://my-worker.workers.dev/profiles/usr_1 \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Alice","email":"alice@example.com"}'

# Immediately read — should hit KV (write-through means it's there)
curl https://my-worker.workers.dev/profiles/usr_1
# {"id":"usr_1","displayName":"Alice","email":"alice@example.com",...}

# Inspect KV directly
npx wrangler kv:get "profile:v2:usr_1" --binding PROFILE_CACHE
# {"id":"usr_1","displayName":"Alice",...}

# Verify D1 also has the row
npx wrangler d1 execute DB \
  --command "SELECT * FROM user_profiles WHERE id = 'usr_1';"
```

---

## Related

- `cache-aside-kv-d1-fallback.md`
- `write-behind-cache-kv-d1.md`
- `read-through-cache-workers-kv-d1.md`
- `stale-while-revalidate-workers-kv.md`
- `repository-pattern.md`

---

## Sources

- Cloudflare KV docs — consistency model, `put`, `get` with type (2026)
- Cloudflare D1 docs — UPSERT / `ON CONFLICT` (2026)
- Caching Strategies and How to Choose the Right One — Cloudflare blog (2023)
- Designing Data-Intensive Applications, Kleppmann — ch. 5 Replication
