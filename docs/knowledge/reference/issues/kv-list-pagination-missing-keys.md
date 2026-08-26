# KV `list()` Silently Returns Incomplete Results When Namespace Has More Than 1 000 Keys

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker that enumerates all keys in a KV namespace returns fewer keys than expected. The discrepancy is silent — no error is thrown and the response is a valid JSON array, just shorter than the true key count. The issue surfaces only when the namespace grows beyond 1 000 keys and the caller iterates over the result expecting a complete set.

---

## Context

Cloudflare KV's `list()` method returns at most 1 000 keys per call. When there are more keys, the response includes a `cursor` string and sets `list_complete` to `false`. Callers that ignore these fields receive only the first page and silently miss all subsequent pages. This is especially dangerous in maintenance scripts, data-export jobs, and cache-invalidation routines where a partial key list produces incorrect behavior without raising any observable error.

---

## Root Cause

The `list()` call is used without checking `list_complete` or following the `cursor`, so only the first page of up to 1 000 keys is ever returned.

```typescript
// BAD: ignores pagination — silently misses keys beyond the first 1000
import type { KVNamespace } from '@cloudflare/workers-types';

interface Env {
  MY_KV: KVNamespace;
}

export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    // list() returns at most 1000 keys; if list_complete is false,
    // remaining keys are silently dropped
    const { keys } = await env.MY_KV.list();

    const keyNames = keys.map((k) => k.name);
    return Response.json({ count: keyNames.length, keys: keyNames });
  },
};
```

## Fix

Implement a `listAll()` helper that loops until `list_complete` is `true`, passing the `cursor` from each response into the next `list()` call.

```typescript
// GOOD: paginated listAll() — returns every key regardless of namespace size
import type { KVNamespace, KVNamespaceListKey, KVNamespaceListResult } from '@cloudflare/workers-types';

interface Env {
  MY_KV: KVNamespace;
}

/**
 * Exhaustively list all keys in a KV namespace by following pagination cursors.
 *
 * @param kv       - The KV namespace binding.
 * @param prefix   - Optional key prefix to filter by.
 * @param limit    - Page size per request (max 1000, default 1000).
 * @returns        All matching keys across all pages.
 */
async function listAll(
  kv: KVNamespace,
  prefix?: string,
  limit = 1000,
): Promise<KVNamespaceListKey<unknown>[]> {
  const allKeys: KVNamespaceListKey<unknown>[] = [];
  let cursor: string | undefined = undefined;
  let pageCount = 0;
  const MAX_PAGES = 10_000; // Safety cap: 10M keys max

  do {
    const page: KVNamespaceListResult<unknown> = await kv.list({
      prefix,
      limit,
      cursor,
    });

    allKeys.push(...page.keys);
    cursor = page.list_complete ? undefined : (page as { cursor?: string }).cursor;
    pageCount += 1;

    if (pageCount >= MAX_PAGES) {
      console.warn(`listAll() hit MAX_PAGES cap (${MAX_PAGES}); some keys may be missing`);
      break;
    }
  } while (cursor !== undefined);

  return allKeys;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const prefix = url.searchParams.get('prefix') ?? undefined;

    const keys = await listAll(env.MY_KV, prefix);

    return Response.json({
      count: keys.length,
      keys: keys.map((k) => ({
        name: k.name,
        expiration: k.expiration,
        metadata: k.metadata,
      })),
    });
  },
};
```

For very large namespaces (millions of keys) listing all keys in a single Worker request will exceed the CPU time limit. In that case, push pages onto a Queue and aggregate asynchronously:

```typescript
// Stream pages onto a Queue for large-namespace enumeration
async function enqueueAllKeys(
  kv: KVNamespace,
  queue: Queue<{ keys: string[] }>,
  prefix?: string,
): Promise<number> {
  let cursor: string | undefined = undefined;
  let total = 0;

  do {
    const page = await kv.list({ prefix, limit: 1000, cursor });
    const keyNames = page.keys.map((k) => k.name);
    await queue.send({ keys: keyNames });
    total += keyNames.length;
    cursor = page.list_complete ? undefined : (page as { cursor?: string }).cursor;
  } while (cursor !== undefined);

  return total;
}
```

## Verification

