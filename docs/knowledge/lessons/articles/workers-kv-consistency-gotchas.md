# Workers KV Consistency Gotchas

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A user updates their profile, is redirected to the profile page, and sees the old data. A user revokes a session, but the session remains valid for up to 60 seconds in distant regions. A `kv.list()` pagination loop misses recently written keys, producing an inconsistent export. Background workers that write to KV and immediately read it back silently operate on stale data.

## Context

Cloudflare KV is an **eventually consistent** distributed key-value store built on top of Cloudflare's global cache. Writes propagate from the originating data centre outward to all edges within ~60 seconds under normal conditions. Reads always return the locally cached value if one exists, regardless of whether a fresher value exists at the origin. This is optimal for read-heavy, write-once patterns (feature flags, static config, content delivery) and problematic for session state, counters, or any data that must be immediately consistent after a write.

## Solution

```typescript
import { Env } from './types';

// ─── Pattern 1: D1 for consistency-critical data ─────────────────────────────
// Move session tokens, user state, and anything that must reflect writes
// immediately to D1 (SQLite, strongly consistent within a region).

export async function createSession(
  env: Env,
  userId: string,
  ttlSeconds: number
): Promise<string> {
  const token = crypto.randomUUID();
  const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;

  // D1 write is immediately visible to subsequent reads in the same region.
  await env.DB.prepare(
    'INSERT INTO sessions (token, user_id, expires_at) VALUES (?1, ?2, ?3)'
  ).bind(token, userId, expiresAt).run();

  return token;
}

export async function revokeSession(env: Env, token: string): Promise<void> {
  // Immediately consistent — a read a millisecond later sees the deletion.
  await env.DB.prepare('DELETE FROM sessions WHERE token = ?1').bind(token).run();
}

export async function validateSession(
  env: Env,
  token: string
): Promise<{ userId: string } | null> {
  const row = await env.DB.prepare(
    'SELECT user_id FROM sessions WHERE token = ?1 AND expires_at > unixepoch()'
  ).bind(token).first<{ user_id: string }>();
  return row ? { userId: row.user_id } : null;
}

// ─── Pattern 2: KV cacheTtl and its implications ─────────────────────────────
// cacheTtl controls how long edge caches hold a KV value before re-fetching
// from the origin store. Lowering it trades latency for fresher reads.
// The minimum is 60 seconds; there is no way to get sub-60s global
// consistency from KV.

export async function getFeatureFlag(
  env: Env,
  flag: string
): Promise<boolean> {
  // cacheTtl: 60 — the minimum. Even so, a write may not be visible for
  // up to 60 s in distant colos. Acceptable for feature flags; not for sessions.
  const value = await env.FLAGS.get(flag, { cacheTtl: 60 });
  return value === 'true';
}

// ─── Pattern 3: Optimistic UI + Queue-based confirmation ─────────────────────
// For profile updates: immediately return 200 to the client with the new data,
// write to D1 for ground truth, and enqueue a KV cache warm-up so that
// any edge that serves the GET /profile endpoint sees the fresh value soon.

export async function updateProfile(
  env: Env,
  userId: string,
  patch: Record<string, unknown>
): Promise<void> {
  // 1. Ground truth write — immediately consistent.
  await env.DB.prepare(
    'UPDATE users SET profile = json_patch(profile, ?1), updated_at = unixepoch() WHERE id = ?2'
  ).bind(JSON.stringify(patch), userId).run();

  // 2. Enqueue a KV invalidation so edge caches are refreshed shortly.
  // The consumer re-reads from D1 and writes the fresh value to KV.
  await env.PROFILE_INVALIDATION_QUEUE.send({
    type: 'invalidate_profile',
    userId,
    timestamp: Date.now(),
  });
}

// Queue consumer (separate handler / queue worker)
export async function handleProfileInvalidation(
  env: Env,
  messages: MessageBatch<{ type: string; userId: string }>
): Promise<void> {
  for (const msg of messages.messages) {
    const { userId } = msg.body;
    const row = await env.DB.prepare(
      'SELECT profile FROM users WHERE id = ?1'
    ).bind(userId).first<{ profile: string }>();

    if (row) {
      // Write to KV — will propagate globally within ~60 s.
      // TTL: 300 s so stale entries self-clean.
      await env.PROFILES_KV.put(
        `profile:${userId}`,
        row.profile,
        { expirationTtl: 300 }
      );
    }
    msg.ack();
  }
}

// ─── Pattern 4: KV list() pagination caveat ──────────────────────────────────
// kv.list() reflects the state at the origin store, but recently written keys
// (< ~60 s ago) may not appear if the list request is served from an edge
// that has not yet received the write propagation.
//
// Do NOT use kv.list() for inventory that requires complete, fresh enumeration.
// Use D1 or Durable Objects for that.

export async function listAllKeys(
  env: Env,
  prefix: string
): Promise<string[]> {
  const keys: string[] = [];
  let cursor: string | undefined;

  do {
    // list() is eventually consistent — keys written in the last ~60 s may be absent.
    const result = await env.MY_KV.list({ prefix, limit: 1000, cursor });
    keys.push(...result.keys.map(k => k.name));
    cursor = result.list_complete ? undefined : result.cursor;
  } while (cursor);

  return keys;
}

// ─── Pattern 5: Migration from KV to D1 for session data ─────────────────────
// Dual-write bridge: during migration, write to both KV and D1.
// Reads check D1 first (authoritative); fall back to KV for legacy sessions
// that have not yet been migrated. After migration window, remove KV reads.

export async function validateSessionMigrated(
  env: Env,
  token: string
): Promise<{ userId: string } | null> {
  // Phase 1: Check D1 (new sessions live here)
  const d1Row = await env.DB.prepare(
    'SELECT user_id FROM sessions WHERE token = ?1 AND expires_at > unixepoch()'
  ).bind(token).first<{ user_id: string }>();
  if (d1Row) return { userId: d1Row.user_id };

  // Phase 2: Check KV (legacy sessions)
  const kvValue = await env.SESSIONS_KV.get(token, { type: 'json' }) as { userId: string; exp: number } | null;
  if (kvValue && kvValue.exp > Math.floor(Date.now() / 1000)) {
    // Back-fill to D1 so next check is consistent
    await env.DB.prepare(
      'INSERT OR IGNORE INTO sessions (token, user_id, expires_at) VALUES (?1, ?2, ?3)'
    ).bind(token, kvValue.userId, kvValue.exp).run();
    return { userId: kvValue.userId };
  }

  return null;
}
```

