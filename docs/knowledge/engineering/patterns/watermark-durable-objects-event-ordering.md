# Watermark Pattern — Durable Objects Event Ordering

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Events arrive at a Durable Object out of order — perhaps from parallel Workers producing
to a queue, from multi-region fan-in, or from retries that replay older messages after
newer ones already landed.  Processing a stale event over a fresher one corrupts state:
a "user downgraded" event processed after a "user upgraded" event resets the plan
incorrectly; an older inventory snapshot overwrites a newer count.

You need a monotonically advancing watermark stored per Durable Object that lets you
safely discard or defer events that arrive out of causal order.

---

## Context

A **watermark** (also called a *low-water mark* in stream-processing literature) is the
highest sequence number, version vector, or timestamp the object has already accepted.
Any event whose position is at or below the watermark is either a duplicate or stale and
can be safely dropped.  Events above the watermark are accepted and advance it.

Durable Objects provide strong single-writer semantics and synchronous storage — exactly
the right primitive for maintaining a reliable watermark without race conditions.

This pattern is especially valuable when:
- Events carry a producer-assigned monotonic sequence number.
- Multiple producers each maintain their own sequence; a per-producer watermark vector is
  then required.
- Events may be replayed from a dead-letter queue with original timestamps.

---

## Watermark State in a Durable Object

```typescript
// src/do/ordered-event-processor.ts

export interface OrderedEvent {
  producerId: string;
  sequence: number;      // monotonically increasing per producer
  occurredAt: string;    // ISO-8601
  type: string;
  payload: unknown;
}

interface WatermarkMap {

}

export class OrderedEventProcessor implements DurableObject {
  private state: DurableObjectState;
  private watermarks: WatermarkMap = {};
  private initialised = false;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  private async ensureLoaded(): Promise<void> {
    if (this.initialised) return;
    this.watermarks =
      (await this.state.storage.get<WatermarkMap>('watermarks')) ?? {};
    this.initialised = true;
  }

  async fetch(req: Request): Promise<Response> {
    await this.ensureLoaded();

    if (req.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const event = (await req.json()) as OrderedEvent;
    const result = await this.processEvent(event);

    return new Response(JSON.stringify(result), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  private async processEvent(
    event: OrderedEvent,
  ): Promise<{ status: 'accepted' | 'stale' | 'duplicate' }> {
    const current = this.watermarks[event.producerId] ?? -1;

    if (event.sequence <= current) {
      const status = event.sequence === current ? 'duplicate' : 'stale';
      console.warn('Rejected out-of-order event', {
        producerId: event.producerId,
        eventSeq: event.sequence,
        watermark: current,
        status,
      });
      return { status };
    }

    // Accept — advance watermark and apply business logic atomically
    this.watermarks[event.producerId] = event.sequence;
    await this.state.storage.put('watermarks', this.watermarks);

    await this.applyEvent(event);

    return { status: 'accepted' };
  }

  private async applyEvent(event: OrderedEvent): Promise<void> {
    // Example: maintain a per-entity counter keyed by type
    const countKey = `count:${event.type}`;
    const current = (await this.state.storage.get<number>(countKey)) ?? 0;
    await this.state.storage.put(countKey, current + 1);
  }
}
```

---

## Multi-Producer Vector Watermark

```typescript
// src/do/vector-watermark.ts
// When multiple independent producers each have their own sequence space,
// maintain one watermark entry per producer (a vector clock lite).

export interface VectorEvent {
  producerId: string;
  seq: number;
  causedBy?: { producerId: string; seq: number }; // optional causal dependency
  payload: unknown;
}

export class VectorWatermarkDO implements DurableObject {
  private state: DurableObjectState;
  // producer → highest accepted sequence
  private vector: Record<string, number> = {};
  // Buffer for events that arrived before their causal dependency was satisfied
  private pending: VectorEvent[] = [];

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    await this.loadState();
    const event = (await req.json()) as VectorEvent;
    await this.ingest(event);
    // Drain pending queue after each new acceptance
    await this.drainPending();
    return new Response(JSON.stringify({ vector: this.vector }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  private async ingest(event: VectorEvent): Promise<boolean> {
    // Check causal dependency is satisfied
    if (event.causedBy) {
      const dep = event.causedBy;
      const depWatermark = this.vector[dep.producerId] ?? -1;
      if (depWatermark < dep.seq) {
        this.pending.push(event);
        return false; // deferred
      }
    }

    const current = this.vector[event.producerId] ?? -1;
    if (event.seq <= current) return false; // stale/duplicate

    this.vector[event.producerId] = event.seq;
    await this.persistVector();
    await this.applyEvent(event);
    return true;
  }

  private async drainPending(): Promise<void> {
    let changed = true;
    while (changed && this.pending.length > 0) {
      changed = false;
      const remaining: VectorEvent[] = [];
      for (const ev of this.pending) {
        const accepted = await this.ingest(ev);
        if (!accepted) remaining.push(ev);
        else changed = true;
      }
      this.pending = remaining;
    }
    // Persist pending list so it survives hibernation
    await this.state.storage.put('pending', this.pending);
  }

  private async persistVector(): Promise<void> {
    await this.state.storage.put('vector', this.vector);
  }

  private async loadState(): Promise<void> {
    this.vector = (await this.state.storage.get<Record<string, number>>('vector')) ?? {};
    this.pending = (await this.state.storage.get<VectorEvent[]>('pending')) ?? [];
  }

  private async applyEvent(event: VectorEvent): Promise<void> {
    // domain logic
    console.log('Applied', event.producerId, event.seq);
  }
}
```

