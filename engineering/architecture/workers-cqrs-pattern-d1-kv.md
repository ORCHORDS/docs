# CQRS Pattern with D1 and KV on Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker endpoint is overloaded doing both heavy writes (validation, business rules, persistence) and heavy reads (joins, aggregations, filtering) against D1. Read latency spikes because writes lock rows; write throughput drops because reads demand complex SQL. You need independent scaling of read and write paths without a full microservices split.

---

## Context

CQRS (Command Query Responsibility Segregation) separates the *write model* (Commands) from the *read model* (Queries). In Cloudflare Workers:

- **D1** is the source of truth for commands — it enforces constraints and stores authoritative state.
- **KV** holds *projections* — pre-computed, denormalised views tailored to specific query shapes.
- **Queues** propagate domain events from D1 writes to KV projection updaters asynchronously.
- The **eventual consistency window** is typically 50–500 ms (Queue delivery) + KV replication time.

This is a good fit when reads vastly outnumber writes (e.g., product catalog, leaderboards, user profiles) or when read and write schemas naturally diverge.

---

## Solution

```typescript
// ============================================================
// types.ts — shared domain types
// ============================================================
export interface Product {
  id: string;
  name: string;
  price: number; // cents
  stock: number;
  category: string;
  updatedAt: number; // epoch ms
}

export interface CreateProductCommand {
  type: 'CREATE_PRODUCT';
  payload: Omit<Product, 'id' | 'updatedAt'>;
}

export interface UpdatePriceCommand {
  type: 'UPDATE_PRICE';
  payload: { id: string; price: number };
}

export type Command = CreateProductCommand | UpdatePriceCommand;

export interface DomainEvent {
  id: string;
  type: string;
  aggregateId: string;
  payload: unknown;
  occurredAt: number;
}

// ============================================================
// command-handler.ts — write side
// ============================================================
import { D1Database, Queue } from '@cloudflare/workers-types';

export class ProductCommandHandler {
  constructor(
    private db: D1Database,
    private eventQueue: Queue<DomainEvent>,
  ) {}

  async handle(cmd: Command): Promise<{ id: string }> {
    switch (cmd.type) {
      case 'CREATE_PRODUCT':
        return this.createProduct(cmd);
      case 'UPDATE_PRICE':
        return this.updatePrice(cmd);
      default: {
        const _exhaustive: never = cmd;
        throw new Error(`Unknown command: ${(_exhaustive as Command).type}`);
      }
    }
  }

  private async createProduct(cmd: CreateProductCommand): Promise<{ id: string }> {
    // --- Validate ---
    const { name, price, stock, category } = cmd.payload;
    if (!name || name.length < 2) throw new Error('name must be >= 2 chars');
    if (price < 0) throw new Error('price cannot be negative');
    if (stock < 0) throw new Error('stock cannot be negative');

    const id = crypto.randomUUID();
    const now = Date.now();

    // --- Persist to D1 ---
    await this.db
      .prepare(
        `INSERT INTO products (id, name, price, stock, category, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
      )
      .bind(id, name, price, stock, category, now)
      .run();

    // --- Emit domain event ---
    const event: DomainEvent = {
      id: crypto.randomUUID(),
      type: 'PRODUCT_CREATED',
      aggregateId: id,
      payload: { id, name, price, stock, category, updatedAt: now },
      occurredAt: now,
    };
    await this.eventQueue.send(event);

    return { id };
  }

  private async updatePrice(cmd: UpdatePriceCommand): Promise<{ id: string }> {
    const { id, price } = cmd.payload;
    if (price < 0) throw new Error('price cannot be negative');

    const now = Date.now();
    const result = await this.db
      .prepare(
        `UPDATE products SET price = ?1, updated_at = ?2 WHERE id = ?3`,
      )
      .bind(price, now, id)
      .run();

    if (result.meta.changes === 0) throw new Error(`Product ${id} not found`);

    const event: DomainEvent = {
      id: crypto.randomUUID(),
      type: 'PRICE_UPDATED',
      aggregateId: id,
      payload: { id, price, updatedAt: now },
      occurredAt: now,
    };
    await this.eventQueue.send(event);

    return { id };
  }
}

