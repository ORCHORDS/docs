# Durable Objects Storage Read Coalescing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Durable Object handler performs multiple sequential `storage.get()` calls to load independent keys at the start of each request, each adding serialized I/O latency that stacks up against the request deadline. The fix is to coalesce all reads into a single `storage.get(keys[])` batch call or to pre-warm the cache with `storage.list()`.

## Context
Durable Objects storage is backed by a local NVMe-backed key-value store co-located with the isolate, but each `await storage.get(key)` call still crosses an async boundary and may involve disk I/O on a cold isolate. The storage layer supports multi-key reads (`get(keys: string[])`) that are dispatched as a single I/O operation and return a `Map<string, unknown>`. Sequential awaits serialize this I/O unnecessarily. Unlike RPC batch coalescing (where you group outbound Worker-to-DO RPC calls), storage read coalescing happens entirely inside the DO class itself.

## Coalescing Independent Keys into a Single get() Call
Replace sequential single-key reads with one multi-key read at the start of the handler.

```typescript
// BEFORE — sequential I/O, each await blocks the next read
export class SessionDO implements DurableObject {
  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const userId   = await this.state.storage.get<string>("userId");   // I/O 1
    const cart     = await this.state.storage.get<CartItem[]>("cart"); // I/O 2
    const prefs    = await this.state.storage.get<UserPrefs>("prefs"); // I/O 3
    // Total: 3 round-trips to storage

    return buildResponse(userId, cart, prefs);
  }
}

// AFTER — single coalesced read
export class SessionDO implements DurableObject {
  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const data = await this.state.storage.get<string | CartItem[] | UserPrefs>([
      "userId",
      "cart",
      "prefs",
    ]);
    // Returns Map<string, unknown> — one I/O operation
    const userId = data.get("userId") as string | undefined;
    const cart   = data.get("cart")   as CartItem[] | undefined;
    const prefs  = data.get("prefs")  as UserPrefs  | undefined;

    return buildResponse(userId, cart, prefs);
  }
}
```

## Pre-warming with blockConcurrencyWhile
Use `blockConcurrencyWhile` during initialization to load all needed state before any request is processed. This eliminates per-request storage reads entirely for frequently accessed keys.

```typescript
interface SessionState {
  userId: string;
  cart: CartItem[];
  prefs: UserPrefs;
}

export class SessionDO implements DurableObject {
  private session: SessionState | null = null;

  constructor(private state: DurableObjectState) {
    // blockConcurrencyWhile ensures no fetch() runs until this completes.
    state.blockConcurrencyWhile(async () => {
      const data = await state.storage.get<unknown>(["userId", "cart", "prefs"]);
      this.session = {
        userId: (data.get("userId") as string)      ?? "",
        cart:   (data.get("cart")   as CartItem[])  ?? [],
        prefs:  (data.get("prefs")  as UserPrefs)   ?? defaultPrefs(),
      };
    });
  }

  async fetch(request: Request): Promise<Response> {
    // session is guaranteed non-null; no storage I/O required.
    if (!this.session) throw new Error("unreachable");
    return buildResponse(this.session.userId, this.session.cart, this.session.prefs);
  }

  async flushCart(items: CartItem[]): Promise<void> {
    if (!this.session) return;
    this.session.cart = items;
    await this.state.storage.put("cart", items);
  }
}
```

## Batching Reads with storage.list() for Key-prefix Patterns
When all keys share a common prefix, a single `storage.list()` with a prefix filter outperforms individual multi-key `get()` calls.

```typescript
export class ProductCatalogDO implements DurableObject {
  constructor(private state: DurableObjectState) {}

  async loadCategoryProducts(category: string): Promise<Product[]> {
    // Reads all keys matching "product:<category>:<id>" in one call.
    const entries = await this.state.storage.list<Product>({
      prefix: `product:${category}:`,
      limit: 500,
    });
    return Array.from(entries.values());
  }

  async batchWrite(products: Product[]): Promise<void> {
    // Coalesce writes too — put(Map) is a single transaction.
    const batch = new Map<string, Product>();
    for (const p of products) {
      batch.set(`product:${p.category}:${p.id}`, p);
    }
    await this.state.storage.put(batch);
  }
}
```

`storage.list()` returns results in lexicographic key order, which makes it useful for paginated reads as well.

## Anti-patterns
- Calling `storage.get(key)` inside a loop — always collect the keys first, then call `storage.get(keys)` once.
- Using `storage.list()` without a `prefix` or `limit` — a full list scan on a large DO can exhaust memory and CPU time.
- Re-reading keys from storage after an in-memory write — maintain a local shadow copy and write through.
- Forgetting that `blockConcurrencyWhile` blocks all concurrent fetch calls, not just the first — keep the initialization read set minimal.
- Using sequential `await storage.put(key, value)` calls instead of `await storage.put(map)` for multi-key writes.

## Gotchas
- `storage.get(keys[])` returns a `Map` even when some keys are absent; always check `map.has(key)` or use `map.get(key) ?? default`.
- The storage layer enforces a 128 KiB per-value limit; storing large arrays (e.g., full cart objects) as a single value will hit this on large carts — split by item or store a compact representation.
- `blockConcurrencyWhile` introduces latency on the first request after a cold start; subsequent requests benefit from the pre-warmed in-memory state.
- DO storage reads are strongly consistent and durable; they are not a cache and cannot be bypassed for stale reads.
- `storage.list()` with `prefix` still does a range scan under the hood — it is O(n) in the number of matching keys, not O(1).

## Verification
```bash
# Tail DO storage I/O metrics
wrangler tail --format=json | jq 'select(.type == "durable-object-fetch") | .cpuTime'

# Use wrangler d1 execute equivalent for DO SQL storage (if using DO SQLite API)
# Check read counts in Workers Analytics Engine
wrangler analytics-engine query \
  "SELECT sum(double1) as reads FROM DO_METRICS WHERE timestamp > NOW() - INTERVAL '1 hour'"
```

```typescript
// Instrument coalesced reads with server-timing
const t0 = Date.now();
const data = await this.state.storage.get(["userId", "cart", "prefs"]);
const elapsed = Date.now() - t0;
// Attach to response
response.headers.set("Server-Timing", `do-storage;dur=${elapsed}`);
```

## Related
- [`durable-objects-rpc-batch-coalescing.md`](durable-objects-rpc-batch-coalescing.md)
- [`durable-objects-read-cache-layer.md`](durable-objects-read-cache-layer.md)
- [`durable-objects-memory-optimization.md`](durable-objects-memory-optimization.md)
- [`durable-objects-sql-storage-api-query-performance.md`](durable-objects-sql-storage-api-query-performance.md)
- [`durable-objects-low-latency-stateful.md`](durable-objects-low-latency-stateful.md)

## Sources
- https://developers.cloudflare.com/durable-objects/api/storage-api/
- https://developers.cloudflare.com/durable-objects/api/base/#blockconcurrencywhile
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://developers.cloudflare.com/durable-objects/platform/limits/
