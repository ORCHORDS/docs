# Compensating Transaction Pattern with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A multi-step business operation — charge a payment, create an order record, send a confirmation email — must remain consistent even when a later step fails. D1 transactions span only a single database and cannot atomically commit work across external APIs. You need a saga-style rollback mechanism that tracks completed steps and executes compensating actions in reverse order on failure.

---

## Context

The compensating transaction pattern (also called a saga) breaks a distributed operation into ordered steps, each with a corresponding undo action. Every step writes its status to a D1 `transaction_steps` table before proceeding, creating a durable audit log. If a step throws, the orchestrator reads the log and calls compensating functions in reverse order — for example, a payment charge is reversed with a refund, and a created order is deleted. Idempotency keys ensure that compensating actions are safe to retry if the Worker is interrupted mid-rollback. Steps that exceed a maximum retry count are flagged `requires-manual-review` so operations staff can intervene without data loss.

---

## D1 Schema

```sql
-- migrations/0001_transaction_steps.sql
CREATE TABLE IF NOT EXISTS transaction_steps (
  id              TEXT    PRIMARY KEY,   -- UUID
  saga_id         TEXT    NOT NULL,      -- groups steps for one business operation
  step_name       TEXT    NOT NULL,      -- e.g. 'charge_payment'
  status          TEXT    NOT NULL       -- pending | completed | compensated | failed | requires_manual_review
                  CHECK(status IN ('pending','completed','compensated','failed','requires_manual_review')),
  idempotency_key TEXT    NOT NULL UNIQUE,
  attempt_count   INTEGER NOT NULL DEFAULT 0,
  payload         TEXT,                  -- JSON: input data for compensation
  error           TEXT,
  created_at      INTEGER NOT NULL,      -- Unix ms
  updated_at      INTEGER NOT NULL
);

CREATE INDEX idx_saga_id ON transaction_steps (saga_id);
```

---

## Implementation

