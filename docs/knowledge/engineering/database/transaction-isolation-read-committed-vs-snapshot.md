# Transaction Isolation Read Committed Vs Snapshot

## Scope

This article covers PostgreSQL transaction isolation levels, focusing on the default `READ COMMITTED` and the stronger `REPEATABLE READ` and `SERIALIZABLE` levels (PostgreSQL's `REPEATABLE READ` is actually snapshot isolation). It addresses the read phenomena each level prevents, the implementation strategy (MVCC and SSI for `SERIALIZABLE`), and the practical consequences for application correctness and performance. It excludes cross-database isolation levels that do not match Postgres's snapshot model (for example, MySQL's repeatable read semantics) and the use of explicit locking to compensate for weak isolation (which has its own trade-offs covered elsewhere).

## Workflow or implementation guidance

1. **Understand the default: `READ COMMITTED`.** Every statement sees a snapshot of committed data as of statement start; concurrent updates by other transactions are not visible. The snapshot is refreshed per statement, so within one transaction a later statement may see changes made by another transaction that committed in between. This is sufficient for most OLTP workloads but does not prevent non-repeatable reads within a transaction.
2. **Use `REPEATABLE READ` when a multi-statement read must see a consistent view.** A reporting query that reads several tables in one transaction should see them all at the same point-in-time; under `READ COMMITTED`, the second statement could see a concurrent commit that the first did not. `REPEATABLE READ` takes a snapshot at the first statement and holds it for the whole transaction.
3. **Understand that PostgreSQL `REPEATABLE READ` is snapshot isolation, not ANSI `REPEATABLE READ`.** Phantom reads are theoretically possible under snapshot isolation, but in practice the planner's behaviour prevents the classic ANSI phantom. What you get is "no concurrent updates visible to me, but I may fail with `serialization_failure` if my writes conflict with a concurrent transaction".
4. **Use `SERIALIZABLE` for true serializability with optimistic concurrency.** Postgres implements `SERIALIZABLE` with Serializable Snapshot Isolation (SSI), tracking read-write dependencies and aborting transactions that would produce a non-serializable outcome with `SQLSTATE 40001`. The trade-off is a higher abort rate under contention; the application must handle `40001` by retrying.
5. **Be explicit about isolation level in code.** `BEGIN ISOLATION LEVEL REPEATABLE READ` makes the choice visible in the application's transaction boundary; relying on session defaults (which can change between connections, poolers, and migrations) is fragile.
6. **Pair `SERIALIZABLE` with retry logic.** A `SERIALIZABLE` transaction that aborts with `40001` must be retried by the application. Without retry, correctness is no better than `READ COMMITTED` and the cost is wasted.
7. **Watch for long transactions under `REPEATABLE READ`.** The snapshot is held for the entire transaction, and `pg_stat_activity` shows the transaction's `xact_start`. Long-running transactions under `REPEATABLE READ` keep their snapshot from advancing, which can block vacuum and bloat the table.
8. **Avoid `READ COMMITTED` for reporting workloads that need consistency.** A reporting query under `READ COMMITTED` can show inconsistent rows from concurrent commits; for dashboards and reports, set the session to `REPEATABLE READ` for the duration of the report.
9. **Be aware of statement-level cancel behaviour.** Under `READ COMMITTED`, a statement that tries to update a row that another transaction updated and committed may re-evaluate the `WHERE` clause; under `REPEATABLE READ`, the update sees the snapshot and may fail with a `serialization_failure` or, depending on the operation, the row's not-yet-visible state.
10. **Pick the level based on the workload's blast radius, not on habit.** A write-heavy OLTP workload under `SERIALIZABLE` will see many aborts and slow throughput; a write-light reporting workload under `READ COMMITTED` will see inconsistent reads. Match the level to the workload.

## Controls

1. **Isolation level per request type.** A documented mapping of which transactions use which isolation level; the application enforces it at the connection or transaction boundary.
2. **Retry budget for `SERIALIZABLE`.** A retry counter and maximum attempt count per transaction; alerts when the abort rate crosses a threshold.
3. **Long-transaction alert.** A monitor on `pg_stat_activity.xact_start` for transactions held open for more than a configurable duration; long transactions are a vacuum-bloat risk regardless of isolation level, but they are particularly hazardous under `REPEATABLE READ`.
4. **Snapshot-age monitor.** A check on `pg_stat_activity.backend_xmin` or `pg_snapshot_xmin(pg_current_snapshot())` to detect snapshot retention; long-running `REPEATABLE READ` or `SERIALIZABLE` transactions hold back cleanup.
5. **Per-statement isolation test.** CI test that asserts the application's hot transactions set the expected isolation level; fails when a default change is silently adopted.
6. **Reporting workload guard.** Reporting queries that need a consistent view must explicitly set `REPEATABLE READ`; review any reporting code that does not.

## Validation evidence

1. **Concurrent update test under each level.** Run two transactions that read and update the same row under `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`; assert the outcome matches the documented semantics for each.
2. **`SERIALIZABLE` abort test.** Run a workload that produces a known non-serializable interleaving; assert the abort fires with `40001` and that the retry succeeds on the second attempt.
3. **Reporting consistency test.** Run a multi-statement report under `READ COMMITTED` while a concurrent commit lands between them; observe inconsistency. Re-run under `REPEATABLE READ`; assert the snapshot is consistent across statements.
4. **Long-transaction impact test.** Hold a `REPEATABLE READ` transaction open for several minutes while heavy updates accumulate; assert that `pg_stat_activity` shows the snapshot age rising and that vacuum is delayed.
5. **Pooler interaction test.** Run an isolation-level change through a transaction-mode pooler and assert the level does not leak across pooler reassignments; the application re-sets the level per transaction if needed.

## Failure modes and correction

1. **Concurrent update lost under `READ COMMITTED` retry.** Symptom: a row update is silently lost because the `WHERE` clause re-evaluation excludes the row. Correction: ensure `UPDATE ... WHERE` includes a version column or relies on `RETURNING` to detect zero-row updates, and treat zero-row updates as "lost the race".
2. **`SERIALIZABLE` aborts with no application retry.** Symptom: `40001` errors surface to the user. Correction: implement retry logic; a bounded retry count with exponential backoff is the standard pattern.
3. **Reporting query shows inconsistent results.** Symptom: dashboard rows do not sum to a total. Correction: set `REPEATABLE READ` for the report transaction or use a single-statement query that returns consistent data via the planner.
4. **Long `REPEATABLE READ` transaction blocks cleanup.** Symptom: bloat grows, vacuum cannot keep up. Correction: shorten the transaction, or break it into smaller transactions that can each be vacuumed.
5. **Isolation level drift across poolers.** Symptom: the application assumes `READ COMMITTED` but a connection arrives with another level (set by another tenant of the same pool). Correction: explicitly set `SET TRANSACTION ISOLATION LEVEL` per transaction at the application boundary.
6. **Mixing explicit locking with `SERIALIZABLE`.** Symptom: the explicit lock hides a serialization anomaly that `SERIALIZABLE` would otherwise have caught. Correction: pick one strategy; explicit locking is a substitute for SSI's detection, not a complement.

## Limitations

1. **PostgreSQL `REPEATABLE READ` is snapshot isolation, not ANSI `REPEATABLE READ`.** Documents and conversations that quote the ANSI spec may mislead; verify against PostgreSQL's documentation.
2. **`SERIALIZABLE` is not free.** Throughput drops under contention; for workloads with high write rates, the abort rate may exceed the application's tolerance.
3. **Isolation levels do not protect against operator error.** A read that should have been against the primary but was routed to a replica (where lag makes a `SERIALIZABLE` snapshot misleading) is not caught by isolation.
4. **`SERIALIZABLE` depends on statistics;** in degenerate cases, SSI may permit anomalies that strict serializability would not, especially when predicate locks are coarse. Verify against benchmarks.
5. **Cross-database transactions have no consistent isolation level.** A workflow that spans Postgres and another store is bound by the weakest store's level.

## Canonical sources

- PostgreSQL Documentation, Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL Documentation, SET TRANSACTION (isolation level): https://www.postgresql.org/docs/current/sql-set-transaction.html
- PostgreSQL Documentation, Multiversion Concurrency Control: https://www.postgresql.org/docs/current/mvcc.html