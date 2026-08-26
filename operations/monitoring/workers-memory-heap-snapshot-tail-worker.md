# Workers Memory Heap Snapshot Tail Worker

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker's CPU time stays within limits but response latency climbs over hours until the runtime isolate is evicted and replaced by a cold start. The likely culprit is memory pressure: large objects accumulating in module-scope variables, growing caches with no eviction policy, or closures retaining request data across invocations. Cloudflare does not expose a heap profiler in the edge runtime, but you can approximate memory growth through structured size sampling logged at key points, collected by a tail Worker, and written to Analytics Engine for trend analysis.

## Context

Workers isolates are lightweight V8 contexts. Each isolate has a **128 MB memory limit**; exceeding it causes the Worker to be killed mid-request. More commonly, a soft accumulation of module-level state across many requests causes the runtime to evict the isolate prematurely, generating cold starts at unexpected rates. Because the Cloudflare runtime exposes no `process.memoryUsage()` equivalent, memory observability requires a proxy approach:

1. Measure the `byteLength` of known in-memory structures (caches, queues, accumulated buffers).
2. Track the number of live entries in module-scope `Map` / `Set` / `Array` instances.
3. Log these metrics as structured JSON on each request.
4. Collect them in a tail Worker and write time-series data to Analytics Engine.
5. Alert when growth is monotonically increasing across a rolling window.

---

## 1. Instrumented Cache with Size Tracking

Wrap your module-level cache in a class that tracks its own approximate byte size. Call `snapshot()` on each request and log the result.

```typescript
// worker/src/cache.ts

export class SizedCache<K extends string, V> {
  private store = new Map<K, { value: V; bytes: number; addedAt: number }>();
  private totalBytes = 0;
  readonly maxEntries: number;

  constructor(maxEntries = 500) {
    this.maxEntries = maxEntries;
  }

  set(key: K, value: V, approximateBytes: number): void {
    if (this.store.has(key)) {
      const existing = this.store.get(key)!;
      this.totalBytes -= existing.bytes;
      this.store.delete(key);
    }

    // Evict oldest entry when over capacity
    if (this.store.size >= this.maxEntries) {
      const oldest = this.store.keys().next().value;
      if (oldest !== undefined) {
        this.totalBytes -= this.store.get(oldest)!.bytes;
        this.store.delete(oldest);
      }
    }

    this.store.set(key, { value, bytes: approximateBytes, addedAt: Date.now() });
    this.totalBytes += approximateBytes;
  }

  get(key: K): V | undefined {
    return this.store.get(key)?.value;
  }

  snapshot(): { entries: number; approximateBytes: number; oldestEntryAgeMs: number } {
    let oldestTs = Date.now();
    for (const { addedAt } of this.store.values()) {
      if (addedAt < oldestTs) oldestTs = addedAt;
    }
    return {
      entries: this.store.size,
      approximateBytes: this.totalBytes,
      oldestEntryAgeMs: this.store.size > 0 ? Date.now() - oldestTs : 0,
    };
  }

  evictOlderThan(maxAgeMs: number): number {
    const cutoff = Date.now() - maxAgeMs;
    let evicted = 0;
    for (const [key, meta] of this.store.entries()) {
      if (meta.addedAt < cutoff) {
        this.totalBytes -= meta.bytes;
        this.store.delete(key);
        evicted++;
      }
    }
    return evicted;
  }
}
```

---

## 2. Emitting Memory Snapshots Per-Request

In the Worker's `fetch` handler, snapshot all known module-scope structures and emit them as a structured log line.

