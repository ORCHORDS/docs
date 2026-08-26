# Cache Invalidation at the Edge: Event-Driven Purge with Cloudflare Cache API and Queues

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You update a product price in your database and push a new API response to Cloudflare's edge cache, but cached HTML pages, JSON fragments, and image variants across 300 PoPs continue serving stale data for minutes or hours. Time-to-live expiry works for low-stakes content but is unacceptably slow for inventory counts, pricing, or user-facing entitlements. You need near-real-time cache invalidation that is reliable, auditable, and cost-efficient — without hammering the Cloudflare Cache Purge REST API from inside a hot write path.

---

## Context

Cloudflare offers two cache invalidation primitives:

1. **Cache API** (`caches.default` / named caches): Fine-grained per-URL or per-tag invalidation available inside a Worker. `cache.delete(request)` removes a single entry from the PoP where the Worker is executing. Purge-by-tag (`cf.cacheTags`) invalidates across all PoPs via the Cloudflare Cache Purge API.

2. **Cloudflare Cache Purge REST API**: `POST /zones/{zone_id}/purge_cache` — accepts URL list, tag list, or prefix. Rate-limited to 1,000 tag-based purge calls per day (Enterprise) or fewer on lower plans.

The architectural challenge is connecting a write event (e.g., a price update via a CMS webhook or DB trigger) to a purge operation in a way that is:
- **Decoupled**: the write path does not block on cache purge
- **Reliable**: purge is retried on transient failure
- **Batched**: multiple updates within a short window are coalesced into a single purge call
- **Auditable**: purge events are observable

Cloudflare Queues solves the decoupling and reliability requirements; a Durable Object solves batching; the Cache Purge API is the actuator.

---

## Section 1: Cache Tag Strategy — Tagging Responses for Targeted Purge

Before purging anything, responses must be tagged at write time. Cache tags are set in the `Cache-Tag` response header:

```typescript
// cache-tag-middleware.ts
function buildCacheTags(entity: { type: string; id: string; categoryId?: string }): string[] {
  const tags: string[] = [
    `entity:${entity.type}:${entity.id}`,           // exact entity
    `type:${entity.type}`,                           // all entities of this type
  ];
  if (entity.categoryId) {
    tags.push(`category:${entity.categoryId}`);     // category-level invalidation
  }
  return tags;
}

export function withCacheTags(
  response: Response,
  entity: { type: string; id: string; categoryId?: string }
): Response {
  const tags  = buildCacheTags(entity).join(',');
  const clone = new Response(response.body, response);
  clone.headers.set('Cache-Tag', tags);
  clone.headers.set('Cache-Control', 'public, s-maxage=3600, stale-while-revalidate=60');
  return clone;
}

// Usage in a product API Worker:
async function handleProductRequest(id: string, env: Env): Promise<Response> {
  const product = await env.DB.prepare('SELECT * FROM products WHERE id = ?').bind(id).first();
  if (!product) return new Response('Not Found', { status: 404 });

  const response = Response.json(product);
  return withCacheTags(response, {
    type:       'product',
    id:         String(product.id),
    categoryId: String(product.category_id),
  });
}
```

Cache tags longer than 1,024 bytes or containing whitespace are rejected. Keep tags compact: `product:42` not `entity-type=product,entity-id=42`.

---

## Section 2: Write-Side Event Emission to Cloudflare Queues

On every mutating operation, emit an invalidation event to a Queue instead of calling the purge API synchronously:

```typescript
// product-write-handler.ts
interface InvalidationMessage {
  type: 'tag' | 'url' | 'prefix';
  targets: string[];
  source: string;
  triggeredAt: number;
}

interface Env {
  DB: D1Database;
  INVALIDATION_QUEUE: Queue<InvalidationMessage>;
}

export async function updateProduct(
  id: string,
  patch: Partial<Product>,
  env: Env
): Promise<Product> {
  // Write to D1
  const result = await env.DB
    .prepare('UPDATE products SET price = ?, updated_at = ? WHERE id = ? RETURNING *')
    .bind(patch.price, Date.now(), id)
    .first<Product>();

  if (!result) throw new Error(`Product ${id} not found`);

  // Enqueue invalidation — non-blocking
  await env.INVALIDATION_QUEUE.send({
    type: 'tag',
    targets: [
      `entity:product:${id}`,
      `category:${result.category_id}`,
    ],
    source:      'product-write-handler',
    triggeredAt: Date.now(),
  });

  return result;
}
```

