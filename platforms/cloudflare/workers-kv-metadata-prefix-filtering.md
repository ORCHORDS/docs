# Workers KV Metadata and Prefix Filtering

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to list KV keys by prefix to iterate over a logical namespace partition (e.g.,
all sessions for a user, all cache entries for a tenant), AND you want to attach
structured metadata to each key so you can filter or sort on the listing side without
fetching every value. The default KV `list()` API supports prefix filtering and metadata
reading, but the ergonomics and limits are easy to misuse at scale.

## Context

KV `list()` returns up to 1000 keys per call with an optional `prefix`, `cursor`, and
`limit` parameter. Each listed key can carry a `metadata` object (up to 1024 bytes of
JSON) that is stored cheaply alongside the key and returned in list results — without
needing to call `get()` on each key individually.

Metadata is written at `put()` time and is immutable without overwriting the key.
It is ideal for: creation timestamps, content-type tags, tenant IDs, TTL hints,
or small index fields. It is not a query engine — you cannot filter by metadata server-side;
all filtering happens client-side after listing.

Limits (as of 2026):
- Metadata max size: 1024 bytes per key
- List returns max 1000 keys per page
- `list()` operations count toward KV read limits (100k reads/day on free, unlimited on paid)

---

## 1. Writing Metadata at Put Time

```typescript
interface Env {
  SESSIONS: KVNamespace;
}

interface SessionMeta {
  userId: string;
  createdAt: number;
  role: 'admin' | 'member' | 'viewer';
  region: string;
}

export async function createSession(
  env: Env,
  sessionId: string,
  userId: string,
  role: SessionMeta['role'],
  region: string
): Promise<void> {
  const meta: SessionMeta = {
    userId,
    createdAt: Date.now(),
    role,
    region,
  };

  await env.SESSIONS.put(
    `session:${userId}:${sessionId}`,
    JSON.stringify({ token: crypto.randomUUID() }),
    {
      expirationTtl: 86400, // 24 hours
      metadata: meta,       // stored alongside key, returned in list()
    }
  );
}
```

---

## 2. Listing Keys by Prefix with Metadata

```typescript
interface ListedSession {
  key: string;
  metadata: SessionMeta | null;
  expiration?: number;
}

export async function listUserSessions(
  env: Env,
  userId: string
): Promise<ListedSession[]> {
  const prefix = `session:${userId}:`;
  const sessions: ListedSession[] = [];
  let cursor: string | undefined;

  do {
    const result = await env.SESSIONS.list<SessionMeta>({
      prefix,
      limit: 1000,
      cursor,
    });

    for (const key of result.keys) {
      sessions.push({
        key: key.name,
        metadata: key.metadata ?? null,
        expiration: key.expiration,
      });
    }

    cursor = result.list_complete ? undefined : result.cursor;
  } while (cursor);

  return sessions;
}
```

---

## 3. Client-Side Metadata Filtering

Since KV has no server-side metadata filter, apply predicates after listing. For large
namespaces this can be expensive — keep the metadata small and denormalised to reduce
iterations.

```typescript
export async function getAdminSessions(
  env: Env,
  userId: string
): Promise<ListedSession[]> {
  const all = await listUserSessions(env, userId);
  // Filter by role in client code after listing
  return all.filter(s => s.metadata?.role === 'admin');
}

export async function getRecentSessions(
  env: Env,
  userId: string,
  since: number // epoch ms
): Promise<ListedSession[]> {
  const all = await listUserSessions(env, userId);
  return all
    .filter(s => (s.metadata?.createdAt ?? 0) >= since)
    .sort((a, b) => (b.metadata?.createdAt ?? 0) - (a.metadata?.createdAt ?? 0));
}
```

---

## 4. Prefix Hierarchy for Multi-Tenant Namespacing

Use a structured key prefix scheme to partition a single KV namespace across multiple
tenants without needing separate namespaces:

```
{tenantId}:{entity}:{id}
```

