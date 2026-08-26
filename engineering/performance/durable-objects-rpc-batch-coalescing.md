# Durable Objects RPC Batch Coalescing Latency Reduction

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Worker makes multiple independent RPC calls to the same Durable Object stub within
a single request handler. Each call adds a full round-trip penalty: serialization,
network hop to the DO's location, execution, serialization back. With three sequential
calls to the same stub the added latency is 3× the intra-region RTT (often 2–8 ms per
hop in the same Cloudflare region, but 20–80 ms if the Worker and DO are in different
regions due to smart placement divergence).

Typical symptom: tail latency (p99) of a Worker endpoint spikes relative to p50 when
business logic issues calls like `stub.getUser()`, `stub.getSettings()`, and
`stub.getFeatureFlags()` back-to-back.

## Context

Durable Objects expose an RPC interface via the `DurableObject` class methods when the
Worker and DO share a service binding. Each awaited call is serialized independently.
Unlike a database that supports `SELECT ... JOIN` or batched queries, the DO RPC
interface does not automatically coalesce concurrent calls — each `await` is a
round-trip.

The fix is to design a **batch method** on the DO that accepts a typed request
describing multiple logical operations, processes them in a single invocation, and
returns a composite result. This reduces N round-trips to 1.

Workers RPC (introduced with the workers-types v4 / `@cloudflare/workers-types` 4.x)
transmits arguments and return values using the structured-clone algorithm with
extensions for `ReadableStream`, `Response`, `Request`, and `Error`. Batch payloads
composed of plain objects serialize efficiently.

## Designing the Batch Method

Define a discriminated-union request type so the DO can dispatch each operation
independently without coupling caller logic into the DO internals.

```typescript
// shared/do-batch.ts
export type BatchOp =
  | { kind: "getUser"; userId: string }
  | { kind: "getSettings"; namespace: string }
  | { kind: "getFeatureFlags"; context: { region: string; tier: string } };

export type BatchResult<T extends BatchOp> =
  T extends { kind: "getUser" }     ? User :
  T extends { kind: "getSettings" } ? Settings :
  T extends { kind: "getFeatureFlags" } ? FeatureFlags :
  never;

export type BatchRequest = BatchOp[];
export type BatchResponse = (User | Settings | FeatureFlags | null)[];
```

```typescript
// do/session-state.ts
import { BatchRequest, BatchResponse } from "../shared/do-batch";

export class SessionState extends DurableObject {
  async batch(ops: BatchRequest): Promise<BatchResponse> {
    // Process all ops in one call — single DO activation, no extra RTTs.
    return Promise.all(
      ops.map((op) => {
        switch (op.kind) {
          case "getUser":         return this.#fetchUser(op.userId);
          case "getSettings":     return this.#fetchSettings(op.namespace);
          case "getFeatureFlags": return this.#fetchFeatureFlags(op.context);
          default:
            // Exhaustiveness guard — TypeScript narrows `op` to `never` here.
            throw new Error(`Unknown op: ${(op as BatchOp).kind}`);
        }
      })
    );
  }

  #fetchUser(userId: string): Promise<User | null> { /* ... */ }
  #fetchSettings(namespace: string): Promise<Settings | null> { /* ... */ }
  #fetchFeatureFlags(context: { region: string; tier: string }): Promise<FeatureFlags> { /* ... */ }
}
```

## Caller-Side Coalescing

```typescript
// worker/handler.ts
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userId, region, tier } = parseRequest(request);

    const stub = env.SESSION_STATE.get(
      env.SESSION_STATE.idFromName(userId)
    );

    // Single round-trip instead of three.
    const [user, settings, flags] = await stub.batch([
      { kind: "getUser",         userId },
      { kind: "getSettings",     namespace: "ui" },
      { kind: "getFeatureFlags", context: { region, tier } },
    ]);

    if (!user) return new Response("Not found", { status: 404 });

    return Response.json(buildPayload(user, settings, flags));
  },
};
```

## Parallel vs. Sequential Coalescing

When the caller does not need results from one RPC to construct the arguments of
another (i.e., the operations are independent), they can be issued with
`Promise.all` even *without* a batch method — but this still incurs N concurrent
RTTs, each requiring a separate DO activation lock window. The batch method is
superior because:

1. **Single activation**: The DO executes all operations in one JS microtask queue
   drain, holding the implicit in-memory lock once.
