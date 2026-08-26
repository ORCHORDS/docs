# Bridge Pattern — Workers Storage Backend Abstraction

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker persists data to KV for caching, D1 for relational reads, and R2 for large
blobs. The high-level "repository" layer (what does the data mean?) keeps getting
tangled with the low-level "driver" layer (which Cloudflare binding do I call?). When
you need to add R2 tiering or swap D1 for Hyperdrive you find yourself editing business
logic files. The Bridge pattern decouples the two hierarchies so the abstraction and
the implementation can vary independently.

## Context

The Bridge pattern holds a reference to an implementor interface inside an abstraction
class; subclasses of the abstraction refine the high-level behaviour while concrete
implementors swap the low-level mechanism. In a Worker this maps to:

- **Abstraction** — `BlobStore` (semantic: put/get/delete named blobs with metadata)
- **Implementors** — `KvDriver`, `R2Driver`, `D1BlobDriver` (each uses a different
  binding and encodes/decodes data differently)
- **Refined abstractions** — `CachingBlobStore` (adds a KV read-through cache in front
  of any implementor), `AuditedBlobStore` (logs every write to a queue)

Neither the refined abstractions nor the business logic ever import the concrete drivers
directly; the only coupling is the `StorageDriver` interface.

## Implementor Interface

```typescript
// storage/driver.ts
export interface StorageDriver {
  get(key: string): Promise<ArrayBuffer | null>;
  put(key: string, value: ArrayBuffer, meta?: Record<string, string>): Promise<void>;
  delete(key: string): Promise<void>;
  list(prefix: string): Promise<string[]>;
}
```

## Concrete Implementors

```typescript
// storage/kv-driver.ts
import type { StorageDriver } from './driver';

export class KvDriver implements StorageDriver {
  constructor(private readonly ns: KVNamespace) {}

  async get(key: string): Promise<ArrayBuffer | null> {
    return this.ns.get(key, 'arrayBuffer');
  }
  async put(key: string, value: ArrayBuffer, meta?: Record<string, string>): Promise<void> {
    await this.ns.put(key, value, { metadata: meta });
  }
  async delete(key: string): Promise<void> {
    await this.ns.delete(key);
  }
  async list(prefix: string): Promise<string[]> {
    const { keys } = await this.ns.list({ prefix });
    return keys.map(k => k.name);
  }
}

// storage/r2-driver.ts
import type { StorageDriver } from './driver';

export class R2Driver implements StorageDriver {
  constructor(private readonly bucket: R2Bucket) {}

  async get(key: string): Promise<ArrayBuffer | null> {
    const obj = await this.bucket.get(key);
    return obj ? obj.arrayBuffer() : null;
  }
  async put(key: string, value: ArrayBuffer, meta?: Record<string, string>): Promise<void> {
    await this.bucket.put(key, value, {
      customMetadata: meta,
    });
  }
  async delete(key: string): Promise<void> {
    await this.bucket.delete(key);
  }
  async list(prefix: string): Promise<string[]> {
    const { objects } = await this.bucket.list({ prefix });
    return objects.map(o => o.key);
  }
}
```

## Abstraction Layer

```typescript
// storage/blob-store.ts
import type { StorageDriver } from './driver';

export interface BlobMeta {
  contentType: string;

}

export class BlobStore {
  constructor(protected readonly driver: StorageDriver) {}

  async fetch(key: string): Promise<ArrayBuffer | null> {
    return this.driver.get(key);
  }

  async store(key: string, data: ArrayBuffer, meta: BlobMeta): Promise<void> {
    await this.driver.put(key, data, meta as Record<string, string>);
  }

  async remove(key: string): Promise<void> {
    await this.driver.delete(key);
  }

  async keys(prefix: string): Promise<string[]> {
    return this.driver.list(prefix);
  }
}
```

## Refined Abstractions

```typescript
// storage/caching-blob-store.ts
import { BlobStore, type BlobMeta } from './blob-store';
import type { StorageDriver } from './driver';
import { KvDriver } from './kv-driver';

/**
 * Wraps any driver with a KV read-through cache.
 * Hot reads hit KV; misses fall through to the primary driver and backfill.
 */
export class CachingBlobStore extends BlobStore {
  private readonly cache: KvDriver;

  constructor(primary: StorageDriver, cacheNs: KVNamespace) {
    super(primary);
    this.cache = new KvDriver(cacheNs);
  }

  async fetch(key: string): Promise<ArrayBuffer | null> {
    const cached = await this.cache.get(key);
    if (cached) return cached;

    const value = await this.driver.get(key);
    if (value) {
      // Backfill with a 5-minute TTL; fire-and-forget
      this.cache.put(key, value).catch(() => {});
    }
    return value;
  }

  async store(key: string, data: ArrayBuffer, meta: BlobMeta): Promise<void> {
    await this.driver.put(key, data, meta as Record<string, string>);
    // Invalidate cache on write
    await this.cache.delete(key);
  }
}

// storage/audited-blob-store.ts
import { BlobStore, type BlobMeta } from './blob-store';
import type { StorageDriver } from './driver';

export class AuditedBlobStore extends BlobStore {
  constructor(driver: StorageDriver, private readonly queue: Queue<unknown>) {
    super(driver);
  }

  async store(key: string, data: ArrayBuffer, meta: BlobMeta): Promise<void> {
    await super.store(key, data, meta);
    await this.queue.send({ event: 'blob.stored', key, size: data.byteLength, ts: Date.now() });
  }

  async remove(key: string): Promise<void> {
    await super.remove(key);
    await this.queue.send({ event: 'blob.deleted', key, ts: Date.now() });
  }
}
```

