# Write Coalescing and Batching with Durable Objects and D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
High-frequency write traffic — page-view counters, real-time leaderboards, shopping-cart mutations — would saturate D1's per-region write throughput if every event triggered an individual SQL statement. Write coalescing buffers mutations in a Durable Object and flushes them to D1 as a single batch on a fixed cadence.

## Context
D1 supports batch statements via `db.batch()` but the bottleneck is the number of individual round-trips, not the statement count within a single batch. A Durable Object serialises all concurrent requests to one JavaScript event loop so it can accumulate writes from thousands of simultaneous Workers and drain them periodically. The alarm API drives the flush schedule without a keep-alive connection. The pattern reduces D1 write RPCs by 2–3 orders of magnitude under load while keeping visible latency under 1 second.

## Durable Object — Write Buffer

The buffer accumulates deltas in memory and flushes to D1 on alarm.

```typescript
// src/durable-objects/write-buffer.ts
interface CounterDelta {
  entityId: string;
  table: string;
  column: string;
  delta: number;
}

interface SetDelta {
  entityId: string;
  table: string;
  fields: Record<string, string | number | null>;
}

type PendingWrite = { type: 'counter'; item: CounterDelta }
                 | { type: 'set'; item: SetDelta };

interface Env {
  DB: D1Database;
}

const FLUSH_INTERVAL_MS = 800;

export class WriteBuffer implements DurableObject {
  private pending: PendingWrite[] = [];
  private alarmScheduled = false;
  private storage: DurableObjectStorage;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.storage = state.storage;
    this.env = env;
  }

  async fetch(req: Request): Promise<Response> {
    const write = await req.json<PendingWrite>();
    this.pending.push(write);

    if (!this.alarmScheduled) {
      await this.storage.setAlarm(Date.now() + FLUSH_INTERVAL_MS);
      this.alarmScheduled = true;
    }

    return Response.json({ queued: true, pending: this.pending.length });
  }

  async alarm(): Promise<void> {
    this.alarmScheduled = false;
    if (this.pending.length === 0) return;

    const batch = this.pending.splice(0); // drain the buffer atomically
    await this.flush(batch);

    // Reschedule if more writes arrived during the flush
    if (this.pending.length > 0) {
      await this.storage.setAlarm(Date.now() + FLUSH_INTERVAL_MS);
      this.alarmScheduled = true;
    }
  }

  private async flush(writes: PendingWrite[]): Promise<void> {
    const stmts: D1PreparedStatement[] = [];

    // Coalesce counter deltas: group by (table, column, entityId) → sum deltas
    const counterMap = new Map<string, CounterDelta>();
    for (const w of writes) {
      if (w.type !== 'counter') continue;
      const key = `${w.item.table}::${w.item.column}::${w.item.entityId}`;
      const existing = counterMap.get(key);
      if (existing) {
        existing.delta += w.item.delta;
      } else {
        counterMap.set(key, { ...w.item });
      }
    }

    for (const c of counterMap.values()) {
      stmts.push(
        this.env.DB.prepare(
          `INSERT INTO ${c.table} (id, ${c.column})
           VALUES (?, ?)
           ON CONFLICT(id) DO UPDATE SET ${c.column} = ${c.column} + excluded.${c.column}`
        ).bind(c.entityId, c.delta)
      );
    }

    // Set writes: keep only the last value per entityId + table
    const setMap = new Map<string, SetDelta>();
    for (const w of writes) {
      if (w.type !== 'set') continue;
      const key = `${w.item.table}::${w.item.entityId}`;
      const existing = setMap.get(key);
      setMap.set(key, { ...w.item, fields: { ...(existing?.fields ?? {}), ...w.item.fields } });
    }

    for (const s of setMap.values()) {
      const cols = Object.keys(s.fields);
      const updates = cols.map((c) => `${c} = excluded.${c}`).join(', ');
      stmts.push(
        this.env.DB.prepare(
          `INSERT INTO ${s.table} (id, ${cols.join(', ')})
           VALUES (?, ${cols.map(() => '?').join(', ')})
           ON CONFLICT(id) DO UPDATE SET ${updates}`
        ).bind(s.entityId, ...Object.values(s.fields))
      );
    }

    if (stmts.length > 0) {
      await this.env.DB.batch(stmts);
    }
  }
}
```

