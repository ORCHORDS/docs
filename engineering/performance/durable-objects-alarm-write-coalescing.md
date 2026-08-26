# Durable Objects Alarm-Based Write Coalescing Latency

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Durable Object that persists every incoming event immediately via `this.ctx.storage.put()` hits
Cloudflare's storage write rate limit (16 concurrent writes per object, plus per-second caps) and
accumulates per-write latency that compounds under fan-in workloads. A chat room, analytics
aggregator, or rate-limiter receiving 100+ writes per second exhibits visible tail latency from
storage back-pressure.

Alarm-based write coalescing buffers writes in memory and flushes them to storage in a single
batched put inside a scheduled alarm, decoupling acknowledgment latency from persistence latency.

## Context

Cloudflare Durable Objects provide transactional key-value storage through `DurableObjectStorage`.
Each `storage.put()` is durable when it returns — it blocks the request until the write is
confirmed. Under high write rates, this creates a latency chain: every inbound request waits for
the previous write to confirm before proceeding.

The Alarms API (`storage.setAlarm()`) schedules a callback (`alarm()` method) up to 30 days in the
future; the minimum practical interval is ~1 second. Alarms fire even after a DO goes to sleep and
wake the object. This makes them ideal for coalescing: accept writes into an in-memory buffer,
schedule an alarm for the next flush window, and persist all buffered writes in one storage
transaction.

The trade-off: writes are acknowledged to clients immediately but are not yet durable. A crash
between buffer acceptance and alarm flush loses the buffered data. Use this pattern only when
eventual consistency (seconds-scale) is acceptable and the source can replay on reconnect.

## 1. Naive per-request write (problematic under load)

```typescript
export class NaiveCounter implements DurableObject {
  private value = 0;
  constructor(private ctx: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    // BAD: every request pays a synchronous storage write
    this.value++;
    await this.ctx.storage.put("value", this.value);  // latency bottleneck
    return new Response(String(this.value));
  }
}
```

Under 200 concurrent requests to a single DO this pattern serializes writes, creating a queue of
unresolved `put()` promises that blocks each new request for O(depth × write_latency) ms.

## 2. Alarm-based coalescing with in-memory buffer

```typescript
interface BufferedWrite {
  key: string;
  value: unknown;
  resolve: () => void;
  reject: (err: unknown) => void;
}

export class CoalescingStore implements DurableObject {
  private buffer: Map<string, { value: unknown; resolve: () => void }> = new Map();
  private alarmScheduled = false;
  private FLUSH_INTERVAL_MS = 1000; // flush at most once per second

  constructor(private ctx: DurableObjectState, private env: Env) {
    // Restore any in-flight alarm state across hibernation wakes
    this.ctx.blockConcurrencyWhile(async () => {
      this.alarmScheduled = (await this.ctx.storage.getAlarm()) !== null;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const { key, value } = await request.json<{ key: string; value: unknown }>();

    await new Promise<void>((resolve, reject) => {
      // Coalesce: last writer wins for the same key within the flush window
      this.buffer.set(key, { value, resolve });
      if (!this.alarmScheduled) {
        this.scheduleFlush();
      }
      resolve(); // acknowledge immediately — not yet persisted
    });

    return new Response(JSON.stringify({ ok: true, buffered: true }), {
      headers: { "content-type": "application/json" }
    });
  }

  private scheduleFlush(): void {
    const flushAt = Date.now() + this.FLUSH_INTERVAL_MS;
    this.ctx.storage.setAlarm(flushAt);
    this.alarmScheduled = true;
  }

  async alarm(): Promise<void> {
    this.alarmScheduled = false;
    if (this.buffer.size === 0) return;

    const snapshot = new Map(this.buffer);
    this.buffer.clear();

    // Single batched write for all buffered keys
    const writes: Record<string, unknown> = {};
    for (const [key, { value }] of snapshot) {
      writes[key] = value;
    }
    await this.ctx.storage.put(writes);

    // If new writes arrived while we were flushing, schedule another alarm
    if (this.buffer.size > 0) {
      this.scheduleFlush();
    }
  }
}
```

## 3. Durable write confirmation with backpressure signal

When callers require durable confirmation, hold a promise in the buffer that resolves after the
alarm flush. Callers opt in by setting a header.