---

## Worker Producing Sequenced Events

```typescript
// src/workers/event-producer.ts
// A Worker that increments a per-producer atomic counter in KV to assign sequences.

export interface Env {
  COUNTER_KV: KVNamespace;
  PROCESSOR_DO: DurableObjectNamespace;
}

export async function produceEvent(
  producerId: string,
  type: string,
  payload: unknown,
  env: Env,
): Promise<void> {
  // KV does not have atomic increment — use a Durable Object counter instead
  // or accept that sequences can have gaps (gaps are fine; only monotonicity matters)
  const seqKey = `seq:${producerId}`;
  const raw = await env.COUNTER_KV.get(seqKey);
  const nextSeq = raw === null ? 0 : parseInt(raw, 10) + 1;
  await env.COUNTER_KV.put(seqKey, String(nextSeq));

  const event = {
    producerId,
    sequence: nextSeq,
    occurredAt: new Date().toISOString(),
    type,
    payload,
  };

  // Route to a single DO instance per logical entity (e.g., per tenant)
  const id = env.PROCESSOR_DO.idFromName('global');
  const stub = env.PROCESSOR_DO.get(id);
  await stub.fetch(new Request('https://do/events', {
    method: 'POST',
    body: JSON.stringify(event),
    headers: { 'Content-Type': 'application/json' },
  }));
}
```

---

## Watermark Exposure Endpoint

```typescript
// Expose current watermark state for observability / admin queries
async function handleWatermarkQuery(
  state: DurableObjectState,
): Promise<Response> {
  const watermarks = await state.storage.get<Record<string, number>>('watermarks') ?? {};
  const pendingCount = ((await state.storage.get<unknown[]>('pending')) ?? []).length;

  return new Response(
    JSON.stringify({
      watermarks,
      pendingCount,
      asOf: new Date().toISOString(),
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );
}
```

---

## Anti-patterns

- **Using wall-clock timestamps as the watermark** — clocks skew across Workers; two
  events with the same millisecond timestamp create an ambiguous ordering.  Use a
  monotonic sequence number assigned by a single authority.
- **Advancing the watermark before persisting it** — if the `storage.put` fails after
  in-memory update but before persistence, the object accepts a future event that will
  appear stale after hibernation recovery.  Always persist before side effects.
- **Silently discarding stale events without logging** — stale rejections are observability
  signals; log them with the watermark and the arriving sequence for gap analysis.
- **Unbounded pending buffer** — events waiting on causal dependencies accumulate in
  memory; cap the buffer and reject (or DLQ) events that exceed it.
- **One DO for all entities** — the watermark DO becomes a hot spot; shard by entity ID
  (`idFromName(entityId)`) so each entity has an independent ordering context.

---

## Gotchas

- **Durable Object hibernation** — in-memory state (including `this.vector`) is lost when
  the DO hibernates; always load from `storage` on the first request of a new activation.
- **Storage transaction semantics** — `storage.put` is durable but individual puts are
  not automatically atomic with each other.  Use `state.storage.transaction(...)` if you
  need to update watermarks and other keys together atomically.
- **Sequence gaps are expected** — a producer may skip sequence numbers due to retries or
  dropped messages; the watermark only requires monotonicity, not contiguity.
- **Pending buffer after hibernation** — the pending list must be persisted to storage;
  an in-memory-only pending buffer is silently dropped on hibernation.
- **Cross-DO causal ordering** is hard — the vector watermark approach handles single-DO
  scope; for cross-DO causality you need distributed coordination (saga, two-phase,
  or a global sequence store).

---

## Verification

```bash
# Integration test: send events out of order, verify only monotone-advancing ones land

# 1. POST sequence=5 → expect accepted
# 2. POST sequence=3 → expect stale
# 3. POST sequence=5 → expect duplicate
# 4. POST sequence=6 → expect accepted
# 5. GET /watermark → expect { "default": 6 }
```

```typescript
// test/watermark.test.ts (Miniflare / Vitest)
it('rejects stale sequence', async () => {
  const stub = getMiniflareStub('OrderedEventProcessor');

  const r1 = await stub.fetch(makeReq({ producerId: 'p1', sequence: 5, type: 'X', payload: {} }));
  expect((await r1.json() as { status: string }).status).toBe('accepted');

  const r2 = await stub.fetch(makeReq({ producerId: 'p1', sequence: 3, type: 'X', payload: {} }));
  expect((await r2.json() as { status: string }).status).toBe('stale');
});
```

---

## Related

- `event-sourcing-cloudflare-workers-d1.md` — append-only event log
- `snapshot-durable-objects-versioning.md` — snapshotting ordered DO state
- `request-batching-durable-objects.md` — batching events into the DO
- `inbox-pattern-idempotent-consumption.md` — duplicate guard that pairs with watermark

---

## Sources

- "Designing Data-Intensive Applications" ch. 8 — ordering guarantees and watermarks
  Kleppmann, 2017
- Cloudflare Durable Objects storage API
  https://developers.cloudflare.com/durable-objects/api/storage-api/
- Google Dataflow watermark model
  https://cloud.google.com/dataflow/docs/concepts/streaming-pipelines#watermarks
