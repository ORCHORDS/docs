# KV Cache Hit Rate Analytics Engine Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Workers application uses KV as its caching layer in front of a D1 database. Response times are within SLO on average, but P95 latency spikes every few minutes — a pattern consistent with KV misses forcing synchronous D1 reads. You need to measure the KV hit rate per key prefix, detect when it drops below an acceptable threshold, and alert before the miss storm cascades into D1 latency degradation. Cloudflare does not expose a native KV cache hit metric; you must instrument it at the application layer and write it to Analytics Engine.

## Context

Cloudflare KV is an eventually consistent key-value store with a built-in read cache at the edge. A "hit" means the value was served from the edge cache without a remote read; a "miss" means the edge had to fetch from the central KV store (adding ~20–50 ms) or the key did not exist (requiring a fallback to D1). The KV API does not distinguish between edge cache hits and central-store hits — both return a value — so the only reliable signal is whether `kv.get()` returned `null` (a miss) or a value (a hit).

The monitoring pattern:
1. Wrap all `kv.get` calls in a typed helper that records hit/miss.
2. Emit a structured log line per request with hit count, miss count, and key prefix breakdown.
3. Collect in a tail Worker and write to Analytics Engine.
4. Alert when the rolling hit rate drops below an SLO threshold per key prefix.

---

## 1. KV Access Wrapper with Hit/Miss Tracking

```typescript
// worker/src/kv-instrumented.ts

import type { KVNamespace } from "@cloudflare/workers-types";

export interface KvHitRecord {
  prefix: string;
  hits: number;
  misses: number;
  totalLatencyMs: number;
}

export class InstrumentedKv {
  private readonly kv: KVNamespace;
  private readonly records = new Map<string, KvHitRecord>();

  constructor(kv: KVNamespace) {
    this.kv = kv;
  }

  private prefixOf(key: string): string {
    // Use the first path segment as the prefix, e.g. "user:123" → "user"
    const colon = key.indexOf(":");
    return colon > -1 ? key.slice(0, colon) : key;
  }

  async get<T = string>(
    key: string,
    options?: Parameters<KVNamespace["get"]>[1],
  ): Promise<T | null> {
    const prefix = this.prefixOf(key);
    const t0 = Date.now();
    const value = await this.kv.get(key, options as never) as T | null;
    const latencyMs = Date.now() - t0;

    const existing = this.records.get(prefix) ?? { prefix, hits: 0, misses: 0, totalLatencyMs: 0 };
    if (value !== null) {
      existing.hits++;
    } else {
      existing.misses++;
    }
    existing.totalLatencyMs += latencyMs;
    this.records.set(prefix, existing);

    return value;
  }

  async put(
    key: string,
    value: string,
    options?: Parameters<KVNamespace["put"]>[2],
  ): Promise<void> {
    return this.kv.put(key, value, options);
  }

  async delete(key: string): Promise<void> {
    return this.kv.delete(key);
  }

  /** Drain all accumulated hit/miss records. Call once per request before logging. */
  drain(): KvHitRecord[] {
    const records = Array.from(this.records.values());
    this.records.clear();
    return records;
  }
}
```

---

## 2. Worker with Per-Request KV Metrics Logging

```typescript
// worker/src/index.ts

import type { KVNamespace, D1Database } from "@cloudflare/workers-types";
import { InstrumentedKv } from "./kv-instrumented.js";

export interface Env {
  CACHE: KVNamespace;
  DB: D1Database;
}

const KV_TTL_SECONDS = 300; // 5-minute TTL for cached values

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get("userId");
    if (!userId) return new Response("missing userId", { status: 400 });

    const kv = new InstrumentedKv(env.CACHE);
    const t0 = Date.now();

    // Attempt KV cache read
    let profile = await kv.get<string>(`user:${userId}`, "text");

    if (profile === null) {
      // KV miss — fall back to D1
      const row = await env.DB.prepare(
        "SELECT id, name, email FROM users WHERE id = ?",
      ).bind(userId).first<{ id: string; name: string; email: string }>();

      if (!row) return new Response("not found", { status: 404 });

      profile = JSON.stringify(row);

      // Backfill KV asynchronously
      ctx.waitUntil(
        env.CACHE.put(`user:${userId}`, profile, { expirationTtl: KV_TTL_SECONDS }),
      );
    }

    const kvRecords = kv.drain();
    const totalDurationMs = Date.now() - t0;

    // Emit structured log — collected by tail Worker
    console.log(JSON.stringify({
      event: "request.complete",
      path: url.pathname,
      durationMs: totalDurationMs,
      kvMetrics: kvRecords,
    }));

    return new Response(profile, {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 3. Tail Worker — Write KV Metrics to Analytics Engine

```typescript
// tail-worker/src/index.ts

