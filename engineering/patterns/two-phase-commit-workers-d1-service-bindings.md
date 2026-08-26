# Two-Phase Commit Across Workers via Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A business operation must update data in two or more independent services — for example,
deducting credits in a billing Worker and creating a record in a fulfilment Worker —
and both changes must either both succeed or both be rolled back. Sagas with compensating
transactions solve many such cases, but sometimes you want *true atomicity*: neither
service commits unless both agree, without requiring you to write rollback logic for
every failure mode.

## Context

Two-Phase Commit (2PC) is a distributed transaction protocol with two rounds:

1. **Prepare phase** — the *coordinator* asks each *participant* to "vote": can you
   commit this transaction? Each participant writes the intent to durable storage (a
   prepare log) and replies `yes` or `no`.
2. **Commit phase** — if all participants vote `yes`, the coordinator sends `commit`;
   if any votes `no`, the coordinator sends `abort`. Participants finalise or undo.

On Cloudflare, the coordinator is typically a Durable Object (for durable coordinator
state across retries), and participants are Service Binding Workers backed by D1.
Durable Objects provide the single-writer, crash-recoverable coordinator needed for
2PC correctness.

**When to use 2PC vs Saga:**
- Use 2PC when compensation logic is complex, error-prone, or impossible (e.g.
  decrementing a counter that another actor may have already modified).
- Use Sagas when long-running operations or multiple hops make the blocking prepare
  phase impractical.
- 2PC adds latency (two network round trips across service bindings); reserve it for
  operations where consistency is worth the cost.

## Coordinator Durable Object

```typescript
// coordinator/two-phase-coordinator.ts
export interface ParticipantVote {
  participantId: string;
  vote: 'yes' | 'no';
  reason?: string;
}

export interface TransactionState {
  txId: string;
  phase: 'preparing' | 'committing' | 'aborting' | 'committed' | 'aborted';
  participants: string[];
  votes: ParticipantVote[];
  payload: unknown;
  startedAt: string;
}

export class TwoPhaseCoordinator implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/begin' && request.method === 'POST') {
      return this.beginTransaction(await request.json());
    }
    if (url.pathname === '/vote' && request.method === 'POST') {
      return this.receiveVote(await request.json());
    }
    if (url.pathname === '/status') {
      return this.getStatus();
    }
    return new Response('Not Found', { status: 404 });
  }

  private async beginTransaction(body: {
    txId: string;
    participants: string[];
    payload: unknown;
  }): Promise<Response> {
    const { txId, participants, payload } = body;

    const existing = await this.state.storage.get<TransactionState>('tx');
    if (existing) {
      return new Response(JSON.stringify({ error: 'coordinator_busy', txId: existing.txId }), {
        status: 409,
      });
    }

    const tx: TransactionState = {
      txId,
      phase: 'preparing',
      participants,
      votes: [],
      payload,
      startedAt: new Date().toISOString(),
    };
    await this.state.storage.put('tx', tx);
    return new Response(JSON.stringify({ txId, phase: 'preparing' }), { status: 202 });
  }

  private async receiveVote(body: ParticipantVote): Promise<Response> {
    const tx = await this.state.storage.get<TransactionState>('tx');
    if (!tx || tx.phase !== 'preparing') {
      return new Response(JSON.stringify({ error: 'no_active_prepare' }), { status: 409 });
    }

    tx.votes.push(body);

    const allVoted = tx.participants.every((p) =>
      tx.votes.some((v) => v.participantId === p),
    );

    if (!allVoted) {
      await this.state.storage.put('tx', tx);
      return new Response(JSON.stringify({ waiting: true, votesReceived: tx.votes.length }));
    }

    // Decision: commit only if all voted yes
    const allYes = tx.votes.every((v) => v.vote === 'yes');
    tx.phase = allYes ? 'committing' : 'aborting';
    await this.state.storage.put('tx', tx);

    return new Response(JSON.stringify({ decision: tx.phase }));
  }

  private async getStatus(): Promise<Response> {
    const tx = await this.state.storage.get<TransactionState>('tx');
    if (!tx) return new Response(JSON.stringify({ phase: 'idle' }));
    return new Response(JSON.stringify(tx));
  }
}
```

## Participant Worker (Prepare / Commit / Abort)

