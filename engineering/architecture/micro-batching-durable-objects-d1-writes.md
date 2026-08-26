# Micro-batching D1 Writes with Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project reaction events arrive at 500–2,000 req/s during viral post spikes. Each reaction triggers an individual D1 INSERT. At that volume, D1's per-write latency (~5–15 ms round-trip) means the write path becomes the bottleneck, Workers start queuing, and costs spike because D1 bills per query. The solution is to accumulate writes in a Durable Object buffer and flush them to D1 in a single batched INSERT every 250–500 ms, reducing the number of D1 queries by 100–400× while keeping end-to-end latency bounded.

## Context

**Micro-batching** is a flow-control pattern that trades a small, bounded amount of latency at the application layer to achieve significantly higher throughput and lower cost at the persistence layer. The Durable Object acts as a stateful accumulator: Workers append to the buffer via a service binding, and a Durable Object alarm flushes the buffer to D1 on a fixed cadence. This is distinct from the `write-coalescing-durable-objects-d1.md` article (which coalesces concurrent writes to the *same key*) — micro-batching accumulates writes to *different keys* for the purpose of bulk INSERT efficiency.

## 1. Buffer Accumulator Durable Object

The DO holds an in-memory array of pending writes. An alarm is scheduled on the first write after a flush; subsequent writes within the flush window just append to the array without triggering additional alarms.

```typescript
interface ReactionWrite {
  userId: string;
  postId: string;
  emoji: string;
  ts: number;
}

export class ReactionBatcherDO implements DurableObject {
  private buffer: ReactionWrite[] = [];
  private alarmScheduled = false;
  private readonly flushIntervalMs = 300;
  private readonly maxBufferSize = 500; // flush early if buffer gets large

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const write = await request.json<ReactionWrite>();
    this.buffer.push(write);

    if (!this.alarmScheduled) {
      await this.state.storage.setAlarm(Date.now() + this.flushIntervalMs);
      this.alarmScheduled = true;
    }

    if (this.buffer.length >= this.maxBufferSize) {
      await this.flush();
    }

    return new Response('queued', { status: 202 });
  }

  async alarm(): Promise<void> {
    this.alarmScheduled = false;
    await this.flush();
  }

  private async flush(): Promise<void> {
    if (this.buffer.length === 0) return;

    const batch = this.buffer.splice(0); // drain atomically
    await writeBatchToD1(batch, this.env.DB);
    console.log('micro_batch_flushed', { count: batch.length });
  }
}
```

## 2. Bulk INSERT into D1

Build a single parameterised INSERT with multiple value rows. D1 supports up to ~999 bound parameters per query (SQLite limit); chunk by row count accordingly.

```typescript
const MAX_ROWS_PER_INSERT = 200; // 4 params × 200 = 800 — safely under the 999 limit

async function writeBatchToD1(
  writes: ReactionWrite[],
  db: D1Database,
): Promise<void> {
  for (let i = 0; i < writes.length; i += MAX_ROWS_PER_INSERT) {
    const chunk = writes.slice(i, i + MAX_ROWS_PER_INSERT);
    const placeholders = chunk.map(() => '(?, ?, ?, ?)').join(', ');
    const values = chunk.flatMap((w) => [w.userId, w.postId, w.emoji, w.ts]);

    await db
      .prepare(
        `INSERT OR IGNORE INTO reactions (user_id, post_id, emoji, ts)
         VALUES ${placeholders}`,
      )
      .bind(...values)
      .run();
  }
}
```

`INSERT OR IGNORE` provides idempotency: if the Worker crashes after the D1 write but before the DO buffer is drained, the retry will attempt to insert the same rows and silently skip duplicates.

## 3. Worker-Side Routing to the Batcher DO

Route all incoming reaction writes to the same DO instance per post (or globally for reactions). Using `idFromName` on the post ID shards the batcher across posts, preventing a single DO from becoming a hot spot for a viral post.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<ReactionWrite>();

    // Shard by postId so viral posts get their own batcher DO instance
    const doId = env.REACTION_BATCHER.idFromName(`batcher:${body.postId}`);
    const stub = env.REACTION_BATCHER.get(doId);

    const response = await stub.fetch(
      new Request('https://do.internal/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    );

    // Return 202 Accepted immediately — writes are not yet durable in D1
    return new Response(null, { status: 202 });
  },
};
```

`wrangler.toml`:

```toml
[[durable_objects.bindings]]
name = "REACTION_BATCHER"
class_name = "ReactionBatcherDO"