```typescript
// src/compensating-transaction.ts
import { randomUUID } from "node:crypto";

export interface Env {
  DB: D1Database;
}

const MAX_RETRIES = 3;

// ── Types ──────────────────────────────────────────────────────────────────

interface StepRecord {
  id: string;
  sagaId: string;
  stepName: string;
  idempotencyKey: string;
  payload: string;
}

type StepFn   = (payload: unknown) => Promise<unknown>;
type UndoFn   = (payload: unknown) => Promise<void>;

interface Step {
  name:    string;
  execute: StepFn;
  undo:    UndoFn;
}

// ── Helpers ────────────────────────────────────────────────────────────────

async function recordStep(
  db: D1Database,
  sagaId: string,
  stepName: string,
  payload: unknown,
  status: string
): Promise<string> {
  const id             = randomUUID();
  const idempotencyKey = `${sagaId}:${stepName}`;
  const now            = Date.now();

  await db
    .prepare(
      `INSERT INTO transaction_steps
         (id, saga_id, step_name, status, idempotency_key, attempt_count, payload, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)`
    )
    .bind(id, sagaId, stepName, status, idempotencyKey, JSON.stringify(payload), now, now)
    .run();

  return id;
}

async function updateStep(
  db: D1Database,
  id: string,
  status: string,
  error?: string
): Promise<void> {
  await db
    .prepare(
      `UPDATE transaction_steps
         SET status = ?, error = ?, attempt_count = attempt_count + 1, updated_at = ?
       WHERE id = ?`
    )
    .bind(status, error ?? null, Date.now(), id)
    .run();
}

// ── Orchestrator ───────────────────────────────────────────────────────────

export async function runSaga(
  db: D1Database,
  sagaId: string,
  steps: Step[],
  initialPayload: unknown
): Promise<void> {
  const completedSteps: Array<{ step: Step; recordId: string; result: unknown }> = [];
  let payload: unknown = initialPayload;

  for (const step of steps) {
    // Check for existing idempotency record (retry safety)
    const existing = await db
      .prepare(`SELECT id, status FROM transaction_steps WHERE idempotency_key = ?`)
      .bind(`${sagaId}:${step.name}`)
      .first<{ id: string; status: string }>();

    if (existing?.status === "completed") {
      // Already done in a prior attempt — skip
      console.log(`[saga:${sagaId}] step ${step.name} already completed, skipping`);
      continue;
    }

    if (existing?.status === "requires_manual_review") {
      throw new Error(`Step ${step.name} requires manual review, aborting saga`);
    }

    const recordId = existing?.id ?? (await recordStep(db, sagaId, step.name, payload, "pending"));

    let attempts = 0;
    let succeeded = false;
    let lastError: unknown;

    while (attempts < MAX_RETRIES && !succeeded) {
      attempts++;
      try {
        const result = await step.execute(payload);
        await updateStep(db, recordId, "completed");
        completedSteps.push({ step, recordId, result });
        payload   = result; // pass output to next step as input
        succeeded = true;
      } catch (err) {
        lastError = err;
        console.warn(`[saga:${sagaId}] step ${step.name} attempt ${attempts} failed:`, err);
      }
    }

    if (!succeeded) {
      const finalStatus = attempts >= MAX_RETRIES ? "requires_manual_review" : "failed";
      await updateStep(db, recordId, finalStatus, String(lastError));

      // ── Execute compensating actions in reverse order ──────────────────
      console.error(`[saga:${sagaId}] rolling back ${completedSteps.length} completed steps`);
      for (const completed of [...completedSteps].reverse()) {
        try {
          await completed.step.undo(completed.result);
          await updateStep(db, completed.recordId, "compensated");
          console.log(`[saga:${sagaId}] compensated step ${completed.step.name}`);
        } catch (undoErr) {
          // Undo failures are logged but don't abort the rollback loop
          await updateStep(db, completed.recordId, "requires_manual_review", String(undoErr));
          console.error(`[saga:${sagaId}] undo failed for ${completed.step.name}:`, undoErr);
        }
      }

      throw new Error(
        `Saga ${sagaId} failed at step '${step.name}' after ${attempts} attempt(s). ${finalStatus === "requires_manual_review" ? "Flagged for manual review." : ""}`
      );
    }
  }

  console.log(`[saga:${sagaId}] completed successfully`);
}

// ── Example steps: charge → order → email ─────────────────────────────────

export function buildOrderSaga(env: { paymentApiUrl: string; emailApiUrl: string }) {
  return [
    {
      name: "charge_payment",
      async execute(payload: unknown) {
        const { userId, amountCents } = payload as { userId: string; amountCents: number };
        const res  = await fetch(`${env.paymentApiUrl}/charge`, {
          method: "POST",
          body:   JSON.stringify({ userId, amountCents }),
          headers: { "Content-Type": "application/json" },
        });
        if (!res.ok) throw new Error(`Payment API ${res.status}`);
        return res.json(); // { chargeId, userId, amountCents }
      },
      async undo(result: unknown) {
        const { chargeId } = result as { chargeId: string };
        const res = await fetch(`${env.paymentApiUrl}/refund`, {
          method: "POST",
          body:   JSON.stringify({ chargeId }),
          headers: { "Content-Type": "application/json" },
        });
        if (!res.ok) throw new Error(`Refund API ${res.status}`);
      },
    },
    {
      name: "create_order",
      async execute(payload: unknown) {
        const charge = payload as { chargeId: string; userId: string; amountCents: number };
        const res    = await fetch("https://internal.orders/create", {
          method: "POST",
          body:   JSON.stringify(charge),
          headers: { "Content-Type": "application/json" },
        });
        if (!res.ok) throw new Error(`Orders API ${res.status}`);
        return res.json(); // { orderId, ...charge }
      },
      async undo(result: unknown) {
        const { orderId } = result as { orderId: string };
        await fetch(`https://internal.orders/${orderId}`, { method: "DELETE" });
      },
    },
    {
      name: "send_email",
      async execute(payload: unknown) {
        const order = payload as { orderId: string; userId: string };
        const res   = await fetch(`${env.emailApiUrl}/send`, {
          method: "POST",
          body:   JSON.stringify({ to: order.userId, orderId: order.orderId }),
          headers: { "Content-Type": "application/json" },
        });
        if (!res.ok) throw new Error(`Email API ${res.status}`);
        return order;
      },
      async undo(_result: unknown) {
        // Email is best-effort; no compensation needed
      },
    },
  ] satisfies Step[];
}
```

---

## Integration / Testing

```typescript
// test/saga.test.ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { runSaga } from "../src/compensating-transaction";

