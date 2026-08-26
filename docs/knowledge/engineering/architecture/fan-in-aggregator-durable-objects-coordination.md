# Fan-In Aggregator Pattern with Durable Objects Coordination

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You dispatch work to N parallel Workers (scatter phase) and need a single place to
collect, merge, and act on all N results before continuing — without polling, without
a shared database lock, and without losing a result if the aggregator restarts mid-flight.
Classic scenarios: parallel micro-service fan-out whose combined response must reach the
client, multi-region price aggregation, distributed map-reduce whose reduce step must
happen exactly once, or test-result rollup after a sharded test suite.

## Context

Cloudflare Workers are stateless. A naive fan-in using KV suffers race conditions and
no atomic "all N arrived" signal. Durable Objects solve this cleanly: one DO per
aggregation job holds mutable state (received-count, partial results, alarm), serialises
all writes through its single-threaded actor model, and fires an alarm when the expected
count is satisfied. The producer learns the aggregation key before scattering; each
worker reports to the same DO namespace; the DO emits the merged result downstream when
the quorum is met or a deadline expires.

## 1. Aggregator Durable Object

```typescript
// src/aggregator-do.ts
import { DurableObject } from "cloudflare:workers";

interface AggState {
  expected: number;
  results: Record<string, unknown>;
  deadline: number; // unix ms
  done: boolean;
}

export class AggregatorDO extends DurableObject<Env> {
  private state: AggState | null = null;

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    switch (url.pathname) {
      case "/init": return this.init(req);
      case "/report": return this.report(req);
      case "/result": return this.result();
      default: return new Response("not found", { status: 404 });
    }
  }

  // Called once by the scatter coordinator
  async init(req: Request): Promise<Response> {
    const { expected, ttlMs = 30_000 } = await req.json<{
      expected: number;
      ttlMs?: number;
    }>();
    const deadline = Date.now() + ttlMs;
    this.state = { expected, results: {}, deadline, done: false };
    await this.ctx.storage.put("state", this.state);
    await this.ctx.storage.setAlarm(deadline);
    return new Response("ok");
  }

  // Called by each scattered worker with its partial result
  async report(req: Request): Promise<Response> {
    this.state ??= await this.ctx.storage.get<AggState>("state");
    if (!this.state || this.state.done) return new Response("stale", { status: 409 });

    const { key, value } = await req.json<{ key: string; value: unknown }>();
    this.state.results[key] = value;
    await this.ctx.storage.put("state", this.state);

    if (Object.keys(this.state.results).length >= this.state.expected) {
      await this.finalise("complete");
    }
    return new Response("accepted");
  }

  async result(): Promise<Response> {
    this.state ??= await this.ctx.storage.get<AggState>("state");
    if (!this.state) return new Response("not found", { status: 404 });
    return Response.json({ done: this.state.done, results: this.state.results });
  }

  // Alarm fires on deadline expiry — partial results are still emitted
  async alarm(): Promise<void> {
    await this.finalise("timeout");
  }

  private async finalise(reason: string): Promise<void> {
    if (!this.state || this.state.done) return;
    this.state.done = true;
    await this.ctx.storage.put("state", this.state);
    // Emit to downstream via Queue or DO binding
    await this.env.RESULTS_QUEUE.send({
      reason,
      results: this.state.results,
      receivedCount: Object.keys(this.state.results).length,
      expectedCount: this.state.expected,
    });
  }
}
```

## 2. Scatter Coordinator Worker

```typescript
// src/scatter.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { jobId, shards } = await req.json<{
      jobId: string;
      shards: string[];
    }>();

    // Provision the aggregator DO for this job
    const aggId = env.AGGREGATOR.idFromName(jobId);
    const agg = env.AGGREGATOR.get(aggId);
    await agg.fetch(
      new Request("https://do/init", {
        method: "POST",
        body: JSON.stringify({ expected: shards.length, ttlMs: 20_000 }),
      })
    );

    // Fan-out: each shard Worker reports back independently
    await Promise.allSettled(
      shards.map((shardId) =>
        env.SHARD_WORKER.fetch(
          new Request("https://shard/process", {
            method: "POST",
            body: JSON.stringify({ jobId, shardId }),
          })
        )
      )
    );

    return Response.json({ jobId, shards: shards.length, status: "scattered" });
  },
};
```

