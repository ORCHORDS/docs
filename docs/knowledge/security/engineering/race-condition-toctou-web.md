# race-condition-toctou-web

**Issue:** Time-of-check to time-of-use (TOCTOU, CWE-367) and broader race conditions (CWE-362) occur when a web application validates a precondition in one step and acts on it in a later, non-atomic step. Modern HTTP/2 and HTTP/3 clients can pipeline dozens of truly concurrent requests over one connection, so an attacker can fire N parallel withdrawals, transfers, coupon redemptions, or votes that all pass a check against the same stale state before any of them commits. The canonical exploit is the limit-overrun: balance is read, compared, then debited in separate operations, letting concurrent requests overdraw balances, redeem single-use codes many times, or exceed rate and quota limits. Because the vulnerable window is microseconds wide and entirely server-side, these bugs pass functional tests that use sequential requests and surface only under adversarial concurrency.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Vulnerable patterns

1. **Check-then-act on shared state.** Reading a balance, stock count, or quota in one query, comparing it in application code, then writing in a second query creates a gap in which every concurrent request sees the same pre-update value.
2. **Read-modify-write in application memory.** Loading an entity into an ORM, mutating a field in the process, and saving it back means the last writer silently discards every other concurrent update, which is exploitable for likes, credits, and point balances.
3. **Single-use enforcement via a SELECT.** Verifying a promo code or one-time token exists with a SELECT and deleting it later lets two simultaneous requests both observe the row before either delete lands.
4. **Non-idempotent money and messaging endpoints.** Payment charge, transfer, and send endpoints without idempotency keys double-execute when clients or intermediaries retry, and attackers can deliberately trigger the retries.
5. **Filesystem TOCTOU.** Checking a symlink or file attribute with stat and then opening the path lets an attacker swap the target between the two calls, a classic local variant when handling uploads in shared directories.

## Atomicity defenses

1. **Atomic conditional updates.** Replace check-then-act with a single statement whose WHERE clause encodes the precondition, such as UPDATE accounts SET balance = balance - :amt WHERE id = :id AND balance >= :amt, and treat zero rows affected as a decline; the row lock serializes competing requests.
2. **Pessimistic row locking.** SELECT ... FOR UPDATE (or the store-level equivalent) around a read-modify-write transaction holds the lock across the business logic so only one request at a time can progress through the critical section.
3. **Optimistic concurrency with versions.** Add a version or etag column and require UPDATE ... WHERE version = :seen, retrying on mismatch; this prevents lost updates in ORM-heavy code without holding locks.
4. **Atomic single-use consumption.** Make redemption itself the atomic marker: DELETE ... RETURNING, an UPDATE of a consumed_at column, or an INSERT into a unique-constrained redemptions table all let exactly one concurrent request win and the rest fail cleanly.
5. **Compare-and-swap primitives.** Redis Lua scripts, WATCH/MULTI, or database-native CAS operations give the same single-winner semantics in cache-backed counters and rate limiters.

## Idempotency and request-level controls

1. **Server-enforced idempotency keys.** Require a client-generated key on all money-movement and messaging endpoints, store the key with a unique constraint alongside the first response, and replay the stored response to duplicate submissions instead of re-executing the effect.
2. **Single-flight execution.** Route concurrent identical operations through a per-key lock or queue so the second caller waits for or receives the first caller's result rather than racing it.
3. **Queue serialized mutations.** For high-contention resources such as flash-sale inventory, admit requests to a serialized queue or use a ledger with an append-only design so ordering is imposed by one writer rather than fought over by many.

## Testing and monitoring

1. **Concurrent regression tests.** Automated tests should replay each stateful endpoint with 20-50 simultaneous requests using a single HTTP/2 connection and assert the invariant (final balance, redemption count, quota ceiling) rather than asserting any single response.
2. **Single-packet attack awareness.** Assume attackers use last-byte synchronization techniques to land requests in the same server tick; defenses must rely on server-side atomicity, never on the difficulty of timing requests.
3. **Invariant monitors and reconciliation.** Background jobs that recompute balances from ledgers, count redemptions against issuance, and alert on negative balances or over-run quotas catch races that slipped through review.
4. **Chaos and burst drills.** Load tests with adversarial replay patterns, such as the same coupon from many sessions, validate that locks and idempotency hold under realistic concurrency before an attacker demonstrates it in production.

## References informing this article

1. **MITRE CWE-362 and CWE-367.** Canonical definitions of race conditions and TOCTOU with the atomicity-based remediation principle.
2. **PortSwigger research on HTTP/2 single-packet request race conditions.** Demonstrates why concurrent windows are reliably exploitable on modern protocol stacks.
3. **ZeriFlow and pwnsy race condition guides (2025).** Practical limit-overrun exploitation and the locking-plus-idempotency defense pattern.
4. **OWASP guidance on idempotency in API design.** Idempotency key semantics for payment and messaging endpoints.
