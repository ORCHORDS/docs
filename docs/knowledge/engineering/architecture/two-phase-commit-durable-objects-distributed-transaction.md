# Two-Phase Commit with Durable Objects Distributed Transaction

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to atomically update two or more independent resources — e.g. debit a wallet DO
and credit another wallet DO — where neither a single D1 transaction nor a saga with
compensations is sufficient because business rules forbid partial rollback visibility.
Classic cases: cross-account transfers, inventory reservation paired with order creation
in separate bounded contexts, or multi-tenant ledger entries that must commit together.

## Context

True distributed 2PC is notoriously fragile; Cloudflare Durable Objects make a
lightweight, correct implementation feasible because each DO is a single-threaded actor
with durable storage and an alarm-based recovery path. A Coordinator DO orchestrates
Phase 1 (prepare) and Phase 2 (commit/abort), while Participant DOs implement a simple
state machine: `idle → prepared → committed | aborted`. The coordinator persists its
decision before issuing Phase 2 messages, guaranteeing recovery after any crash.

## 1. Participant Durable Object

```typescript
// src/participant-do.ts
import { DurableObject } from "cloudflare:workers";

type ParticipantState = "idle" | "prepared" | "committed" | "aborted";

interface ParticipantRecord {
  txId: string;
  state: ParticipantState;
  delta: number; // business payload
  balance: number;
}

export class WalletDO extends DurableObject<Env> {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    switch (url.pathname) {
      case "/prepare": return this.prepare(req);
      case "/commit": return this.commit(req);
      case "/abort": return this.abort(req);
      case "/balance": return this.getBalance();
      default: return new Response("not found", { status: 404 });
    }
  }

  async prepare(req: Request): Promise<Response> {
    const { txId, delta } = await req.json<{ txId: string; delta: number }>();
    const balance = (await this.ctx.storage.get<number>("balance")) ?? 0;
    if (balance + delta < 0) {
      return Response.json({ vote: "abort", reason: "insufficient funds" });
    }
    // Write tentative record — balance not yet changed
    await this.ctx.storage.put<ParticipantRecord>(`tx:${txId}`, {
      txId,
      state: "prepared",
      delta,
      balance,
    });
    return Response.json({ vote: "commit" });
  }

  async commit(req: Request): Promise<Response> {
    const { txId } = await req.json<{ txId: string }>();
    const rec = await this.ctx.storage.get<ParticipantRecord>(`tx:${txId}`);
    if (!rec || rec.state === "committed") return Response.json({ ok: true });
    await this.ctx.storage.transaction(async (txn) => {
      const balance = (await txn.get<number>("balance")) ?? 0;
      await txn.put("balance", balance + rec.delta);
      await txn.put<ParticipantRecord>(`tx:${txId}`, { ...rec, state: "committed" });
    });
    return Response.json({ ok: true });
  }

  async abort(req: Request): Promise<Response> {
    const { txId } = await req.json<{ txId: string }>();
    const rec = await this.ctx.storage.get<ParticipantRecord>(`tx:${txId}`);
    if (!rec) return Response.json({ ok: true });
    await this.ctx.storage.put<ParticipantRecord>(`tx:${txId}`, {
      ...rec,
      state: "aborted",
    });
    return Response.json({ ok: true });
  }

  async getBalance(): Promise<Response> {
    return Response.json({ balance: (await this.ctx.storage.get<number>("balance")) ?? 0 });
  }
}
```

## 2. Coordinator Durable Object

