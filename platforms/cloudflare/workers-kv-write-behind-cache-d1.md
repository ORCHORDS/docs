# Workers KV Write-Behind Cache with D1 Backing Store

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker reads a config object, user profile, or product record on every request. D1 queries at the edge add 10–50 ms of latency on every hit. You want reads to return in < 1 ms from KV while D1 remains the authoritative store. Writes should update D1 first, then invalidate or refresh the KV entry asynchronously — the write-behind (also called write-around or cache-aside) pattern.

## Context

Workers KV is globally replicated with < 1 ms read latency after a key is warm in the local PoP. D1 is the source of truth: it enforces constraints, transactions, and joins. KV holds a denormalized, serialized snapshot of D1 rows. The cache-aside pattern keeps KV in sync by: (1) reading from KV, falling back to D1 on miss and writing the result back, and (2) invalidating KV on every D1 write.

KV's eventual consistency model means a key invalidated in one PoP may still be served from another PoP's cache for up to 60 seconds. Design for stale reads in that window, or use a version token to detect and reject stale data.

---

## 1. Wrangler Configuration

```toml
# wrangler.toml
name = "kv-cache-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[kv_namespaces]]
binding = "CACHE"
id = "your-kv-namespace-id"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "your-d1-database-id"
```

---

## 2. Cache-Aside Read

```typescript
// src/cache.ts
export interface Env {
  CACHE: KVNamespace;
  DB: D1Database;
}

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  plan: "free" | "pro" | "enterprise";
  updatedAt: string;
}

const CACHE_TTL_SECONDS = 300; // 5 minutes

export async function getUserProfile(
  env: Env,
  userId: string
): Promise<UserProfile | null> {
  const cacheKey = `user:${userId}`;

  // 1. Try KV first
  const cached = await env.CACHE.get<UserProfile>(cacheKey, "json");
  if (cached !== null) return cached;

  // 2. Miss — query D1
  const row = await env.DB.prepare(
    "SELECT id, name, email, plan, updated_at FROM users WHERE id = ?"
  )
    .bind(userId)
    .first<{ id: string; name: string; email: string; plan: string; updated_at: string }>();

  if (!row) return null;

  const profile: UserProfile = {
    id: row.id,
    name: row.name,
    email: row.email,
    plan: row.plan as UserProfile["plan"],
    updatedAt: row.updated_at,
  };

  // 3. Backfill KV asynchronously (don't block response)
  // Use waitUntil in the fetch handler; here we return the value and let
  // the caller enqueue the KV write via ctx.waitUntil
  return profile;
}

export async function primeCache(
  env: Env,
  userId: string,
  profile: UserProfile
): Promise<void> {
  await env.CACHE.put(`user:${userId}`, JSON.stringify(profile), {
    expirationTtl: CACHE_TTL_SECONDS,
  });
}
```

```typescript
// src/index.ts
import { getUserProfile, primeCache, Env } from "./cache";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const userId = new URL(request.url).searchParams.get("userId");
    if (!userId) return new Response("Missing userId", { status: 400 });

    const profile = await getUserProfile(env, userId);
    if (!profile) return new Response("Not found", { status: 404 });

    // If we got a D1 hit (profile came from DB, not cache), backfill KV
    // Detect D1 path by checking CACHE directly — or use a flag from getUserProfile
    ctx.waitUntil(primeCache(env, userId, profile));

    return Response.json(profile);
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Cache Invalidation on Write

On every mutation, write to D1 first, then delete (or overwrite) the KV entry:

```typescript
// src/mutations.ts
import { Env, UserProfile, primeCache } from "./cache";

export async function updateUserPlan(
  env: Env,
  ctx: ExecutionContext,
  userId: string,
  plan: UserProfile["plan"]
): Promise<void> {
  // 1. Authoritative write to D1
  const result = await env.DB.prepare(
    "UPDATE users SET plan = ?, updated_at = ? WHERE id = ?"
  )
    .bind(plan, new Date().toISOString(), userId)
    .run();

  if (!result.meta.changes) throw new Error("User not found");

  // 2. Invalidate KV — delete forces a D1 re-fetch on next read
  ctx.waitUntil(env.CACHE.delete(`user:${userId}`));
}

