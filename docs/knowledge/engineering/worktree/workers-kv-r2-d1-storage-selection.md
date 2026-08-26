# Choosing Cloudflare Storage Primitives: KV, R2, D1, and Durable Objects

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your team is building a new feature in a Cloudflare Worker and reaches for KV because it is the most familiar storage option. Three months later, the feature has complex queries that KV cannot support, or it has high write throughput that creates consistency bugs, or it needs atomic counters that KV's eventual-consistency model breaks. Choosing the wrong storage primitive creates expensive refactors. This article gives you a decision framework to pick correctly the first time.

---

## Context

Cloudflare's storage layer for Workers has four first-party primitives:

| Primitive | Model | Consistency | Latency | Ideal scale |
|---|---|---|---|---|
| **KV** | Key-value | Eventual | ~10–50ms read globally | Millions of keys, read-heavy |
| **R2** | Object storage | Strong (per-object) | ~50–200ms | Large blobs, any count |
| **D1** | SQLite (relational) | Strong (per-DB) | ~5–20ms in-region | Structured data, complex queries |
| **Durable Objects** | Single-threaded actor | Linearizable | ~5ms co-located | Shared mutable state, coordination |

Each primitive is billed differently and has different operational characteristics in a monorepo context where multiple Workers might share the same storage.

---

## Section 1: Workers KV — When to Use It

KV is a globally distributed key-value store. Reads are served from the nearest PoP (edge cache), making it exceptionally fast for globally distributed reads. Writes propagate within ~60 seconds.

**Use KV when:**
- Data is read far more often than written (config, feature flags, A/B test assignments, cached API responses)
- Global read performance matters more than write consistency
- Data fits a flat key-value shape; no queries beyond exact-key lookup or prefix scan
- You can tolerate eventual consistency (a write may not be visible to all PoPs for up to 60 seconds)

**Avoid KV when:**
- You need immediate read-after-write consistency (e.g., session invalidation that must be instant everywhere)
- Your access pattern involves listing large numbers of keys (list operations are expensive and paginated)
- You need transactional updates across multiple keys

```typescript
// Good KV use case: feature flag lookup
export async function isFeatureEnabled(
  env: Env,
  flag: string,
  userId: string
): Promise<boolean> {
  // Fast global read — acceptable if flag changes take 60s to propagate
  const config = await env.FLAGS.get(flag, { type: "json" });
  if (!config) return false;
  return config.enabled && !config.blocklist.includes(userId);
}

// Bad KV use case: inventory counter
// KV has no atomic increment — use Durable Objects instead
async function decrementStock(env: Env, productId: string): Promise<void> {
  const count = Number(await env.STOCK.get(productId));
  // RACE CONDITION: two Workers may both read 1, both write 0
  await env.STOCK.put(productId, String(count - 1));
}
```

---

## Section 2: R2 — When to Use It

R2 is Cloudflare's S3-compatible object store. It stores arbitrary binary objects (images, videos, PDFs, JSON documents) with strong per-object consistency and zero egress fees to Workers.

**Use R2 when:**
- Storing blobs: user-uploaded files, build artifacts, generated reports, backups
- Object size is > 128 KB (KV has a 25 MB limit per value, but KV is inefficient for large objects)
- You need presigned URLs for direct browser uploads or downloads
- You need to serve objects as static assets via Cloudflare's CDN (R2 public bucket + custom domain)

**Avoid R2 when:**
- You need per-record structured queries (R2 has no query language; use D1 for metadata)
- Your objects are < 1 KB and access is extremely frequent (KV is cheaper and faster for tiny frequent reads)

```typescript
// Good R2 use case: user avatar upload via presigned URL
export async function createUploadUrl(
  env: Env,
  userId: string,
  filename: string
): Promise<{ url: string; key: string }> {
  const key = `avatars/${userId}/${Date.now()}-${filename}`;
  // Generate a temporary upload URL (1 hour)
  const url = await env.ASSETS.createMultipartUpload(key);
  return { url: url.uploadId, key };
}

// Stream a large file from R2 to the client
export async function streamAsset(
  env: Env,
  key: string
): Promise<Response> {
  const object = await env.ASSETS.get(key);
  if (!object) return new Response("Not found", { status: 404 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  return new Response(object.body, { headers });
}
```