## Worker Entry Point

Business logic only sees `BlobStore`; the concrete driver is wired at startup.

```typescript
// worker.ts
import { R2Driver }          from './storage/r2-driver';
import { KvDriver }          from './storage/kv-driver';
import { CachingBlobStore }  from './storage/caching-blob-store';
import { AuditedBlobStore }  from './storage/audited-blob-store';

export interface Env {
  ASSETS:      R2Bucket;
  ASSET_CACHE: KVNamespace;
  AUDIT_QUEUE: Queue<unknown>;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const primaryDriver = new R2Driver(env.ASSETS);
    const withCache     = new CachingBlobStore(primaryDriver, env.ASSET_CACHE);
    const store         = new AuditedBlobStore(withCache['driver'], env.AUDIT_QUEUE);
    // ^ For chained refinements, pass the inner abstraction's driver through.
    // Or compose differently: AuditedBlobStore(primaryDriver) inside CachingBlobStore.

    const url  = new URL(req.url);
    const key  = url.pathname.slice(1); // strip leading "/"

    if (req.method === 'GET') {
      const data = await withCache.fetch(key);
      if (!data) return new Response('Not found', { status: 404 });
      return new Response(data);
    }

    if (req.method === 'PUT') {
      const body = await req.arrayBuffer();
      await store.store(key, body, {
        contentType: req.headers.get('content-type') ?? 'application/octet-stream',
      });
      return new Response(null, { status: 204 });
    }

    return new Response('Method not allowed', { status: 405 });
  },
};
```

## Anti-patterns

- **Merging the two hierarchies** — Adding a `CachingR2Store` concrete class that
  extends `R2Driver` (instead of extending `BlobStore` and holding a driver) re-couples
  the two axes. Always put caching logic in a refined abstraction, not a concrete driver.
- **Leaking driver types** — Returning `R2ObjectBody` or `KVNamespaceGetOptions` from
  the abstraction layer means callers depend on the implementor. Every method on
  `BlobStore` should speak in terms of `ArrayBuffer`, `string`, or domain types.
- **One class per combination** — Without Bridge you'd end up with `CachingKvStore`,
  `CachingR2Store`, `AuditedKvStore`, `AuditedR2Store` — combinatorial explosion.

## Gotchas

- R2's `list()` returns at most 1,000 keys per call and requires pagination for larger
  buckets. The `R2Driver.list()` above is simplified; add a `truncated`/`cursor` loop
  for production.
- KV `get` with `'arrayBuffer'` returns `null` on a miss, not an empty buffer. Guard
  downstream with `if (cached)`, never `if (cached.byteLength > 0)`.
- `CachingBlobStore` fires the KV backfill as fire-and-forget (`catch(() => {})`). If
  the Worker's CPU limit is reached before the microtask resolves, the write is dropped.
  For critical paths, `await` the backfill and accept the latency.

## Verification

```typescript
// test/blob-store.test.ts
import { BlobStore } from '../storage/blob-store';

class MemoryDriver {
  private store = new Map<string, ArrayBuffer>();
  async get(k: string) { return this.store.get(k) ?? null; }
  async put(k: string, v: ArrayBuffer) { this.store.set(k, v); }
  async delete(k: string) { this.store.delete(k); }
  async list(prefix: string) { return [...this.store.keys()].filter(k => k.startsWith(prefix)); }
}

const driver = new MemoryDriver();
const store  = new BlobStore(driver);
const data   = new TextEncoder().encode('hello').buffer;

await store.store('greet/en', data, { contentType: 'text/plain' });
const fetched = await store.fetch('greet/en');
console.assert(fetched !== null);
console.assert(new TextDecoder().decode(fetched!) === 'hello');
```

## Related

- `abstract-factory-pattern-workers-provider-switching.md` — factory-based provider
  selection (complementary to Bridge for multi-family switching)
- `cache-aside-kv-d1-fallback.md` — KV-as-cache without the abstraction layer
- `repository-pattern.md` — similar separation of domain logic from persistence

## Sources

- GoF *Design Patterns* (1994) — Bridge, pp. 151–161
- Cloudflare R2 API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare KV API: https://developers.cloudflare.com/kv/api/
- Cloudflare Queues: https://developers.cloudflare.com/queues/reference/javascript-apis/
