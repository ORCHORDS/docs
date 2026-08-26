# saga-pattern

**Issue:** Distributed transactions across multiple services
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to transfer money from user A to user B. The flow:
1. Debit A
2. Credit B
3. Record the transfer

If step 1 succeeds but step 2 fails, A is debited but B is
not credited. The money is lost. You have an inconsistent
state.

## Root cause
**Distributed transactions across services can't be atomic.**
Each service has its own DB. You can't have a single
transaction across all of them.

**Source:** Chris Richardson — Microservices.io:
https://microservices.io/patterns/data/saga.html

> "A saga is a sequence of local transactions. ... Each local
> transaction updates the data within a single service. The
> first transaction in a saga is initiated by an external
> request ... Each subsequent transaction is initiated by the
> completion of the previous one."

## The pattern

### Choreography
Each service publishes an event; other services react.

```ts
// Service A: debit
await db.run(`UPDATE accounts SET balance = balance - 100 WHERE id = 'A'`);
await queue.publish({ type: 'account.debited', accountId: 'A', amount: 100 });

// Service B: react to account.debited
queue.subscribe('account.debited', async (msg) => {
  await db.run(`UPDATE accounts SET balance = balance + 100 WHERE id = 'B'`);
  await queue.publish({ type: 'account.credited', accountId: 'B', amount: 100 });
});

// Service C: react to account.credited
queue.subscribe('account.credited', async (msg) => {
  await db.run(`INSERT INTO transfers (from, to, amount) VALUES (?, ?, ?)`);
});
```

### Orchestration
A central orchestrator manages the flow.

```ts
class TransferOrchestrator {
  async transfer(from: string, to: string, amount: number): Promise<void> {
    try {
      await serviceA.debit(from, amount);
      await serviceB.credit(to, amount);
      await serviceC.record(from, to, amount);
    } catch (err) {
      // Compensating actions
      if (err.step === 'B') {
        await serviceA.credit(from, amount);  // reverse the debit
      }
      if (err.step === 'C') {
        await serviceB.debit(to, amount);
        await serviceA.credit(from, amount);
      }
      throw err;
    }
  }
}
```

## Compensating actions

The hardest part of a saga. Each step needs a "undo" that
might not be a simple reverse:

| Step | Forward | Compensate |
|---|---|---|
| Debit account | Subtract balance | Add balance (refund) |
| Send email | Send | (Can't unsend — log + accept) |
| Reserve inventory | Mark reserved | Release the reservation |
| Ship package | Mark shipped | (Can't un-ship — start return process) |

For irreversible steps, the saga can't truly roll back. It
can only compensate for the parts that are reversible, and
log the rest for manual handling.

## Idempotency

Each step must be **idempotent** — running it twice has the
same effect as running it once. This is because:
- Network failures cause retries
- The orchestrator may re-run a step
- A duplicate message can be processed twice

```ts
async function idempotentDebit(accountId: string, amount: number, transactionId: string, db: D1Database): Promise<void> {
  // Check if this transaction was already processed
  const existing = await db.prepare(
    `SELECT 1 FROM processed_transactions WHERE id = ?`
  ).bind(transactionId).first();
  if (existing) return;  // Already processed

  await db.prepare(
    `UPDATE accounts SET balance = balance - ? WHERE id = ?`
  ).bind(amount, accountId).run();

  await db.prepare(
    `INSERT INTO processed_transactions (id, action, created_at) VALUES (?, 'debit', ?)`
  ).bind(transactionId, Date.now()).run();
}
```

The `processed_transactions` table ensures each step runs
exactly once, even with retries.

## When to use a saga

✅ Use a saga when:
- **You have a multi-step process** that must eventually
  complete
- **Each step is a separate service / DB**
- **The process can be retried safely** (idempotent steps)
- **You can compensate for partial failures** (or accept
  them)

❌ Don't use a saga when:
- **The entire process fits in one service** (use a single
  DB transaction)
- **The steps can't be compensated** (e.g. "send physical
  mail" — once it's sent, it's sent)
- **You need immediate consistency** (sagas are eventually
  consistent)

## Verification
- **Test:** `test/saga.test.ts > happy path: all 3 steps
  complete` — passes
- **Test:** `test/saga.test.ts > step 2 fails: step 1
  compensates` — passes
- **Test:** `test/saga.test.ts > step is retried: idempotency
  holds` — passes
- **Live:** Saga completion is monitored; alerts on
  stuck sagas

## Gotchas
- **The saga can get stuck.** If a step never completes
  (worker dies, message lost), the saga is stuck. Add a
  timeout + manual intervention.
- **The compensation is not always possible.** Some steps
  (e.g. "send email") can't be undone. Design for "best
  effort compensation + manual cleanup for the rest."
- **The orchestrator is a SPOF.** If the orchestrator dies
  mid-saga, the saga is stuck. Use a durable orchestrator
  (e.g. CF Workflows, Temporal, AWS Step Functions).
- **A long saga holds state.** If the saga takes days
  (e.g. "place order → ship → deliver → confirm"), the
  state must persist. Use a durable workflow engine.
- **Testing sagas is hard.** The failure modes are
  combinatorial. Use property-based testing (e.g. fast-check).

## Related
- `event-sourcing.md` (sagas are event-driven)
- `queue-system-design.md` (the queue is the saga's backbone)
- `idempotency-keys.md` (essential for saga steps)
- Chris Richardson: https://microservices.io/patterns/data/saga.html
- Temporal: https://temporal.io/
- CF Workflows: https://developers.cloudflare.com/workflows/