## 3. Shard Worker Reporting Back

```typescript
// src/shard-worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { jobId, shardId } = await req.json<{
      jobId: string;
      shardId: string;
    }>();

    // Perform actual work
    const result = await computeShard(shardId);

    // Report to the aggregator DO
    const aggId = env.AGGREGATOR.idFromName(jobId);
    const agg = env.AGGREGATOR.get(aggId);
    await agg.fetch(
      new Request("https://do/report", {
        method: "POST",
        body: JSON.stringify({ key: shardId, value: result }),
      })
    );

    return new Response("reported");
  },
};

async function computeShard(shardId: string): Promise<unknown> {
  // ... shard-specific computation
  return { shardId, value: Math.random() };
}
```

## 4. Results Consumer (Queue Handler)

```typescript
// src/result-consumer.ts
export default {
  async queue(batch: MessageBatch<AggregationResult>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { reason, results, receivedCount, expectedCount } = msg.body;

      if (reason === "timeout") {
        console.warn(
          `Job timed out: received ${receivedCount}/${expectedCount} shards`
        );
      }

      // Merge partial results and write to D1
      const merged = mergeResults(results);
      await env.DB.prepare(
        "INSERT OR REPLACE INTO job_results (job_id, payload, partial) VALUES (?, ?, ?)"
      )
        .bind(
          Object.keys(results)[0]?.split(":")[0] ?? "unknown",
          JSON.stringify(merged),
          receivedCount < expectedCount ? 1 : 0
        )
        .run();

      msg.ack();
    }
  },
};

function mergeResults(results: Record<string, unknown>): unknown {
  return Object.values(results).reduce((acc, r) => ({ ...acc, ...(r as object) }), {});
}
```

## 5. Wrangler Configuration

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "AGGREGATOR"
class_name = "AggregatorDO"

[[migrations]]
tag = "v1"
new_classes = ["AggregatorDO"]

[[queues.producers]]
binding = "RESULTS_QUEUE"
queue = "aggregation-results"

[[queues.consumers]]
queue = "aggregation-results"
max_batch_size = 20
max_batch_timeout = 5
```

## Anti-patterns

- **Aggregating in a plain Worker**: no durable state; a restart loses partial results.
- **Polling KV for quorum**: race-prone; N concurrent writers overwrite each other.
- **One DO per shard**: defeats the purpose; the fan-in point must be singular.
- **No deadline alarm**: a missing shard stalls the job forever, leaking the DO.
- **Storing raw results unboundedly**: cap payload size per shard; use the claim-check
  pattern (R2 + reference key) for results > 128 KB.

## Gotchas

- DO storage `put` is synchronous within the actor but async to durable media — always
  `await` it before returning from `report()` or a restart could lose the write.
- `Promise.allSettled` in the scatter step means shard failures are silent; check each
  `SettledResult.status` and report error shards to the DO as a sentinel value.
- `idFromName(jobId)` must be globally unique — prefix with a tenant or timestamp to
  prevent cross-job collisions.
- Alarms are best-effort: they fire at least once but can fire multiple times. Guard
  `finalise` with the `done` flag and make it idempotent.
- DO egress (calling back to shard Workers) counts against CPU time; keep `finalise`
  light — emit to a Queue, not a synchronous downstream call.

## Verification

```typescript
// Smoke test: send 3 shards, expect all 3 in results
const res = await env.AGGREGATOR.get(
  env.AGGREGATOR.idFromName("test-job-1")
).fetch(new Request("https://do/result"));
const { done, results } = await res.json();
console.assert(done === true, "job should be done");
console.assert(Object.keys(results).length === 3, "should have 3 results");

// Timeout test: init with 5 expected shards, send only 2, wait for alarm
// assert result Queue receives a message with reason="timeout"
```

## Related

- `actor-model-durable-objects-workers.md`
- `aggregator-pattern-workers-subrequests-parallel.md`
- `scatter-gather-workers-service-bindings.md`
- `claim-check-pattern-large-messages.md`
- `durable-object-alarm-api-scheduled-retry.md`

## Sources

- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Enterprise Integration Patterns — Gregor Hohpe & Bobby Woolf (Aggregator pattern, p. 268)
- Cloudflare DO alarm API — https://developers.cloudflare.com/durable-objects/api/alarms/
