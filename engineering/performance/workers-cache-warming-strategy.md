# Cache Warming Strategies for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After a deployment, Workers Cache API entries are cold: the first user request
for each URL hits the origin, adding 100–400 ms of latency until the cache
warms naturally. For high-traffic pages the cold-cache window is short. For
long-tail URLs (e.g., individual track pages) the cache may never warm because
traffic is sparse.

Common signals:
- Cache hit rate drops to 0 % immediately after every deploy.
- Origin error rate spikes for 2–5 minutes post-deploy as traffic arrives on a
  cold cache.
- Analytics show high TTFB on the first visit to rarely-requested pages.

---

## Context

Cloudflare's Cache API (`caches.default`) caches responses keyed by URL within
a data-centre's cache storage. Unlike Cloudflare's HTTP cache (which warms
automatically on the first external request that passes through the edge), Cache
API entries must be populated by the Worker itself via `cache.put()`.

Cache warming is the practice of proactively issuing subrequests to populate
these entries before real users arrive. The mechanism here uses:

- **Cloudflare Queues** to decouple warming from the deploy event.
- **Sitemap parsing** to discover URLs to warm.
- **Priority scoring** to warm high-traffic URLs first.
- **Rate-limiting** to avoid overwhelming the origin.

---

## Solution

```typescript
// cache-warmer.ts  — two exports: the Queue consumer and the warming Worker
import type { ExecutionContext, Queue, MessageBatch } from '@cloudflare/workers-types';

export interface Env {
  WARM_QUEUE: Queue<WarmTask>;
  CACHE_HIT_RATE: AnalyticsEngineDataset;
  SITEMAP_URL: string;          // e.g. https://example.com/sitemap.xml
  ORIGIN: string;               // internal origin to warm
  WARM_CONCURRENCY: string;     // number of parallel warm fetches per batch
  PRIORITY_PREFIXES: string;    // comma-separated URL prefixes to prioritise
}

interface WarmTask {
  url: string;
  priority: number; // 0 = lowest, 100 = highest
  attempt: number;
}

// ---------------------------------------------------------------------------
// Deploy-time trigger: parse sitemap and enqueue warm tasks
// Call this from a CI/CD pipeline after wrangler deploy:
//   curl -X POST https://api.example.com/_admin/warm-cache \
//        -H 'X-Warm-Token: <secret>'
// ---------------------------------------------------------------------------

export async function handleWarmTrigger(
  request: Request,
  env: Env
): Promise<Response> {
  const urls = await fetchSitemapUrls(env.SITEMAP_URL);
  const priorityPrefixes = env.PRIORITY_PREFIXES.split(',').map((p) => p.trim());

  const tasks: WarmTask[] = urls.map((url) => ({
    url,
    priority: scorePriority(url, priorityPrefixes),
    attempt: 0,
  }));

  // Sort descending so high-priority tasks are processed first
  tasks.sort((a, b) => b.priority - a.priority);

  // Enqueue in batches of 100 (Queue batch limit)
  const BATCH_SIZE = 100;
  for (let i = 0; i < tasks.length; i += BATCH_SIZE) {
    const batch = tasks.slice(i, i + BATCH_SIZE);
    await env.WARM_QUEUE.sendBatch(
      batch.map((task) => ({ body: task, delaySeconds: 0 }))
    );
  }

  return new Response(
    JSON.stringify({ enqueued: tasks.length }),
    { headers: { 'content-type': 'application/json' } }
  );
}

// ---------------------------------------------------------------------------
// Sitemap fetcher — handles sitemap index + sitemap files
// ---------------------------------------------------------------------------

async function fetchSitemapUrls(sitemapUrl: string): Promise<string[]> {
  const resp = await fetch(sitemapUrl);
  if (!resp.ok) throw new Error(`Sitemap fetch failed: ${resp.status}`);
  const text = await resp.text();

  // Detect sitemap index
  if (text.includes('<sitemapindex')) {
    const childUrls = [...text.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
      (m) => m[1].trim()
    );
    const childResults = await Promise.all(
      childUrls.map((u) => fetchSitemapUrls(u))
    );
    return childResults.flat();
  }

  // Regular sitemap
  return [...text.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1].trim());
}

// ---------------------------------------------------------------------------
// Priority scorer — higher score = warm first
// ---------------------------------------------------------------------------

function scorePriority(url: string, priorityPrefixes: string[]): number {
  const path = new URL(url).pathname;
  for (let i = 0; i < priorityPrefixes.length; i++) {
    if (path.startsWith(priorityPrefixes[i])) {
      // Earlier in the list = higher priority
      return 100 - i * 10;
    }
  }
  return 10; // default low priority for long-tail URLs
}

// ---------------------------------------------------------------------------
// Queue consumer: executes cache warming
// ---------------------------------------------------------------------------

export default {
  // Called when a WarmTask is dequeued
  async queue(
    batch: MessageBatch<WarmTask>,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    const concurrency = parseInt(env.WARM_CONCURRENCY || '5', 10);
    const messages = [...batch.messages];

    // Process in concurrent slices to avoid origin overload
    for (let i = 0; i < messages.length; i += concurrency) {
      const slice = messages.slice(i, i + concurrency);
      await Promise.allSettled(
        slice.map(async (msg) => {
          const task = msg.body;
          try {
            const warmed = await warmUrl(task.url, env);
            if (warmed) {
              msg.ack();
            } else {
              // Already cached — ack and record hit
              recordCacheEvent(env.CACHE_HIT_RATE, task.url, 'pre-warm-hit');
              msg.ack();
            }
          } catch (err) {
            if (task.attempt < 3) {
              // Re-enqueue with exponential backoff
              const delaySeconds = Math.pow(2, task.attempt) * 5;
              await env.WARM_QUEUE.send(
                { ...task, attempt: task.attempt + 1 },
                { delaySeconds }
              );
              msg.ack(); // ack original; retry is a new message
            } else {
              msg.ack(); // give up after 3 attempts
              console.error(`Cache warm failed for ${task.url}: ${err}`);
            }
          }
        })
      );
    }
  },

  // Regular request handler — records actual cache hits for comparison
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(request.url, { method: 'GET' });

    const cached = await cache.match(cacheKey);
    if (cached) {
      ctx.waitUntil(
        recordCacheEvent(env.CACHE_HIT_RATE, request.url, 'hit')
      );
      return cached;
    }

    const origin = await fetch(request);
    if (origin.ok) {
      const toCache = origin.clone();
      ctx.waitUntil(
        (async () => {
          await cache.put(cacheKey, toCache);
          recordCacheEvent(env.CACHE_HIT_RATE, request.url, 'miss');
        })()
      );
    }
    return origin;
  },
};

// ---------------------------------------------------------------------------
// Warming function
// Returns true if the URL was fetched and stored; false if already cached.
// ---------------------------------------------------------------------------

async function warmUrl(url: string, env: Env): Promise<boolean> {
  const cache = caches.default;
  const cacheKey = new Request(url, { method: 'GET' });

  const existing = await cache.match(cacheKey);
  if (existing) return false; // already warm

  const resp = await fetch(new Request(url, {
    headers: {
      'x-cache-warm': '1',
      'user-agent': 'orchords-cache-warmer/1.0',
    },
  }));

  if (!resp.ok) {
    throw new Error(`Origin returned ${resp.status} for ${url}`);
  }

  // Respect cache-control from origin; skip if no-store
  const cc = resp.headers.get('cache-control') ?? '';
  if (cc.includes('no-store') || cc.includes('private')) {
    return false;
  }

  await cache.put(cacheKey, resp);
  return true;
}

// ---------------------------------------------------------------------------
// Analytics Engine helper
// ---------------------------------------------------------------------------

function recordCacheEvent(
  dataset: AnalyticsEngineDataset,
  url: string,
  event: 'hit' | 'miss' | 'pre-warm-hit'
): void {
  try {
    dataset.writeDataPoint({
      blobs: [new URL(url).pathname, event],
      doubles: [1],
      indexes: [event],
    });
  } catch {
    // Non-critical
  }
}
```

