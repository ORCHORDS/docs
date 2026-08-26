# job-queue-skip-locked

**Issue:** Background work (emails, exports, webhooks, image processing) needs a job queue, and the team default is to reach for Redis or RabbitMQ — adding a second stateful system, a second failure domain, and a second backup story. For low-to-moderate throughput, Postgres already has the concurrency primitive needed: `SELECT ... FOR UPDATE SKIP LOCKED` lets multiple workers dequeue from the same table without blocking each other or double-processing rows. Done naively, however, a Postgres queue develops stale stuck jobs, double deliveries, and runaway table bloat from MVCC churn.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How SKIP LOCKED claiming works

1. **The core claim query.** Workers run `SELECT id, payload FROM jobs WHERE status = 'pending' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1` inside a transaction, update the row to `running`, and commit. Rows already locked by another worker are skipped instead of waited on, so N workers can poll concurrently with no lock convoy.
2. **Why plain FOR UPDATE fails.** Without `SKIP LOCKED`, every worker's claim query blocks on the row the first worker holds; when that transaction commits, the blocked workers wake up, re-evaluate, and fight over the next row — throughput collapses to near-serial under contention.
3. **Locks live only as long as the transaction.** Postgres row locks are tied to transactions, not sessions. The claim must be a short transaction that flips status and commits; the actual work happens after commit, otherwise a slow job holds locks and a crashed worker rolls the job back to pending unexpectedly.
4. **Ordering is best-effort.** `ORDER BY id` gives FIFO among currently unlocked rows, but a row locked-and-released or a retried job can be overtaken. If strict ordering per entity matters, add a `partition_key` and use advisory locks or a per-key sequence to serialize.

## Reliability mechanics every queue needs

1. **Visibility timeout via `locked_at`.** Set `locked_at = now()` when claiming and have a reaper query re-queue rows where `status = 'running' AND locked_at < now() - interval '5 minutes'`. This is the manual equivalent of what Redis-based queues give you for free and is what rescues jobs from crashed workers.
2. **Attempt counter and max attempts.** Track `attempts int`, increment on failure, and move the job to a `dead_jobs` table (dead-letter) once a cap is reached. Without this, a poison payload loops forever between claim and failure.
3. **Exponential backoff with `run_at`.** On failure set `run_at = now() + (interval '1 second' * power(2, attempts))` and include `run_at <= now()` in the claim predicate to get delayed retries without a scheduler.
4. **Idempotent handlers.** At-least-once delivery is unavoidable — a worker can finish the work and crash before marking the row done. Handlers must tolerate seeing the same job twice (idempotency keys on side effects).
5. **One transaction per state change, never one for the whole job.** Wrapping the entire job execution in the claim transaction keeps rows locked for the full duration and destroys concurrency; keep claim, completion, and failure as separate short transactions.

## The MVCC bloat problem and its mitigation

1. **Queues are worst-case churn.** Each job is insert → update (claim) → update (finish) → delete, so the queue table's tail is a constant stream of dead tuples. Brandur Leach's "Postgres Job Queues & Failure By MVCC" is the canonical treatment of how this bloats the table and pressures autovacuum.
2. **Aggressive per-table autovacuum settings.** Configure the jobs table with low `autovacuum_vacuum_scale_factor` (e.g. 0.01) and `autovacuum_vacuum_cost_delay = 0` so vacuum keeps up with the churn; a queue table is one of the few places per-table overrides are clearly justified.
3. **Delete or partition aggressively.** Archive finished jobs to a separate `jobs_archive` table or use a time-partitioned jobs table so `DROP PARTITION` reclaims space instead of vacuum deletes; a forever-growing `jobs` table also slows the claim query's index scan.
4. **Watch for long transactions poisoning the tail.** Any long-running transaction (analytics, a forgotten psql session) prevents vacuum from cleaning dead job tuples, bloating the hot table; monitor `pg_stat_activity` for `state = 'idle in transaction'`.
5. **Index only what the claim needs.** A partial index like `CREATE INDEX ON jobs (run_at) WHERE status = 'pending'` keeps claim scans tight; a plain btree on `status` includes millions of dead/finished rows and wastes pages.

## When a Postgres queue stops being the right answer

1. **Throughput in the thousands of jobs per second.** At high churn the vacuum cost and WAL volume of the update-per-claim pattern dominate; dedicated brokers (SQS, Redis Streams, RabbitMQ) are designed for that regime.
2. **You need broker-native semantics.** Delayed queues, priorities with preemption, fan-out to many consumers, or exactly-once-ish delivery contracts push you toward purpose-built systems; bolting them onto SQL is where the anti-pattern accusations come from.
3. **Consider the extension middle ground.** `pgmq` (from Tembo) packages visibility timeouts and archive tables as a Postgres extension with a familiar queue API, and newer extensions like `pg_bestqueue` attack the contention problem with shared-memory rings — both keep your operational footprint single-database.
4. **Otherwise, embrace the simplicity.** For a team already running Postgres with modest volume (roughly up to hundreds of jobs/second), the SKIP LOCKED queue gives transactional enqueue (job + business row in one commit), SQL observability, and zero new infrastructure — as the Prisma blog argues, you often don't need a job queue system at all.