```typescript
// participant/billing-worker.ts — one participant in the 2PC protocol
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/prepare' && request.method === 'POST') {
      const { txId, amount, accountId } = await request.json<{
        txId: string;
        amount: number;
        accountId: string;
      }>();
      return prepare(txId, amount, accountId, env.DB);
    }

    if (url.pathname === '/commit' && request.method === 'POST') {
      const { txId } = await request.json<{ txId: string }>();
      return commit(txId, env.DB);
    }

    if (url.pathname === '/abort' && request.method === 'POST') {
      const { txId } = await request.json<{ txId: string }>();
      return abort(txId, env.DB);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function prepare(
  txId: string,
  amount: number,
  accountId: string,
  db: D1Database,
): Promise<Response> {
  // Write prepare log — durable record of intent
  await db.batch([
    db
      .prepare(
        `INSERT OR IGNORE INTO prepare_log (tx_id, participant, amount, account_id, prepared_at)
         VALUES (?, 'billing', ?, ?, ?)`,
      )
      .bind(txId, amount, accountId, new Date().toISOString()),
  ]);

  // Check balance — vote no if insufficient funds
  const row = await db
    .prepare('SELECT balance FROM accounts WHERE id = ?')
    .bind(accountId)
    .first<{ balance: number }>();

  if (!row || row.balance < amount) {
    return new Response(
      JSON.stringify({ vote: 'no', reason: 'insufficient_funds' }),
      { status: 200 },
    );
  }

  return new Response(JSON.stringify({ vote: 'yes' }), { status: 200 });
}

async function commit(txId: string, db: D1Database): Promise<Response> {
  const log = await db
    .prepare('SELECT * FROM prepare_log WHERE tx_id = ? AND participant = ?')
    .bind(txId, 'billing')
    .first<{ amount: number; account_id: string }>();

  if (!log) return new Response(JSON.stringify({ error: 'no_prepare_log' }), { status: 409 });

  await db.batch([
    db
      .prepare('UPDATE accounts SET balance = balance - ? WHERE id = ?')
      .bind(log.amount, log.account_id),
    db
      .prepare('DELETE FROM prepare_log WHERE tx_id = ? AND participant = ?')
      .bind(txId, 'billing'),
  ]);

  return new Response(JSON.stringify({ committed: true }), { status: 200 });
}

async function abort(txId: string, db: D1Database): Promise<Response> {
  // Simply remove the prepare log — no state was applied during prepare
  await db
    .prepare('DELETE FROM prepare_log WHERE tx_id = ? AND participant = ?')
    .bind(txId, 'billing')
    .run();

  return new Response(JSON.stringify({ aborted: true }), { status: 200 });
}
```

## Orchestrating a Full 2PC Transaction