```typescript
// Unit test: seed >1000 keys in a mock KV, assert listAll returns all of them
import { describe, it, expect, vi } from 'vitest';

// Minimal mock KV that pages at `pageSize` keys
function makeMockKV(totalKeys: number, pageSize = 1000) {
  const allKeys = Array.from({ length: totalKeys }, (_, i) => ({
    name: `key-${String(i).padStart(6, '0')}`,
  }));

  return {
    async list({ cursor, limit = pageSize }: { cursor?: string; limit?: number } = {}) {
      const offset = cursor ? parseInt(cursor, 10) : 0;
      const page = allKeys.slice(offset, offset + limit);
      const nextOffset = offset + limit;
      const list_complete = nextOffset >= totalKeys;
      return {
        keys: page,
        list_complete,
        cursor: list_complete ? undefined : String(nextOffset),
      };
    },
  };
}

describe('listAll', () => {
  it('returns all keys when namespace has exactly 1000 keys', async () => {
    const kv = makeMockKV(1000) as unknown as KVNamespace;
    const keys = await listAll(kv);
    expect(keys).toHaveLength(1000);
  });

  it('returns all keys when namespace has 1001 keys (crosses page boundary)', async () => {
    const kv = makeMockKV(1001) as unknown as KVNamespace;
    const keys = await listAll(kv);
    expect(keys).toHaveLength(1001);
  });

  it('returns all keys when namespace has 5432 keys', async () => {
    const kv = makeMockKV(5432) as unknown as KVNamespace;
    const keys = await listAll(kv);
    expect(keys).toHaveLength(5432);
  });

  it('returns filtered keys when prefix is specified', async () => {
    // Mock that only returns keys matching the prefix
    const kv = makeMockKV(100) as unknown as KVNamespace;
    const spy = vi.spyOn(kv, 'list');
    await listAll(kv, 'key-000');
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ prefix: 'key-000' }));
  });
});
```

```bash
# Run the tests
npm test -- --reporter=verbose kv-list

# Check actual key count in a remote namespace via wrangler
npx wrangler kv key list --binding MY_KV --remote | jq length
# If this returns exactly 1000 and you know there are more, pagination is broken

# Manually inspect pagination with curl (Workers KV REST API)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces/$NAMESPACE_ID/keys?limit=1000" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '{result_info, count: (.result | length)}'
# result_info.cursor will be present if list_complete is false
```

---

## Anti-patterns

- **Using `kv.list()` directly in application code without a pagination wrapper** — Any caller that does not check `list_complete` will silently return a partial result the moment the namespace exceeds 1 000 keys. Always wrap `list()` in a helper like `listAll()`.
- **Assuming a 1 000-key result means the namespace has exactly 1 000 keys** — The API returns up to 1 000 keys; a full page does not mean the listing is complete. Check `list_complete` explicitly.
- **Listing all keys in a latency-sensitive request handler** — Each `list()` page is a separate network call. Listing millions of keys blocks the Worker for seconds. Offload large enumerations to scheduled cron handlers or Queue consumers.
- **Not specifying a `prefix`** — Without a prefix, `listAll()` returns every key in the namespace. Prefer storing keys with a structured prefix hierarchy (`user:{id}:session:{id}`) and listing only the relevant subtree.

---

## Gotchas

- The `cursor` field is only present on the response object when `list_complete` is `false`. Attempting to access `page.cursor` when `list_complete` is `true` returns `undefined` and must be handled. The TypeScript types do not always reflect this accurately — cast to `{ cursor?: string }` if needed.
- Key order in `list()` results is lexicographic by key name, not insertion order. Do not rely on order for business logic unless you prefix keys with a sortable timestamp.
- KV `list()` has eventual consistency. A key written in the same request may not appear in a subsequent `list()` call. For strong consistency, use D1 or Durable Object storage.
- The `limit` parameter accepts values from 1 to 1000. Passing a value above 1000 results in an error, not a silent truncation.
- KV `list()` charges one read operation per page. A namespace with 50 000 keys costs 50 read operations per full enumeration. Factor this into rate-limit and cost calculations.

---

## Related

- `d1-query-timeout-full-table-scan.md`
- `workers-503-service-unavailable-subrequest-limit.md`

---

## Sources

- Cloudflare KV list() reference — https://developers.cloudflare.com/kv/api/list-keys/
- Cloudflare KV limits — https://developers.cloudflare.com/kv/platform/limits/
- Workers KV REST API — https://developers.cloudflare.com/api/resources/kv/subresources/namespaces/subresources/keys/methods/list/