```typescript
// Write a tenant asset
async function putAsset(
  env: Env,
  tenantId: string,
  assetId: string,
  data: unknown,
  contentType: string
): Promise<void> {
  await env.SESSIONS.put(
    `${tenantId}:asset:${assetId}`,
    JSON.stringify(data),
    {
      metadata: { tenantId, contentType, createdAt: Date.now() },
    }
  );
}

// List all assets for a tenant
async function listTenantAssets(env: Env, tenantId: string) {
  return listWithPrefix(env.SESSIONS, `${tenantId}:asset:`);
}

// List all keys for any entity type under a tenant
async function listTenantKeys(env: Env, tenantId: string) {
  return listWithPrefix(env.SESSIONS, `${tenantId}:`);
}

async function listWithPrefix<M>(ns: KVNamespace<string>, prefix: string) {
  const keys: KVNamespaceListKey<M>[] = [];
  let cursor: string | undefined;
  do {
    const result = await ns.list<M>({ prefix, cursor });
    keys.push(...result.keys);
    cursor = result.list_complete ? undefined : result.cursor;
  } while (cursor);
  return keys;
}
```

---

## 5. Updating Metadata Without Changing the Value

KV has no metadata-only update operation. To update metadata you must re-put the key.
Avoid a double-read round trip by caching the value in memory if it was recently fetched.

```typescript
async function promoteToAdmin(
  env: Env,
  userId: string,
  sessionId: string
): Promise<void> {
  const key = `session:${userId}:${sessionId}`;

  // Must read value to re-put it (no metadata-only patch)
  const { value, metadata } = await env.SESSIONS.getWithMetadata<SessionMeta>(key, 'json');
  if (!value || !metadata) throw new Error('Session not found');

  await env.SESSIONS.put(key, JSON.stringify(value), {
    metadata: { ...metadata, role: 'admin' },
    // Preserve expiration if needed — must re-specify it
    expirationTtl: 86400,
  });
}
```

---

## 6. Bulk Deletion by Prefix

KV has no native bulk delete. Delete all keys matching a prefix by listing then deleting
in parallel batches.

```typescript
export async function deleteUserSessions(env: Env, userId: string): Promise<number> {
  const keys = await listWithPrefix(env.SESSIONS, `session:${userId}:`);

  // Delete in parallel, chunk to stay within subrequest budget
  const CHUNK = 100;
  let deleted = 0;
  for (let i = 0; i < keys.length; i += CHUNK) {
    const chunk = keys.slice(i, i + CHUNK);
    await Promise.all(chunk.map(k => env.SESSIONS.delete(k.name)));
    deleted += chunk.length;
  }
  return deleted;
}
```

---

## Anti-Patterns

- **Using metadata as a full search index.** Metadata is returned in list results but
  there is no server-side `WHERE metadata.field = value` filter. For real filtering,
  maintain a secondary index in D1 or use a separate KV key as an index entry.
- **Storing large blobs in metadata.** The 1024-byte cap means metadata is for tiny scalar
  fields only. Large objects belong in the value.
- **Assuming `list()` is strongly consistent.** KV `list()` is eventually consistent.
  A key written seconds ago may not appear in a list call hitting a different edge node.
- **Prefix-scanning the entire namespace in a hot path.** Iterating thousands of keys in
  a request adds tens of milliseconds per 1000-key page. Pre-compute counts/indexes.

---

## Gotchas

- `list()` without a `prefix` returns all keys in insertion order with no server-side
  sort. You cannot sort keys by metadata server-side.
- When `expirationTtl` is set, `list()` returns the `expiration` epoch (seconds) on each
  key. Already-expired keys are excluded from results, but there can be a brief lag.
- Metadata is typed as `unknown` by default in the Workers types. Pass the generic type
  parameter `list<MyMeta>()` and `getWithMetadata<MyMeta>()` to get typed metadata.
- `list()` cursor pagination is forward-only; there is no reverse pagination.
- Keys are lexicographically ordered by their full name string. Structure prefix schemes
  to take advantage of this (`YYYY-MM-DD:` date prefixes sort chronologically).

---

## Verification

```bash
# Write a key with metadata
wrangler kv key put --namespace-id=<id> "session:user1:abc" '{"token":"xyz"}' \
  --metadata '{"userId":"user1","role":"admin","createdAt":1724428800000}'

# List keys with prefix and inspect metadata
wrangler kv key list --namespace-id=<id> --prefix "session:user1:"
# Expected: key names + metadata JSON in output

# Read key with metadata
wrangler kv key get --namespace-id=<id> --metadata "session:user1:abc"
```

---

## Related

- `kv-best-practices.md`
- `kv-eventually-consistent.md`
- `workers-kv-bulk-operations-list-pagination.md`
- `d1-best-practices.md`
- `cloudflare-for-saas-custom-hostnames.md`

---

## Sources

- https://developers.cloudflare.com/kv/api/list-keys/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#metadata
- https://developers.cloudflare.com/kv/platform/limits/
