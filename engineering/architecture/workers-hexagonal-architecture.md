# Hexagonal (Ports and Adapters) Architecture for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker business logic is tightly coupled to Cloudflare-specific bindings (`env.DB.prepare(...)`, `env.KV.get(...)`, `env.R2.put(...)`). Unit tests require a full Miniflare environment, D1 migrations, and KV setup. Swapping D1 for a different storage backend is a multi-file refactor. The Worker entry point is 500 lines of interleaved infrastructure and business rules.

---

## Context

Hexagonal Architecture (Alistair Cockburn, 2005) structures an application around a **domain core** that communicates with the outside world only through **ports** (interfaces) and **adapters** (implementations). The domain never imports infrastructure code directly.

In Cloudflare Workers:

- **Ports** are TypeScript interfaces (`ProductRepository`, `CachePort`, `FileStoragePort`, `ExternalServicePort`).
- **Adapters** implement those interfaces using Cloudflare bindings (`D1ProductRepository`, `KVCacheAdapter`, `R2FileAdapter`, `ServiceBindingAdapter`).
- **Dependency injection** happens in the Worker entry point (`worker.ts`) which wires adapters into the domain service.
- **In-memory adapters** (`InMemoryProductRepository`, etc.) allow pure unit tests with zero infrastructure.

---

## Solution

```typescript
// ============================================================
// domain/ports.ts — all ports (interfaces) the domain needs
// ============================================================

export interface Product {
  id: string;
  name: string;
  priceCents: number;
  stock: number;
  imageKey: string | null;
}

export interface ProductRepository {
  findById(id: string): Promise<Product | null>;
  findAll(limit: number, offset: number): Promise<Product[]>;
  save(product: Product): Promise<void>;
  delete(id: string): Promise<void>;
}

export interface CachePort {
  get<T>(key: string): Promise<T | null>;
  set<T>(key: string, value: T, ttlSeconds: number): Promise<void>;
  invalidate(key: string): Promise<void>;
}

export interface FileStoragePort {
  put(key: string, data: ReadableStream | ArrayBuffer, contentType: string): Promise<void>;
  get(key: string): Promise<ReadableStream | null>;
  delete(key: string): Promise<void>;
  publicUrl(key: string): string;
}

export interface NotificationPort {
  send(userId: string, message: string): Promise<void>;
}

// ============================================================
// domain/product-service.ts — pure domain logic, zero CF imports
// ============================================================
export class ProductService {
  constructor(
    private repo: ProductRepository,
    private cache: CachePort,
    private files: FileStoragePort,
  ) {}

  async getProduct(id: string): Promise<Product> {
    const cacheKey = `product:${id}`;
    const cached = await this.cache.get<Product>(cacheKey);
    if (cached) return cached;

    const product = await this.repo.findById(id);
    if (!product) throw new ProductNotFoundError(id);

    await this.cache.set(cacheKey, product, 300);
    return product;
  }

  async listProducts(page: number, pageSize: number): Promise<Product[]> {
    const cacheKey = `products:page:${page}:${pageSize}`;
    const cached = await this.cache.get<Product[]>(cacheKey);
    if (cached) return cached;

    const products = await this.repo.findAll(pageSize, (page - 1) * pageSize);
    await this.cache.set(cacheKey, products, 60);
    return products;
  }

  async createProduct(
    name: string,
    priceCents: number,
    stock: number,
    imageFile?: { stream: ReadableStream; contentType: string },
  ): Promise<Product> {
    if (!name || name.length < 2) throw new ValidationError('name must be >= 2 chars');
    if (priceCents < 0) throw new ValidationError('price cannot be negative');

    const id = crypto.randomUUID();
    let imageKey: string | null = null;

    if (imageFile) {
      imageKey = `products/${id}/image`;
      await this.files.put(imageKey, imageFile.stream, imageFile.contentType);
    }

    const product: Product = { id, name, priceCents, stock, imageKey };
    await this.repo.save(product);
    await this.cache.invalidate(`products:page:1:20`); // bust list cache
    return product;
  }

  async updateStock(id: string, delta: number): Promise<Product> {
    const product = await this.repo.findById(id);
    if (!product) throw new ProductNotFoundError(id);
    product.stock = Math.max(0, product.stock + delta);
    await this.repo.save(product);
    await this.cache.invalidate(`product:${id}`);
    return product;
  }
}

export class ProductNotFoundError extends Error {
  constructor(id: string) { super(`Product ${id} not found`); this.name = 'ProductNotFoundError'; }
}
export class ValidationError extends Error {
  constructor(msg: string) { super(msg); this.name = 'ValidationError'; }
}

// ============================================================
// adapters/d1-product-repository.ts
// ============================================================
export class D1ProductRepository implements ProductRepository {
  constructor(private db: D1Database) {}

  async findById(id: string): Promise<Product | null> {
    const row = await this.db
      .prepare('SELECT id, name, price_cents, stock, image_key FROM products WHERE id = ?1')
      .bind(id)
      .first<{ id: string; name: string; price_cents: number; stock: number; image_key: string | null }>();
    if (!row) return null;
    return { id: row.id, name: row.name, priceCents: row.price_cents, stock: row.stock, imageKey: row.image_key };
  }

  async findAll(limit: number, offset: number): Promise<Product[]> {
    const { results } = await this.db
      .prepare('SELECT id, name, price_cents, stock, image_key FROM products LIMIT ?1 OFFSET ?2')
      .bind(limit, offset)
      .all<{ id: string; name: string; price_cents: number; stock: number; image_key: string | null }>();
    return results.map((r) => ({ id: r.id, name: r.name, priceCents: r.price_cents, stock: r.stock, imageKey: r.image_key }));
  }

  async save(product: Product): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO products (id, name, price_cents, stock, image_key)
         VALUES (?1, ?2, ?3, ?4, ?5)
         ON CONFLICT (id) DO UPDATE
           SET name = excluded.name, price_cents = excluded.price_cents,
               stock = excluded.stock, image_key = excluded.image_key`,
      )
      .bind(product.id, product.name, product.priceCents, product.stock, product.imageKey)
      .run();
  }

  async delete(id: string): Promise<void> {
    await this.db.prepare('DELETE FROM products WHERE id = ?1').bind(id).run();
  }
}

