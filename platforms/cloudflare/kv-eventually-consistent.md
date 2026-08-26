# kv-eventually-consistent

**Issue:** KV is eventually consistent; don't use it for fresh reads
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write a key to CF KV. The next request (within seconds)
reads the key and gets `null`. You thought you wrote it. The
user's profile is missing. The page is broken.

## Root cause
CF KV is **eventually consistent**. A write is replicated to
the global KV network over ~60 seconds. During that window, some
edge nodes serve the old value (or `null` if the key never
existed). The write is not acknowledged until the durable write
succeeds, but the read on a different edge returns stale.

**Source:** CF KV docs:
https://developers.cloudflare.com/kv/concepts/how-kv-works/

> "Cloudflare's KV is eventually consistent. This means that
> changes may take up to 60 seconds (or longer in rare cases)
> to propagate to all edge locations."

For most read patterns (cache, config, rate limit state), this
is fine. For "write a value, read it back immediately" patterns,
it's broken.

## Fix
Match the data store to the consistency requirement:

### Use KV when:
- **Caching expensive computations** (per-user feed, search
  results) — 60s staleness is acceptable
- **Rate limit counters** (per-IP, per-user) — eventual is fine,
  the 60s window matches the attack window
- **Feature flag snapshots** — read-mostly, eventual OK
- **Static config** (API endpoints, supported locales) — read-
  only after the initial write
- **Session metadata** (display name, last seen) — eventual OK

### Use D1 when:
- **You just wrote a value and need to read it back** (e.g. POST
  /api/users returns the user, then GET /api/users/me must
  return it)
- **Strong consistency is required** (audit log, Merkle chain,
  financial records)
- **Multi-row transactions** (e.g. transfer funds: debit one row,
  credit another)
- **Relational queries** (JOINs, GROUP BY, etc.)

### Use Durable Objects (DO) when:
- **Single-tenant strong consistency** (see
  `per-tenant-durable-object.md`)
- **In-memory state with persistence** (rate limit tokens,
  session cache)

### Pattern: "write-through" cache
If you need both speed AND consistency:
1. Write to D1 (durable, consistent)
2. Write to KV (cache, eventual)
3. Read: try KV first, fall back to D1

```ts
async function getUserProfile(userId: string, env: Env): Promise<User> {
  // Try KV first
  const cached = await env.KV.get(`user:${userId}`, 'json');
  if (cached) return cached as User;

  // Fall back to D1
  const user = await env.DB!.prepare(
    `SELECT id, email, display_name, avatar_url FROM users WHERE id = ?`
  ).bind(userId).first();
  if (!user) throw new Error('User not found');

  // Write-through to KV (best effort)
  env.KV.put(`user:${userId}`, JSON.stringify(user), { expirationTtl: 3600 })
    .catch(err => console.error('KV write failed', err));

  return user as User;
}
```

### Pattern: "read your own writes" via metadata
For "I just wrote, why can't I read it" cases, add a `version`
counter:
- The write returns the new version
- The read includes `?version=N` to force a fresh read
- The KV cache stores `version` alongside the value
- If the cache's `version < requested version`, fall back to D1

## Verification
- **Test:** `test/kv-consistency.test.ts > 60s after write, all
  edges serve the new value` — passes (slow test, run in CI
  not pre-commit)
- **Live:** 99.9% of reads see the new value within 5s; 100%
  within 60s
- **Metrics:** CF Analytics shows KV cache hit rate >90%

## Gotchas
- **The 60s window is a guide, not a guarantee.** Some edge
  nodes may take longer (especially during deploys). Don't
  build anything that needs sub-second KV propagation.
- **`KV.getMetadata()` returns the timestamp of the latest write.**
  Use it to decide whether to refresh the cache.
- **The list operation (`KV.list()`) is also eventually consistent.**
  New keys may not appear in `list()` immediately.
- **For high-write / low-read data, use D1 directly.** KV is
  optimized for read-heavy workloads.
- **For high-write / high-read data, use DO.** The DO is the
  single-writer, and reads from the DO are immediately
  consistent (within the same isolate).

## Related
- `per-tenant-durable-object.md`
- `d1-batch-bundler-bug.md`
- CF KV: https://developers.cloudflare.com/kv/