```typescript
// worker/src/index.ts

import { SizedCache } from "./cache.js";

// Module-level state — this persists across requests within an isolate
const responseCache = new SizedCache<string, string>(1000);
const pendingJobs = new Map<string, unknown>();
let totalBytesProcessed = 0;

function approximateStringBytes(s: string): number {
  // UTF-16 in V8: 2 bytes per char for ASCII, 4 for supplementary
  return s.length * 2;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const cacheKey = url.pathname;

    // Evict stale entries on every request (keep isolate healthy)
    responseCache.evictOlderThan(5 * 60_000);

    const cached = responseCache.get(cacheKey);
    if (cached) {
      const snap = responseCache.snapshot();
      console.log(JSON.stringify({
        event: "memory.snapshot",
        cacheEntries: snap.entries,
        cacheBytes: snap.approximateBytes,
        pendingJobs: pendingJobs.size,
        totalBytesProcessed,
        cacheHit: true,
      }));
      return new Response(cached, { headers: { "Content-Type": "application/json" } });
    }

    const body = JSON.stringify({ path: cacheKey, ts: Date.now() });
    totalBytesProcessed += approximateStringBytes(body);
    responseCache.set(cacheKey, body, approximateStringBytes(body));

    const snap = responseCache.snapshot();
    console.log(JSON.stringify({
      event: "memory.snapshot",
      cacheEntries: snap.entries,
      cacheBytes: snap.approximateBytes,
      cacheOldestEntryAgeMs: snap.oldestEntryAgeMs,
      pendingJobs: pendingJobs.size,
      totalBytesProcessed,
      cacheHit: false,
    }));

    return new Response(body, { headers: { "Content-Type": "application/json" } });
  },
};
```

---

## 3. Tail Worker — Collecting Memory Metrics into Analytics Engine

```typescript
// tail-worker/src/index.ts

import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env {
  MEMORY_METRICS: AnalyticsEngineDataset;
}

interface MemorySnapshot {
  event: string;
  cacheEntries?: number;
  cacheBytes?: number;
  cacheOldestEntryAgeMs?: number;
  pendingJobs?: number;
  totalBytesProcessed?: number;
  cacheHit?: boolean;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const workerName = event.scriptName ?? "unknown";

      for (const log of event.logs) {
        let parsed: MemorySnapshot;
        try {
          const raw = typeof log.message[0] === "string"
            ? log.message[0]
            : JSON.stringify(log.message[0]);
          parsed = JSON.parse(raw);
        } catch {
          continue;
        }

        if (parsed.event !== "memory.snapshot") continue;

        env.MEMORY_METRICS.writeDataPoint({
          blobs: [
            workerName,                                   // blob1: worker name
            event.outcome,                                // blob2: invocation outcome
          ],
          doubles: [
            parsed.cacheEntries ?? 0,                     // double1: cache size (entries)
            parsed.cacheBytes ?? 0,                       // double2: cache size (bytes)
            parsed.cacheOldestEntryAgeMs ?? 0,            // double3: oldest entry age ms
            parsed.pendingJobs ?? 0,                      // double4: pending jobs in module scope
            parsed.totalBytesProcessed ?? 0,              // double5: cumulative bytes processed
            parsed.cacheHit ? 1 : 0,                      // double6: cache hit flag
          ],
          indexes: [workerName],
        });
      }
    }
  },
};
```

---

## 4. Analytics Engine Queries for Memory Trend Detection

```sql
-- Average cache byte size per hour over the last 24 hours
-- A monotonically increasing trend indicates a leak
SELECT
  toStartOfHour(timestamp)           AS hour,
  blob1                              AS worker,
  AVG(double2)                       AS avg_cache_bytes,
  MAX(double2)                       AS peak_cache_bytes,
  AVG(double1)                       AS avg_cache_entries,
  COUNT()                            AS sample_count
FROM MEMORY_METRICS
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY hour, worker
ORDER BY hour ASC, worker;

-- Isolates with cache growth > 10 MB in the last hour
SELECT
  blob1  AS worker,
  MAX(double2) - MIN(double2) AS byte_growth,
  MAX(double2)                AS peak_bytes
FROM MEMORY_METRICS
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY worker
HAVING byte_growth > 10485760
ORDER BY byte_growth DESC;
```

---

## 5. Alerting on Sustained Memory Growth

A scheduled Worker cron queries Analytics Engine and fires a Slack alert if the cache grows beyond a threshold without declining.

