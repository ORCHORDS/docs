# Advisory Lock Pattern Pg Try Advisory Xact Lock

## Scope

This article covers the `pg_try_advisory_xact_lock` pattern for non-blocking mutual exclusion inside a single Postgres transaction: leader election for cron fan-out, single-flight cache or report generation, per-tenant serialization of read-modify-write flows, and deduplication of concurrently arriving jobs. It addresses the specific decision of choosing the *try* (non-blocking) form of the *transaction-scoped* advisory lock rather than the blocking session-level `pg_advisory_lock`. It does not cover D1/SQLite locking (see the D1 advisory-lock article), distributed lock managers with fencing tokens, or `SELECT ... FOR UPDATE` row locking, all of which are separate tools with different semantics.

## Workflow or implementation guidance

1. **Prefer the transaction-scoped variant unless a transaction cannot contain the work.** `pg_try_advisory_xact_lock(key)` returns a boolean instead of blocking, and Postgres releases the lock automatically at commit or rollback. Because the lifetime is bound to the transaction, there is no leak path where an exception unwinds the stack without cleanup. Reserve session-scoped `pg_try_advisory_lock` for jobs that span multiple transactions, and treat those as requiring an explicit release discipline.
2. **Execute the acquire as the first statement of the transaction, then branch on the result.** The canonical shape is: begin, `SELECT pg_try_advisory_xact_lock(<key>) AS acquired`, and if the result is false, roll back immediately and return a "skipped" result. Committing an empty transaction after a failed acquire is harmless but wasteful; rolling back keeps connection turnover fast under a pooler.
3. **Derive the key from a namespaced registry, not a bare integer.** Use the two-argument form `pg_try_advisory_xact_lock(classid, objid)` so unrelated features never collide: for example classid `4210` for digest generation, `4211` for report materialization, with objid derived from a stable identifier such as the tenant's integer primary key. A registry table mapping classids to owning services makes collisions a reviewable problem rather than a 2 a.m. outage.
4. **Derive keys from immutable identifiers.** `hashtextextended(tenant_slug, 42)` is acceptable while slugs are immutable, but a display name that can be renamed will silently move the lock mid-flight. Prefer integer primary keys or a hash seeded per-classid.
5. **Keep the critical section short and hold no external side effects inside the lock window when using the try pattern.** The try pattern's contract is "at most one, otherwise skip", so the locked work should be either idempotent or purely transactional. Sending email or calling a third-party API inside the lock converts "skip" semantics into partial-work ambiguity: the transaction can still roll back after the side effect has fired.
6. **Wire timeouts defensively even though try does not block.** The acquire itself returns instantly, but the work that follows can still block on row locks or I/O. Set `lock_timeout` and `statement_timeout` for the session so a wedged critical section surfaces as an error rather than an indefinitely held advisory lock.
7. **Use it for per-tenant serialization of a read-modify-write window.** When a flow must not run concurrently for one tenant but may run concurrently across tenants, taking the advisory key inside the same transaction that performs the write closes the check-then-act gap that a plain flag column leaves open.

## Controls

1. **Key registry.** A table of `(classid, service, description, owner)` rows, enforced in code review, so no two features claim the same namespace without a deliberate decision.
2. **Single construction point for keys.** One module with named constants and a `deriveKey(classid, resourceId)` helper; business code never inlines raw integers.
3. **Bounded critical section.** `statement_timeout` set for the acquiring session, sized to roughly twice the p99 duration of the locked work.
4. **Observability.** Increment skip and acquire counters per key, and join `pg_locks` (`locktype = 'advisory'`) to `pg_stat_activity` in dashboards so held duration is visible.
5. **Pooler compatibility check.** Confirm the deployment uses transaction-mode pooling only with xact-scoped locks; session-scoped advisory locks must be gated behind session pooling or a direct connection.
6. **Re-verification after acquisition.** After acquiring, re-read the guarded state inside the same transaction; the lock proves exclusion, not that the world is still in the expected state.

## Validation evidence

1. **Concurrency test with N parallel transactions.** Launch 20 concurrent transactions that each attempt `pg_try_advisory_xact_lock(4210, 42)` and then sleep 200 ms; assert exactly one returns true and nineteen return false, and that total wall time approximates one critical section rather than twenty.
2. **Release-on-rollback test.** Acquire the lock in a transaction, deliberately raise an error, confirm rollback, then verify `SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'` returns zero for that key on a fresh connection.
3. **Pooler test.** Run the concurrency test through PgBouncer in transaction mode and confirm the results are identical; then demonstrate the failure mode by running a session-scoped `pg_advisory_lock` variant and observing orphaned locks.
4. **Cron overlap test.** Schedule the guarded job at an interval shorter than its runtime, verify via logs that every overlapping invocation logs a skip with the same key, and verify the digest output is produced exactly once.
5. **EXPLAIN-level confirmation is not applicable but lock visibility is.** Query `pg_locks` for `advisory` rows during the critical section and confirm `granted = t` with the expected classid/objid pair.

## Failure modes and correction

1. **Blocking variant used by mistake (`pg_advisory_xact_lock`).** Under contention the queue of waiters converts a single slow job into a convoy that exhausts the pool. Correction: switch to the try variant and treat "false" as a normal, counter-incrementing skip.
2. **Session lock leaking through a pooled connection.** A session-scoped lock acquired on one server connection is invisible to the application after the connection returns to the pool. Correction: migrate to the xact variant, or run session locks on a dedicated direct connection with an acquire/release helper and try/finally semantics.
3. **Key collision across features.** Two teams independently pick key `1`. Symptoms are bizarre mutual exclusion that only appears in production traffic. Correction: adopt the classid registry and re-derive keys from primary keys.
4. **Side effects inside the lock window.** An email sent before the transaction commits, followed by a rollback, leaves a permanent effect with no database record. Correction: move non-transactional effects after commit, driven by an outbox row written inside the critical section.
5. **Deadlock from inconsistent multi-key ordering.** Acquiring keys A then B in one path and B then A in another triggers the deadlock detector. Correction: define one canonical global order for multi-key acquisition and enforce it in the key module.
6. **Using the lock to enforce a data invariant.** The lock serializes access but proves nothing about state when it is not held. Correction: add a partial unique index for the invariant; keep the lock purely for concurrency shaping.

## Limitations

1. **Cluster-scoped only.** Advisory locks exist within one Postgres cluster; two services on separate databases cannot coordinate with them.
2. **No fencing tokens.** A paused-then-resumed process can believe it still holds exclusivity. Tasks where double-execution is expensive need a lease row with an expiry and a fencing token checked by consumers.
3. **No queueing or fairness.** The try form gives no ordering guarantee among retrying callers; it is "at most one now", not "eventually all in order".
4. **Opaque keys.** The 64-bit key space is invisible to most dashboards; without a registry, interpreting `pg_locks` output during an incident is guesswork.
5. **Not a substitute for constraints.** Any code path that bypasses the application (manual SQL, a batch script, a different service) is unaffected by the lock.

## Canonical sources

- PostgreSQL Documentation, Explicit Locking — Advisory Locks: https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS
- PostgreSQL Documentation, Monitoring — The pg_locks view: https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-LOCKS-VIEW
- PgBouncer Documentation, Features (pool modes and their statement restrictions): https://www.pgbouncer.org/features.html