import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env {
  KV_HIT_RATE: AnalyticsEngineDataset;
}

interface KvHitRecord {
  prefix: string;
  hits: number;
  misses: number;
  totalLatencyMs: number;
}

interface RequestCompleteLog {
  event: string;
  path?: string;
  durationMs?: number;
  kvMetrics?: KvHitRecord[];
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const workerName = event.scriptName ?? "unknown";

      for (const log of event.logs) {
        let parsed: RequestCompleteLog;
        try {
          const raw = typeof log.message[0] === "string"
            ? log.message[0]
            : JSON.stringify(log.message[0]);
          parsed = JSON.parse(raw);
        } catch {
          continue;
        }

        if (parsed.event !== "request.complete" || !parsed.kvMetrics?.length) continue;

        for (const rec of parsed.kvMetrics) {
          const total = rec.hits + rec.misses;
          if (total === 0) continue;

          const hitRate = rec.hits / total;

          env.KV_HIT_RATE.writeDataPoint({
            blobs: [
              rec.prefix,                          // blob1: KV key prefix
              workerName,                          // blob2: worker name
              parsed.path ?? "unknown",            // blob3: request path
            ],
            doubles: [
              rec.hits,                            // double1: hit count
              rec.misses,                          // double2: miss count
              total,                               // double3: total lookups
              hitRate,                             // double4: hit rate 0–1
              rec.totalLatencyMs,                  // double5: total latency for this prefix
              total > 0 ? rec.totalLatencyMs / total : 0, // double6: avg latency per lookup
            ],
            indexes: [rec.prefix],                // index: filter per prefix in AE SQL
          });
        }
      }
    }
  },
};
```

---

## 4. Analytics Engine Queries for Hit Rate SLO Tracking

```sql
-- Rolling 1-hour hit rate per KV prefix
SELECT
  blob1                        AS kv_prefix,
  SUM(double1)                 AS total_hits,
  SUM(double2)                 AS total_misses,
  SUM(double3)                 AS total_lookups,
  SUM(double1) / SUM(double3)  AS hit_rate,
  AVG(double6)                 AS avg_lookup_latency_ms
FROM KV_HIT_RATE
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY kv_prefix
ORDER BY hit_rate ASC;

-- Per-minute hit rate trend for the "user" prefix (detect cache warming/expiry events)
SELECT
  toStartOfMinute(timestamp)   AS minute,
  SUM(double1) / SUM(double3)  AS hit_rate,
  SUM(double2)                 AS misses
FROM KV_HIT_RATE
WHERE blob1 = 'user'
  AND timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY minute
ORDER BY minute ASC;

-- Workers with the worst KV hit rates in the last 30 minutes
SELECT
  blob2                        AS worker,
  blob1                        AS kv_prefix,
  SUM(double1) / SUM(double3)  AS hit_rate,
  SUM(double3)                 AS lookups
FROM KV_HIT_RATE
WHERE timestamp > NOW() - INTERVAL '30' MINUTE
GROUP BY worker, kv_prefix
HAVING hit_rate < 0.8 AND lookups > 50
ORDER BY hit_rate ASC
LIMIT 20;
```

---

## 5. Cron Alert Worker for Hit Rate SLO Breach

```typescript
// alert-worker/src/index.ts

export interface Env {
  CF_ACCOUNT_ID: string;
  AE_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
  HIT_RATE_SLO: string; // e.g. "0.9" — 90%
}

export default {
  async scheduled(_evt: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(checkHitRateSlo(env));
  },
};

