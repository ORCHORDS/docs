# KV Write Amplification Discovered via kv list Returning Stale Keys

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers-based session management system used KV with short TTLs (300 seconds) to store user session tokens. After implementing a logout endpoint that deleted session keys, users reported being able to still access protected routes for up to 60 seconds after logging out. An audit using `wrangler kv key list` confirmed the deleted keys were still appearing in list results long after their TTL had expired and after explicit `DELETE` operations.

---

## Context

Cloudflare Workers KV is an eventually-consistent key-value store distributed globally across Cloudflare's edge. Reads via `kv.get(key)` are fast and eventually consistent with a typical propagation time of up to 60 seconds. However, `kv.list()` (and the equivalent `wrangler kv key list`) queries a central metadata store that can lag behind individual key deletions and TTL expirations by up to 60 seconds. The team was using `kv.list({ prefix: 'session:' })` to enumerate active sessions for an admin dashboard and to validate logout — an architectural mistake that mixed KV's strengths (fast per-key get) with its weakness (eventual consistency of the list index).

---

## What Went Wrong

```typescript
// auth/session.ts — broken: using KV list() for session validation
export async function isSessionValid(
  sessionId: string,
  env: Env
): Promise<boolean> {
  // BAD: list() can return deleted/expired keys for up to 60 seconds
  const { keys } = await env.SESSION_KV.list({ prefix: 'session:' });
  const activeIds = new Set(keys.map(k => k.name.replace('session:', '')));
  return activeIds.has(sessionId);
}

export async function logout(sessionId: string, env: Env): Promise<void> {
  // Delete the key — but list() won't reflect this immediately
  await env.SESSION_KV.delete(`session:${sessionId}`);
}

// admin/dashboard.ts — also broken: listing all active sessions via KV
export async function getActiveSessions(env: Env): Promise<string[]> {
  const { keys } = await env.SESSION_KV.list({ prefix: 'session:' });
  // Returns stale keys including expired/deleted sessions
  return keys.map(k => k.name);
}
```

```bash
# Demonstrating the problem: delete a key and immediately list — stale key appears
wrangler kv key delete --binding SESSION_KV "session:abc123" --remote
wrangler kv key list --binding SESSION_KV --prefix "session:" --remote
# Output still shows session:abc123 for up to 60 seconds after deletion
```

## Root Cause

Cloudflare Workers KV uses an eventually-consistent replication model. The `list()` operation reads from a central metadata index that replicates key deletions and TTL expirations asynchronously. This metadata replication can lag by up to 60 seconds. By contrast, `get(key)` reads from the nearest edge cache and is subject to the same eventual consistency window, but key deletions propagate through the cache invalidation path separately from the list index. The team was relying on `list()` as a source-of-truth for session existence — a pattern that KV's consistency model does not support. Additionally, listing all keys with a prefix for every session check was O(n) in the number of active sessions, creating unnecessary KV API quota consumption (write amplification in reads).

## The Fix

```typescript
// auth/session.ts — fixed: use kv.get() for existence check (not list())
// and D1 as source-of-truth for session enumeration

export async function isSessionValid(
  sessionId: string,
  env: Env
): Promise<boolean> {
  // GOOD: get() by exact key is the correct pattern for existence checks.
  // A missing or expired key returns null immediately (within the ~60s consistency window,
  // which is acceptable for session checks — logout propagates globally within 60s).
  const session = await env.SESSION_KV.get(`session:${sessionId}`, 'json');
  return session !== null;
}

export async function logout(sessionId: string, env: Env): Promise<void> {
  // Delete from KV (propagates to all edges within ~60s)
  await env.SESSION_KV.delete(`session:${sessionId}`);

  // ALSO record logout in D1 for immediate consistency in admin views
  await env.DB.prepare(
    'UPDATE sessions SET logged_out_at = CURRENT_TIMESTAMP WHERE id = ?'
  )
    .bind(sessionId)
    .run();
}

export async function createSession(
  userId: string,
  env: Env
): Promise<string> {
  const sessionId = crypto.randomUUID();
  const expiresAt = Date.now() + 300_000; // 300s TTL

  // Write to KV for fast per-key edge lookups
  await env.SESSION_KV.put(
    `session:${sessionId}`,
    JSON.stringify({ userId, expiresAt }),
    { expirationTtl: 300 }
  );

  // Write to D1 as canonical source-of-truth for enumeration
  await env.DB.prepare(
    'INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)'
  )
    .bind(sessionId, userId, new Date(expiresAt).toISOString())
    .run();

  return sessionId;
}
```

```typescript
// admin/dashboard.ts — fixed: enumerate sessions from D1, not KV list()
export async function getActiveSessions(env: Env): Promise<Session[]> {
  // D1 is consistent and supports complex queries; use it for enumeration
  const { results } = await env.DB.prepare(
    `SELECT id, user_id, expires_at, logged_out_at
     FROM sessions
     WHERE expires_at > CURRENT_TIMESTAMP
       AND logged_out_at IS NULL
     ORDER BY expires_at DESC
     LIMIT 100`
  ).all();

  return results as Session[];
}
```

