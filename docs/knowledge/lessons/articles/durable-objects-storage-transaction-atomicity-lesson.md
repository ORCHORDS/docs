# Durable Objects Storage Transaction Atomicity Lesson

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A billing Durable Object that managed account credits issued double-spend
events during a brief network blip. A request to debit credits timed out on
the client side, was retried, and the debit was applied twice. Investigation
showed that the first request had partially executed: some storage keys were
updated while others were not, leaving the DO in an inconsistent state before
the retry ran the full debit again.

---

## Context

Cloudflare Durable Objects provide strongly consistent, serialized storage per
DO instance. However, making multiple `storage.put()` calls in sequence is
**not** inherently atomic. If an exception or a network interruption occurs
between two puts, the first put may persist while the second does not.

The DO runtime does offer `storage.transaction()` for atomic multi-key
operations, but it is easy to miss or misuse. The incident team had assumed
that because DO requests are serialized (no concurrent handlers), partial
writes were impossible. Serialization prevents races between requests but does
not prevent a single request from leaving partial state if it throws or times
out mid-write.

---

## DO Storage Consistency Model

Durable Objects guarantee:

1. **Serialized request handling**: only one `fetch()` (or alarm) runs at a
   time per DO instance. There are no concurrent writes.
2. **In-memory transactions via `storage.transaction()`**: a set of reads and
   writes that either all commit or all roll back.
3. **Durability**: committed writes survive isolate eviction and restart.

What is NOT guaranteed without `storage.transaction()`:

- Atomicity across multiple sequential `put()` calls in a single handler.
- Read-modify-write consistency if the handler throws after the write.

---

## The Bug

```typescript
// BUGGY billing debit handler (simplified)
async function debitCredits(
  storage: DurableObjectStorage,
  userId: string,
  amount: number,
): Promise<void> {
  const balance = (await storage.get<number>(`balance:${userId}`)) ?? 0;

  if (balance < amount) {
    throw new Error("insufficient credits");
  }

  // BUG: two separate puts — not atomic
  await storage.put(`balance:${userId}`, balance - amount);
  // If anything throws here, the ledger entry is missing but the balance was already debited
  await storage.put(`ledger:${Date.now()}`, { userId, amount, type: "debit" });
}
```

When the network timed out after the first `put` but before the second, the
balance was decremented but no ledger entry was created. On client retry, the
balance was decremented again.

---

## The Fix: `storage.transaction()`

```typescript
async function debitCredits(
  storage: DurableObjectStorage,
  userId: string,
  amount: number,
  idempotencyKey: string,
): Promise<void> {
  await storage.transaction(async (txn) => {
    // Idempotency: check if this debit was already applied
    const alreadyApplied = await txn.get<boolean>(`idem:${idempotencyKey}`);
    if (alreadyApplied) return; // safe to retry

    const balance = (await txn.get<number>(`balance:${userId}`)) ?? 0;
    if (balance < amount) {
      throw new Error("insufficient credits");
    }

    // All puts inside the transaction are atomic
    await txn.put(`balance:${userId}`, balance - amount);
    await txn.put(`ledger:${idempotencyKey}`, {
      userId,
      amount,
      type: "debit",
      timestamp: Date.now(),
    });
    await txn.put(`idem:${idempotencyKey}`, true);
  });
}
```

If any `put` inside `storage.transaction()` fails, or if the callback throws,
no changes are committed. All reads and writes inside the callback are part of
the same atomic unit.

---

## Idempotency Keys are Non-Negotiable

Retry is the correct client behavior when a request times out. Without
idempotency keys the debit will be applied on every retry.

```typescript
// Caller — always supply an idempotency key
export class BillingDO implements DurableObject {
  constructor(private readonly state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }

    const body = await request.json<{
      userId: string;
      amount: number;
      idempotencyKey: string;
    }>();

    if (!body.idempotencyKey) {
      return new Response("idempotencyKey is required", { status: 400 });
    }

    try {
      await debitCredits(
        this.state.storage,
        body.userId,
        body.amount,
        body.idempotencyKey,
      );
      return new Response(null, { status: 204 });
    } catch (err) {
      if (err instanceof Error && err.message === "insufficient credits") {
        return new Response("insufficient credits", { status: 402 });
      }
      throw err;
    }
  }
}
```

