# Hot Row Update Skip Locked Queue Table

## Scope

This article covers the "queue table" pattern for serializing work among concurrent workers: a `jobs` table whose rows represent pending units of work, with workers using `SELECT ... FOR UPDATE SKIP LOCKED` (and the analogous `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED)` claim pattern) to claim work without blocking on their peers. It addresses the application-layer queue alternative to dedicated queue systems (Redis Streams, RabbitMQ, SQS, Kafka) when the work is best co-located with the relational data. It excludes message-broker queues, priority scheduling across heterogeneous job types (which requires different priority columns or a separate scheduler), and Postgres-specific logical replication as a transport.

## Workflow or implementation guidance

1. **Define the schema deliberately.** A `jobs` table with columns for `id`, `kind` (or `type`), `payload` (jsonb), `status` (`pending`, `running`, `done`, `failed`, `dead`), `attempts`, `max_attempts`, `run_after` (or `available_at`), `locked_by` (worker id), `locked_until` (lease expiry), and timestamps. Indexes: a partial index on `(run_after)` where `status='pending'` to make claim scans small, plus an index on `(id)` if not implicit.
2. **Use `SELECT ... FOR UPDATE SKIP LOCKED` to claim a small batch.** Inside one transaction: `WITH next_jobs AS (SELECT id FROM jobs WHERE status='pending' AND run_after <= now() ORDER BY id FOR UPDATE SKIP LOCKED LIMIT $1) UPDATE jobs SET status='running', locked_by=$2, locked_until=$3 WHERE id IN (SELECT id FROM next_jobs) RETURNING *;`. Each worker sees a different non-overlapping set of rows; long-running peers do not block the worker.
3. **Set a lease, not a permanent lock.** Update `locked_until` to `now() + lease_seconds`. If the worker dies, the lease eventually expires and another worker can re-claim. The lease is the liveness signal that makes the queue crash-safe.
4. **Reap stale leases on claim.** When claiming, the `WHERE` clause should include `AND (locked_until IS NULL OR locked_until < now())` so a crashed worker's job is recoverable. Combining this with `FOR UPDATE SKIP LOCKED` is the canonical pattern.
5. **Bound the transaction.** Do the claim, do the work, and finish with one transaction per batch; for very long work, keep a heartbeat that updates `locked_until` without re-claiming, so the row stays "owned" but the worker does not hold a row lock for minutes.
6. **Mark terminal states explicitly.** On success, `UPDATE ... SET status='done'`. On failure, increment `attempts` and either reset to `pending` for retry, route to a `dead` status (and a dead-letter table for inspection), or re-queue with `run_after` set to a future time for exponential backoff.
7. **Use a partial index tuned for the claim query.** `CREATE INDEX ... ON jobs (run_after) WHERE status='pending';` keeps the index small as rows progress to terminal states; the planner uses it for the claim scan and ignores the rest.
8. **Keep the queue and the work side-by-side.** A queue whose payload references data in another table can lose consistency if that data is updated concurrently; co-locating the work with the data it modifies, or carrying the necessary state in the payload, is the simplest way to avoid surprises.
9. **Avoid `SELECT ... FOR UPDATE` without `SKIP LOCKED`.** Plain `FOR UPDATE` queues waiters behind one another, which is the opposite of the pattern's intent. The `SKIP LOCKED` clause is what makes the pattern fair and parallel.

## Controls

1. **Lease expiry enforcement.** Reaper query for rows whose `locked_until < now() - grace_period` resets them to `pending` so a crashed worker does not leak jobs.
2. **Dead-line escalation.** A monitor that surfaces jobs in `status='dead'` (exceeded `max_attempts`) so a human can intervene.
3. **Per-worker concurrency cap.** Application-level limit on how many rows one worker may claim at once; combined with the per-row `max_attempts` budget to bound damage from a buggy consumer.
4. **Claim-rate observability.** Counters for claimed rows, completed rows, failed rows, and reaped rows per minute; alerts on a stall where the queue length rises faster than the throughput.
5. **Backoff schedule documented.** A constant for the `run_after` schedule that delays retry of a failed job to spread load and prevent hot loops.
6. **Long-claim alarm.** Alert when any row's `locked_until` is updated too many times in a row (a heartbeat flag), indicating a job whose work has slipped past its expected runtime.

## Validation evidence

1. **Parallel claim test.** Launch N workers claiming from the same queue; assert each row is claimed by exactly one worker across all invocations, with zero duplicates and zero claims that never finish.
2. **Crash recovery test.** Kill one worker mid-claim; advance the clock past the lease; assert another worker re-claims the same row and the system reaches steady state.
3. **Bounded queue depth test.** With a constant inflow, the system reaches a queue depth where arrival rate equals completion rate; assert the steady state is below an SLA threshold.
4. **Dead-line escalation test.** Force a job to exceed `max_attempts`; assert it transitions to `status='dead'` and the escalation monitor surfaces it.
5. **Index utilization test.** `EXPLAIN ANALYZE` the claim query against a large jobs table; assert the partial index is selected and that index pages are small relative to the table.

## Failure modes and correction

1. **Workers block on one another.** Symptom: throughput is one-row-at-a-time despite many workers. Correction: add `SKIP LOCKED` to the claim; verify with `EXPLAIN` that the row-locking plan is the one in effect.
2. **A single long-running job holds a row lock for too long.** Symptom: subsequent claims wait on the locked row even with `SKIP LOCKED` because the work transaction has not ended. Correction: split the work — claim in one transaction, do the work outside the row lock, update the row in a short follow-up transaction; or use the heartbeat pattern to extend the lease without holding the lock.
3. **Crashed worker leaves jobs permanently "running".** Symptom: queue depth grows even with healthy workers. Correction: enforce the lease-expiry reaper; ensure `locked_until` is checked on claim.
4. **`SKIP LOCKED` causes starvation.** Symptom: under extreme contention, some rows are perpetually claimed last or reaped last. Correction: this is by design but can be mitigated by ordering the claim query by a non-skewed column (for example `id`) and by bounding the worker count.
5. **Queue payload becomes inconsistent with the data it references.** Symptom: a job processes a row whose state has changed since the job was enqueued. Correction: at work time, re-read the referenced row inside the work transaction, or carry a version stamp and check it.
6. **Index bloat as jobs accumulate.** Symptom: partial index grows even when most rows are terminal because status updates flip rows out of the predicate. Correction: include terminal rows in the predicate only when needed for ordering; periodically `VACUUM` and rebuild the partial index.

## Limitations

1. **Postgres is not a message broker.** It does not offer delivery guarantees beyond what the database transaction gives; ordering, retention, and replay semantics are application responsibility.
2. **The pattern does not span clusters.** A queue table on one Postgres cluster is invisible to workers on another; cross-cluster work needs an external transport.
3. **`SKIP LOCKED` is row-level granularity.** Locking a logical group of rows requires either one row at a time, or a higher-level lock (advisory, partition-level) to keep the group atomic.
4. **Backpressure is application-managed.** Without an external queue's depth limit, the application must decide when to refuse new work; runaway producers can fill the table until disk or memory pressure emerges.
5. **Long-running work is at odds with short transactions.** Either work is short enough to fit inside the row lock, or the lease/heartbeat pattern adds complexity that a dedicated queue handles natively.

## Canonical sources

- PostgreSQL Documentation, SELECT — The Locking Clause (FOR UPDATE / SKIP LOCKED): https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE
- PostgreSQL Documentation, Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL Documentation, Partial Indexes: https://www.postgresql.org/docs/current/indexes-partial.html