## Prevention

```typescript
// Monitoring: emit KV list vs D1 count discrepancy to Analytics Engine
export async function auditSessionConsistency(env: Env & { AE: AnalyticsEngineDataset }): Promise<void> {
  const { keys } = await env.SESSION_KV.list({ prefix: 'session:' });
  const kvCount = keys.length;

  const { results } = await env.DB.prepare(
    'SELECT COUNT(*) AS cnt FROM sessions WHERE expires_at > CURRENT_TIMESTAMP AND logged_out_at IS NULL'
  ).all();
  const d1Count = Number(results[0]?.cnt ?? 0);

  const drift = Math.abs(kvCount - d1Count);

  env.AE.writeDataPoint({
    blobs: ['session_consistency_audit'],
    doubles: [kvCount, d1Count, drift],
    indexes: ['kv_d1_session_drift'],
  });

  if (drift > 50) {
    console.warn(`Session count drift: KV=${kvCount}, D1=${d1Count}, drift=${drift}`);
  }
}
```

```bash
# Lint rule (eslint custom rule or grep in CI) to flag kv.list() usage in auth paths
# Add to .github/workflows/lint.yml:
# - name: Forbid kv.list() in auth module
#   run: |
#     if grep -r 'SESSION_KV\.list\|kv\.list' src/auth/; then
#       echo "ERROR: Do not use kv.list() in auth paths — use D1 for session enumeration"
#       exit 1
#     fi
```

---

## Anti-patterns

- **Using `kv.list()` for existence checks** — `list()` is for key discovery, not for checking if a specific key is live; use `kv.get(key)` for that.
- **Treating `kv.list()` as strongly consistent** — The list index can lag up to 60 seconds behind deletions and TTL expirations; never make security decisions based on list output.
- **Per-request `kv.list()` calls** — `list()` is paginated and slow for large key spaces; calling it per-request creates unnecessary API quota usage and latency.
- **KV as sole session store without a consistent fallback** — KV's eventual consistency makes it unsuitable as the sole truth for session enumeration; pair it with D1 for queries and KV for fast per-key lookups.
- **Short TTL + immediate deletion assumption** — Even with a 5-minute TTL, expired keys can appear in `list()` for 60 seconds beyond expiry; do not assume TTL-expired keys are immediately invisible to `list()`.

---

## Gotchas

- `kv.get(key)` is also eventually consistent — a key deleted at one edge may still be readable at another edge for up to 60 seconds. For hard security boundaries, invalidate sessions in D1 and check D1 on auth.
- `kv.list()` returns a maximum of 1000 keys per page; for key spaces larger than 1000, you must paginate using the `cursor` field — this is easy to miss.
- Cloudflare's KV consistency guarantee is "read-after-write" within the same Cloudflare colo only — cross-colo propagation takes up to 60 seconds.
- Writing to a key with `expirationTtl` does NOT remove it from `list()` at TTL time atomically — the list index cleans up expired keys eventually, not immediately.
- `wrangler kv key list` output is sorted lexicographically, not by creation time — do not infer insertion order from list output.
- Analytics Engine `writeDataPoint()` is fire-and-forget (no await needed for non-critical monitoring) but the binding must be configured in `wrangler.toml`.

---

## Verification

```bash
# Test: create a session, delete it, and verify get() returns null immediately
SESSION_ID=$(wrangler kv key put --binding SESSION_KV \
  "session:test-$(date +%s)" '{"userId":"u1"}' \
  --expiration-ttl 300 --remote && echo "test-$(date +%s)")

wrangler kv key delete --binding SESSION_KV "session:${SESSION_ID}" --remote

# get() should return null (key not found)
wrangler kv key get --binding SESSION_KV "session:${SESSION_ID}" --remote \
  && echo "FAIL: key still readable" || echo "PASS: key not found via get()"

# list() may still show the key for up to 60s — this is expected / the bug we worked around
wrangler kv key list --binding SESSION_KV --prefix "session:" --remote | grep "${SESSION_ID}" \
  && echo "KNOWN: key still in list index (eventual consistency)" \
  || echo "list() already cleaned up"

# Verify D1 is the correct source of truth after logout
wrangler d1 execute orchords-db --remote \
  --command "SELECT id, logged_out_at FROM sessions WHERE id = '${SESSION_ID}';"
```

---

## Related

- `lessons-d1-import-large-csv-timeout.md`
- `eventual-consistency-surprises-clients.md`

---

## Sources

- Cloudflare Workers KV How it works — https://developers.cloudflare.com/kv/concepts/how-kv-works/
- KV list() API — https://developers.cloudflare.com/kv/api/list-keys/
- KV consistency model — https://developers.cloudflare.com/kv/reference/consistency/
- Analytics Engine overview — https://developers.cloudflare.com/analytics/analytics-engine/
- D1 Worker API — https://developers.cloudflare.com/d1/worker-api/
