# Compensating Transactions: Workers, Saga Rollback

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A example project "boost" purchase saga spans three services: charge karma credits (D1), increment the
post's boost counter (Durable Object), and fan-out boost notifications (Queue). If notification
fan-out fails after the charge and counter increment have committed, the user loses credits and
the post shows a false boost count. Distributed rollback requires explicit compensating
transactions for each already-completed step.

## Context

Cloudflare Workers have no global transaction coordinator. Each step executes in an independent
Worker invocation, Durable Object call, or Queue consumer. Once a step commits its side-effect,
it cannot be rolled back by a shared lock or two-phase protocol. Compensation is the only
mechanism: for every forward operation `f`, design an inverse `f⁻¹` that restores the system
to the pre-`f` state, then invoke compensations in reverse order on failure.

## Saga State Machine in a Durable Object

A coordinator Durable Object persists the saga state. Each step updates the stored record so
the saga survives container restarts and is re-entrant on retry.

```typescript
type SagaStep = 'pending' | 'charging' | 'boosting' | 'notifying' | 'done' | 'compensating' | 'failed';

interface BoostSaga {
  sagaId: string;
  postId: string;
  userId: string;
  creditAmount: number;
  chargeApplied: boolean;
  boostApplied: boolean;
  step: SagaStep;
  error?: string;
}

export class BoostSagaCoordinator extends DurableObject {
  async run(postId: string, userId: string, creditAmount: number): Promise<void> {
    const sagaId = crypto.randomUUID();
    let saga: BoostSaga = {
      sagaId, postId, userId, creditAmount,
      chargeApplied: false, boostApplied: false,
      step: 'pending',
    };
    await this.ctx.storage.put('saga', saga);

    try {
      saga = await this.#stepCharge(saga);
      saga = await this.#stepBoost(saga);
      saga = await this.#stepNotify(saga);
      saga.step = 'done';
      await this.ctx.storage.put('saga', saga);
    } catch (err) {
      saga.error = String(err);
      saga.step = 'compensating';
      await this.ctx.storage.put('saga', saga);
      await this.#compensate(saga);
    }
  }

  async #stepCharge(saga: BoostSaga): Promise<BoostSaga> {
    const env = this.env as Env;
    saga.step = 'charging';
    await this.ctx.storage.put('saga', saga);

    await env.DB.prepare(
      `UPDATE users SET karma = karma - ? WHERE id = ? AND karma >= ?`
    ).bind(saga.creditAmount, saga.userId, saga.creditAmount).run();

    saga.chargeApplied = true;
    await this.ctx.storage.put('saga', saga);
    return saga;
  }

  async #stepBoost(saga: BoostSaga): Promise<BoostSaga> {
    const env = this.env as Env;
    saga.step = 'boosting';
    await this.ctx.storage.put('saga', saga);

    const postDO = env.POSTS.get(env.POSTS.idFromName(saga.postId));
    await postDO.fetch('https://internal/boost', { method: 'POST' });

    saga.boostApplied = true;
    await this.ctx.storage.put('saga', saga);
    return saga;
  }

  async #stepNotify(saga: BoostSaga): Promise<BoostSaga> {
    const env = this.env as Env;
    saga.step = 'notifying';
    await this.ctx.storage.put('saga', saga);

    await env.EVENTS.send({
      eventType: 'PostBoosted',
      postId: saga.postId,
      boosterId: saga.userId,
    });

    return saga;
  }

  async #compensate(saga: BoostSaga): Promise<void> {
    const env = this.env as Env;

    // Reverse order: undo boost before refunding credits.
    if (saga.boostApplied) {
      try {
        const postDO = env.POSTS.get(env.POSTS.idFromName(saga.postId));
        await postDO.fetch('https://internal/unboost', { method: 'POST' });
      } catch {
        // Log and alert — manual intervention may be required.
        console.error(`Failed to unboost post ${saga.postId} for saga ${saga.sagaId}`);
      }
    }

    if (saga.chargeApplied) {
      try {
        await env.DB.prepare(
          `UPDATE users SET karma = karma + ? WHERE id = ?`
        ).bind(saga.creditAmount, saga.userId).run();
      } catch {
        console.error(`Failed to refund karma for user ${saga.userId} saga ${saga.sagaId}`);
      }
    }

    saga.step = 'failed';
    await this.ctx.storage.put('saga', saga);
  }
}
```

