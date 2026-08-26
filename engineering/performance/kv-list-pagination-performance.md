# KV List Operation Pagination Performance in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers script walks all keys in a KV namespace to build a sitemap, purge expired entries, or produce an admin inventory. A single `namespace.list()` call returns at most 1,000 keys. With 50,000 keys the script iterates 50 pages, each costing a subrequest. At 50 subrequests against the 1,000-subrequest-per-request limit, and each `list()` taking 10–40 ms, the total walk takes 500–2,000 ms — or the script hits the CPU time limit before finishing.

## Context

`KVNamespace.list()` returns up to 1,000 keys per call and a `list_complete` boolean plus a `cursor` for the next page. Each page costs one subrequest. Workers have a hard limit of 1,000 subrequests per request and a 30-second wall-clock limit (50 ms CPU on the free plan, 30 s on Paid). Large namespace walks must use prefix filtering, parallel partial scans, and Queue-based chunking to stay within these bounds.

---

## Basic Cursor Pagination

```typescript
async function* listAllKeys(
  namespace: KVNamespace,
  prefix?: string
): AsyncGenerator<KVNamespace.Key[]> {
  let cursor: string | undefined;

  do {
    const page = await namespace.list({ prefix, cursor, limit: 1000 });
    yield page.keys;
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
}

// Usage:
for await (const batch of listAllKeys(env.MY_KV, 'user:')) {
  for (const key of batch) {
    console.log(key.name, key.expiration, key.metadata);
  }
}
```

## Limiting Scan Depth to Avoid Subrequest Exhaustion

Track pages and abort with a partial result when approaching the subrequest ceiling.

```typescript
interface ScanResult {
  keys: KVNamespace.Key[];
  cursor: string | null;
  pagesScanned: number;
}

async function scanNamespace(
  namespace: KVNamespace,
  opts: { prefix?: string; maxPages?: number; cursor?: string }
): Promise<ScanResult> {
  const maxPages = opts.maxPages ?? 10; // default: scan at most 10,000 keys
  const allKeys: KVNamespace.Key[] = [];
  let cursor = opts.cursor;
  let pagesScanned = 0;

  while (pagesScanned < maxPages) {
    const page = await namespace.list({
      prefix: opts.prefix,
      cursor,
      limit: 1000,
    });
    allKeys.push(...page.keys);
    pagesScanned++;

    if (page.list_complete) {
      return { keys: allKeys, cursor: null, pagesScanned };
    }
    cursor = page.cursor;
  }

  // Return partial results with a cursor so the next invocation continues
  return { keys: allKeys, cursor: cursor ?? null, pagesScanned };
}
```

## Queue-based Chunked Walk for Large Namespaces

Offload multi-page scans to Queues so each Worker invocation handles one page.

```typescript
// Producer: enqueue the first scan job
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await env.KV_WALK_QUEUE.send({ prefix: 'user:', cursor: null });
  },
};

// Consumer: process one page per Queue message
export const kvWalkConsumer: ExportedHandlerQueueHandler<Env, { prefix: string; cursor: string | null }> = {
  async queue(batch, env) {
    for (const msg of batch.messages) {
      const { prefix, cursor } = msg.body;
      const page = await env.MY_KV.list({
        prefix,
        cursor: cursor ?? undefined,
        limit: 1000,
      });

      // Process this page
      await processKeys(page.keys, env);

      if (!page.list_complete) {
        // Enqueue next page
        await env.KV_WALK_QUEUE.send({ prefix, cursor: page.cursor });
      }
      msg.ack();
    }
  },
};
```

## Parallel Prefix Scanning for Sharded Namespaces

If keys are sharded by a known prefix (e.g., first character of a UUID), scan prefixes in parallel to cut wall-clock time.

```typescript
const HEX_CHARS = '0123456789abcdef';

async function parallelPrefixScan(namespace: KVNamespace): Promise<KVNamespace.Key[]> {
  // Scan all 16 hex prefixes in parallel (fan-out of 16 subrequests in one batch)
  const pages = await Promise.all(
    HEX_CHARS.split('').map(char =>
      namespace.list({ prefix: char, limit: 1000 })
    )
  );

  // If any prefix has >1000 keys, fall back to cursor pagination for that prefix
  const overflow = pages
    .map((page, i) => (!page.list_complete ? HEX_CHARS[i] : null))
    .filter(Boolean) as string[];

  const extra = await Promise.all(
    overflow.map(prefix => collectAllKeys(namespace, prefix))
  );

  return [
    ...pages.flatMap(p => p.keys),
    ...extra.flat(),
  ];
}

async function collectAllKeys(namespace: KVNamespace, prefix: string): Promise<KVNamespace.Key[]> {
  const all: KVNamespace.Key[] = [];
  let cursor: string | undefined;
  do {
    const page = await namespace.list({ prefix, cursor, limit: 1000 });
    all.push(...page.keys);
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return all;
}
```