// ============================================================
// adapters/kv-cache-adapter.ts
// ============================================================
export class KVCacheAdapter implements CachePort {
  constructor(private kv: KVNamespace) {}

  async get<T>(key: string): Promise<T | null> {
    const raw = await this.kv.get(key);
    return raw ? (JSON.parse(raw) as T) : null;
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    await this.kv.put(key, JSON.stringify(value), { expirationTtl: ttlSeconds });
  }

  async invalidate(key: string): Promise<void> {
    await this.kv.delete(key);
  }
}

// ============================================================
// adapters/r2-file-adapter.ts
// ============================================================
export class R2FileAdapter implements FileStoragePort {
  constructor(
    private bucket: R2Bucket,
    private publicBaseUrl: string,
  ) {}

  async put(key: string, data: ReadableStream | ArrayBuffer, contentType: string): Promise<void> {
    await this.bucket.put(key, data, { httpMetadata: { contentType } });
  }

  async get(key: string): Promise<ReadableStream | null> {
    const obj = await this.bucket.get(key);
    return obj?.body ?? null;
  }

  async delete(key: string): Promise<void> {
    await this.bucket.delete(key);
  }

  publicUrl(key: string): string {
    return `${this.publicBaseUrl}/${key}`;
  }
}

// ============================================================
// adapters/service-binding-notification-adapter.ts
// ============================================================
interface NotificationService {
  fetch(input: RequestInfo, init?: RequestInit): Promise<Response>;
}

export class ServiceBindingNotificationAdapter implements NotificationPort {
  constructor(private service: NotificationService) {}

  async send(userId: string, message: string): Promise<void> {
    const res = await this.service.fetch('/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, message }),
    });
    if (!res.ok) throw new Error(`Notification service error: ${res.status}`);
  }
}

