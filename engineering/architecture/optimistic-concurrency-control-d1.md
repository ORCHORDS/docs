# Optimistic Concurrency Control with D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Two example project Workers simultaneously receive a request to edit the same user profile. Both read the current row, compute their update independently, and write back — the second write silently overwrites the first. The result is a lost update with no error surfaced to either caller. Pessimistic locking (SELECT FOR UPDATE) does not exist in D1; distributed locks add latency and complexity. The correct solution for low-contention write paths is **optimistic concurrency control (OCC)** using a version column.

## Context

OCC assumes conflicts are rare. Each row carries a monotonically increasing `version` integer (or an `updated_at` timestamp with sufficient resolution). A writer reads the current version, includes it in the WHERE clause of the UPDATE, and checks the number of affected rows. If `changes() == 0`, another writer modified the row first — the client receives a `409 Conflict` and retries with fresh data. D1 supports this pattern natively through its `meta.changes` result field. This is distinct from the distributed lock and fencing token articles: OCC requires no external state and adds zero latency to the happy path.

## 1. Schema Design with a Version Column

Add a `version INTEGER NOT NULL DEFAULT 1` column to any table that needs OCC. Increment it atomically in the UPDATE itself — never in application code before the query.

```sql
CREATE TABLE user_profiles (
  user_id     TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  bio         TEXT NOT NULL DEFAULT '',
  version     INTEGER NOT NULL DEFAULT 1,
  updated_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
```

An integer version is preferable to a timestamp because:
- D1 stores `CURRENT_TIMESTAMP` at second resolution by default, making two concurrent writes within the same second indistinguishable.
- Integer increment is cheaper than string comparison.
- Version numbers communicate intent clearly in error messages.

## 2. Read–Modify–Write with OCC Guard

The canonical OCC pattern: read version, apply business logic, write with `WHERE version = ?`, check `meta.changes`.

```typescript
interface UserProfile {
  userId: string;
  displayName: string;
  bio: string;
  version: number;
}

async function updateProfile(
  db: D1Database,
  userId: string,
  patch: Partial<Pick<UserProfile, 'displayName' | 'bio'>>,
): Promise<UserProfile> {
  const current = await db
    .prepare('SELECT * FROM user_profiles WHERE user_id = ?')
    .bind(userId)
    .first<UserProfile>();

  if (!current) throw new NotFoundError(`user ${userId} not found`);

  const next: UserProfile = {
    ...current,
    ...patch,
    version: current.version + 1,
  };

  const result = await db
    .prepare(
      `UPDATE user_profiles
         SET display_name = ?, bio = ?, version = ?, updated_at = CURRENT_TIMESTAMP
       WHERE user_id = ? AND version = ?`,
    )
    .bind(next.displayName, next.bio, next.version, userId, current.version)
    .run();

  if (result.meta.changes === 0) {
    throw new ConflictError(`version conflict on user ${userId} at version ${current.version}`);
  }

  return next;
}
```

## 3. HTTP Layer — Surfacing Conflicts as 409