// Minimal D1 stub
function makeDb(rows: Record<string, unknown> = {}) {
  const store = new Map<string, unknown>();
  return {
    prepare: (sql: string) => ({
      bind: (..._args: unknown[]) => ({
        run:   async () => {},
        first: async () => rows[sql] ?? null,
      }),
    }),
  } as unknown as D1Database;
}

describe("compensating transaction saga", () => {
  afterEach(() => vi.restoreAllMocks());

  it("runs all steps on success", async () => {
    const calls: string[] = [];
    const steps = [
      { name: "step_a", execute: async () => { calls.push("exec_a"); return {}; }, undo: async () => { calls.push("undo_a"); } },
      { name: "step_b", execute: async () => { calls.push("exec_b"); return {}; }, undo: async () => { calls.push("undo_b"); } },
    ];
    await runSaga(makeDb() as D1Database, "saga-1", steps, {});
    expect(calls).toEqual(["exec_a", "exec_b"]);
  });

  it("compensates completed steps when a later step fails", async () => {
    const calls: string[] = [];
    const steps = [
      { name: "step_a", execute: async () => { calls.push("exec_a"); return {}; }, undo: async () => { calls.push("undo_a"); } },
      { name: "step_b", execute: async () => { throw new Error("fail"); }, undo: async () => {} },
    ];
    await expect(runSaga(makeDb() as D1Database, "saga-2", steps, {})).rejects.toThrow();
    expect(calls).toContain("exec_a");
    expect(calls).toContain("undo_a");
  });
});
```

---

## Anti-patterns

- **No idempotency keys** — retrying a failed Worker without idempotency checks charges the customer twice and creates duplicate orders.
- **Throwing from undo functions** — an undo function that throws and is not caught halts the rollback loop, leaving earlier steps un-compensated.
- **Storing step state in memory only** — if the Worker crashes mid-saga, in-memory state is lost; only D1 records survive a restart.
- **Reversing steps in forward order** — compensating actions must run in reverse order; a forward rollback can cause foreign-key violations and orphaned records.

---

## Gotchas

- D1 is synchronous per-request but your saga may span multiple Worker invocations if using Queues for retry; ensure the `saga_id` is durable (e.g., stored in a Queue message).
- The `requires_manual_review` state must trigger an alerting mechanism (e.g., write to an alerting queue or send to PagerDuty); the pattern itself only flags the row.
- Email sending has no reliable undo; model it as best-effort and document that compensated sagas may still have sent an email.
- D1's `UNIQUE` constraint on `idempotency_key` provides the write-once guarantee; handle the `UNIQUE constraint failed` SQLite error in retry loops.

---

## Verification

```bash
# Apply migration
npx wrangler d1 migrations apply DB

# Query saga audit log after a test run
npx wrangler d1 execute DB --command \
  "SELECT saga_id, step_name, status, attempt_count FROM transaction_steps ORDER BY created_at"

# Find rows requiring manual review
npx wrangler d1 execute DB --command \
  "SELECT * FROM transaction_steps WHERE status = 'requires_manual_review'"
```

---

## Related

- `write-behind-cache-workers-kv-d1.md`
- `scatter-gather-workers-service-bindings.md`

---

## Sources

- Saga pattern — https://microservices.io/patterns/data/saga.html
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Workers error handling — https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