// ============================================================
// adapters/in-memory-adapters.ts — for unit tests
// ============================================================
export class InMemoryProductRepository implements ProductRepository {
  private store = new Map<string, Product>();

  async findById(id: string) { return this.store.get(id) ?? null; }
  async findAll(limit: number, offset: number) {
    return Array.from(this.store.values()).slice(offset, offset + limit);
  }
  async save(product: Product) { this.store.set(product.id, { ...product }); }
  async delete(id: string) { this.store.delete(id); }
}

export class InMemoryCacheAdapter implements CachePort {
  private store = new Map<string, { value: unknown; expiresAt: number }>();

  async get<T>(key: string): Promise<T | null> {
    const entry = this.store.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) { this.store.delete(key); return null; }
    return entry.value as T;
  }
  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    this.store.set(key, { value, expiresAt: Date.now() + ttlSeconds * 1000 });
  }
  async invalidate(key: string): Promise<void> { this.store.delete(key); }
}

export class InMemoryFileAdapter implements FileStoragePort {
  private store = new Map<string, ArrayBuffer>();

  async put(key: string, data: ReadableStream | ArrayBuffer): Promise<void> {
    this.store.set(key, data instanceof ArrayBuffer ? data : new ArrayBuffer(0));
  }
  async get(key: string): Promise<ReadableStream | null> {
    const buf = this.store.get(key);
    if (!buf) return null;
    return new ReadableStream({ start(c) { c.enqueue(new Uint8Array(buf)); c.close(); } });
  }
  async delete(key: string): Promise<void> { this.store.delete(key); }
  publicUrl(key: string): string { return `/test-files/${key}`; }
}

// ============================================================
// worker.ts — wiring (composition root)
// ============================================================
interface Env {
  DB: D1Database;
  PRODUCTS_KV: KVNamespace;
  PRODUCT_IMAGES: R2Bucket;
  NOTIFICATION_SVC: ServiceBindingNotificationAdapter; // Service Binding
  R2_PUBLIC_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // --- Wire adapters ---
    const repo = new D1ProductRepository(env.DB);
    const cache = new KVCacheAdapter(env.PRODUCTS_KV);
    const files = new R2FileAdapter(env.PRODUCT_IMAGES, env.R2_PUBLIC_URL);

    // --- Inject into domain service ---
    const service = new ProductService(repo, cache, files);

    const url = new URL(request.url);

