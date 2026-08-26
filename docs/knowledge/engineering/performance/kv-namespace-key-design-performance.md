# KV Namespace Key Design Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
KV reads that are logically related (e.g., all keys for a single user session) are scattered across the global KV ring because the key names hash to different shards, resulting in higher tail latency and no opportunity for prefix-scan optimizations. Intentional key naming strategies can improve cache locality, enable metadata-only reads, and reduce unnecessary list() scans.

## Context
Cloudflare KV is a globally distributed eventually-consistent key-value store. Keys are routed to storage nodes based on a hash of the key name, so the key naming scheme directly affects which operations are possible and how efficiently they execute. KV does not support server-side filters within a namespace beyond prefix listing, making key structure the primary API for organizing and efficiently accessing related data. Each `get()` is charged as one read operation; `list()` with a prefix is one operation returning up to 1000 keys per page. Keys can be up to 512 bytes; values up to 25 MB.

## Hierarchical Key Naming for Prefix List Scans
Use structured prefixes so related keys can be retrieved with a single `list()` instead of multiple `get()` calls.

```typescript
// Key schema: "<entity>:<id>:<attribute>"
// Examples:
//   user:u_42:profile
//   user:u_42:cart
//   user:u_42:prefs
//   session:s_99:token
//   session:s_99:meta

export class KVRepository {
  constructor(private kv: KVNamespace) {}

  // Fetch all attributes for a user in one list() + parallel get() instead of N sequential gets.
  async getAllUserKeys(userId: string): Promise<Map<string, unknown>> {
    const prefix = `user:${userId}:`;
    const listed = await this.kv.list({ prefix, limit: 20 });

    // Batch parallel gets for all discovered keys.
    const entries = await Promise.all(
      listed.keys.map(async ({ name }) => {
        const value = await this.kv.get(name, { type: "json" });
        return [name.slice(prefix.length), value] as const;
      })
    );

    return new Map(entries.filter(([, v]) => v !== null));
  }

  async setUserAttribute(userId: string, attr: string, value: unknown): Promise<void> {
    await this.kv.put(`user:${userId}:${attr}`, JSON.stringify(value));
  }
}
```

## Using Metadata to Avoid Full Value Reads
Store lightweight lookup data in metadata so callers that only need a summary can skip the value read entirely.

```typescript
interface ProductMeta {
  price: number;
  inStock: boolean;
  updatedAt: number;
}

export async function putProduct(
  kv: KVNamespace,
  product: Product
): Promise<void> {
  const meta: ProductMeta = {
    price: product.price,
    inStock: product.inventory > 0,
    updatedAt: Date.now(),
  };

  await kv.put(`product:${product.id}`, JSON.stringify(product), {
    metadata: meta,
    expirationTtl: 86400, // 24 h
  });
}

export async function getProductPrice(
  kv: KVNamespace,
  productId: string
): Promise<number | null> {
  // getWithMetadata<null> avoids transferring the full product JSON
  // when only price is needed — metadata is returned inline with the key listing.
  const { metadata } = await kv.getWithMetadata<ProductMeta>(`product:${productId}`);
  return metadata?.price ?? null;
}

export async function listInStockProducts(kv: KVNamespace): Promise<string[]> {
  const listed = await kv.list<ProductMeta>({ prefix: "product:", limit: 1000 });
  // Filter entirely from metadata — zero value reads.
  return listed.keys
    .filter(k => k.metadata?.inStock === true)
    .map(k => k.name.replace("product:", ""));
}
```

## Key Versioning for Cache Invalidation Without Delete
Embed a version token in the key to atomically rotate to a new value without deleting the old one mid-flight.

```typescript
// src/versioned-kv.ts
const VERSION_KEY = "global:config:version";

export async function publishConfig(
  kv: KVNamespace,
  config: AppConfig
): Promise<void> {
  const version = Date.now().toString(36); // Base-36 timestamp as compact version token
  // Write the new version first, then update the pointer atomically.
  await kv.put(`config:v:${version}`, JSON.stringify(config), { expirationTtl: 3600 });
  await kv.put(VERSION_KEY, version);
}

export async function getConfig(kv: KVNamespace): Promise<AppConfig | null> {
  const version = await kv.get(VERSION_KEY);
  if (!version) return null;
  return kv.get<AppConfig>(`config:v:${version}`, { type: "json" });
}
```

Old versioned keys expire automatically via `expirationTtl` without requiring explicit delete calls, which avoids write amplification and reduces race conditions during rolling deployments.

## Key Length and Character Set Considerations
Short, predictable keys reduce serialization overhead and are easier to reason about in list() output.

```typescript
// PREFER: short, structured, URL-safe keys
const good = `sess:${sessionId}`;   // "sess:01J2KXYZ..." (~40 chars)

// AVOID: long keys with repeated namespace prefix already in the KV binding name
const bad = `my-app-production-session-store:session:${sessionId}`; // wasteful

// PREFER: URL-safe characters to avoid encoding issues in wrangler CLI output
// Allowed: letters, digits, _, -, ., ~, :
// AVOID: spaces, /, ?, #, [ in keys unless you control all read paths
```

## Anti-patterns
- Using UUIDs as top-level keys with no prefix — prevents prefix list scans entirely and makes debugging production KV state difficult.
- Embedding full JSON blobs in metadata — metadata has a 1024-byte limit; keep it to a compact summary.
- Using list() without a prefix on a namespace with millions of keys — returns keys in hash order (not insertion order), is expensive, and is quota-counted per page.
- Relying on list() for real-time sorted queries — KV list() returns keys in UTF-8 lexicographic order of the key name, not by expiration or write time.
- Creating one KV namespace per entity type rather than using key prefixes within a shared namespace — Cloudflare limits the number of KV namespaces per account.

## Gotchas
- KV list() is eventually consistent — a key written moments ago may not appear in a list() from a different edge node.
- Key expiration is approximate; KV does not guarantee deletion at exactly `expirationTtl` seconds — do not rely on it for hard time-critical invalidation.
- `getWithMetadata()` still counts as one read operation even when the value is not read; use `kv.list()` with metadata to batch metadata reads for many keys at once.
- The 1000-key limit per `list()` page requires cursor-based pagination for large namespaces.
- Keys beginning with `__` (double underscore) are reserved by Cloudflare; avoid that prefix.

## Verification
```bash
# List keys with a prefix to verify structure
wrangler kv key list --binding CONFIG_KV --prefix "user:u_42:"

# Check metadata without reading value
wrangler kv key get --binding CONFIG_KV "product:p_001" --metadata-only

# Count keys in namespace (page through to get total)
wrangler kv key list --binding CONFIG_KV --limit 1000 | jq 'length'

# Measure list() latency from a Worker
curl -w "\nTotal: %{time_total}s\n" https://your.worker.dev/admin/kv-list-bench
```

## Related
- [`kv-metadata-only-reads-optimization.md`](kv-metadata-only-reads-optimization.md)
- [`kv-bulk-get-batching.md`](kv-bulk-get-batching.md)
- [`kv-read-performance.md`](kv-read-performance.md)
- [`kv-eventual-consistency-stale-data.md`](kv-eventual-consistency-stale-data.md)
- [`kv-cache-warming-prefetch-strategy.md`](kv-cache-warming-prefetch-strategy.md)

## Sources
- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/kv/platform/limits/
- https://developers.cloudflare.com/kv/api/list-key-value-pairs/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#metadata
- https://developers.cloudflare.com/kv/platform/pricing/