async function checkHitRateSlo(env: Env): Promise<void> {
  const slo = parseFloat(env.HIT_RATE_SLO ?? "0.9");

  const sql = `
    SELECT
      blob1                        AS kv_prefix,
      blob2                        AS worker,
      SUM(double1) / SUM(double3)  AS hit_rate,
      SUM(double2)                 AS misses,
      SUM(double3)                 AS lookups
    FROM KV_HIT_RATE
    WHERE timestamp > NOW() - INTERVAL '5' MINUTE
    GROUP BY kv_prefix, worker
    HAVING hit_rate < ${slo} AND lookups > 20
    ORDER BY hit_rate ASC
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

  const json = await res.json() as {
    data: Array<{ kv_prefix: string; worker: string; hit_rate: number; misses: number; lookups: number }>
  };

  if (!json.data?.length) return;

  const lines = json.data.map(
    (r) => `• prefix \`${r.kv_prefix}\` on \`${r.worker}\`: hit rate ${(r.hit_rate * 100).toFixed(1)}% (${r.misses} misses / ${r.lookups} total)`,
  );

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `:warning: *KV hit rate below ${(slo * 100).toFixed(0)}% SLO*\n${lines.join("\n")}\nThis may indicate cache expiry, cold isolates, or TTL misconfiguration.`,
    }),
  });
}
```

---

## Anti-patterns

- **Measuring hit rate across all keys without prefix segmentation** — a single aggregate hit rate hides which key families are cold; always group by prefix so you can distinguish user cache misses from config cache misses.
- **Treating `kv.get()` latency as a proxy for hit vs. miss** — KV latency varies by PoP and key size; a slow hit can appear slower than a fast miss. Use the return value (`null` = miss), not latency, as the signal.
- **Logging KV metrics on every individual key lookup** — that generates O(keys-per-request) log lines; accumulate into per-prefix counters and emit once per request with `drain()`.
- **Setting the SLO threshold below 70%** — KV is designed as a cache, not a database; if more than 30% of reads are misses, the issue is usually TTL configuration or the absence of a cache-warming strategy, not an infrastructure problem.

## Gotchas

- The `InstrumentedKv` class uses `new Map()` at construction time. Because it is constructed inside the `fetch` handler (not at module scope), it is a fresh instance per request — there is no cross-request state accumulation.
- KV `get` returning `null` can mean the key does not exist **or** the key exists but has expired. The instrumentation does not distinguish these; for eviction analysis you need a separate key-existence audit.
- Analytics Engine data is available with a ~60 s lag; the 5-minute window in the alert query means the earliest you can detect a miss surge is roughly 65 seconds after it begins.
- KV has a **free tier read limit of 100,000 reads per day**; the `InstrumentedKv` wrapper adds no extra reads, but ensure your Workers are not inflating read counts with speculative pre-fetching.

## Verification

```bash
# 1. Deploy with tail worker bound
wrangler deploy --config worker/wrangler.toml
wrangler deploy --config tail-worker/wrangler.toml

# 2. Warm the cache with 10 requests for the same userId
for i in $(seq 1 10); do
  curl -s "https://my-worker.example.workers.dev/?userId=abc123" > /dev/null
done

# 3. Expire the KV key and fire 10 more requests (they should miss)
wrangler kv key delete --namespace-id $KV_NAMESPACE_ID "user:abc123"
for i in $(seq 1 10); do
  curl -s "https://my-worker.example.workers.dev/?userId=abc123" > /dev/null
done

# 4. After ~90 s, query AE to confirm hits vs. misses recorded
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $AE_TOKEN" \
  --data "SELECT blob1, SUM(double1) AS hits, SUM(double2) AS misses FROM KV_HIT_RATE WHERE timestamp > NOW() - INTERVAL '10' MINUTE GROUP BY blob1"

# 5. Confirm "user" prefix shows ~10 misses and ~10 hits
```

## Related

- `kv-operation-rate-analytics-engine.md`
- `kv-stale-read-ratio-slo-analytics-engine.md`
- `cache-hit-rate-monitoring.md`
- `workers-kv-latency-consistency-monitoring.md`
- `d1-query-latency-histogram-analytics-engine.md`

## Sources

- Cloudflare KV Documentation — developers.cloudflare.com/kv
- Cloudflare KV Limits — developers.cloudflare.com/kv/platform/limits
- Cloudflare Analytics Engine — developers.cloudflare.com/analytics/analytics-engine
- Cloudflare Workers Tail Workers — developers.cloudflare.com/workers/observability/tail-workers