// ============================================================
// projection-updater.ts — Queue consumer, updates KV
// ============================================================
import { KVNamespace } from '@cloudflare/workers-types';

export class ProductProjectionUpdater {
  constructor(private kv: KVNamespace) {}

  async apply(event: DomainEvent): Promise<void> {
    switch (event.type) {
      case 'PRODUCT_CREATED': {
        const product = event.payload as Product;
        await this.kv.put(
          `product:${product.id}`,
          JSON.stringify(product),
          { expirationTtl: 60 * 60 * 24 * 7 }, // 7 days
        );
        await this.addToCategory(product);
        break;
      }
      case 'PRICE_UPDATED': {
        const { id, price, updatedAt } = event.payload as {
          id: string;
          price: number;
          updatedAt: number;
        };
        const raw = await this.kv.get(`product:${id}`);
        if (!raw) break; // projection not yet built — skip; rebuild will catch it
        const product: Product = JSON.parse(raw);
        product.price = price;
        product.updatedAt = updatedAt;
        await this.kv.put(`product:${id}`, JSON.stringify(product));
        break;
      }
    }
  }

  private async addToCategory(product: Product): Promise<void> {
    const key = `category:${product.category}`;
    const raw = await this.kv.get(key);
    const ids: string[] = raw ? JSON.parse(raw) : [];
    if (!ids.includes(product.id)) ids.push(product.id);
    await this.kv.put(key, JSON.stringify(ids));
  }
}

// ============================================================
// query-handler.ts — read side, KV only
// ============================================================
export class ProductQueryHandler {
  constructor(private kv: KVNamespace) {}

  async getById(id: string): Promise<Product | null> {
    const raw = await this.kv.get(`product:${id}`);
    return raw ? (JSON.parse(raw) as Product) : null;
  }

  async listByCategory(category: string): Promise<Product[]> {
    const idsRaw = await this.kv.get(`category:${category}`);
    if (!idsRaw) return [];
    const ids: string[] = JSON.parse(idsRaw);
    const products = await Promise.all(ids.map((id) => this.getById(id)));
    return products.filter(Boolean) as Product[];
  }
}

// ============================================================
// worker.ts — entry point wiring
// ============================================================
interface Env {
  DB: D1Database;
  PRODUCTS_KV: KVNamespace;
  PRODUCT_EVENTS: Queue<DomainEvent>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // --- Commands ---
    if (request.method === 'POST' && url.pathname === '/commands') {
      const cmd: Command = await request.json();
      const handler = new ProductCommandHandler(env.DB, env.PRODUCT_EVENTS);
      try {
        const result = await handler.handle(cmd);
        return Response.json(result, { status: 202 });
      } catch (err) {
        return Response.json({ error: (err as Error).message }, { status: 400 });
      }
    }

    // --- Queries ---
    if (request.method === 'GET' && url.pathname.startsWith('/products/')) {
      const id = url.pathname.split('/')[2];
      const queries = new ProductQueryHandler(env.PRODUCTS_KV);
      const product = await queries.getById(id);
      if (!product) return Response.json({ error: 'not found' }, { status: 404 });
      return Response.json(product);
    }

    if (request.method === 'GET' && url.pathname === '/products') {
      const category = url.searchParams.get('category') ?? '';
      const queries = new ProductQueryHandler(env.PRODUCTS_KV);
      const products = await queries.listByCategory(category);
      return Response.json(products);
    }

    // --- Projection rebuild (admin) ---
    if (request.method === 'POST' && url.pathname === '/admin/rebuild-projections') {
      const authHeader = request.headers.get('Authorization');
      if (authHeader !== `Bearer ${(env as unknown as { ADMIN_TOKEN: string }).ADMIN_TOKEN}`) {
        return new Response('Forbidden', { status: 403 });
      }
      await rebuildProjections(env.DB, env.PRODUCTS_KV);
      return Response.json({ ok: true });
    }

