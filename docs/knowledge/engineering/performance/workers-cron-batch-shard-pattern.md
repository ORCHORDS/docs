# Workers Cron Trigger Sharding for Large Dataset Batch Processing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A nightly cron job scans a D1 table of 500 000 rows to send digest emails. The Worker processes rows in a loop but hits the **15-minute wall-clock limit** or the **30-second CPU time limit** (Bundled Workers) before completing. Increasing batch size causes memory pressure; decreasing it means the job never finishes before the next run starts.

## Context

Workers cron triggers (`[triggers]` in `wrangler.toml`) are single invocations subject to the same runtime limits as fetch handlers. A Bundled Worker gets 10 ms CPU time per invocation; an **Unbound (Standard) Worker** gets up to 5 minutes of CPU time but the wall-clock limit for scheduled events is 15 minutes. For datasets that cannot be processed in a single invocation, the options are:

1. **Shard with multiple cron expressions** that each process a slice of the dataset.
2. **Fan out to Queues**: the cron trigger enqueues work items; queue consumers process them in parallel.
3. **Cursor checkpoint in KV**: a single cron run processes as much as it can and writes a cursor to KV; the next invocation picks up where it left off.

Strategy 1 is simplest for time-sharded data. Strategy 2 is best for throughput. Strategy 3 handles arbitrary dataset sizes without needing multiple cron expressions.

---

## Strategy 1: Environment-Variable Shards with Multiple Cron Expressions

```toml
# wrangler.toml — four Workers, each processing one shard
[[env.shard0.triggers]]
crons = ["0 3 * * *"]   # 03:00 UTC

[[env.shard1.triggers]]
crons = ["5 3 * * *"]   # 03:05 UTC

[[env.shard2.triggers]]
crons = ["10 3 * * *"]  # 03:10 UTC

[[env.shard3.triggers]]
crons = ["15 3 * * *"]  # 03:15 UTC

[env.shard0.vars]
SHARD_INDEX = "0"
SHARD_COUNT = "4"

[env.shard1.vars]
SHARD_INDEX = "1"
SHARD_COUNT = "4"

# etc.
```

```typescript
// src/index.ts
interface Env {
  DB: D1Database;
  SHARD_INDEX: string;
  SHARD_COUNT: string;
  MAILER_QUEUE: Queue<{ userId: string; email: string }>;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const shardIndex = Number(env.SHARD_INDEX);
    const shardCount = Number(env.SHARD_COUNT);

    // Modulo shard: user rows whose (id % shardCount) === shardIndex
    const stmt = env.DB.prepare(`
      SELECT id, email FROM users
      WHERE (CAST(id AS INTEGER) % ?) = ?
        AND digest_enabled = 1
      LIMIT 5000
    `);

    const { results } = await stmt.bind(shardCount, shardIndex).all<{ id: string; email: string }>();

    // Fan out to Queue in batches of 100
    const BATCH = 100;
    for (let i = 0; i < results.length; i += BATCH) {
      const slice = results.slice(i, i + BATCH);
      await env.MAILER_QUEUE.sendBatch(
        slice.map(row => ({ body: { userId: row.id, email: row.email } }))
      );
    }

    console.log(`Shard ${shardIndex}/${shardCount}: queued ${results.length} emails`);
  },
} satisfies ExportedHandler<Env>;
```

---

## Strategy 2: Queue Fan-out from a Single Cron Trigger

```typescript
interface Env {
  DB: D1Database;
  WORK_QUEUE: Queue<{ userId: string; email: string }>;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Enqueue all rows; the queue consumer does the heavy work at full concurrency
    let cursor: string | null = null;
    let total = 0;
    const PAGE = 1000;

    do {
      const stmt = cursor
        ? env.DB.prepare("SELECT id, email FROM users WHERE digest_enabled=1 AND id > ? ORDER BY id LIMIT ?")
            .bind(cursor, PAGE)
        : env.DB.prepare("SELECT id, email FROM users WHERE digest_enabled=1 ORDER BY id LIMIT ?")
            .bind(PAGE);

      const { results } = await stmt.all<{ id: string; email: string }>();
      if (!results.length) break;

      await env.WORK_QUEUE.sendBatch(
        results.map(r => ({ body: { userId: r.id, email: r.email } }))
      );

      total += results.length;
      cursor = results[results.length - 1].id;
    } while (results.length === PAGE);

    console.log(`Cron: enqueued ${total} digest jobs`);
  },
} satisfies ExportedHandler<Env>;
```

---

## Strategy 3: KV Cursor Checkpointing for Resumable Runs