export async function updateUserProfile(
  env: Env,
  ctx: ExecutionContext,
  userId: string,
  patch: Partial<Pick<UserProfile, "name" | "email">>
): Promise<UserProfile> {
  const sets: string[] = [];
  const values: unknown[] = [];
  if (patch.name !== undefined) { sets.push("name = ?"); values.push(patch.name); }
  if (patch.email !== undefined) { sets.push("email = ?"); values.push(patch.email); }
  if (!sets.length) throw new Error("Nothing to update");

  sets.push("updated_at = ?");
  values.push(new Date().toISOString());
  values.push(userId);

  await env.DB.prepare(
    `UPDATE users SET ${sets.join(", ")} WHERE id = ?`
  ).bind(...values).run();

  // Re-read and warm the cache immediately (write-through variant)
  const fresh = await env.DB.prepare(
    "SELECT id, name, email, plan, updated_at FROM users WHERE id = ?"
  ).bind(userId).first<UserProfile>();

  if (!fresh) throw new Error("User not found after update");

  const profile: UserProfile = { ...fresh, updatedAt: fresh.updatedAt };
  ctx.waitUntil(primeCache(env, userId, profile));
  return profile;
}
```

---

## 4. Versioned Cache Keys to Handle Stale Reads

KV's global consistency window is up to 60 seconds. If stale reads are unacceptable, embed a version token in the cache key and store the current version in D1:

```typescript
async function getVersionedProfile(env: Env, userId: string): Promise<UserProfile | null> {
  // Fetch current version from D1 (fast index scan)
  const versionRow = await env.DB.prepare(
    "SELECT version FROM users WHERE id = ?"
  ).bind(userId).first<{ version: number }>();

  if (!versionRow) return null;

  const cacheKey = `user:${userId}:v${versionRow.version}`;
  const cached = await env.CACHE.get<UserProfile>(cacheKey, "json");
  if (cached) return cached;

  // Full row fetch + cache prime
  const row = await env.DB.prepare(
    "SELECT id, name, email, plan, updated_at, version FROM users WHERE id = ?"
  ).bind(userId).first<UserProfile & { version: number }>();

  if (!row) return null;
  const profile: UserProfile = { id: row.id, name: row.name, email: row.email, plan: row.plan, updatedAt: row.updatedAt };
  await env.CACHE.put(cacheKey, JSON.stringify(profile), { expirationTtl: 300 });
  // Old version keys expire naturally; no explicit delete needed
  return profile;
}
```

On write, increment `version` in the D1 `UPDATE` statement. The new key misses KV and re-fetches from D1; the old versioned key expires via TTL.

---

## 5. Bulk Invalidation with KV Metadata Tags

For invalidating a set of related keys (e.g. all entries for a tenant), store a `tag` in KV metadata and use `list()` with a prefix:

```typescript
async function invalidateTenant(env: Env, tenantId: string): Promise<void> {
  let cursor: string | undefined;
  do {
    const result = await env.CACHE.list({
      prefix: `user:${tenantId}:`,
      cursor,
      limit: 1000,
    });
    await Promise.all(result.keys.map((k) => env.CACHE.delete(k.name)));
    cursor = result.list_complete ? undefined : result.cursor;
  } while (cursor);
}
```

---

## Anti-patterns

- **Awaiting KV writes on the hot path** — `await env.CACHE.put(...)` inside the response path adds 10–50 ms to every request. Enqueue with `ctx.waitUntil()` unless you need the write acknowledged before responding.
- **Using KV as the write target** — writing to KV first (before D1) means a Worker crash between the two writes leaves KV ahead of D1. Always write D1 first.
- **Not handling KV `null` as a miss** — `env.CACHE.get()` returns `null` for both a miss and a deleted key. Always fall through to D1 on `null`.
- **Caching mutable lists with non-deterministic ordering** — if D1 returns `SELECT *` rows in an arbitrary order, two cache entries for the same key may differ. Always add `ORDER BY` to cacheable queries.
- **Forgetting TTL on cache priming** — a KV key without `expirationTtl` never expires. Stale data persists indefinitely after D1 writes that fail to invalidate.

---

## Gotchas

- KV `list()` in a Workers environment counts against your KV read operations quota. Bulk invalidation via listing is expensive; prefer key-level deletes on known keys.
- KV `put` with `expirationTtl` must be ≥ 60 seconds. Values below 60 throw a validation error at runtime.
- `ctx.waitUntil()` must be called before the `fetch` handler returns its `Response`. Scheduling it after `return Response.json(...)` has no effect.
- KV is eventually consistent across PoPs. A `delete` after a D1 write may not be reflected in all PoPs for up to 60 seconds. This is the staleness window; accept it or use versioned keys.
- D1 is not currently available via `getBindings()` in Vitest pool integration tests — mock the DB interface or use a test D1 database bound in `wrangler.toml` under `[env.test]`.

---

## Verification

```bash
# Deploy
wrangler deploy

# Prime cache with a first read (should hit D1)
time curl "https://kv-cache-worker.<subdomain>.workers.dev?userId=usr_001"
# ~15-40ms (D1 hit)

# Second read (should hit KV)
time curl "https://kv-cache-worker.<subdomain>.workers.dev?userId=usr_001"
# ~1-5ms (KV hit)

# Inspect KV key directly
wrangler kv key get "user:usr_001" --namespace-id <namespace-id>

# Trigger invalidation via mutation endpoint, then re-time a read
```

---

## Related

- `kv-best-practices.md`
- `kv-eventually-consistent.md`
- `d1-best-practices.md`
- `workers-cache-api.md`
- `cloudflare-cache-rules-ttl-workers-bypass-pattern.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/kv/reference/consistency/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