The Queue `send()` call completes in < 5 ms. If the write path fails after the enqueue, the Queue message is a harmless spurious purge (idempotent). If the purge fails, the Queue consumer retries automatically.

---

## Section 3: Batching Purge Requests with a Durable Object Accumulator

Purge-by-tag API calls are expensive (rate-limited). Batch messages from the Queue into windows of 500 ms using a Durable Object alarm:

```typescript
// PurgeBatcherDO.ts
import { DurableObject } from 'cloudflare:workers';
import { InvalidationMessage } from './product-write-handler';

interface Env {
  PURGE_BATCHER: DurableObjectNamespace;
  CLOUDFLARE_ZONE_ID: string;
  CLOUDFLARE_API_TOKEN: string;
}

export class PurgeBatcherDO extends DurableObject {
  private pending: Set<string> = new Set();
  private alarmSet = false;

  async fetch(request: Request): Promise<Response> {
    const messages = await request.json<InvalidationMessage[]>();

    for (const msg of messages) {
      if (msg.type === 'tag') {
        for (const tag of msg.targets) this.pending.add(tag);
      }
    }

    // Set a debounce alarm — fires 500 ms after first message in this batch window
    if (!this.alarmSet) {
      await this.ctx.storage.setAlarm(Date.now() + 500);
      this.alarmSet = true;
    }

    return new Response('queued');
  }

  async alarm(): Promise<void> {
    this.alarmSet = false;

    if (this.pending.size === 0) return;

    const tags  = [...this.pending];
    this.pending.clear();

    // Cloudflare Cache Purge API — purge-by-tag
    const env   = this.env as Env;
    const resp  = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${env.CLOUDFLARE_ZONE_ID}/purge_cache`,
      {
        method:  'POST',
        headers: {
          'Authorization': `Bearer ${env.CLOUDFLARE_API_TOKEN}`,
          'Content-Type':  'application/json',
        },
        body: JSON.stringify({ tags }),
      }
    );

    if (!resp.ok) {
      const text = await resp.text();
      // Re-queue tags for next alarm cycle rather than losing them
      for (const tag of tags) this.pending.add(tag);
      await this.ctx.storage.setAlarm(Date.now() + 5_000); // retry in 5 s
      this.alarmSet = true;
      console.error(`Purge failed (${resp.status}): ${text}`);
    } else {
      console.log(`Purged ${tags.length} cache tags: ${tags.join(', ')}`);
    }
  }
}
```

---

## Section 4: Queue Consumer — Bridging Queue to the Batcher DO

```typescript
// queue-consumer.ts
import { PurgeBatcherDO } from './PurgeBatcherDO';
export { PurgeBatcherDO };

interface Env {
  PURGE_BATCHER: DurableObjectNamespace;
}

export default {
  // Queue consumer receives batches of up to 100 messages
  async queue(batch: MessageBatch<InvalidationMessage>, env: Env): Promise<void> {
    // Route all messages through a single global batcher instance
    const stub = env.PURGE_BATCHER.get(env.PURGE_BATCHER.idFromName('global'));

    await stub.fetch(
      new Request('https://do/batch', {
        method: 'POST',
        body:   JSON.stringify(batch.messages.map(m => m.body)),
      })
    );

    // Acknowledge all messages — retries are handled by the DO
    batch.ackAll();
  },
};
```

`wrangler.toml`:
```toml
[[queues.consumers]]
queue          = "cache-invalidation"
max_batch_size = 100
max_batch_timeout = 1          # seconds — wait up to 1 s to fill a batch of 100

[[durable_objects.bindings]]
name       = "PURGE_BATCHER"
class_name = "PurgeBatcherDO"
```

---

## Section 5: URL-Level Purge for Cache API (Single-PoP)

Cache tags require Enterprise plan. For non-Enterprise accounts, purge specific URLs using the Cache API from inside a Worker (purges only the current PoP) or use the REST API's URL-based purge (purges all PoPs, limited to 30 URLs per call):

```typescript
// url-purge.ts — Worker-side Cache API purge (current PoP only)
async function purgeLocalCacheUrls(urls: string[]): Promise<void> {
  const cache = caches.default;
  await Promise.all(
    urls.map(url => cache.delete(new Request(url)))
  );
}