```typescript
// alert-worker/src/index.ts

export interface Env {
  CF_ACCOUNT_ID: string;
  AE_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(checkMemoryGrowth(env));
  },
};

async function checkMemoryGrowth(env: Env): Promise<void> {
  const sql = `
    SELECT
      blob1                                              AS worker,
      MAX(double2) - MIN(double2)                        AS byte_growth,
      MAX(double2)                                       AS peak_bytes,
      COUNT()                                            AS samples
    FROM MEMORY_METRICS
    WHERE timestamp > NOW() - INTERVAL '1' HOUR
    GROUP BY worker
    HAVING byte_growth > 5242880
    ORDER BY byte_growth DESC
    LIMIT 10
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.AE_TOKEN}` },
      body: sql,
    },
  );

  const data = await res.json() as { data: Array<{ worker: string; byte_growth: number; peak_bytes: number }> };
  if (!data.data || data.data.length === 0) return;

  const lines = data.data.map(
    (r) => `• *${r.worker}*: grew ${(r.byte_growth / 1024 / 1024).toFixed(1)} MB, peak ${(r.peak_bytes / 1024 / 1024).toFixed(1)} MB`,
  );

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `:warning: *Worker memory growth detected*\n${lines.join("\n")}`,
    }),
  });
}
```

---

## Anti-patterns

- **Logging on every subrequest** — memory snapshots should be logged once per top-level invocation, not per subrequest; logging per subrequest inflates Analytics Engine write costs and makes averages meaningless.
- **Using `JSON.stringify(bigObject).length` inline in hot paths** — serialising a large module-scope object to measure its size is expensive and can itself cause GC pressure; track byte sizes incrementally at `set` time.
- **Treating `totalBytesProcessed` as a proxy for live heap size** — cumulative throughput is not the same as live memory; track live entry counts and byte estimates of current collections, not historical throughput.
- **Skipping eviction** — a `SizedCache` without a TTL-based eviction call is functionally a memory leak; call `evictOlderThan` on every request or in a cron trigger.

## Gotchas

- The tail Worker's `TailEvent` does not include the Worker's actual V8 heap size; everything here is a **proxy measurement** derived from application-level accounting. It is directional, not precise.
- Workers isolates are **not shared across requests on different edge nodes**; a cache that looks healthy in Analytics Engine averages might be leaking on a small subset of PoPs that happen to be receiving sticky traffic.
- `wrangler tail` in development reflects log output from a single local isolate; production memory growth often only manifests after hundreds of requests on long-lived isolates.
- Module-scope Maps and Sets are **not reset between requests** within an isolate but **are reset on cold start**; a sudden drop in `cacheEntries` in your Analytics Engine data signals an isolate restart, not intentional eviction.

## Verification

```bash
# 1. Deploy all workers
wrangler deploy --config worker/wrangler.toml
wrangler deploy --config tail-worker/wrangler.toml

# 2. Drive 200 unique-path requests to force cache growth
for i in $(seq 1 200); do
  curl -s "https://my-worker.example.workers.dev/path-$i" > /dev/null
done

# 3. After ~60 s, query Analytics Engine for the trend
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $AE_TOKEN" \
  --data "SELECT AVG(double2) AS avg_bytes, MAX(double2) AS peak_bytes FROM MEMORY_METRICS WHERE timestamp > NOW() - INTERVAL '10' MINUTE"

# 4. Confirm avg_bytes and peak_bytes are increasing as requests accumulate
# 5. Verify eviction kicks in by looking for a plateau or decline
```

## Related

- `durable-objects-memory-tail-workers.md`
- `tail-worker-structured-log-sampling-strategies.md`
- `worker-cpu-monitoring.md`
- `cold-start-latency-monitoring.md`
- `workers-cpu-time-percentile-analytics-engine.md`

## Sources

- Cloudflare Workers Limits — developers.cloudflare.com/workers/platform/limits
- Cloudflare Tail Workers — developers.cloudflare.com/workers/observability/tail-workers
- V8 Heap and Memory Management — v8.dev/blog/trash-talk
- Cloudflare Analytics Engine — developers.cloudflare.com/analytics/analytics-engine