    try {
      if (request.method === 'GET' && url.pathname === '/products') {
        const page = parseInt(url.searchParams.get('page') ?? '1', 10);
        const products = await service.listProducts(page, 20);
        return Response.json(products);
      }

      if (request.method === 'GET' && url.pathname.startsWith('/products/')) {
        const id = url.pathname.split('/')[2];
        const product = await service.getProduct(id);
        return Response.json(product);
      }

      if (request.method === 'POST' && url.pathname === '/products') {
        const formData = await request.formData();
        const name = formData.get('name') as string;
        const price = parseInt(formData.get('price') as string, 10);
        const stock = parseInt(formData.get('stock') as string, 10);
        const imageFile = formData.get('image') as File | null;

        const product = await service.createProduct(
          name,
          price,
          stock,
          imageFile
            ? { stream: imageFile.stream(), contentType: imageFile.type }
            : undefined,
        );
        return Response.json(product, { status: 201 });
      }

      if (request.method === 'PATCH' && url.pathname.endsWith('/stock')) {
        const id = url.pathname.split('/')[2];
        const { delta } = await request.json<{ delta: number }>();
        const product = await service.updateStock(id, delta);
        return Response.json(product);
      }
    } catch (err) {
      if (err instanceof ProductNotFoundError)
        return Response.json({ error: err.message }, { status: 404 });
      if (err instanceof ValidationError)
        return Response.json({ error: err.message }, { status: 400 });
      throw err;
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Implementation Details

**Unit test with in-memory adapters (Vitest)**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { ProductService, ProductNotFoundError } from '../domain/product-service';
import {
  InMemoryProductRepository,
  InMemoryCacheAdapter,
  InMemoryFileAdapter,
} from '../adapters/in-memory-adapters';

describe('ProductService', () => {
  let service: ProductService;

  beforeEach(() => {
    service = new ProductService(
      new InMemoryProductRepository(),
      new InMemoryCacheAdapter(),
      new InMemoryFileAdapter(),
    );
  });

  it('creates and retrieves a product', async () => {
    const created = await service.createProduct('Widget', 999, 10);
    const found = await service.getProduct(created.id);
    expect(found.name).toBe('Widget');
    expect(found.priceCents).toBe(999);
  });

  it('throws ProductNotFoundError for missing product', async () => {
    await expect(service.getProduct('missing-id')).rejects.toBeInstanceOf(ProductNotFoundError);
  });

  it('updates stock correctly', async () => {
    const created = await service.createProduct('Gadget', 1999, 5);
    const updated = await service.updateStock(created.id, -3);
    expect(updated.stock).toBe(2);
  });
});
```

**D1 schema**

```sql
CREATE TABLE IF NOT EXISTS products (
  id          TEXT    PRIMARY KEY,
  name        TEXT    NOT NULL,
  price_cents INTEGER NOT NULL,
  stock       INTEGER NOT NULL DEFAULT 0,
  image_key   TEXT
);
```

---

## Anti-patterns

- **Importing `D1Database` in domain files** — the domain must never reference Cloudflare types. If you see `import type { D1Database } from '@cloudflare/workers-types'` outside an adapter, the boundary has been broken.
- **Fat Worker entry point** — the wiring in `worker.ts` should be 10–20 lines per route. Business logic belongs in `ProductService`.
- **Adapter logic in the domain** — retry logic, serialization, caching TTL, SQL queries: all in adapters. The domain service asks for data; the adapter decides how to fetch it.
- **Skipping in-memory adapters** — teams that skip in-memory adapters inevitably couple tests to Miniflare, making CI slower and tests flakier.

---

## Gotchas

- R2 `bucket.get()` returns `R2ObjectBody | null`. The `body` property is a `ReadableStream`. If you consume it once, it cannot be replayed. Pass the stream directly to the response — do not buffer it unless necessary.
- KV `put` with `expirationTtl` requires a minimum TTL of 60 seconds on Cloudflare. In-memory adapters should accept any TTL for testing flexibility.
- Service Bindings (`env.NOTIFICATION_SVC`) call another Worker in the same account via the Cloudflare network with zero egress cost. The binding's type in `wrangler.toml` is `service`. Type it as `{ fetch: typeof fetch }` in the Env interface.
- Constructor injection (used here) is the simplest DI approach. For larger applications with many services, consider a lightweight DI container or a factory module that reads `env` once and wires everything.

---

## Verification

```bash
# Create a product
curl -X POST https://worker.example.com/products \
  -F 'name=Widget' -F 'price=999' -F 'stock=50'

# List products (served from KV cache on second call)
curl https://worker.example.com/products?page=1

# Update stock
curl -X PATCH https://worker.example.com/products/<id>/stock \
  -H 'Content-Type: application/json' -d '{"delta":-5}'

# Run unit tests (no Workers runtime needed)
npx vitest run
```

---

## Related

- `workers-anti-corruption-layer.md` — ACL adapters plug in as infrastructure adapters
- `workers-cqrs-pattern-d1-kv.md` — CQRS command/query handlers can use the same port interfaces
- `sidecar-pattern-service-binding.md` — Service Binding adapters follow the same pattern

---

## Sources

- [Cloudflare Workers documentation](https://developers.cloudflare.com/workers/)
- Alistair Cockburn, *Hexagonal Architecture* — https://alistair.cockburn.us/hexagonal-architecture/
- Tom Hombergs, *Get Your Hands Dirty on Clean Architecture* (2nd ed.)
- Robert C. Martin, *Clean Architecture*, Part V