---

## Read-Modify-Write Patterns

Any time a handler reads a value and then writes back a derived value, that
entire read-modify-write must be inside a transaction to prevent inconsistency
if the handler is interrupted:

```typescript
// SAFE: read-modify-write inside a transaction
await this.state.storage.transaction(async (txn) => {
  const counter = (await txn.get<number>("counter")) ?? 0;
  await txn.put("counter", counter + 1);
});

// UNSAFE: read outside, write inside — no atomicity guarantee
const counter = (await this.state.storage.get<number>("counter")) ?? 0;
await this.state.storage.put("counter", counter + 1); // could race with alarm
```

Note: Because DO handlers are serialized, the "unsafe" pattern above will
not race with another concurrent `fetch()`. However, it can still yield
incorrect results if an alarm fires between the read and the write, or if the
handler throws an exception after a partial set of puts in a multi-key
scenario.

---

## DO Alarm + Transaction Interaction

Alarms run as separate "requests" in the DO's serialized queue. If a `fetch()`
handler and an alarm both write to the same keys, they are serialized and
cannot interleave. However, if the alarm needs atomically consistent state
(e.g., expiring a subscription and writing an audit event), the alarm body
should also use `storage.transaction()`.

```typescript
async alarm(): Promise<void> {
  await this.state.storage.transaction(async (txn) => {
    const expiredAt = await txn.get<number>("subscriptionExpiry");
    if (!expiredAt || Date.now() < expiredAt) return;

    await txn.put("status", "expired");
    await txn.put("expiredAt", Date.now());
    await txn.delete("subscriptionExpiry");
  });
}
```

---

## Anti-patterns

- Multiple sequential `storage.put()` calls for logically related data without
  a transaction.
- Performing a `storage.delete()` outside a transaction before confirming a
  compensating write succeeded.
- Assuming serialized handler execution is sufficient for atomicity — it
  prevents concurrent races but not partial-write failures.
- Retrying on the client without an idempotency key — transforms a transient
  network blip into a double-spend.
- Using large transactions (hundreds of keys) — the DO runtime has limits on
  transaction size; design key schemas so each transaction touches a small,
  bounded set of keys.

---

## Gotchas

**`storage.transaction()` does not retry on conflict**: Unlike database
optimistic concurrency, DO transactions do not retry automatically. If the
transaction callback throws, the transaction is aborted and the error propagates
to the caller. Implement application-level retry if needed.

**Transaction size limits**: Each transaction can touch at most 128 keys and
the total value size has limits. Design data models so related atomic writes
fit within these bounds.

**In-memory state + storage state can diverge**: If a DO keeps in-memory state
(e.g., a `Map` field on the class) and storage state, and a transaction
commits to storage but the in-memory update happens after a throw, they will
diverge. Keep in-memory state as a cache derived from storage, not as a
separate authoritative source.

**`blockConcurrencyWhile` vs transactions**: `state.blockConcurrencyWhile()`
is for guarding the initialization critical section (loading state before
serving requests), not for general-purpose atomic writes. Do not use it as a
substitute for `storage.transaction()`.

---

## Verification

1. Write a unit test using Miniflare's `DurableObjectStub` that simulates a
   throw between two `put()` calls. Assert the DO is left in the pre-operation
   state (consistent).
2. Write an integration test that sends the same debit request twice with the
   same idempotency key. Assert the balance is only decremented once.
3. Add a reconciliation job (alarm-based) that periodically sums all ledger
   entries and compares against the stored balance. Alert on any discrepancy.

---

## Related

- `durable-objects-alarm-backlog-cascade-revival-lesson.md` — alarm sequencing
- `durable-objects-storage-quota-limit-incident.md` — storage limits
- `kv-consistency-mode-eventual-reads-production-bug.md` — KV vs DO consistency
- `irreversible-fulfillment-must-follow-atomic-claim.md` — idempotency patterns

---

## Sources

- Cloudflare Durable Objects documentation: "Transactional storage API"
- Cloudflare Workers documentation: "Durable Objects — in-memory state"
- Cloudflare blog: "Building a location-aware distributed app using Durable Objects"
