# Fan-In Aggregation: Workers + Queues + D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple upstream Workers independently compute partial results for a shared batch job (e.g., price aggregation from five regional APIs, multi-source ML inference, parallel document processing). You need to collect all partial results, detect when the batch is complete, and trigger downstream processing — without polling loops or external orchestrators.

## Context

Cloudflare's stateless Workers model makes coordinating fan-in hard: no shared memory, no blocking waits. The solution combines three primitives:

- **Queues** — decoupled transport from producers to a single Consumer Worker.
- **D1** — durable partial-result accumulation with SQL-level dedup.
- **Durable Objects** — per-batch completion tracking with atomic counters and alarms for deadline enforcement.

## Fan-In Architecture and Code

```typescript
// shared/types.ts
export interface PartialResult {
  batch_id: string;
  source: string;
  payload: unknown;
  received_at: string;
}

// producer-worker/index.ts  — one of N upstream producers
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const batchId = new URL(request.url).searchParams.get('batch_id') ?? crypto.randomUUID();
    const result = await computePartialResult(env);   // domain-specific

    await env.RESULTS_QUEUE.send({
      batch_id: batchId,
      source:   env.SOURCE_NAME,          // e.g. 'region-us-east'
      payload:  result,
      received_at: new Date().toISOString(),
    } satisfies PartialResult);

    return Response.json({ accepted: true, batch_id: batchId });
  },
};

// consumer-worker/index.ts  — single Consumer Worker
export default {
  async queue(batch: MessageBatch<PartialResult>, env: Env): Promise<void> {
    // 1. Persist partial results to D1 (upsert — idempotent on source)
    const stmt = env.DB.prepare(`
      INSERT INTO partial_results (batch_id, source, payload, received_at)
      VALUES (?1, ?2, ?3, ?4)
      ON CONFLICT (batch_id, source) DO UPDATE SET
        payload     = excluded.payload,
        received_at = excluded.received_at
    `);

    const inserts = batch.messages.map((msg) =>
      stmt.bind(
        msg.body.batch_id,
        msg.body.source,
        JSON.stringify(msg.body.payload),
        msg.body.received_at,
      )
    );
    await env.DB.batch(inserts);

    // 2. Notify the per-batch Durable Object that parts arrived
    const uniqueBatches = [...new Set(batch.messages.map((m) => m.body.batch_id))];
    await Promise.all(
      uniqueBatches.map((id) => {
        const doId = env.BATCH_TRACKER.idFromName(id);
        const stub = env.BATCH_TRACKER.get(doId);
        return stub.fetch('https://internal/arrived', {
          method: 'POST',
          body: JSON.stringify({ batch_id: id }),
        });
      })
    );

    batch.ackAll();
  },
};

// batch-tracker-do/index.ts
export class BatchTrackerDO {
  private storage: DurableObjectStorage;
  constructor(state: DurableObjectState, private env: Env) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/init') {
      // Called by the job initiator with expected source count
      const { batch_id, expected } = await request.json<{ batch_id: string; expected: number }>();
      await this.storage.put('expected', expected);
      await this.storage.put('received', 0);
      await this.storage.put('batch_id', batch_id);
      // Deadline alarm: 5 minutes from now
      await this.storage.setAlarm(Date.now() + 5 * 60 * 1_000);
      return Response.json({ status: 'initialized' });
    }

    if (url.pathname === '/arrived') {
      const expected = (await this.storage.get<number>('expected')) ?? 0;
      const received = ((await this.storage.get<number>('received')) ?? 0) + 1;
      await this.storage.put('received', received);

      if (received >= expected) {
        await this.triggerDownstream();
      }
      return Response.json({ received, expected, complete: received >= expected });
    }

    return new Response('Not found', { status: 404 });
  }

  async alarm(): Promise<void> {
    // Deadline passed — trigger downstream with whatever arrived
    const batchId = await this.storage.get<string>('batch_id');
    const received = (await this.storage.get<number>('received')) ?? 0;
    const expected = (await this.storage.get<number>('expected')) ?? 0;
    console.warn(`Batch ${batchId} timed out: ${received}/${expected} parts received`);
    await this.triggerDownstream(timedOut: true);
  }

  private async triggerDownstream(timedOut = false): Promise<void> {
    const batchId = await this.storage.get<string>('batch_id');
    await this.env.DOWNSTREAM_QUEUE.send({ batch_id: batchId, timed_out: timedOut });
    await this.storage.deleteAll();   // clean up DO state
  }
}
```

## D1 Schema

```sql
CREATE TABLE partial_results (
  batch_id    TEXT NOT NULL,
  source      TEXT NOT NULL,
  payload     TEXT NOT NULL,   -- JSON
  received_at TEXT NOT NULL,
  PRIMARY KEY (batch_id, source)
);
CREATE INDEX idx_partial_results_batch ON partial_results (batch_id);
```

## Wrangler Binding Configuration

```jsonc
// wrangler.jsonc (consumer-worker)
{
  "queues": {
    "consumers": [{ "queue": "results-queue", "max_batch_size": 100, "max_batch_timeout": 5 }]
  },
  "durable_objects": {
    "bindings": [{ "name": "BATCH_TRACKER", "class_name": "BatchTrackerDO" }]
  },
  "d1_databases": [{ "binding": "DB", "database_name": "aggregation-db", "database_id": "..." }]
}
```

## Anti-patterns

- **DO per message** — one DO per batch, not per message; DO per message inflates costs and namespace pressure.
- **Polling D1 for completion** — use the DO alarm instead; polling adds latency and burns D1 read quota.
- **Storing large payloads in DO storage** — DO storage is limited; persist to D1, track only counts in the DO.
- **Not setting an alarm** — without a deadline alarm, a missing partial causes the batch to hang forever.

## Gotchas

- The `ON CONFLICT` upsert requires D1's SQLite `UPSERT` syntax — available in all current D1 builds.
- Queues deliver **at-least-once**; the `ON CONFLICT DO UPDATE` makes D1 inserts idempotent, but the DO `/arrived` counter increments on every delivery. Guard with a `processed_sources` set in DO storage if double-counting matters.
- `storage.setAlarm` overwrites any existing alarm; call it only during `/init`, not on every `/arrived`.
- DO `deleteAll()` in `triggerDownstream` is intentional — it decommissions the DO after the batch completes.

## Verification

```bash
# 1. Initiate a batch with expected=3
curl -X POST https://api.example.com/batches/init \
  -d '{"batch_id":"test-001","expected":3}'

# 2. Send 3 partial results via producer workers
curl 'https://producer-a.example.com/?batch_id=test-001'
curl 'https://producer-b.example.com/?batch_id=test-001'
curl 'https://producer-c.example.com/?batch_id=test-001'

# 3. Query D1 to confirm all 3 partials arrived
wrangler d1 execute aggregation-db \
  --command "SELECT * FROM partial_results WHERE batch_id='test-001'"
```

## Related

- `competing-consumers-workers-queues-concurrency.md`
- `async-request-reply-workers-durable-objects.md`
- Cloudflare Queues — Consumer Workers
- Durable Objects — Alarms API

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/d1/