## Using Metadata to Avoid Extra Gets

Store expiration or type information in key metadata at write time so `list()` results are self-contained — no follow-up `get()` per key needed.

```typescript
// Write with metadata
await env.MY_KV.put('user:42', JSON.stringify(userData), {
  expirationTtl: 86400,
  metadata: {
    userId: 42,
    tier: 'pro',
    updatedAt: Date.now(),
  },
});

// List with metadata — no get() calls needed
const page = await env.MY_KV.list({ prefix: 'user:', limit: 1000 });
const proUsers = page.keys.filter(
  k => (k.metadata as { tier: string })?.tier === 'pro'
);
// proUsers is ready without any additional subrequests
```

## Counting Keys Without Fetching Values

Use `list()` to count or sample keys without retrieving values, which is far cheaper than `get()` for membership checks.

```typescript
async function countKeysWithPrefix(
  namespace: KVNamespace,
  prefix: string
): Promise<number> {
  let count = 0;
  let cursor: string | undefined;
  do {
    const page = await namespace.list({ prefix, limit: 1000, cursor });
    count += page.keys.length;
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return count;
}
```

---

## Anti-patterns

- **Calling `get()` for every key returned by `list()`**: 1,000 keys → 1,001 subrequests (1 list + 1,000 gets). Store needed data in key metadata at write time.
- **Walking an unbounded namespace in a single `fetch()` handler**: A 100,000-key namespace needs 100 pages = 100 subrequests plus processing time. Use Queues or Cron Triggers with state stored in another KV key.
- **Not persisting the cursor**: If the walk is interrupted (CPU limit, error), a cursor-less restart rescans from the beginning. Always checkpoint the cursor in KV or a Durable Object.
- **Using `list()` for key existence checks**: `get()` is cheaper for single key lookups. `list()` is for bulk enumeration.
- **Assuming `list()` order is insertion order**: KV lists keys in lexicographic order by key name, not insertion time. Design key names accordingly if ordered iteration matters.

---

## Gotchas

- `list({ limit: 1000 })` is the maximum per call. Requesting more silently caps at 1,000.
- The `cursor` string is opaque and version-specific. Never parse or construct it manually; only pass it back to `list()`.
- `list_complete: true` does not mean the namespace has fewer than 1,000 keys — it means there are no more keys after this page for the given prefix and cursor.
- Deleted keys may still appear in `list()` results for up to 60 seconds after deletion due to KV eventual consistency.
- The `expiration` field on a key is a Unix timestamp in seconds, not a TTL offset. Compare with `Math.floor(Date.now() / 1000)`.

---

## Verification

```typescript
// Confirm cursor pagination covers all keys
let count = 0;
let cursor: string | undefined;
do {
  const page = await env.MY_KV.list({ prefix: 'test:', cursor, limit: 1000 });
  count += page.keys.length;
  cursor = page.list_complete ? undefined : page.cursor;
} while (cursor);

console.assert(count === expectedTotal, `Expected ${expectedTotal}, got ${count}`);
```

Use `wrangler kv key list --namespace-id <ID> --prefix test:` to independently verify counts from the CLI.

---

## Related

- `kv-pipeline-bulk-operations-workers.md` — batching GET/PUT via fetch pipelines
- `kv-bulk-get-batching.md` — coalescing multiple gets
- `kv-metadata-only-reads-optimization.md` — metadata-first read patterns
- `workers-queues-background-offload.md` — offloading long work to Queues

---

## Sources

- KV `list()` API reference: https://developers.cloudflare.com/kv/api/list-keys/
- KV limits (1,000 keys per list): https://developers.cloudflare.com/kv/platform/limits/
- Workers subrequest limits: https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Queues consumer docs: https://developers.cloudflare.com/queues/reference/how-queues-works/