2. **Single serialization boundary**: Arguments travel in one structured-clone pass.
3. **Predictable CPU billing**: One activation = one CPU-time accounting window;
   N concurrent stubs = N windows with higher variance.

```typescript
// WORSE: parallel but still N round-trips and N lock windows.
const [user, settings, flags] = await Promise.all([
  stub.getUser(userId),
  stub.getSettings("ui"),
  stub.getFeatureFlags({ region, tier }),
]);

// BETTER: single round-trip and single lock window via batch method.
const [user, settings, flags] = await stub.batch([...]);
```

## Typed Batch Helper

Wrapping the batch call in a typed helper restores per-operation type safety at
the call site without leaking the array-index gymnastics.

```typescript
// shared/batch-helper.ts
import type { DurableObjectStub } from "@cloudflare/workers-types";
import type { BatchOp, BatchResponse } from "./do-batch";

export async function batchDO(
  stub: DurableObjectStub,
  ops: BatchOp[]
): Promise<BatchResponse> {
  return (stub as unknown as { batch: (ops: BatchOp[]) => Promise<BatchResponse> }).batch(ops);
}

// Usage with destructuring keeps types aligned by position.
const [user, settings, flags] = await batchDO(stub, [
  { kind: "getUser",         userId },
  { kind: "getSettings",     namespace: "ui" },
  { kind: "getFeatureFlags", context: { region, tier } },
]);
```

## Anti-patterns

- **Mega-batch everything**: A batch method with 30 operation types becomes hard to
  maintain and can inflate per-call CPU time. Scope each batch method to a coherent
  read model (e.g., "session initialization data").
- **Awaiting inside the batch handler**: `await Promise.all(ops.map(...))` inside
  the DO is correct. Awaiting them sequentially defeats the purpose.
- **Ignoring DO location divergence**: If the DO is consistently in a different
  Cloudflare region from the calling Worker (visible via Trace Worker spans), fix the
  placement mismatch first — a batch method on a remote DO saves N−1 RTTs, but the
  first RTT is still expensive.
- **Returning raw internal state**: Batch responses cross the RPC boundary. Do not
  return non-serializable objects (`Map`, `Set`, class instances with prototype
  methods) unless you implement custom serializers.

## Gotchas

- **Error propagation**: `Promise.all` inside the DO rejects on the first error.
  If partial failures are acceptable, use `Promise.allSettled` and encode
  `{ ok: false; error: string }` in the response union.
- **Structured-clone limits**: `undefined` values survive structured-clone in most
  implementations but be explicit — return `null` for absent optional fields.
- **Wrangler dev mode**: In `wrangler dev`, DO RPC crosses an in-process boundary,
  not a real network hop. Latency measurements in dev mode will not reveal the
  N-RTT problem; use `wrangler dev --remote` or deploy to staging to observe it.
- **Workers RPC vs. HTTP**: If you use HTTP fetch (not RPC) to reach the DO, the
  same batching principle applies — POST a single JSON body with an array of
  operations and respond with an array of results.

## Verification

1. Add `Date.now()` timestamps around the un-batched calls and the batched call in
   a staging Worker, log them via `console.log`, and compare tail latency in the
   Workers Logs dashboard.
2. Use a Trace Worker to capture span durations for `durable_object_rpc` events;
   verify the count drops from N to 1 per request.
3. Run a load test with `k6` or `wrk` targeting the endpoint; compare p99 latency
   before and after. Expect a 40–70 % reduction when N ≥ 3 and DO is in a different
   PoP from the Worker.

```typescript
// Trace Worker snippet to count DO RPC spans per request.
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const ev of events) {
      const rpcSpans = ev.diagnosticsChannel?.filter(
        (s) => s.event?.type === "durable_object_rpc"
      ) ?? [];
      console.log(`DO RPC calls: ${rpcSpans.length}`);
    }
  },
};
```

## Related

- `durable-objects-alarm-write-coalescing.md`
- `durable-objects-read-cache-layer.md`
- `workers-request-coalescing-deduplication.md`
- `workers-subrequest-fanout-parallelism.md`
- `workers-tail-latency-p99-p50-gap.md`

## Sources

- Cloudflare Workers RPC documentation: https://developers.cloudflare.com/workers/runtime-apis/rpc/
- Durable Objects overview: https://developers.cloudflare.com/durable-objects/
- Workers Trace events: https://developers.cloudflare.com/workers/observability/logs/tail-workers/