---

## Section 3: D1 — When to Use It

D1 is Cloudflare's managed SQLite database. It runs in the same PoP as the Worker (with replication to read replicas), offering low-latency SQL queries with full ACID transactions.

**Use D1 when:**
- Data is relational and benefits from joins, aggregations, or complex WHERE clauses
- You need ACID transactions across multiple rows or tables
- Schema migrations matter (Wrangler supports D1 migration files)
- Your data is structured and query patterns evolve over time
- Write volume is moderate (D1 is not designed for millions of writes per second)

**Avoid D1 when:**
- You need sub-millisecond latency for simple key lookups (use KV)
- You're storing binary blobs > 1 MB (store in R2; put metadata in D1)
- You need global multi-primary write consistency (D1 has a primary region; read replicas lag slightly)

```typescript
// Good D1 use case: paginated query with filter
export async function listOrders(
  env: Env,
  userId: string,
  page: number,
  status: "pending" | "shipped" | "delivered"
): Promise<Order[]> {
  const limit = 20;
  const offset = (page - 1) * limit;
  const { results } = await env.DB.prepare(
    `SELECT id, total, status, created_at
     FROM orders
     WHERE user_id = ? AND status = ?
     ORDER BY created_at DESC
     LIMIT ? OFFSET ?`
  )
    .bind(userId, status, limit, offset)
    .all<Order>();
  return results;
}

// D1 transaction: debit + insert in one atomic operation
export async function placeOrder(env: Env, userId: string, total: number) {
  await env.DB.batch([
    env.DB.prepare("UPDATE accounts SET balance = balance - ? WHERE id = ?")
      .bind(total, userId),
    env.DB.prepare("INSERT INTO orders (user_id, total, status) VALUES (?, ?, 'pending')")
      .bind(userId, total),
  ]);
}
```

---

## Section 4: Durable Objects — When to Use Them

Durable Objects are single-threaded stateful actors. All requests to a given Durable Object ID are routed to a single instance in one data center, serializing access and providing linearizable consistency.

**Use Durable Objects when:**
- You need atomic counters, rate limiters, or locks shared across many Worker requests
- You're building real-time features: WebSocket chat rooms, presence indicators, collaborative editing
- You need a single point of coordination for a resource (auction, booking, payment)
- You need in-memory state that persists across requests to the same object

**Avoid Durable Objects when:**
- Your use case is read-heavy with no coordination need (KV is simpler and faster)
- You don't need single-instance coordination (most CRUD apps don't)
- Your team is not prepared for the actor programming model (state lives in one location; cold starts relocate the DO)

```typescript
// Durable Object: atomic rate limiter
export class RateLimiter implements DurableObject {
  private counts = new Map<string, { count: number; resetAt: number }>();

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get("key") ?? "default";
    const limit = Number(url.searchParams.get("limit") ?? "100");
    const windowMs = Number(url.searchParams.get("windowMs") ?? "60000");

    const now = Date.now();
    let entry = this.counts.get(key);
    if (!entry || entry.resetAt <= now) {
      entry = { count: 0, resetAt: now + windowMs };
    }
    entry.count++;
    this.counts.set(key, entry);

    const allowed = entry.count <= limit;
    return Response.json({
      allowed,
      remaining: Math.max(0, limit - entry.count),
      resetAt: entry.resetAt,
    });
  }
}

// Worker calling the DO
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const id = env.RATE_LIMITER.idFromName(ip);
    const stub = env.RATE_LIMITER.get(id);
    const result = await stub.fetch(
      `https://do/check?key=${ip}&limit=100&windowMs=60000`
    );
    const { allowed } = await result.json<{ allowed: boolean }>();
    if (!allowed) return new Response("Rate limited", { status: 429 });
    // ... handle the actual request
    return new Response("OK");
  },
};
```

---

## Section 5: Combining Primitives

Real applications use multiple primitives together. A typical API Worker pattern:

```
User uploads avatar → Worker validates → R2 (blob storage)
Worker writes metadata → D1 (structured record: userId, key, size, mime)
Worker invalidates CDN cached URL → KV (mark key as stale)
Worker rate-limits per user → Durable Object (atomic counter)
```

```typescript
// Combining D1 + R2 + KV in one operation
export async function uploadAvatar(
  env: Env,
  userId: string,
  file: File
): Promise<{ key: string }> {
  const key = `avatars/${userId}/${crypto.randomUUID()}.${file.name.split(".").pop()}`;

  // 1. Store blob in R2
  await env.ASSETS.put(key, file.stream(), {
    httpMetadata: { contentType: file.type },
  });

  // 2. Record metadata in D1
  await env.DB.prepare(
    "INSERT INTO user_avatars (user_id, r2_key, size, mime, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
  )
    .bind(userId, key, file.size, file.type)
    .run();

  // 3. Invalidate the user's cached avatar URL in KV
  await env.CACHE.delete(`avatar:${userId}`);

  return { key };
}
```

---

## Section 6: Monorepo Binding Sharing

Multiple Workers in a monorepo can share the same D1 database or R2 bucket. Declare the same resource IDs in each Worker's `wrangler.toml`:

```toml
# packages/api-worker/wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "shared-db"
database_id = "xxxx..."