Translate OCC conflicts into standard HTTP `409 Conflict` responses with an `ETag` / `If-Match` contract so API clients know to re-fetch and retry.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'PATCH') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const userId = getUserId(request);
    const body = await request.json<{ displayName?: string; bio?: string }>();

    try {
      const updated = await updateProfile(env.DB, userId, body);
      return Response.json(updated, {
        headers: { ETag: `"${updated.version}"` },
      });
    } catch (err) {
      if (err instanceof ConflictError) {
        return new Response(err.message, {
          status: 409,
          headers: { 'Content-Type': 'text/plain' },
        });
      }
      throw err;
    }
  },
};
```

Clients should send `If-Match: "3"` on updates. The Worker reads the version from the header instead of a fresh DB read for a single-round-trip optimistic check:

```typescript
function versionFromIfMatch(request: Request): number | null {
  const header = request.headers.get('If-Match');
  if (!header) return null;
  const match = header.replace(/"/g, '');
  const n = parseInt(match, 10);
  return isNaN(n) ? null : n;
}
```

## 4. Batch OCC with D1 `batch()`

For updating multiple related rows atomically (e.g., profile + settings), use `db.batch()` to run all OCC-guarded statements in a single network round-trip.

```typescript
async function updateProfileAndSettings(
  db: D1Database,
  userId: string,
  profilePatch: Partial<UserProfile>,
  settingsPatch: Record<string, string>,
): Promise<void> {
  const [profileResult, settingsResult] = await db.batch([
    db
      .prepare(
        `UPDATE user_profiles SET display_name = ?, version = version + 1
         WHERE user_id = ? AND version = ?`,
      )
      .bind(profilePatch.displayName, userId, profilePatch.version),
    db
      .prepare(
        `UPDATE user_settings SET theme = ?, version = version + 1
         WHERE user_id = ? AND version = ?`,
      )
      .bind(settingsPatch.theme, userId, settingsPatch.settingsVersion),
  ]);

  if (profileResult.meta.changes === 0 || settingsResult.meta.changes === 0) {
    throw new ConflictError('concurrent modification detected');
  }
}
```

## 5. Retry with Exponential Backoff on the Client

OCC conflicts should be retried transparently for idempotent operations. Implement a short backoff to avoid thundering-herd re-contention.

```typescript
async function updateWithRetry(
  db: D1Database,
  userId: string,
  patch: Partial<UserProfile>,
  maxAttempts = 3,
): Promise<UserProfile> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await updateProfile(db, userId, patch);
    } catch (err) {
      if (err instanceof ConflictError && attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, 2 ** attempt * 50)); // 100 ms, 200 ms
        continue;
      }
      throw err;
    }
  }
  throw new Error('unreachable');
}
```

## Anti-patterns

- **Incrementing the version in application code before the query** — this always succeeds regardless of concurrent writes; the version must be incremented inside the SQL `SET version = version + 1` so it happens atomically on the row.
- **Using `updated_at` as the version at second-resolution** — two writes within the same second both pass the WHERE clause; use an integer column.
- **Retrying infinitely on conflict** — cap retries at 3–5 and surface a `409` to the caller; infinite retry loops can cause cascading write storms under high contention.
- **Skipping the `meta.changes` check** — D1 UPDATE does not throw when zero rows match; always assert `result.meta.changes >= 1`.

## Gotchas

- D1 `meta.changes` counts rows affected by the UPDATE, not rows matched; a row that matches but whose values did not change still increments `changes` in most SQLite implementations — this is fine for OCC purposes.
- D1 is not truly serialisable across separate statements in the same Worker invocation; `batch()` executes statements atomically in a single transaction, but two Workers running separate `batch()` calls concurrently still race — OCC handles this correctly.
- Version columns do not replace application-level conflict resolution: the 409 tells the client that a conflict occurred, but it is up to the product (example project profile merge vs. last-write-wins) to decide what the retry should do with the now-stale client-side data.
- Keep version integers as `INTEGER` not `TEXT` in D1; SQLite compares text versions lexicographically (`"10" < "9"`), which would silently break the OCC guard.

## Verification

1. Start two concurrent Workers both reading version `5` of a user profile, then both issuing the OCC-guarded UPDATE; assert exactly one returns success and one returns a `ConflictError`.
2. Issue a PATCH with `If-Match: "2"` against a row at version `3`; assert a `409` response.
3. After a conflict, re-fetch the row and resubmit the update; assert it succeeds and the version increments to the expected value.
4. Run a `db.batch()` with one valid and one stale version across two tables; assert both `meta.changes` are checked and a conflict surfaces correctly.

## Related

- `idempotency-design.md`
- `idempotency-keys-workers-api.md`
- `lease-based-distributed-lock-d1-cas.md`
- `fencing-tokens.md`
- `acid-vs-base-tradeoffs.md`

## Sources

- SQLite `changes()` function: https://www.sqlite.org/lang_corefunc.html#changes
- Cloudflare D1 batch operations: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Martin Fowler — Optimistic Offline Lock pattern: https://martinfowler.com/eaaCatalog/optimisticOfflineLock.html