```typescript
// orchestrator.ts — called by the gateway Worker
export interface Env {
  COORDINATOR_DO: DurableObjectNamespace;
  BILLING_SERVICE: Fetcher;
  FULFILMENT_SERVICE: Fetcher;
}

export async function runTwoPhaseCommit(
  txId: string,
  billingPayload: { amount: number; accountId: string },
  fulfilmentPayload: { orderId: string; items: string[] },
  env: Env,
): Promise<{ success: boolean; decision: string }> {
  const coordinator = env.COORDINATOR_DO.get(
    env.COORDINATOR_DO.idFromName(txId),
  );

  // --- BEGIN ---
  await coordinator.fetch('http://do/begin', {
    method: 'POST',
    body: JSON.stringify({ txId, participants: ['billing', 'fulfilment'], payload: {} }),
    headers: { 'Content-Type': 'application/json' },
  });

  // --- PREPARE PHASE (parallel) ---
  const [billingVote, fulfilmentVote] = await Promise.all([
    env.BILLING_SERVICE.fetch('http://billing/prepare', {
      method: 'POST',
      body: JSON.stringify({ txId, ...billingPayload }),
      headers: { 'Content-Type': 'application/json' },
    }).then((r) => r.json<{ vote: 'yes' | 'no'; reason?: string }>()),

    env.FULFILMENT_SERVICE.fetch('http://fulfilment/prepare', {
      method: 'POST',
      body: JSON.stringify({ txId, ...fulfilmentPayload }),
      headers: { 'Content-Type': 'application/json' },
    }).then((r) => r.json<{ vote: 'yes' | 'no'; reason?: string }>()),
  ]);

  // Register votes with coordinator
  const [billingDecision] = await Promise.all([
    coordinator.fetch('http://do/vote', {
      method: 'POST',
      body: JSON.stringify({ participantId: 'billing', ...billingVote }),
      headers: { 'Content-Type': 'application/json' },
    }).then((r) => r.json<{ decision?: string }>()),

    coordinator.fetch('http://do/vote', {
      method: 'POST',
      body: JSON.stringify({ participantId: 'fulfilment', ...fulfilmentVote }),
      headers: { 'Content-Type': 'application/json' },
    }),
  ]);

  const decision = billingDecision.decision ?? 'committing';

  // --- COMMIT / ABORT PHASE (parallel) ---
  const action = decision === 'committing' ? 'commit' : 'abort';
  await Promise.all([
    env.BILLING_SERVICE.fetch(`http://billing/${action}`, {
      method: 'POST',
      body: JSON.stringify({ txId }),
      headers: { 'Content-Type': 'application/json' },
    }),
    env.FULFILMENT_SERVICE.fetch(`http://fulfilment/${action}`, {
      method: 'POST',
      body: JSON.stringify({ txId }),
      headers: { 'Content-Type': 'application/json' },
    }),
  ]);

  return { success: decision === 'committing', decision };
}
```

## Recovery: Handling Coordinator Crashes

```typescript
// recovery/recover-stalled-tx.ts — run on a cron schedule
export async function recoverStalledTransactions(
  db: D1Database,
  coordinator: DurableObjectStub,
): Promise<void> {
  // Find prepare log entries older than 60 seconds with no corresponding commit/abort
  const stalled = await db
    .prepare(
      `SELECT tx_id FROM prepare_log
       WHERE prepared_at < datetime('now', '-60 seconds')
       GROUP BY tx_id`,
    )
    .all<{ tx_id: string }>();

  for (const { tx_id } of stalled.results) {
    const statusRes = await coordinator.fetch('http://do/status');
    const status = await statusRes.json<{ phase?: string; txId?: string }>();

    if (status.txId === tx_id && status.phase === 'committing') {
      // Coordinator decided commit but participant missed it — apply commit
      await db
        .prepare('DELETE FROM prepare_log WHERE tx_id = ?')
        .bind(tx_id)
        .run();
      console.log({ event: 'recovered_commit', tx_id });
    } else {
      // Default to abort for unknown or aborted state
      await db
        .prepare('DELETE FROM prepare_log WHERE tx_id = ?')
        .bind(tx_id)
        .run();
      console.log({ event: 'recovered_abort', tx_id });
    }
  }
}
```

## Anti-patterns

- **Running 2PC across more than 3–4 participants** — the probability that at least one
  participant fails in the prepare window grows with participant count. Use Sagas with
  compensation for workflows with many steps.
- **Not persisting the prepare log to D1** — an in-memory prepare state is lost on
  Worker restart; the prepare log is the durability guarantee of the protocol.
- **Allowing participants to apply state during prepare** — prepare must only *lock*
  or *record intent*, never modify live data. Actual state changes happen only in the
  commit phase.
- **No recovery / timeout handler** — if the coordinator crashes after `committing` is
  stored but before sending `commit` to participants, the system is in a blocking state
  forever without a recovery Worker.
- **Using 2PC for non-critical background work** — the latency cost (two network round
  trips across service bindings) is only justified for operations requiring true atomicity.

## Gotchas

- Workers CPU time limits apply across the full orchestration: prepare + voting + commit
  must complete within a single Worker invocation. For long-running participants, use
  the Durable Object coordinator as the long-lived process and respond to the client
  with a transaction ID for polling.
- D1 does not expose advisory locks; the "lock" during prepare is implemented as the
  prepare log row itself. If two coordinators race to prepare the same account, the
  second prepare sees the first's log and can vote `no` proactively.
- Service Binding calls count against the calling Worker's CPU budget and are subject
  to the 50 subrequest limit per Worker invocation. Large fan-outs should delegate to
  a Queue instead.
- Durable Objects have a single-threaded, single-instance model: two concurrent 2PC
  operations sharing the same coordinator DO name will serialise through
  `blockConcurrencyWhile`. Use the `txId` as the DO name for per-transaction isolation.

## Verification

```bash
# Integration test: verify commit succeeds when all participants vote yes
curl -X POST https://api.example.com/transfer \
  -H "Content-Type: application/json" \
  -d '{"from":"account-A","to":"account-B","amount":100}'
# Expect: {"success":true,"decision":"committing"}

# Verify abort when billing has insufficient funds
curl -X POST https://api.example.com/transfer \
  -H "Content-Type: application/json" \
  -d '{"from":"account-empty","to":"account-B","amount":9999}'
# Expect: {"success":false,"decision":"aborting"}

# Confirm prepare_log is empty after committed transaction
wrangler d1 execute <DB_NAME> \
  --command "SELECT COUNT(*) FROM prepare_log WHERE tx_id = '<txId>'"
# Expect: 0
```

## Related

- `saga-pattern-multi-step-workers.md`
- `compensating-transaction-payment-flows.md`
- `distributed-lock-durable-objects.md`
- `idempotency-key-pattern-workers-d1.md`
- `unit-of-work-pattern-d1-workers.md`
- `outbox-pattern-d1-reliable-publishing.md`

## Sources

- Gray & Lamport — A New Solution to Dijkstra's Concurrent Programming Problem (2PC foundations)
- Designing Data-Intensive Applications — Martin Kleppmann (Chapter 9: Consistency and Consensus)
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