---

## Implementation Details

**Cloudflare Queues** decouple the deploy trigger from the warming work. The CI
pipeline hits the `/_admin/warm-cache` endpoint, which enqueues thousands of
tasks without blocking. The Queue consumer processes them asynchronously at a
controlled rate.

**Priority ordering**: Tasks are sorted before enqueueing. Because Queues
deliver in approximate FIFO order, high-priority URLs reach the consumer first
and are cached before real traffic arrives.

**Concurrency control**: Processing `WARM_CONCURRENCY` URLs per tick (default
5) prevents origin overload. Tune this based on your origin's concurrency
capacity.

**Retry with backoff**: Transient origin errors (502, 503) are retried via
re-enqueueing with `delaySeconds`. After 3 attempts the task is abandoned and
logged.

**Cache hit rate measurement**: `AnalyticsEngineDataset.writeDataPoint` records
hit/miss events. Query `SELECT sum(doubles[0]) WHERE blobs[1] = 'hit'` vs
`'miss'` to compute hit rate before and after warming.

---

## Anti-patterns

- **Warming from the deploy hook synchronously**: Fetch + cache.put for 10 000
  URLs inline in a CI step will hit Worker CPU limits and timeout. Always use a
  Queue.
- **Warming private or authenticated pages**: Cache API stores responses at the
  edge without user context. Never warm responses that contain session data.
- **Ignoring `Cache-Control: no-store`**: The origin may intentionally prohibit
  caching. Respect it.
- **Over-warming long-tail URLs**: Warming 100 000 infrequently visited pages
  wastes origin capacity. Limit warming to URLs above a traffic threshold or
  matching priority prefixes.

---

## Gotchas

- `cache.put()` requires a GET or HEAD request as the cache key. POST responses
  cannot be cached.
- Cache entries created via `cache.put()` are local to the Cloudflare data
  centre that ran the Worker. The cache does not replicate globally. If you need
  global coverage, the warming Consumer must run in each data centre — use a
  Smart Queue with `migration_strategy: 'closest'` or trigger warming from
  multiple regions.
- Warmed responses do not inherit Cloudflare's CDN TTL rules. The TTL is
  whatever `Cache-Control` the origin returns.
- `sendBatch` has a maximum of 100 messages per call and 256 KB per message.

---

## Verification

```bash
# Trigger cache warming (from CI after deploy)
curl -X POST https://api.example.com/_admin/warm-cache \
  -H "X-Warm-Token: $WARM_TOKEN"

# Watch queue depth drain in Cloudflare dashboard:
# Workers & Pages → Queues → WARM_QUEUE → Consumers → Messages processed

# Query hit rate after warming:
# Analytics Engine GraphQL — compare hit counts 10 min before vs 10 min after
```

---

## Related

- `workers-connection-coalescing.md` — Parallel subrequests to reduce RTT during warming
- `workers-ttfb-optimization.md` — Streaming responses from the warm cache
- `d1-read-replica-pattern.md` — DB-level caching as complement to Cache API warming

---

## Sources

- [Cloudflare Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- [Cloudflare Queues — sendBatch](https://developers.cloudflare.com/queues/platform/javascript-apis/#sendbatch)
- [Analytics Engine — writeDataPoint](https://developers.cloudflare.com/analytics/analytics-engine/)
- [Sitemap protocol](https://www.sitemaps.org/protocol.html)