```typescript
interface Env {
  DB: D1Database;
  STATE_KV: KVNamespace;
  MAILER_QUEUE: Queue<{ userId: string; email: string }>;
}

const CURSOR_KEY = "digest:cursor";
const PAGE_SIZE = 2000;
const MAX_WALL_MS = 12 * 60 * 1000; // 12 min — leave 3 min buffer under 15 min limit

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const runStart = Date.now();

    // Resume from last checkpoint or start from beginning
    let cursor = (await env.STATE_KV.get(CURSOR_KEY)) ?? "0";
    let processed = 0;
    let exhausted = false;

    while (Date.now() - runStart < MAX_WALL_MS) {
      const { results } = await env.DB.prepare(`
        SELECT id, email FROM users
        WHERE digest_enabled = 1 AND id > ?
        ORDER BY id LIMIT ?
      `).bind(cursor, PAGE_SIZE).all<{ id: string; email: string }>();

      if (!results.length) {
        exhausted = true;
        break;
      }

      await env.MAILER_QUEUE.sendBatch(
        results.map(r => ({ body: { userId: r.id, email: r.email } }))
      );

      processed += results.length;
      cursor = results[results.length - 1].id;

      // Checkpoint: persist cursor so the next cron invocation can resume
      await env.STATE_KV.put(CURSOR_KEY, cursor);
    }

    if (exhausted) {
      // Full pass complete; reset cursor for the next scheduled run
      await env.STATE_KV.delete(CURSOR_KEY);
      console.log(`Cron: completed full pass, processed ${processed} rows`);
    } else {
      console.log(`Cron: time limit reached after ${processed} rows; resuming from ${cursor}`);
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Cron Schedule Reference for Common Sharding Scenarios

```typescript
// Utility to validate that shard crons are non-overlapping
function cronSlots(baseHour: number, shards: number, offsetMinutes = 5): string[] {
  return Array.from({ length: shards }, (_, i) => {
    const minute = (i * offsetMinutes) % 60;
    const hour = baseHour + Math.floor((i * offsetMinutes) / 60);
    return `${minute} ${hour} * * *`;
  });
}

// Example: 4 shards starting at 03:00, 5-minute gaps
// ["0 3 * * *", "5 3 * * *", "10 3 * * *", "15 3 * * *"]
console.log(cronSlots(3, 4));
```

---

## Tracking Shard Progress with Analytics Engine

```typescript
interface Env {
  DB: D1Database;
  STATE_KV: KVNamespace;
  MAILER_QUEUE: Queue<{ userId: string; email: string }>;
  ANALYTICS: AnalyticsEngineDataset;
}

function recordShardRun(
  analytics: AnalyticsEngineDataset,
  shardIndex: number,
  processed: number,
  exhausted: boolean,
  durationMs: number
): void {
  analytics.writeDataPoint({
    blobs: [String(shardIndex), exhausted ? "complete" : "partial"],
    doubles: [processed, durationMs],
    indexes: ["digest-cron"],
  });
}
```

---

## Anti-patterns

- **Single cron trigger, synchronous row-by-row processing**: each `await db.prepare().run()` per row compounds latency; 500 k rows at 1 ms each = 500 s, far beyond the 15-minute wall-clock limit.
- **Modulo sharding on a non-integer UUID primary key**: `id % 4` only works on integer IDs. For UUIDs, shard on a derived integer (`ABS(CAST(SUBSTR(id,1,8) AS INTEGER)) % 4`) or use date-range sharding.
- **Resetting cursor at the start of each run instead of after completion**: if a run fails mid-way the cursor is lost and the next run restarts from the beginning, doubling work.
- **Using cron with a 1-minute interval to simulate stream processing**: cron triggers have cold-start cost; use **Workers Queues** or **Durable Objects alarms** for sub-minute polling.

## Gotchas

- **Unbound Workers scheduled event CPU**: Standard plan Workers scheduled events have up to **5 minutes of CPU time** and **15 minutes wall-clock**. Bundled plan is capped at **30 seconds CPU**. Confirm your plan before choosing strategy.
- `wrangler.toml` cron expressions are **UTC only**. Daylight saving time is irrelevant, but communicating with stakeholders about local-time equivalents is the developer's responsibility.
- Multiple cron expressions for the same Worker **cannot share state within a single run** without KV or Durable Objects—each invocation is an independent isolate.
- The Cloudflare scheduler fires crons **within ±30 seconds of the specified minute** under normal conditions; don't rely on sub-minute precision for sequencing.

## Verification

```bash
# Trigger a cron manually from Wrangler for testing
wrangler dev --test-scheduled
# In a second terminal:
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Confirm cursor checkpoint in KV after a partial run
wrangler kv key get --namespace-id=<ID> "digest:cursor"

# Check Analytics Engine shard completion rate
# SELECT blob2, count() FROM dataset WHERE indexes_0 = 'digest-cron'
#   AND timestamp > NOW() - INTERVAL '24' HOUR GROUP BY blob2
```

## Related

- `workers-cron-trigger-self-healing-retry.md`
- `d1-cursor-pagination-keyset-performance.md`
- `queues-consumer-concurrency-throughput.md`
- `queues-throughput-batching.md`
- `workers-waituntil-background-processing.md`

## Sources

- Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Workers Limits (scheduled): https://developers.cloudflare.com/workers/platform/limits/#worker-limits
- Queues `sendBatch`: https://developers.cloudflare.com/queues/examples/send-batch/