# packages/admin-worker/wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "shared-db"
database_id = "xxxx..."     # Same ID — same physical database
```

Manage schema migrations from a single canonical location:

```
migrations/
└── shared-db/
    ├── 0001_create_users.sql
    ├── 0002_create_orders.sql
    └── 0003_add_indexes.sql
```

Apply migrations centrally in CI before deploying any Worker:

```bash
wrangler d1 migrations apply shared-db --env production --config packages/api-worker/wrangler.toml
```

---

## Anti-patterns

- **Using KV as a queue.** KV has no message ordering, acknowledgment, or at-least-once delivery. Use Cloudflare Queues for work queues.
- **Storing all data in Durable Objects.** DOs are actors, not general-purpose databases. Their storage API (`this.ctx.storage`) is a key-value store with a 128 KB per-value limit and is tied to one geographic instance. Large datasets belong in D1.
- **Using D1 for blob storage.** SQLite BLOB columns are inefficient for objects > 1 MB. Store blobs in R2 and metadata in D1.
- **One massive KV namespace shared by all Workers.** Namespace leakage causes cross-Worker data collisions. Separate namespaces per Worker per environment.
- **Directly querying D1 from a hot path.** D1 has ~5–20ms per query latency. Cache results in KV when the same query runs on every request.

---

## Gotchas

- KV `list()` returns at most 1000 keys per call. Paginate with the `cursor` parameter if you have more keys.
- D1 does not support `RETURNING` for multi-row statements in some compatibility dates. Test with your `compatibility_date`.
- Durable Object instances are billed per CPU-millisecond, not per request. An infinite loop in a DO is expensive — always set timeouts.
- R2 presigned URLs require the bucket to be private. Making a bucket public disables presigned URL functionality.
- KV values have a 25 MB maximum. R2 objects support multipart upload for files up to 5 TB.
- D1 free tier is limited to 100,000 rows read per day. Monitor `d1_read_queries` in Cloudflare Analytics.

---

## Verification

```bash
# List all KV namespaces in your account
wrangler kv namespace list

# List all D1 databases
wrangler d1 list

# List all R2 buckets
wrangler r2 bucket list

# Inspect D1 row counts per table (useful for capacity planning)
wrangler d1 execute shared-db --command \
  "SELECT name, (SELECT COUNT(*) FROM pragma_table_info(name)) FROM sqlite_master WHERE type='table';" \
  --env production

# Check KV namespace size (key count)
wrangler kv key list --namespace-id <id> | wc -l
```

---

## Related

- `wrangler-environments-staging-production.md` — per-environment resource IDs in wrangler.toml
- `cloudflare-workers-vitest-miniflare-testing.md` — testing all four storage primitives locally
- `cloudflare-workers-observability-tail-workers.md` — monitoring storage latency in production
- `monorepo-workspace-cloudflare-workers.md` — monorepo package structure for Workers

---

## Sources

- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- Cloudflare R2 docs — https://developers.cloudflare.com/r2/
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare Durable Objects docs — https://developers.cloudflare.com/durable-objects/
- Storage options comparison — https://developers.cloudflare.com/workers/platform/storage-options/