    return new Response('Not found', { status: 404 });
  },

  // Queue consumer
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    const updater = new ProductProjectionUpdater(env.PRODUCTS_KV);
    for (const msg of batch.messages) {
      await updater.apply(msg.body);
      msg.ack();
    }
  },
};

async function rebuildProjections(db: D1Database, kv: KVNamespace): Promise<void> {
  const { results } = await db.prepare('SELECT * FROM products').all<Product>();
  const updater = new ProductProjectionUpdater(kv);
  for (const row of results) {
    const product: Product = {
      id: row.id,
      name: row.name,
      price: row.price,
      stock: row.stock,
      category: row.category,
      updatedAt: row.updatedAt,
    };
    await updater.apply({
      id: crypto.randomUUID(),
      type: 'PRODUCT_CREATED',
      aggregateId: product.id,
      payload: product,
      occurredAt: product.updatedAt,
    });
  }
}
```

---

## Implementation Details

**D1 schema**

```sql
CREATE TABLE IF NOT EXISTS products (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  price       INTEGER NOT NULL,
  stock       INTEGER NOT NULL DEFAULT 0,
  category    TEXT NOT NULL,
  updated_at  INTEGER NOT NULL
);
```

**wrangler.toml bindings**

```toml
[[d1_databases]]
binding = "DB"
database_name = "products-db"
database_id   = "<your-d1-id>"

[[kv_namespaces]]
binding = "PRODUCTS_KV"
id      = "<your-kv-id>"

[[queues.producers]]
binding = "PRODUCT_EVENTS"
queue   = "product-events"

[[queues.consumers]]
queue              = "product-events"
max_batch_size     = 50
max_batch_timeout  = 5
```

**Consistency window handling** — Clients should tolerate a brief staleness window. After a write command returns `202 Accepted`, the KV projection updates within ~200–500 ms. If the client immediately polls the read endpoint, add `Retry-After: 1` to command responses and document this in your API contract.

---

## Anti-patterns

- **Reading D1 on the query path** defeats the purpose. Once projections are in KV, query handlers must never touch D1.
- **Skipping the Queue** and updating KV synchronously in the command handler creates tight coupling and risks partial failures where D1 committed but KV did not.
- **One giant KV value** per aggregate: KV values can reach 25 MB, but large values slow serialization. Keep projections lean — store only what the read model needs.
- **No projection rebuild endpoint**: Without it, a bug in the projection updater means corrupt read data forever.

---

## Gotchas

- KV is **eventually consistent** across regions. A write in one colo may take up to 60 seconds to appear globally. For geographically sensitive reads, consider Durable Objects instead of KV.
- D1 `meta.changes` returns `0` on a no-op `UPDATE`. Always check this to detect missing aggregates.
- Queues guarantee **at-least-once** delivery. Make projection updates **idempotent** — applying the same event twice must not corrupt state.
- KV has a per-account write rate limit. For high-throughput writes, batch KV puts in the Queue consumer.

---

## Verification

```bash
# 1. Create a product
curl -X POST https://worker.example.com/commands \
  -H 'Content-Type: application/json' \
  -d '{"type":"CREATE_PRODUCT","payload":{"name":"Widget","price":999,"stock":50,"category":"gadgets"}}'
# → {"id": "<uuid>"}

# 2. Wait ~500ms, then read via KV projection
curl https://worker.example.com/products/<uuid>
# → {"id":"...","name":"Widget","price":999,...}

# 3. Rebuild projections
curl -X POST https://worker.example.com/admin/rebuild-projections \
  -H 'Authorization: Bearer <ADMIN_TOKEN>'
```

---

## Related

- `workers-event-sourcing-d1.md` — pair CQRS with event sourcing for full audit trail
- `lambda-architecture-batch-stream.md` — batch/stream hybrid when KV projections need periodic recompute
- `graceful-degradation-feature-tiers.md` — serve stale KV data when D1 is degraded

---

## Sources

- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- [Cloudflare KV documentation](https://developers.cloudflare.com/kv/)
- [Cloudflare Queues documentation](https://developers.cloudflare.com/queues/)
- Martin Fowler, *CQRS* — https://martinfowler.com/bliki/CQRS.html
- Greg Young, *CQRS Documents* (2010)
