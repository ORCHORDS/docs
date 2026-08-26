# event-driven-testing

**Issue:** Event-driven systems (queues, pub/sub, webhooks, eventual-consistency stores) have no synchronous return value to assert on, so tests either race or sleep for arbitrary fixed durations
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context

You publish an event to a queue and assert that the handler eventually wrote a row to the database.
The test does `setTimeout(2000)` then queries the DB. On your machine it passes. In CI it fails
intermittently because the handler took 2.1s. Someone bumps the timeout to 5000ms. Now the test is
slow everywhere and still occasionally flakes on a cold runner. Worse, the test can pass for the
wrong reason — an old event from a previous run is sitting in the DB and the assertion matches it.

Symptoms of bad event-driven tests:
- tests pass locally, fail in CI, pass again on retry (classic race)
- suite takes minutes because every test sleeps "just in case"
- tests pass even with the handler disabled (asserting against stale data)
- tests fail when run in parallel because two tests consume the same queue
- ordering bugs ("event B handled before A") only surface in production

## Pattern / Solution

Replace sleeps with deterministic waiting, and assert the causal chain — not just the end state.

### 1. Use a polling waiter with a deadline, not a fixed sleep
```ts
async function waitFor<T>(
  fn: () => Promise<T>,
  { timeout = 5000, interval = 50 }: { timeout?: number; interval?: number } = {}
): Promise<T> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { return await fn(); } catch { await new Promise(r => setTimeout(r, interval)); }
  }
  throw new Error(`waitFor timed out after ${timeout}ms`);
}

await expect(waitFor(() => db.query("SELECT ..."))).resolves.toEqual(expected);
```
This is fast on success (50ms granularity) and only slow on genuine failure (times out at 5s with a
clear error). Crucially, it fails with a real assertion error, not a silent sleep expiry.

### 2. Assert the event was emitted, not just the side effect
Use an in-process fake bus or a test-only subscriber to capture emitted events:
```ts
const emitted = eventBus.record();
await orderService.place(order);
expect(emitted).toContainEqual({ type: "OrderPlaced", id: order.id });
```
This catches "side effect happened but the event wasn't published" (e.g., DB commit ran but the
`publish` was after a crash) — a common source of eventually-consistent bugs.

### 3. Test ordering and idempotency explicitly
- **Ordering:** publish A then B quickly, assert the handler processed them in order (or assert it
  does NOT matter, if your design is order-independent). Never assume — document it with a test.
- **Idempotency:** publish the same event twice (same `eventId`), assert the handler applied it
  once. This is the #1 missing test in event-driven systems and the #1 cause of duplicate charges.
- **At-least-once delivery:** publish, crash the handler mid-processing, re-deliver, assert the
  final state is correct and not doubled.

### 4. Isolate by partition/queue per test
Parallel tests sharing one queue will steal each other's messages. Give each test a unique
correlation id or a dedicated queue/topic and filter on it:
```ts
const testQueue = `test-${randomUUID()}`;
```
Otherwise test A's handler consumes test B's event and both tests pass for the wrong reasons.

### 5. Test the failure paths
- handler throws → event is retried or dead-lettered (assert which)
- poison message → moves to DLQ after N attempts, not infinite retry
- consumer is down → events queue up, not lost
- DB transaction commits but publish fails → eventual consistency strategy (outbox) works

## Gotchas

- `setTimeout`-based waits are the dominant cause of slow + flaky event-driven suites. Every fixed
  sleep is either too short (flaky) or too long (slow). Replace all of them with polling waiters.
- A polling waiter that asserts equality can pass against stale data from a previous test. Always
  include a unique correlation id in the query and assert on it, or truncate the table in `beforeEach`.
- Running consumers in the test process while ALSO running them for real (e.g., a worker process
  started by docker-compose) causes two consumers to fight over the same queue. Start only one.
- `Date.now()` in events makes tests non-deterministic. Inject a clock or assert with a tolerance.
- "It works if I run just this one test" but fails in the full suite = shared state (queue, topic,
  DB row, in-memory singleton bus). Reset all subscribers between tests.
- Asserting `expect(handler).toHaveBeenCalled()` alone does not prove the handler finished its async
  work — it only proves it started. Await the side effect, not the call.
- Eventual consistency is not "no consistency". Define the SLA in the test: "row visible within 5s".
  A 60s wait that eventually passes means the system is broken, not correct.
- Outbox-pattern bugs (committed row never published because the outbox poller crashed) are invisible
  to most tests. Add a test that kills the poller mid-flight and asserts recovery.

## Related
- streaming-sse-testing
- flaky-test-detection
- flaky-test-remediation
- contract-timeout-and-cancellation-tests
- test-database-isolation
- transactional-test-rollback
- ci-test-parallelization
