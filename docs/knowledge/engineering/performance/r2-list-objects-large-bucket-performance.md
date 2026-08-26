# R2 List Objects Performance for Large Buckets

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker calls `env.BUCKET.list()` on an R2 bucket that has grown to 10 million objects. The
call takes 3–8 seconds, occasionally timing out. The Worker needs to paginate through all
objects for a nightly inventory job, or enumerate objects within a prefix for a directory-
listing API. Performance degrades linearly as the bucket grows.

---

## Context

R2's `list()` operation is backed by a distributed object-metadata store. Unlike S3's flat
key namespace list which is O(n) over a sorted key space, R2 list operations are bounded per
page (up to 1 000 objects per call) but each page still requires a metadata index scan for
the given prefix and cursor position. The cost of `list()` scales with:

1. **Prefix cardinality** — a broad prefix (or no prefix) scans more index shards.
2. **Object count within the prefix** — more objects means more index entries to skip through.
3. **Delimiter usage** — using `delimiter: '/'` enables a virtual directory listing that
   returns common prefixes (equivalent to sub-directories) rather than every individual key.

Strategies to improve `list()` performance focus on: narrowing the key space scanned per
call, avoiding `list()` when alternatives exist, and caching results externally.

---

## Key Naming Strategy for Listable Buckets

Key design is the most impactful lever. A flat namespace (`userId/filename`) is hard to
enumerate efficiently at scale. A time-partitioned namespace allows narrowing the scan to a
specific period:

```
# Flat (hard to enumerate efficiently at scale):
user-abc123/photo-1.jpg
user-abc123/photo-2.jpg
user-xyz789/photo-1.jpg

# Time-partitioned (good for time-range scans):
2026/08/23/user-abc123/photo-1.jpg
2026/08/23/user-xyz789/photo-1.jpg

# Reverse-chronological ULID prefix (good for "latest N" queries):
01J6XXXXXXXXXXXXXXXX/user-abc123/photo-1.jpg
```

A time-partitioned key scheme means "list all objects from today" becomes
`prefix: '2026/08/23/'` which scans only the current day's index shard rather than the
entire bucket.

---

## Basic Paginated List with Cursor

```typescript
export interface Env {
  BUCKET: R2Bucket;
}

interface ListResult {
  keys: string[];
  cursor: string | null;
  truncated: boolean;
}

export async function listPrefix(
  bucket: R2Bucket,
  prefix: string,
  limit = 1000,
): Promise<ListResult> {
  const response = await bucket.list({ prefix, limit });
  return {
    keys: response.objects.map(o => o.key),
    cursor: response.truncated ? response.cursor : null,
    truncated: response.truncated,
  };
}

// Full paginated enumeration — use only in background jobs, not hot paths
export async function* listAll(
  bucket: R2Bucket,
  prefix: string,
): AsyncGenerator<R2Object[]> {
  let cursor: string | undefined;

  do {
    const response = await bucket.list({
      prefix,
      limit: 1000,
      cursor,
    });

    yield response.objects;
    cursor = response.truncated ? response.cursor : undefined;
  } while (cursor !== undefined);
}

// Usage in a Cron Trigger Worker
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    let objectCount = 0;
    for await (const batch of listAll(env.BUCKET, '2026/08/')) {
      objectCount += batch.length;
      // Process batch without loading all objects into memory simultaneously
    }
    console.log(`Total objects in August 2026: ${objectCount}`);
  },
};
```

---

## Directory-Style Listing with Delimiter

Using `delimiter: '/'` returns only the immediate "children" of a prefix — individual object
keys at that level plus common prefix strings representing sub-"directories". This is
dramatically faster than listing all objects recursively for deep namespace trees.

```typescript
export async function listDirectory(
  bucket: R2Bucket,
  prefix: string,  // e.g. 'users/abc123/'
): Promise<{ files: string[]; subdirectories: string[] }> {
  const response = await bucket.list({
    prefix,
    delimiter: '/',
    limit: 1000,
  });

  return {
    // Actual object keys at this level (files)
    files: response.objects.map(o => o.key),
    // Common prefixes — virtual subdirectories
    subdirectories: response.delimitedPrefixes,
  };
}

// Example: listing 'users/abc123/' in a bucket with keys:
// users/abc123/avatar.jpg
// users/abc123/docs/report.pdf
// users/abc123/docs/invoice.pdf
//
// Returns:
// { files: ['users/abc123/avatar.jpg'], subdirectories: ['users/abc123/docs/'] }
// Not: ['users/abc123/docs/report.pdf', 'users/abc123/docs/invoice.pdf']
```

---

## HEAD Instead of LIST for Existence Checks

The most common misuse of `list()` is checking whether a specific object exists:

```typescript
// WRONG — lists up to 1000 objects to find one
const { objects } = await env.BUCKET.list({ prefix: key, limit: 1 });
const exists = objects.some(o => o.key === key);

// RIGHT — O(1) HEAD request, returns null if not found
const object = await env.BUCKET.head(key);
const exists = object !== null;
```

`R2Bucket.head(key)` returns `R2Object | null` in constant time, reading only the metadata
entry for the exact key. Always prefer `head()` over `list()` for point lookups.

---

## Caching List Results in KV

For listing workloads that are read frequently but written infrequently (e.g. an asset
directory for a static site generator), cache the `list()` results in KV:

