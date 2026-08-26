# Parallel Saga Orchestration — Fork/Join with Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An e-commerce checkout must reserve inventory, authorise payment, and notify the warehouse simultaneously rather than in sequence. Sequential saga adds up individual step latencies (~800 ms × 3 = 2.4 s). A parallel saga forks all three branches at once, joins when all complete (or compensates any that fail), and finishes in ~800 ms — the time of the slowest branch.

## Context

Standard saga orchestration runs steps in a linear chain. A parallel saga adds a **fork** gate that launches multiple branches concurrently and a **join** gate that waits for all branches. Each branch is itself a mini-saga with its own compensating transactions. If any branch fails after others have succeeded, the coordinator triggers compensation in reverse branch order.

Durable Objects are ideal orchestrators: a single `SagaCoordinator` DO holds the saga state, fans out to per-branch Workers via `fetch()`, and awaits all `Promise.allSettled()` results. The DO's persistent storage survives Worker eviction during long-running coordination.

---

## State Model

```typescript
interface BranchState {
  name: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'compensated';
  result?: unknown;
  error?: string;
}

interface SagaState {
  sagaId: string;
  phase: 'running' | 'succeeded' | 'compensating' | 'failed';
  branches: BranchState[];
  startedAt: number;
}
```

---

## Saga Coordinator (Durable Object)

```typescript
export class SagaCoordinator implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const { sagaId, orderId } = await request.json<{ sagaId: string; orderId: string }>();

    const saga: SagaState = {
      sagaId,
      phase: 'running',
      branches: [
        { name: 'inventory', status: 'pending' },
        { name: 'payment',   status: 'pending' },
        { name: 'warehouse', status: 'pending' },
      ],
      startedAt: Date.now(),
    };
    await this.state.storage.put('saga', saga);

    // --- FORK: launch all branches in parallel ---
    const results = await Promise.allSettled([
      this.runBranch(saga, 'inventory', orderId),
      this.runBranch(saga, 'payment',   orderId),
      this.runBranch(saga, 'warehouse', orderId),
    ]);

    const failures = results.filter(r => r.status === 'rejected');

    if (failures.length > 0) {
      saga.phase = 'compensating';
      await this.state.storage.put('saga', saga);
      await this.compensateAll(saga, orderId);
      saga.phase = 'failed';
    } else {
      saga.phase = 'succeeded';
    }

    await this.state.storage.put('saga', saga);
    return Response.json(saga);
  }

  private async runBranch(saga: SagaState, name: string, orderId: string): Promise<void> {
    const branch = saga.branches.find(b => b.name === name)!;
    branch.status = 'running';
    await this.state.storage.put('saga', saga);

    const res = await this.env.BRANCH_SERVICE.fetch(
      new Request(`https://internal/${name}`, {
        method: 'POST',
        body: JSON.stringify({ orderId }),
        headers: { 'Content-Type': 'application/json' },
      })
    );

    if (!res.ok) {
      branch.status = 'failed';
      branch.error = await res.text();
      await this.state.storage.put('saga', saga);
      throw new Error(`Branch ${name} failed: ${branch.error}`);
    }

    branch.status = 'succeeded';
    branch.result = await res.json();
    await this.state.storage.put('saga', saga);
  }

  // --- JOIN + COMPENSATE: reverse compensation for succeeded branches ---
  private async compensateAll(saga: SagaState, orderId: string): Promise<void> {
    const toCompensate = saga.branches.filter(b => b.status === 'succeeded');

    await Promise.allSettled(
      toCompensate.map(async (branch) => {
        await this.env.BRANCH_SERVICE.fetch(
          new Request(`https://internal/${branch.name}/compensate`, {
            method: 'POST',
            body: JSON.stringify({ orderId }),
            headers: { 'Content-Type': 'application/json' },
          })
        );
        branch.status = 'compensated';
        await this.state.storage.put('saga', saga);
      })
    );
  }
}
```

---

## Invoking the Coordinator

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { orderId } = await request.json<{ orderId: string }>();
    const sagaId = crypto.randomUUID();

    const id = env.SAGA_COORDINATOR.idFromName(sagaId);
    const stub = env.SAGA_COORDINATOR.get(id);

    const result = await stub.fetch(
      new Request('https://do/run', {
        method: 'POST',
        body: JSON.stringify({ sagaId, orderId }),
        headers: { 'Content-Type': 'application/json' },
      })
    );

    return result;
  },
};
```

---

## Branch Service (Stub Example)

```typescript
// Each branch is a separate Worker or DO; this is the inventory branch stub
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const { orderId } = await request.json<{ orderId: string }>();

    if (url.pathname.endsWith('/compensate')) {
      await env.DB.prepare(`UPDATE reservations SET status='cancelled' WHERE order_id=?`)
        .bind(orderId).run();
      return new Response('compensated');
    }

    const result = await env.DB.prepare(
      `INSERT INTO reservations(order_id, status) VALUES(?, 'reserved') RETURNING *`
    ).bind(orderId).first();

    return Response.json(result);
  },
};
```

---

## Partial Failure Semantics

| Scenario | Outcome |
|---|---|
| All branches succeed | Phase → `succeeded`; no compensation |
| One branch fails, others succeed | Phase → `compensating`; parallel compensation of successes |
| Compensation itself fails | Log + alarm for manual reconciliation; phase stays `compensating` |
| DO evicted mid-run | Storage survives; next HTTP request resumes from persisted state |

---

## Anti-patterns

- **Shared mutable state across branches** — branches should operate on independent resources. If two branches both write to the same D1 row, the parallel saga loses its parallelism benefit and introduces race conditions.
- **Long-running HTTP waits inside `runBranch`** — DO CPU time is limited. For branches that take > 30 s, use an alarm-based polling pattern instead.
- **Compensation in fixed order** — compensating sequentially in a parallel saga is unnecessary and slower. Compensate in parallel unless one compensation depends on another.
- **Not persisting branch state before launching** — if the DO is evicted before the first `storage.put`, a retry rediscovers nothing and relaunches duplicate work.

---

## Gotchas

- `Promise.allSettled()` never rejects, so check `results.filter(r => r.status === 'rejected')` explicitly.
- Durable Objects have a single-threaded execution model within one request. The `await Promise.allSettled(...)` inside a DO *does* parallelise outbound `fetch()` calls because those are I/O, not CPU.
- Branch services must be idempotent (or use idempotency keys) because the coordinator may retry them if the DO is evicted after launching but before recording success.

---

## Verification

```bash
# Trigger a checkout with one failing branch by passing a flag
curl -X POST https://your-worker.workers.dev/checkout \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ord-123","failBranch":"payment"}'

# Confirm inventory reservation was compensated
wrangler d1 execute YOUR_DB --command \
  "SELECT status FROM reservations WHERE order_id='ord-123';"
# Expected: cancelled
```

---

## Related

- `saga-pattern-orchestration.md` — sequential saga orchestration baseline
- `choreography-vs-orchestration-distributed-workflows.md` — when to orchestrate vs choreograph
- `compensating-transaction-workers-saga-rollback.md` — compensation mechanics
- `durable-objects-workflow-state-machine.md` — DO as a persistent state machine
- `fan-in-aggregator-durable-objects-coordination.md` — fan-in without compensation

---

## Sources

- Garcia-Molina & Salem, "Sagas" (1987 SIGMOD)
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Microservices Patterns ch.4 — Saga pattern: https://microservices.io/patterns/data/saga.html