## Implementation Details

**The ~60-second global consistency window** is not guaranteed — it is a typical propagation time. Under regional partitions or heavy load, it can be longer. Cloudflare does not SLA the propagation time. Design systems around "eventually consistent, possibly much later" rather than "eventually consistent in 60 seconds".

**`cacheTtl` minimum of 60 seconds.** There is no way to configure a `cacheTtl` lower than 60 seconds. Any application that requires sub-60-second global consistency for a given key cannot use KV for that key.

**KV `list()` cursor consistency.** The cursor returned by a paginated `list()` is a snapshot of the origin store at the time of the first call. Subsequent pages are consistent with that snapshot, but the snapshot itself may be up to 60 seconds stale. Insertions after the snapshot may appear on later pages or not at all.

**KV read costs.** KV reads from within a Worker are charged per read operation. If you read the same key many times within a request, cache the value in a local variable — KV does not deduplicate reads within the same request.

## Anti-patterns

- **Storing session tokens in KV and expecting immediate revocation.** A revoked session may continue to pass validation in distant colos for up to 60 seconds.
- **Using KV as a distributed counter.** KV has no atomic increment. Two Workers incrementing the same counter concurrently will silently overwrite each other. Use Durable Objects or D1 for counters.
- **Relying on `kv.list()` to confirm a write succeeded.** A key you just wrote will not appear in `list()` results until propagation completes.
- **Not setting `expirationTtl` on ephemeral KV entries.** Orphaned keys accumulate and can push namespaces toward per-namespace key count limits.
- **Using KV for write-heavy workloads.** KV is optimised for reads (cached at edge). Writes are expensive relative to reads and do not benefit from edge caching.

## Gotchas

- **`kv.get()` returns `null` for a key that was just written.** This is not an error — it is eventual consistency. The key will appear on subsequent reads once propagation completes in that edge location.
- **KV `type: 'json'` does not validate schema.** If a value was written as a string but you read it as `json`, you will get a string back, not an object. Always validate the returned type.
- **KV `metadata` has a 1024-byte limit.** Attempting to store metadata larger than 1024 bytes throws an error at write time. This limit has caused production incidents when metadata schemas grew over time.
- **KV `expirationTtl` is measured from write time, not read time.** Unlike Redis `EXPIRE`, there is no way to extend a TTL without rewriting the value.
- **D1 is region-local for writes.** D1 writes go to the primary region and are then replicated. Read replicas may return slightly stale data. For most session workloads, this is acceptable; for global eventual-consistency-free guarantees, combine D1 with Durable Objects.

## Verification

```typescript
// Test: verify that a KV write is NOT immediately visible from a different
// Cloudflare colo. Deploy a Worker that writes a random key, waits 0 ms,
// then reads it back from a hardcoded non-origin colo endpoint.
//
// Expected: read may return null or the previous value.
// After 60 s: read should return the new value.

// Test: verify D1-based session revocation is immediate.
// 1. Create a session, extract the token.
// 2. Call revoke.
// 3. Immediately call validate — expect null.
// This should pass consistently with < 5 ms round-trip.

// Integration test skeleton:
async function testSessionRevocation(env: Env): Promise<void> {
  const token = await createSession(env, 'user-1', 3600);
  await revokeSession(env, token);
  const result = await validateSession(env, token);
  if (result !== null) throw new Error('Revoked session still valid!');
  console.log('PASS: session revocation is immediately consistent via D1');
}
```

## Related

- `kv-consistency-mode-eventual-reads-production-bug.md`
- `kv-eventual-consistency-cache-poisoning-incident.md`
- `workers-kv-write-after-read-consistency-incident.md`
- `cloudflare-storage-primitive-selection.md`
- `d1-transaction-isolation-lessons.md`

## Sources

- Cloudflare KV — How KV Works: https://developers.cloudflare.com/kv/learning/how-kv-works/
- Cloudflare KV — Consistency: https://developers.cloudflare.com/kv/reference/consistency/
- Cloudflare D1 — Read Replication: https://developers.cloudflare.com/d1/configuration/read-replication/
- Cloudflare Queues — Consumer Workers: https://developers.cloudflare.com/queues/reference/consumer-concurrency/