[[migrations]]
tag = "v1"
new_classes = ["ReactionBatcherDO"]
```

## 4. Alarm Recovery on DO Eviction

If the DO is evicted (no requests for ~30 s) while the alarm is still pending, the alarm fires on the next DO instantiation. Confirm the alarm is still registered in the DO constructor to handle the eviction-then-wake scenario.

```typescript
constructor(private state: DurableObjectState, private env: Env) {
  // Re-hydrate alarmScheduled flag from storage alarm presence
  this.state.storage.getAlarm().then((alarm) => {
    if (alarm !== null) this.alarmScheduled = true;
  });
}
```

If the DO is evicted *and* the alarm fires on a fresh instance with an empty in-memory buffer, the `flush()` is a no-op. Any buffered-but-not-flushed writes at the time of eviction are lost because they were in in-memory state, not storage. For example project reactions (at-most-once acceptable), this is fine. For at-least-once guarantees, push writes to DO storage before appending to the in-memory buffer.

## 5. Durability Trade-offs: At-Most-Once vs. At-Least-Once

| Mode | Buffer location | Eviction risk | Latency |
|---|---|---|---|
| At-most-once | In-memory array | Writes lost on eviction | Lowest |
| At-least-once | DO storage + in-memory | Persisted, replayed on wake | +1–3 ms per write |

For at-least-once, append each incoming write to DO storage before adding it to the in-memory buffer, and delete from storage after a successful D1 flush:

```typescript
// On receive
await this.state.storage.put(`write:${crypto.randomUUID()}`, write);
this.buffer.push(write);

// After flush
for (const key of Object.keys(await this.state.storage.list({ prefix: 'write:' }))) {
  await this.state.storage.delete(key);
}
```

## Anti-patterns

- **One global batcher DO for all reactions** — a single DO instance processes one request at a time; under high load it will queue; shard by post ID or user ID to distribute load.
- **Flushing synchronously inside the `fetch` handler** — synchronous D1 writes inside `fetch` defeat the purpose; flush only in `alarm()` or when the buffer ceiling is hit.
- **Setting `flushIntervalMs` below 100 ms** — alarm scheduling has overhead; very short intervals may produce overlapping alarms and double-flush the buffer.
- **Not handling D1 write failures in `flush()`** — if `writeBatchToD1` throws, the buffer is already spliced; writes are lost for at-most-once mode. Wrap in try/catch and re-push the chunk back to the buffer (or route to a DLQ) on failure.

## Gotchas

- DO alarms fire at-least-once; it is possible (though rare) for `alarm()` to be called twice for the same scheduled time. Make `flush()` idempotent by draining the buffer with `splice(0)` before the async D1 write.
- Cloudflare limits each DO instance to one pending alarm at a time; calling `setAlarm()` a second time before the first fires *replaces* the first — this is why `alarmScheduled` must be reset to `false` at the start of `alarm()`, not at the end.
- The SQLite parameter limit in D1 is 999; with 4 columns, that limits a single INSERT to 249 rows. Using 200 as `MAX_ROWS_PER_INSERT` provides a comfortable margin.
- Return `202 Accepted` (not `200 OK`) from the Worker to signal that the write is buffered but not yet durable. Document this contract in the API spec so callers do not assume immediate readability.

## Verification

1. Send 1,000 reaction events in under 1 second; assert D1 receives no more than 5–10 INSERT queries (≤ 300 ms flush cadence × D1 batch size).
2. Force a DO eviction (stop traffic for 35 s) while the buffer is empty; assert the subsequent alarm fires cleanly as a no-op.
3. Send 600 events in a burst; assert the early-flush ceiling triggers before the alarm and the buffer does not grow beyond `maxBufferSize`.
4. Introduce a D1 write failure; assert the Worker responds `202` (the DO already accepted the write) and the batch is re-queued or routed to the DLQ without data loss (at-least-once mode).

## Related

- `write-coalescing-durable-objects-d1.md`
- `d1-batch-operations-query-optimisation.md`
- `durable-object-alarm-api-scheduled-retry.md`
- `backpressure-patterns.md`
- `competing-consumers-durable-objects.md`

## Sources

- Cloudflare Durable Objects alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare D1 batch operations: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite maximum number of host parameters: https://www.sqlite.org/limits.html