// REST API URL purge — all PoPs, call from the DO alarm:
async function purgeUrlsGlobally(
  urls: string[],
  zoneId: string,
  apiToken: string
): Promise<void> {
  // REST API accepts max 30 URLs per call; batch if needed
  for (let i = 0; i < urls.length; i += 30) {
    const batch = urls.slice(i, i + 30);
    const resp  = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
      {
        method:  'POST',
        headers: {
          'Authorization': `Bearer ${apiToken}`,
          'Content-Type':  'application/json',
        },
        body: JSON.stringify({ files: batch }),
      }
    );
    if (!resp.ok) throw new Error(`Purge failed: ${resp.status}`);
  }
}
```

---

## Section 6: Observability and Audit Trail

Log every purge event to Analytics Engine for capacity planning and debugging:

```typescript
// purge-audit.ts
interface PurgeAuditEvent {
  tags: string[];
  count: number;
  source: string;
  durationMs: number;
  success: boolean;
}

async function recordPurge(event: PurgeAuditEvent, ae: AnalyticsEngineDataset): Promise<void> {
  ae.writeDataPoint({
    blobs:      [event.source, event.tags.join(',').slice(0, 2000)],
    doubles:    [event.count, event.durationMs, event.success ? 1 : 0],
    timestamps: [new Date()],
  });
}
```

Query the dataset to answer:
- Which sources generate the most purge events? (cache churn detection)
- What is the average purge latency? (batcher tuning)
- Are there purge failures concentrated in a time window? (API rate limit detection)

---

## Anti-patterns

- **Purging on every cache miss**: Cache misses are not stale data. Purge only on confirmed writes. Spurious purges increase origin load and waste purge rate budget.
- **Calling the Purge API synchronously in the write path**: Any transient Cloudflare API failure blocks the write response. Always decouple via a Queue.
- **Using `cache.delete()` for global purge**: `caches.default.delete()` only invalidates the local PoP's cache entry. Use the REST API or cache tags for global invalidation.
- **One cache tag per URL**: Tags should represent logical entities (product, category, user), not individual URLs. A single tag purge can invalidate thousands of cached responses representing that entity.
- **Ignoring the purge-by-tag rate limit**: The limit is per-zone per-day, not per-request. Batch aggressively; do not set a 100 ms alarm window.

---

## Gotchas

- **Tag propagation delay**: After a tag purge API call returns 200, edge PoPs may take 2–5 seconds to evict tagged entries. Add a short jitter before re-serving requests that must see fresh content.
- **Cache-Tag header size**: The combined size of all Cache-Tag values must not exceed 16 KB per response. More than ~200 tags per response risks header size rejection.
- **Queue delivery at-least-once**: The same invalidation message may be delivered twice. The purge API is idempotent, so double purges are harmless.
- **DO alarm fires only once**: If the DO alarm callback throws, the alarm is rescheduled. If it succeeds, it does not automatically re-arm. The batcher must re-set the alarm only when new messages arrive.
- **Cloudflare API token scopes**: The token used for purge must have `Cache Purge: Purge` permission on the target zone. Store it in a Workers Secret, not KV.

---

## Verification

```bash
# 1. Tag a response
curl -I "https://example.com/api/products/42" | grep cache-tag
# Expected: cache-tag: entity:product:42,category:5

# 2. Confirm it's cached
curl -I "https://example.com/api/products/42" | grep cf-cache-status
# Expected: cf-cache-status: HIT

# 3. Trigger a write (price update) — emits purge event to Queue
curl -X PATCH "https://api.example.com/products/42" \
  -H 'Content-Type: application/json' \
  -d '{"price": 29.99}'

# 4. Within ~1 s (Queue consumer + DO batcher alarm window), re-check cache status
sleep 2
curl -I "https://example.com/api/products/42" | grep cf-cache-status
# Expected: cf-cache-status: MISS or EXPIRED (cache entry purged)

# 5. Verify purge audit in Analytics Engine
wrangler analytics-engine dataset query --dataset=purge_audit \
  "SELECT blob2, SUM(double1) AS tags_purged FROM SCHEMA GROUP BY blob2 ORDER BY tags_purged DESC LIMIT 10"
```

---

## Related

- `caching-topology-cloudflare-native.md` — full cache layer architecture
- `caching-layers-cloudflare-workers-kv-r2.md` — KV vs Cache API vs R2 trade-offs
- `temporal-decoupling-cloudflare-queues.md` — Queue semantics and delivery guarantees
- `async-job-queue-cloudflare-queues-do.md` — Queue consumer patterns
- `durable-object-alarm-api-scheduled-retry.md` — alarm API reference
- `request-coalescing-deduplication-edge.md` — preventing thundering herd on cache miss

---

## Sources

- Cloudflare Cache Purge API: https://developers.cloudflare.com/cache/how-to/purge-cache/
- Cloudflare Cache-Tag documentation: https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tags/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Cloudflare Cache API (Workers): https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