```typescript
// src/coordinator-do.ts
import { DurableObject } from "cloudflare:workers";

type CoordinatorState = "pending" | "prepared" | "committed" | "aborted";

interface CoordinatorRecord {
  txId: string;
  state: CoordinatorState;
  participants: Array<{ name: string; delta: number }>;
}

export class TransactionCoordinatorDO extends DurableObject<Env> {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/begin") return this.begin(req);
    if (url.pathname === "/recover") return this.recover();
    return new Response("not found", { status: 404 });
  }

  async begin(req: Request): Promise<Response> {
    const { txId, participants } = await req.json<{
      txId: string;
      participants: Array<{ name: string; delta: number }>;
    }>();

    const rec: CoordinatorRecord = { txId, state: "pending", participants };
    await this.ctx.storage.put(`coord:${txId}`, rec);
    // Set a recovery alarm in case coordinator dies mid-flight
    await this.ctx.storage.setAlarm(Date.now() + 30_000);

    // Phase 1: Prepare
    const votes = await Promise.all(
      participants.map(async ({ name, delta }) => {
        const stub = this.env.WALLET.get(this.env.WALLET.idFromName(name));
        const resp = await stub.fetch(
          new Request("https://do/prepare", {
            method: "POST",
            body: JSON.stringify({ txId, delta }),
          })
        );
        return resp.json<{ vote: string; reason?: string }>();
      })
    );

    const decision: "committed" | "aborted" = votes.every((v) => v.vote === "commit")
      ? "committed"
      : "aborted";

    // Persist decision BEFORE Phase 2 — crash-safe
    rec.state = decision === "committed" ? "prepared" : "aborted";
    await this.ctx.storage.put(`coord:${txId}`, rec);

    // Phase 2: Commit or Abort
    await this.phase2(txId, participants, decision);

    await this.ctx.storage.deleteAlarm();
    return Response.json({ txId, outcome: decision });
  }

  private async phase2(
    txId: string,
    participants: Array<{ name: string; delta: number }>,
    decision: "committed" | "aborted"
  ): Promise<void> {
    const path = decision === "committed" ? "/commit" : "/abort";
    await Promise.all(
      participants.map(({ name }) => {
        const stub = this.env.WALLET.get(this.env.WALLET.idFromName(name));
        return stub.fetch(
          new Request(`https://do${path}`, {
            method: "POST",
            body: JSON.stringify({ txId }),
          })
        );
      })
    );
    const rec = await this.ctx.storage.get<CoordinatorRecord>(`coord:${txId}`);
    if (rec) {
      await this.ctx.storage.put(`coord:${txId}`, {
        ...rec,
        state: decision,
      });
    }
  }

  // Alarm-based recovery: re-drive Phase 2 for any stuck transactions
  async alarm(): Promise<void> {
    const all = await this.ctx.storage.list<CoordinatorRecord>({ prefix: "coord:" });
    for (const [, rec] of all) {
      if (rec.state === "prepared") {
        await this.phase2(rec.txId, rec.participants, "committed");
      } else if (rec.state === "pending") {
        await this.phase2(rec.txId, rec.participants, "aborted");
      }
    }
  }

  async recover(): Promise<Response> {
    await this.alarm();
    return new Response("recovery triggered");
  }
}
```

## 3. Gateway Worker

```typescript
// src/gateway.ts
import { v4 as uuid } from "uuid";

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { from, to, amount } = await req.json<{
      from: string;
      to: string;
      amount: number;
    }>();

    const txId = uuid();
    const coordId = env.COORDINATOR.idFromName(`coord-${from}-${to}`);
    const coord = env.COORDINATOR.get(coordId);

    const result = await coord.fetch(
      new Request("https://do/begin", {
        method: "POST",
        body: JSON.stringify({
          txId,
          participants: [
            { name: from, delta: -amount },
            { name: to, delta: amount },
          ],
        }),
      })
    );

    const { outcome } = await result.json<{ txId: string; outcome: string }>();
    return Response.json({ txId, outcome }, { status: outcome === "committed" ? 200 : 409 });
  },
};
```

## 4. Wrangler Configuration

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "WALLET"
class_name = "WalletDO"

[[durable_objects.bindings]]
name = "COORDINATOR"
class_name = "TransactionCoordinatorDO"

[[migrations]]
tag = "v1"
new_classes = ["WalletDO", "TransactionCoordinatorDO"]
```

## Anti-patterns

- **Skipping coordinator persistence before Phase 2**: if the coordinator crashes between
  deciding and messaging participants, the transaction is unrecoverable.
- **Using KV as coordinator log**: KV is eventually consistent; the coordinator log
  must be in DO storage for linearisability.
- **Blocking the client during Phase 2**: make Phase 2 async (Queue-driven) for
  high-throughput paths; return the decision immediately after persisting it.
- **Unbounded participant lists**: 2PC latency scales linearly with participants; cap at
  ~10 participants per transaction or decompose into nested sagas.
- **No idempotency on commit/abort**: participants must tolerate duplicate Phase 2 messages.

## Gotchas

- DO `transaction()` is limited to a single DO; cross-DO atomicity requires coordinator-
  managed 2PC as shown — there is no native XA equivalent.
- Alarm-based recovery fires at least once but could fire multiple times; all Phase 2
  operations must be idempotent.
- Participant `prepare` must lock resources without exposing them — balance changes happen
  only on `commit`, never on `prepare`.
- A "prepared" coordinator that never receives its own alarm will be stuck — always set
  the alarm before starting Phase 1, and delete it only after Phase 2 completes.
- Cross-jurisdiction DO placement can add significant latency; pin coordinators and
  participants to the same jurisdiction where data-residency rules allow.

## Verification

```bash
# Transfer $50 from alice to bob
curl -X POST https://worker.example.com/transfer \
  -H "Content-Type: application/json" \
  -d '{"from":"alice","to":"bob","amount":50}'
# Expected: {"txId":"...","outcome":"committed"}

# Verify balances
curl https://worker.example.com/balance/alice  # reduced by 50
curl https://worker.example.com/balance/bob    # increased by 50

# Trigger recovery on stuck coordinator
curl -X POST https://worker.example.com/recover
```

## Related

- `two-phase-commit-alternatives.md`
- `actor-model-durable-objects-workers.md`
- `saga-pattern-orchestration.md`
- `durable-objects-workflow-state-machine.md`
- `idempotency-design.md`

## Sources

- Cloudflare Durable Objects storage transactions — https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- Gray & Reuter, *Transaction Processing* (1992) — 2PC protocol definition
- Martin Kleppmann, *Designing Data-Intensive Applications* ch. 9 — distributed transactions
- Cloudflare DO alarms for recovery — https://developers.cloudflare.com/durable-objects/api/alarms/