## Worker-Side Client

Workers route writes by entity shard to avoid all traffic landing on one DO instance.

```typescript
// src/lib/write-buffer-client.ts
interface Env {
  WRITE_BUFFER: DurableObjectNamespace;
}

function shardId(env: Env, entityId: string): DurableObjectStub {
  // Shard by a prefix of the entity ID for horizontal scale
  const shard = entityId.slice(0, 2); // 256 possible shards
  const id = env.WRITE_BUFFER.idFromName(`shard-${shard}`);
  return env.WRITE_BUFFER.get(id);
}

export async function incrementCounter(
  env: Env,
  table: string,
  column: string,
  entityId: string,
  delta = 1
): Promise<void> {
  const stub = shardId(env, entityId);
  await stub.fetch('https://write-buffer/', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'counter', item: { entityId, table, column, delta } }),
  });
}

export async function setFields(
  env: Env,
  table: string,
  entityId: string,
  fields: Record<string, string | number | null>
): Promise<void> {
  const stub = shardId(env, entityId);
  await stub.fetch('https://write-buffer/', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'set', item: { entityId, table, fields } }),
  });
}
```

## Page-View Tracking Example

```typescript
// src/workers/analytics-ingest.ts
import { incrementCounter, setFields } from '../lib/write-buffer-client';

interface Env {
  WRITE_BUFFER: DurableObjectNamespace;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    const pageId = url.searchParams.get('page') ?? 'unknown';
    const visitorId = req.headers.get('cf-connecting-ip') ?? 'anon';

    ctx.waitUntil(
      Promise.all([
        incrementCounter(env, 'page_stats', 'view_count', pageId),
        setFields(env, 'page_last_visit', pageId, {
          visitor_id: visitorId,
          visited_at: Date.now(),
          country: req.cf?.country ?? null,
        }),
      ])
    );

    return new Response('ok', { status: 202 });
  },
};
```

## Drain Monitoring and Back-pressure

```typescript
// Inside WriteBuffer.fetch() — return pending depth so callers can shed load
const depth = this.pending.length;
if (depth > 5_000) {
  return Response.json(
    { queued: false, reason: 'buffer_full', depth },
    { status: 429 }
  );
}
```

## Anti-patterns
- Flushing on every request instead of on alarm — negates the entire benefit of buffering
- Using a single DO instance for all entity IDs — creates a hot shard under high write volume
- Storing the pending writes in DO persistent storage — slows every enqueue with a `put`; in-memory is intentional (the alarm is the durability boundary)
- Mixing reads into the write buffer DO — reads see stale in-memory state; route reads directly to D1

## Gotchas
- If the DO is evicted before the alarm fires (rare, but possible during a datacenter event), in-memory writes are lost; tolerable for counters, not for financial data
- `db.batch()` has a 100-statement limit per call; chunk `stmts` accordingly for very wide batches
- The `splice(0)` drain in `alarm()` must complete before any new await — if the DO crashes after splice but before the D1 batch commits, those writes are lost; for critical data pair with an outbox in D1 itself
- Worker-side `ctx.waitUntil` keeps the request alive after sending 202 but the DO flush still happens asynchronously

## Verification
```bash
# Send 1000 page-view events concurrently
seq 1 1000 | xargs -P 50 -I{} curl -s \
  "https://analytics.example.workers.dev/?page=home-{}" > /dev/null

# After ~1 second, query D1 for accumulated view counts
wrangler d1 execute mydb --command \
  "SELECT id, view_count FROM page_stats ORDER BY view_count DESC LIMIT 10"
```

## Related
- [Competing Consumers with Durable Objects](competing-consumers-durable-objects.md)
- [D1 Batch Operations Query Optimisation](d1-batch-operations-query-optimisation.md)
- [Durable Object Alarm API Scheduled Retry](durable-object-alarm-api-scheduled-retry.md)
- [Hot Partition Mitigation](hot-partition-mitigation.md)

## Sources
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- Tigerbeetle write-combining design notes: https://tigerbeetle.com/blog/2023-07-11-we-ditched-the-lock-free-skip-list/