## Compensating Action Design

Each compensating operation must be idempotent: running it twice must not double-refund or
double-unboost. Use conditional SQL (`karma = karma + ? WHERE id = ?`) which is naturally
idempotent, and guard the Durable Object unboost with a stored flag.

```typescript
// Inside the Post Durable Object.
export class PostObject extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/boost' && request.method === 'POST') {
      const count = (await this.ctx.storage.get<number>('boostCount')) ?? 0;
      await this.ctx.storage.put('boostCount', count + 1);
      return new Response('OK');
    }

    if (url.pathname === '/unboost' && request.method === 'POST') {
      const count = (await this.ctx.storage.get<number>('boostCount')) ?? 0;
      // Floor at 0 — idempotent regardless of call count.
      await this.ctx.storage.put('boostCount', Math.max(0, count - 1));
      return new Response('OK');
    }

    return new Response('Not Found', { status: 404 });
  }
}
```

## Saga Recovery on Restart

If the coordinator Durable Object is evicted mid-saga, the stored `saga` record allows it to
resume. An alarm fires after a grace period to detect stuck sagas and trigger compensation.

```typescript
export class BoostSagaCoordinator extends DurableObject {
  async alarm(): Promise<void> {
    const saga = await this.ctx.storage.get<BoostSaga>('saga');
    if (!saga) return;

    if (saga.step !== 'done' && saga.step !== 'failed') {
      // Saga is stuck — compensate defensively.
      saga.step = 'compensating';
      await this.ctx.storage.put('saga', saga);
      await this.#compensate(saga);
    }
  }

  async run(postId: string, userId: string, creditAmount: number): Promise<void> {
    // Arm a watchdog alarm before the first step.
    this.ctx.storage.setAlarm(Date.now() + 30_000); // 30 s timeout
    // … saga steps as above …
  }
}
```

## Anti-patterns

- Designing forward steps that cannot be compensated (e.g., an irreversible external payment
  without a refund API) — model these as the last step in the saga so compensation never needs
  to undo them.
- Sharing database rows between forward and compensating steps without optimistic locking — a
  concurrent forward saga for the same user may conflict with an ongoing compensation.
- Logging compensation failures and continuing silently — failed compensation leaves the system
  in an inconsistent state; alert and halt further steps.
- Relying on Queues for the coordination loop itself without a persistent coordinator — a
  choreography-only saga has no single source of truth for which steps completed.

## Gotchas

- D1 `UPDATE … WHERE karma >= ?` returns zero rows affected if the user has insufficient karma;
  check `meta.changes` and treat zero as a business error, not a technical failure.
- Durable Object storage writes are durable but not synchronous across all edge nodes; do not
  assume the stored state is visible to another DO request that arrives within milliseconds.
- Compensating a notification fan-out (Queue send) is often impractical — design notification
  steps to be the last step so they only fire after all reversible steps succeed.
- For example project's anonymous model, the saga coordinator must not store identifying data beyond
  the opaque `userId` token.

## Verification

1. Trigger a boost saga. Inject a failure in `#stepNotify`. Assert karma is refunded and
   `boostCount` returns to its pre-saga value after compensation.
2. Force-evict the DO mid-saga. Let the watchdog alarm fire. Assert the saga reaches `'failed'`
   and all applied steps are compensated.
3. Call `/unboost` twice on a post with boost count = 1. Assert count floors at 0 (idempotency).
4. Verify `saga.step` audit trail: `pending → charging → boosting → notifying` (success path)
   and `pending → charging → boosting → compensating → failed` (failure path).

## Related

- [Saga Pattern — Orchestration](saga-pattern-orchestration.md)
- [Saga Pattern — Choreography](saga-pattern-choreography.md)
- [Process Manager vs. Saga](process-manager-vs-saga.md)
- [Two-Phase Commit — Alternatives](two-phase-commit-alternatives.md)
- [Durable Objects Workflow State Machine](durable-objects-workflow-state-machine.md)
- [Idempotency Design](idempotency-design.md)

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/d1/
- https://microservices.io/patterns/data/saga.html
