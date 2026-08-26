# Read Repair for Eventual Consistency in Workers KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers KV is a globally replicated, eventually-consistent store. A write propagates
to all PoPs within 60 seconds (Cloudflare's SLA). In that window, a KV read in a
distant PoP may return a stale value even though a more recent value was written
elsewhere.

For most cache-layer use cases this is acceptable. But when KV is used as a
lightweight source of truth — feature flags, per-user preferences, configuration
snapshots — you occasionally need a mechanism to detect and correct stale reads
without requiring strong consistency or switching to a different store.

Read repair is a technique from distributed database literature (Cassandra, Dynamo)
where, upon detecting a stale value during a normal read, the system asynchronously
writes the correct value back to the storage node that served the stale read. Applied
to Workers KV via `ctx.waitUntil`, the repair happens in the background after the
response is already sent.

---

## Context

Workers KV guarantees:

- **Read-your-own-writes** within the same isolate/request if using `cacheTtl: 0`.
- **Eventual consistency** across PoPs — new writes propagate within ~60 s.
- **Last-write-wins** — concurrent writes are resolved by wall clock timestamp; the
  write with the higher timestamp survives.

Read repair helps with these specific failure modes:

1. A user writes a setting in region A. Their next request hits region B where the
   write has not yet propagated. They see stale data.
2. A KV value has a logical version number. A read returns version 3 but the canonical
   source (D1) has version 5.

The repair strategy: on every read, compare the KV value against a version source
(a D1 row, or a version header in the KV metadata). If the KV value is behind,
schedule an async write to bring it up to date.

---

## Architecture

```
Request
  │
  ▼
Worker reads KV value ──────────────────────────────► KV PoP (possibly stale)
  │
  ├── version OK? ──► return response
  │
  └── version stale?
        │
        ├── return response (don't block user)
        │
        └── ctx.waitUntil(repairKV()) ──► fetch canonical D1 value ──► write KV
```

---

## Implementation

### 1. KV value schema with version

```typescript
// types.ts
export interface VersionedValue<T> {
  data: T;
  version: number;      // monotonically increasing logical clock
  updatedAt: string;    // ISO-8601 UTC
  source: "d1" | "kv"; // tracks origin for debugging
}
```

### 2. KV metadata for lightweight version check

```typescript
// kv-helpers.ts
interface KVMeta {
  version: number;
}

/**
 * Reads from KV. Returns both the value and its stored version.
 * Uses metadata to avoid deserialising the full body just to check the version.
 */
export async function kvGetVersioned<T>(
  kv: KVNamespace,
  key: string,
): Promise<{ value: VersionedValue<T> | null; version: number }> {
  const result = await kv.getWithMetadata<VersionedValue<T>, KVMeta>(key, "json");
  return {
    value: result.value,
    version: result.metadata?.version ?? -1,
  };
}

export async function kvPutVersioned<T>(
  kv: KVNamespace,
  key: string,
  payload: VersionedValue<T>,
  ttlSeconds = 3600,
): Promise<void> {
  await kv.put(key, JSON.stringify(payload), {
    expirationTtl: ttlSeconds,
    metadata: { version: payload.version } satisfies KVMeta,
  });
}
```

### 3. Canonical version lookup from D1

```typescript
// canon.ts
interface Env {
  DB: D1Database;
  SETTINGS_KV: KVNamespace;
}

export interface UserSetting {
  userId: string;
  theme: string;
  locale: string;
  version: number;
  updatedAt: string;
}

export async function getCanonicalSetting(
  db: D1Database,
  userId: string,
): Promise<UserSetting | null> {
  const row = await db
    .prepare("SELECT * FROM user_settings WHERE user_id = ? LIMIT 1")
    .bind(userId)
    .first<UserSetting>();
  return row ?? null;
}
```

### 4. Read-repair logic

```typescript
// read-repair.ts
import { kvGetVersioned, kvPutVersioned } from "./kv-helpers";
import { getCanonicalSetting, type UserSetting } from "./canon";

interface Env {
  DB: D1Database;
  SETTINGS_KV: KVNamespace;
}

const STALENESS_THRESHOLD_VERSIONS = 0; // any version behind D1 triggers repair

export async function getUserSettingWithRepair(
  userId: string,
  env: Env,
  ctx: ExecutionContext,
): Promise<UserSetting> {
  const key = `user-settings:${userId}`;
  const { value: kvValue, version: kvVersion } = await kvGetVersioned<UserSetting>(
    env.SETTINGS_KV,
    key,
  );

  // Fast path: KV hit with version — validate against D1 version lazily
  if (kvValue) {
    // Async repair: read D1 version (cheap query) and patch KV if needed
    ctx.waitUntil(repairIfStale(userId, kvVersion, env));
    return kvValue.data;
  }

  // KV miss — must read D1 synchronously
  const canonical = await getCanonicalSetting(env.DB, userId);
  if (!canonical) {
    throw new Error(`User settings not found: ${userId}`);
  }

  // Write to KV so future requests are faster
  ctx.waitUntil(
    kvPutVersioned(env.SETTINGS_KV, key, {
      data: canonical,
      version: canonical.version,
      updatedAt: canonical.updatedAt,
      source: "d1",
    }),
  );

  return canonical;
}

async function repairIfStale(
  userId: string,
  kvVersion: number,
  env: Env,
): Promise<void> {
  const key = `user-settings:${userId}`;

  // Only read D1 version, not full row — use a projection
  const row = await env.DB
    .prepare("SELECT version, updated_at FROM user_settings WHERE user_id = ? LIMIT 1")
    .bind(userId)
    .first<{ version: number; updated_at: string }>();

  if (!row) return; // user deleted — KV will expire naturally

  const d1Version = row.version;
  if (kvVersion >= d1Version - STALENESS_THRESHOLD_VERSIONS) {
    return; // KV is fresh — no repair needed
  }

  // KV is stale — fetch full row and repair
  const canonical = await getCanonicalSetting(env.DB, userId);
  if (!canonical) return;

  await kvPutVersioned(env.SETTINGS_KV, key, {
    data: canonical,
    version: canonical.version,
    updatedAt: canonical.updatedAt,
    source: "d1",
  });

  console.log(
    JSON.stringify({
      event: "kv_read_repair",
      userId,
      stalekKvVersion: kvVersion,
      d1Version,
    }),
  );
}
```

### 5. Write path — always update D1 first, then KV

```typescript
// settings-writer.ts
export async function saveUserSetting(
  userId: string,
  patch: Partial<UserSetting>,
  env: Env,
): Promise<UserSetting> {
  // 1. Write canonical record to D1 with incremented version
  const result = await env.DB
    .prepare(`
      UPDATE user_settings
      SET theme = COALESCE(?, theme),
          locale = COALESCE(?, locale),
          version = version + 1,
          updated_at = datetime('now')
      WHERE user_id = ?
      RETURNING *
    `)
    .bind(patch.theme ?? null, patch.locale ?? null, userId)
    .first<UserSetting>();

  if (!result) throw new Error("User not found");

  // 2. Write the new value to KV immediately (best-effort, propagation is async)
  const key = `user-settings:${userId}`;
  await kvPutVersioned(env.SETTINGS_KV, key, {
    data: result,
    version: result.version,
    updatedAt: result.updatedAt,
    source: "d1",
  });

  return result;
}
```

---

## Anti-patterns

- **Doing the D1 lookup synchronously on every read** — defeats the purpose of KV
  caching. Only consult D1 in `waitUntil` or on KV misses.
- **Using wall-clock time for version comparison** — clocks skew across Workers
  instances. Use monotonically-increasing integer versions stored in the D1 row.
- **Repairing on every read regardless of staleness** — this floods D1 with reads.
  Compare KV version to D1 version first; only repair when they diverge.
- **Not logging repair events** — read repair is silent data correction; without logs
  you cannot tell how often KV is stale or whether the propagation window is widening.

---

## Gotchas

- `ctx.waitUntil` runs after the response is sent. If the Worker's CPU budget is
  exhausted before the repair finishes it may be killed. Keep repairs lightweight.
- KV metadata is updated atomically with the value but is a separate read path. If
  you write a value without setting metadata, `getWithMetadata` returns `null` for
  metadata and the version check defaults to `-1` (always stale).
- KV `put` with `expirationTtl` resets the expiry on every write. A hot key that
  is repaired frequently will never expire. Consider whether that is desirable or
  whether you should cap the version lookup frequency with its own throttle.
- Read repair increases write amplification: every stale read triggers a write. In
  the worst case (many PoPs all stale simultaneously) you generate N writes for one
  canonical update. This is acceptable for low-cardinality settings but may be too
  expensive for high-throughput counters.

---

## Verification

```bash
# Write a setting, then immediately read from a different region using a geolocation proxy
curl -X PUT https://api.example.com/settings/user-123 \
  -H "Content-Type: application/json" \
  -d '{"theme":"dark"}'

# Check repair logs (tail Workers logs)
wrangler tail --format=json | jq 'select(.message | test("kv_read_repair"))'

# Verify KV version matches D1 after repair settles (wait ~5 s)
wrangler kv get --namespace-id=<ID> "user-settings:user-123" | jq .version
```

---

## Related

- `cache-aside-kv-d1-fallback.md` — basic KV-as-cache pattern
- `stale-while-revalidate-workers-kv.md` — serving stale + async refresh
- `write-behind-cache-kv-d1.md` — asynchronous write path from KV to D1
- `anti-entropy-consistency-workers.md` — periodic full-scan repair at scale

---

## Sources

- Vogels, W. et al. "Dynamo: Amazon's Highly Available Key-value Store" (SOSP 2007)
- Cloudflare KV consistency model — developers.cloudflare.com/kv/reference/how-kv-works/
- Apache Cassandra read repair — cassandra.apache.org/doc/latest/cassandra/operating/read_repair.html