```typescript
export class ConfirmableStore implements DurableObject {
  private pending: Map<string, { value: unknown; resolvers: Array<() => void> }> = new Map();
  private alarmScheduled = false;

  constructor(private ctx: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const durable = request.headers.get("x-durable-ack") === "1";
    const { key, value } = await request.json<{ key: string; value: unknown }>();

    if (durable) {
      await new Promise<void>((resolve) => {
        const entry = this.pending.get(key);
        if (entry) {
          entry.value = value;
          entry.resolvers.push(resolve);
        } else {
          this.pending.set(key, { value, resolvers: [resolve] });
        }
        this.ensureAlarm();
      });
      return new Response(JSON.stringify({ ok: true, durable: true }), {
        headers: { "content-type": "application/json" }
      });
    }

    // Fire-and-forget path
    const entry = this.pending.get(key);
    if (entry) { entry.value = value; } else {
      this.pending.set(key, { value, resolvers: [] });
    }
    this.ensureAlarm();
    return new Response(JSON.stringify({ ok: true, durable: false }), {
      headers: { "content-type": "application/json" }
    });
  }

  private ensureAlarm(): void {
    if (!this.alarmScheduled) {
      this.ctx.storage.setAlarm(Date.now() + 500);
      this.alarmScheduled = true;
    }
  }

  async alarm(): Promise<void> {
    this.alarmScheduled = false;
    if (this.pending.size === 0) return;

    const snapshot = new Map(this.pending);
    this.pending.clear();

    const writes: Record<string, unknown> = {};
    for (const [key, { value }] of snapshot) {
      writes[key] = value;
    }

    await this.ctx.storage.put(writes);

    // Resolve all durable-ack promises
    for (const { resolvers } of snapshot.values()) {
      for (const resolve of resolvers) resolve();
    }

    if (this.pending.size > 0) this.ensureAlarm();
  }
}
```

## 4. Measuring flush latency and buffer depth

Add observability to the alarm handler to track how effectively writes are being coalesced.

```typescript
async alarm(): Promise<void> {
  const flushStart = Date.now();
  const bufferDepth = this.pending.size;

  // ... flush logic ...

  const flushMs = Date.now() - flushStart;

  // Emit to Analytics Engine for dashboarding
  this.env.ANALYTICS.writeDataPoint({
    blobs: ["do-write-coalescing"],
    doubles: [flushMs, bufferDepth],
    indexes: [this.ctx.id.toString().slice(0, 8)]
  });
}
```

## Anti-patterns

- Setting alarm interval < 1 s — Cloudflare enforces a minimum alarm interval; sub-second alarms
  silently snap to the minimum, making your flush timing unpredictable.
- Clearing `alarmScheduled` before the `storage.put()` in `alarm()` — a crash between the flag
  clear and the write leaves data in the buffer with no alarm to flush it.
- Growing the in-memory buffer without a size cap — a very high write rate can exhaust the DO's
  128 MB memory limit before the next alarm fires.
- Using `storage.put()` inside the `fetch()` handler for writes that could be buffered — defeats
  the purpose of coalescing.
- Forgetting to re-schedule an alarm when new writes arrive during the flush — creates a silent
  data loss window.

## Gotchas

- Alarms survive DO hibernation: the object wakes up automatically to run `alarm()`. However,
  the in-memory buffer does NOT survive hibernation. If the DO hibernates between a write and the
  alarm, the buffer is empty when `alarm()` runs. Mitigate by persisting the buffer to storage on
  hibernation (use `ctx.waitUntil` with a storage write) or accept the loss window.
- `storage.put(map)` with a `Map` argument is not the same as `storage.put(plainObject)` — the
  API accepts a plain object or iterable of `[key, value]` pairs; convert `Map` before passing.
- DO instances are scoped to a specific Cloudflare location via `locationHint`. If requests route
  to different locations, each location's DO has its own buffer. Ensure your DO name is consistent
  across callers to pin to one location.
- Alarm delivery is best-effort with at-least-once semantics: if Cloudflare fails to deliver an
  alarm (very rare), the buffer will not flush. Monitor alarm execution via Logpush worker traces.

## Verification

1. Use `wrangler tail --format pretty` during load tests to observe alarm firings and buffer depths.
2. Check Cloudflare Durable Objects metrics dashboard: compare write operations before/after.
3. Add `Server-Timing` on the fetch response to expose buffer-enqueue latency vs flush latency.
4. Query Analytics Engine for `do-write-coalescing` data points to track P99 flush duration.
5. Inject a simulated crash (throw in `alarm()`) to verify buffer recovery behavior.

## Related

- `durable-objects-low-latency-stateful.md`
- `durable-objects-read-cache-layer.md`
- `durable-objects-memory-optimization.md`
- `durable-objects-hibernation-wake-latency.md`
- `analytics-engine-write-throughput-batching.md`

## Sources

- Cloudflare Durable Objects Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Durable Objects limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- Coalescing writes blog: https://blog.cloudflare.com/durable-objects-alarms/