```typescript
const CACHE_TTL = 300; // 5 minutes

export async function cachedListDirectory(
  bucket: R2Bucket,
  kv: KVNamespace,
  prefix: string,
): Promise<string[]> {
  const cacheKey = `dir-listing:${prefix}`;

  // Try KV first
  const cached = await kv.get<string[]>(cacheKey, 'json');
  if (cached !== null) return cached;

  // Fall back to R2 list
  const result = await bucket.list({ prefix, delimiter: '/' });
  const keys = result.objects.map(o => o.key);

  // Cache with expiration
  await kv.put(cacheKey, JSON.stringify(keys), { expirationTtl: CACHE_TTL });

  return keys;
}

// Invalidate the cache when objects are written or deleted
export async function putObjectAndInvalidate(
  bucket: R2Bucket,
  kv: KVNamespace,
  key: string,
  body: ReadableStream | ArrayBuffer,
): Promise<void> {
  await bucket.put(key, body);

  // Derive the directory prefix from the key (e.g. 'users/abc123/photo.jpg' → 'users/abc123/')
  const prefix = key.slice(0, key.lastIndexOf('/') + 1);
  await kv.delete(`dir-listing:${prefix}`);
}
```

---

## Parallel Prefix Sharding for Inventory Jobs

When a full bucket inventory is required, shard the namespace by a known prefix space and
scan shards in parallel using `Promise.all` or a Durable Object worker pool:

```typescript
// Assumes keys are sharded by first two hex chars of a hash (0-f × 0-f = 256 shards)
const HEX_CHARS = '0123456789abcdef';

export async function parallelInventory(bucket: R2Bucket): Promise<number> {
  const shards = HEX_CHARS.split('').flatMap(a =>
    HEX_CHARS.split('').map(b => `${a}${b}/`),
  );

  // Process in batches of 16 to avoid overwhelming the R2 metadata service
  let total = 0;
  for (let i = 0; i < shards.length; i += 16) {
    const batch = shards.slice(i, i + 16);
    const counts = await Promise.all(
      batch.map(async shard => {
        let count = 0;
        for await (const objects of listAll(bucket, shard)) {
          count += objects.length;
        }
        return count;
      }),
    );
    total += counts.reduce((a, b) => a + b, 0);
  }

  return total;
}
```

---

## R2 List Limits Reference

| Parameter | Limit |
|---|---|
| Max objects per `list()` call | 1 000 |
| Max prefix length | 1 024 bytes |
| Max key length | 1 024 bytes |
| `delimiter` value | Single character (typically `/`) |
| Include custom metadata in list | Via `include: ['customMetadata']` |
| Include HTTP metadata in list | Via `include: ['httpMetadata']` |

Requesting `include: ['customMetadata', 'httpMetadata']` in `list()` returns richer objects
but is marginally slower (more data per page). Omit the `include` option when only keys are
needed.

---

## Anti-patterns

**Calling `list()` on the hot request path.** Every HTTP request that calls `list()` to build
a response body adds 50–500 ms of latency. Cache the listing in KV or compute it in a Cron
Trigger and store the result.

**No prefix on a large bucket.** `bucket.list()` with no `prefix` scans the entire key space.
On a 10-million-object bucket this is extremely slow and approaches the 30 s Worker wall-
clock limit before the first page returns for very large buckets.

**Fetching object bodies during list.** `list()` returns metadata only (key, size, etag, last
modified). Never call `bucket.get(key)` inside a list loop unless the body is genuinely
needed for each object — use streaming or a secondary Worker to process bodies asynchronously.

**Recursive listing with delimiter + follow.** Recursively following all `delimitedPrefixes`
returned by a delimiter-based list multiplies the number of `list()` calls by the depth of
the tree. For deep trees, use a full `list()` with a narrow prefix instead.

---

## Gotchas

- **Eventual consistency.** R2 list operations are eventually consistent. A freshly uploaded
  object may not appear in a `list()` response immediately. Do not rely on list for real-time
  inventory of recently written objects; use a separate metadata store (D1 or KV) for that.

- **`cursor` is opaque.** Do not attempt to parse or construct a cursor string. It encodes
  pagination state internally and may change format across R2 API versions.

- **`truncated: false` with `cursor` set.** Some older R2 SDK versions returned a cursor even
  when `truncated` was `false`. Always check `response.truncated` to determine whether to
  continue pagination, not whether `response.cursor` is defined.

- **Key sort order.** R2 lists objects in lexicographic (UTF-8 byte) order by key. Numeric
  prefixes sort alphabetically (`10/` before `9/`). Use zero-padded numbers (`09/`, `10/`) or
  ISO-8601 date strings (`2026-08-23/`) to ensure correct ordering.

---

## Verification

```typescript
// Benchmark list() latency for a given prefix
const start = performance.now();
const response = await env.BUCKET.list({ prefix: 'test/', limit: 1000 });
const duration = performance.now() - start;
console.log(`list() returned ${response.objects.length} objects in ${duration.toFixed(1)} ms`);

// Emit to Analytics Engine for trending
await env.AE.writeDataPoint({
  blobs: ['r2_list', 'test/'],
  doubles: [duration, response.objects.length],
  indexes: ['r2-list-perf'],
});
```

Target: `list()` with a narrow prefix on a well-partitioned bucket < 50 ms per page at p95.

---

## Related

- `r2-multipart-parallel-upload-throughput.md`
- `r2-range-request-large-file-optimization.md`
- `r2-conditional-get-etag-bandwidth.md`
- `cloudflare-r2-presigned-cdn-acceleration.md`
- `kv-bulk-get-batching.md`
- `workers-subrequest-fanout-parallelism.md`

---

## Sources

- Cloudflare R2 Workers API — list: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#bucket-list
- R2 data access patterns: https://developers.cloudflare.com/r2/buckets/
- R2 limits: https://developers.cloudflare.com/r2/platform/limits/
- R2 pricing: https://developers.cloudflare.com/r2/pricing/
