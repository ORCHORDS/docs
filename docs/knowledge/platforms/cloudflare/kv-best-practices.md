# kv-best-practices

**Issue:** KV best practices — keys, TTL, consistency
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write to KV. The next read returns the old value.
You write again. The next read still returns the old
value. You wonder if KV is broken.

## Root cause
**KV is eventually consistent.** Writes propagate async.

**Source:** CF KV docs.

## The "KV consistency" pattern

For KV consistency:
- **Reads:** Eventually consistent (60s globally)
- **Writes:** Eventually consistent (60s)
- **First read after write:** May return old

```ts
// Write
await env.KV!.put('key', 'value');

// Read (may return old)
const value = await env.KV!.get('key');
```

The read is eventually consistent.

## The "KV use cases" pattern

For KV use cases:
- **Read-heavy:** KV is great
- **Write-heavy:** D1 is better
- **Strongly consistent:** D1, not KV
- **Cache:** KV is good

KV is for read-heavy + eventually consistent.

## The "KV keys" pattern

For keys:
- **Hierarchical:** `tenant:user:123`
- **No PII:** In the key
- **Bounded length:** < 512 bytes

```ts
const key = `tenant:${tenantId}:user:${userId}`;
```

The key is structured.

## The "KV TTL" pattern

For TTL:
- **Set:** `expirationTtl` (in seconds)
- **Max:** 7 days for free, 30 days for paid
- **Default:** No expiration

```ts
await env.KV!.put('key', 'value', { expirationTtl: 86400 });  // 1 day
```

The TTL is set.

## The "KV metadata" pattern

For metadata:
```ts
await env.KV!.put('key', 'value', {
  metadata: { version: 1, source: 'web' },
});

const { value, metadata } = await env.KV!.getWithMetadata('key');
```

The metadata is stored.

## The "KV list" pattern

For list:
```ts
const list = await env.KV!.list({ prefix: 'tenant:t_1:' });
for (const key of list.keys) {
  console.log(key.name);
}
```

The keys are listed.

## The "KV bulk" pattern

For bulk:
```ts
await env.KV!.put('a', '1');
await env.KV!.put('b', '2');
await env.KV!.put('c', '3');
```

The puts are sequential (no bulk API in KV).

## The "KV cache" pattern

For a read-through cache:
```ts
async function getCached<T>(key: string, ttl: number, fetcher: () => Promise<T>): Promise<T> {
  const cached = await env.KV!.get<T>(key, 'json');
  if (cached) return cached;

  const fresh = await fetcher();
  await env.KV!.put(key, JSON.stringify(fresh), { expirationTtl: ttl });
  return fresh;
}
```

The cache is read-through.

## The "KV + D1" pattern

For KV + D1:
- **D1:** Source of truth
- **KV:** Cache

```ts
async function getUser(id: string, env: Env): Promise<User | null> {
  // 1. Check KV
  const cached = await env.KV!.get<User>(`user:${id}`, 'json');
  if (cached) return cached;

  // 2. Check D1
  const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
  if (!user) return null;

  // 3. Cache
  await env.KV!.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });
  return user;
}
```

The cache is layered.

## The "KV observability" pattern

For observability:
- **Read count:** Per minute
- **Write count:** Per minute
- **Storage:** Total bytes
- **Hit rate:** Cache hit / miss

The metrics are in the CF dashboard.

## The "KV cost" pattern

For cost:
- **Reads:** $0.50/M
- **Writes:** $5/M
- **Storage:** $0.50/GB/mo
- **Delete:** $0 (free)

For high-read apps, KV is cost-effective.

## The "KV anti-pattern" anti-patterns

### 1. Strongly consistent reads
- **Issue:** KV is eventually consistent
- **Fix:** Use D1

### 2. PII in key
- **Issue:** GDPR violation
- **Fix:** Use a hash

### 3. TTL too long
- **Issue:** Max 30 days
- **Fix:** Refresh or use D1

### 4. Large values
- **Issue:** Max 25MB per value
- **Fix:** Split or use R2

### 5. Many writes
- **Issue:** Cost + propagation
- **Fix:** Use D1

## Verification
- **Test:** Reads work
- **Test:** TTL works
- **Test:** Cache works
- **Live:** KV metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "strong consistency" anti-pattern.** Use D1.
- **The "PII in key" anti-pattern.** Hash.
- **The "long TTL" anti-pattern.** Refresh or D1.

## Related
- `cloudflare/kv-eventually-consistent.md`
- `cloudflare/workers-cache-api.md`
- `feature-cookbook-caching-strategies.md`
- CF KV: https://developers.cloudflare.com/kv/
