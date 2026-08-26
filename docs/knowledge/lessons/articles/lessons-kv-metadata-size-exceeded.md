# KV Metadata Size Exceeded — Silent put() Failure

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A cache-warming Worker wrote product listings to KV using `put()` with a large JSON blob in the `metadata` field. The `put()` call resolved without throwing, but subsequent `getWithMetadata()` calls returned `null` for those keys. Cached data appeared to be missing despite successful writes. The bug went undetected for two days because the Worker fell back to the origin on cache miss rather than alerting.

---

## Context

Cloudflare KV allows an optional `metadata` object to be attached to any key-value pair. Metadata is returned from `list()` and `getWithMetadata()` without reading the full value body, making it useful for filtering keys without paying for value reads. The Cloudflare documentation states the metadata object must be serialisable to JSON and must not exceed **1024 bytes** after serialisation. If the serialised metadata exceeds this limit, the `put()` call fails. However, in some runtime versions the failure is a rejected Promise that, if not awaited with proper error handling, is silently swallowed.

---

## Root Cause

```typescript
// BAD — large JSON blob stored in metadata
interface ProductMeta {
  id: string;
  title: string;
  description: string; // can be 800+ chars
  tags: string[];       // can be 20+ tags
  variants: { sku: string; price: number; stock: number }[]; // many variants
  updatedAt: string;
}

export async function cacheProduct(
  kv: KVNamespace,
  product: Product,
): Promise<void> {
  const meta: ProductMeta = {
    id: product.id,
    title: product.title,
    description: product.description, // 850 bytes alone
    tags: product.tags,
    variants: product.variants,
    updatedAt: new Date().toISOString(),
  };

  // put() may reject if JSON.stringify(meta).length > 1024
  // but if the caller does not await or catch this properly,
  // the failure is invisible.
  await kv.put(product.id, JSON.stringify(product), { metadata: meta });
  //                                                    ^^^^^^^^^^^^
  //                                           up to 3 KB here — will fail
}
```

The combined size of `description`, `tags`, and `variants` in the metadata object regularly exceeded 1024 bytes. The `put()` Promise rejected, but the caller that invoked `cacheProduct` inside a `Promise.allSettled()` batch discarded rejected reasons:

```typescript
// Also BAD — errors swallowed
await Promise.allSettled(products.map(p => cacheProduct(kv, p)));
// allSettled never throws; rejections are silently recorded as 'rejected'
```

---

## Fix

### 1. Move large data to the KV value body; keep metadata scalar-only

```typescript
// GOOD — metadata contains only small scalar fields
interface ProductMetaSlim {
  status: 'active' | 'archived';
  updatedAt: string; // ISO-8601, ~24 bytes
  variantCount: number;
}

export async function cacheProduct(
  kv: KVNamespace,
  product: Product,
): Promise<void> {
  const meta: ProductMetaSlim = {
    status: product.status,
    updatedAt: new Date().toISOString(),
    variantCount: product.variants.length,
  };

  assertMetadataSize(meta); // throws before the API call if too large

  await kv.put(
    product.id,
    JSON.stringify(product), // full data lives in the value body
    { metadata: meta },
  );
}
```

### 2. Add a pre-write size assertion

```typescript
const KV_METADATA_LIMIT_BYTES = 1024;

function assertMetadataSize(meta: unknown): void {
  const bytes = new TextEncoder().encode(JSON.stringify(meta)).length;
  if (bytes > KV_METADATA_LIMIT_BYTES) {
    throw new RangeError(
      `KV metadata too large: ${bytes} bytes (limit ${KV_METADATA_LIMIT_BYTES}). ` +
      'Move large fields to the value body.',
    );
  }
}
```

### 3. Never swallow put() rejections

```typescript
// GOOD — surface failures immediately
const results = await Promise.allSettled(
  products.map(p => cacheProduct(kv, p)),
);

const failures = results.filter(r => r.status === 'rejected');
if (failures.length > 0) {
  // Log to your observability pipeline; do not silently continue
  console.error('KV cache write failures:', failures.map(f => (f as PromiseRejectedResult).reason));
  throw new Error(`${failures.length} KV writes failed`);
}
```

---

## Prevention / Detection

```typescript
// Unit test: assert slim metadata stays under limit
import { describe, it, expect } from 'vitest';

describe('assertMetadataSize', () => {
  it('passes for slim metadata', () => {
    const meta = { status: 'active', updatedAt: '2026-08-24T00:00:00Z', variantCount: 3 };
    expect(() => assertMetadataSize(meta)).not.toThrow();
  });

  it('throws when metadata exceeds 1024 bytes', () => {
    const meta = { description: 'x'.repeat(1025) };
    expect(() => assertMetadataSize(meta)).toThrow(RangeError);
  });
});
```

```bash
# Integration test: verify put + getWithMetadata round-trip succeeds
wrangler dev --test-scheduled
curl -s http://localhost:8787/cache-warm | jq '.failures'
# Expected: 0
```

---

## Anti-patterns

- **Storing entire DTOs in KV metadata** — metadata is for lightweight index fields; the value body has a 25 MB limit and is the right place for rich data.
- **Using `Promise.allSettled` without inspecting rejections** — allSettled masks errors by design; always iterate results and surface failures.
- **Relying on the runtime to throw on oversized metadata** — error surfacing varies by Workers runtime version; the `assertMetadataSize` guard makes the contract explicit and testable.

---

## Gotchas

- The 1024-byte limit applies to the JSON-serialised metadata, not the raw object. A seemingly small object with long string values can exceed the limit.
- `kv.list()` returns metadata without fetching value bodies — this is the primary use-case for metadata. If you need the list to be fast, keep metadata small enough that KV's index can serve it cheaply.
- `kv.getWithMetadata()` returns `{ value: null, metadata: null }` for keys that do not exist *and* for keys whose `put()` silently failed. There is no way to distinguish the two without attempting the write again.

---

## Verification

```bash
# 1. Deploy the fixed Worker
wrangler deploy

# 2. Trigger a cache-warm run
curl -X POST https://api.example.com/admin/cache-warm

# 3. Spot-check a key
wrangler kv key get --binding=PRODUCT_CACHE <product-id>

# 4. Verify metadata is present and slim
wrangler kv key get --binding=PRODUCT_CACHE <product-id> --metadata
```

---

## Related

- `lessons-d1-migration-breaking-change-production.md`

---

## Sources

- Cloudflare KV Limits — https://developers.cloudflare.com/kv/platform/limits/
- Cloudflare KV put() Reference — https://developers.cloudflare.com/kv/api/write-key-value-pairs/
