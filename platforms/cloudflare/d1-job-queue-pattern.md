# d1-job-queue-pattern

**Issue:** Background jobs on the example project platform run through a plain D1 `jobs` table rather than a managed message queue. A row is inserted with `status='pending'`, a Worker scheduled by a cron trigger polls for due work, atomically claims it by writing a lease (visibility timeout), executes it, and updates status to `done` or increments `attempts` toward a max-attempts dead-letter state. Because D1 is SQLite under the hood, the classic Postgres `FOR UPDATE SKIP LOCKED` claiming query does not exist, so correctness depends entirely on an atomic single-statement claim plus lease expiry for crash recovery.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Schema and lifecycle states

1. **Jobs table columns.** `id`, `type`, `payload` (JSON), `status` (`pending` / `leased` / `done` / `failed` / `dead`), `attempts`, `max_attempts`, `run_at`, `lease_expires_at`, `created_at`, `last_error`. Every field that drives claiming or retry must be a column, not buried in payload, so the poll query stays index-friendly.
2. **Status machine.** `pending` → `leased` (claimed, lease holds it) → `done` on success, or back to `pending` on retryable failure with `attempts+1`; when `attempts >= max_attempts` the row moves to `dead` (the dead-letter state) instead of being retried. `dead` rows stay queryable for manual inspection and replay.
3. **Lease is the visibility timeout.** The lease (`lease_expires_at`) is the D1 equivalent of the [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html): a claimed job is invisible to other pollers only until the lease expires. A Worker that crashes mid-job leaves the row stuck in `leased` until the lease lapses, after which the next poll reclaims it — no external recovery process needed.

## The atomic claim (why SKIP LOCKED is unavailable)

1. **SQLite has no `FOR UPDATE SKIP LOCKED`.** D1 is SQLite; SQLite has no row-level locks and a single-writer model, so the popular Postgres pattern ([Prisma: "you don't need a job queue, Postgres has SKIP LOCKED"](https://www.prisma.io/blog/you-dont-need-a-job-queue-postgres-already-has-skip-locked), [HN discussion](https://news.ycombinator.com/item?id=20020501)) cannot be transplanted. Concurrent claimers must not `SELECT` then `UPDATE` in two statements — two cron invocations can both SELECT the same pending row between statements.
2. **Claim with one conditional UPDATE.** `UPDATE jobs SET status='leased', lease_expires_at=?, attempts=attempts+1 WHERE id = (SELECT id FROM jobs WHERE status='pending' AND run_at <= ? ORDER BY run_at LIMIT 1) AND (lease_expires_at IS NULL OR lease_expires_at < ?) RETURNING *` — D1 executes statements atomically, so exactly one concurrent worker's UPDATE matches the row; the other gets zero rows and simply finds nothing to do. Increment `attempts` at claim time, not completion, so a crash still counts as an attempt.
3. **Completion must be guarded by the lease.** Mark `done` with `WHERE id=? AND status='leased' AND lease_expires_at > now`. If the lease expired and another worker reclaimed the job, the slow worker's completion write is rejected instead of clobbering the second attempt's state — the same lease-discipline the [Queues pull-consumer article](https://developers.cloudflare.com/queues/configuration/pull-consumers/) demands of ack-before-effect bugs.
4. **Single-writer contention is the ceiling.** Because all writes serialize, concurrent cron workers give no parallelism benefit against one hot D1 database; prefer one poller that processes a small batch per invocation over many racing pollers. This is the fundamental reason the pattern holds at low-to-medium throughput only.

## Cron-triggered polling

1. **One scheduled handler drives the loop.** A [Cron Trigger](https://developers.cloudflare.com/workers/configuration/cron-triggers/) fires the poller on a fixed schedule (minimum granularity one minute); each invocation claims up to N due jobs and processes them serially. Cron cadence is the lower bound on job latency — a per-minute cron cannot start a job faster than ~60s after enqueue.
2. **Enqueue is transactional with business data.** The winning feature of a DB-backed queue: `INSERT INTO jobs ...` happens in the same D1 batch/transaction as the business write (e.g., "row approved" + "notification job"), so a job can never exist without its trigger data or vice versa. A managed queue cannot give you that atomicity across systems.
3. **Poll query must stay cheap.** Index `(status, run_at)` so the due-work scan is a point lookup; always `LIMIT` the batch per invocation; and sweep `leased` rows with expired leases implicitly via the claim's `lease_expires_at < ?` predicate rather than a separate reaper query.

## Retry, dead-letter, and observability

1. **Retry counter with max attempts.** Each failed attempt increments `attempts`; the claim path (or the failure handler) checks `attempts >= max_attempts` and routes to `dead` instead of back to `pending`. Keep `max_attempts` per-job-type (a thumbnail retry can be aggressive; an outbound-email retry should not).
2. **Dead-letter status is a query, not a separate system.** `SELECT * FROM jobs WHERE status='dead'` is the DLQ — replay is `UPDATE ... SET status='pending', attempts=0, run_at=now`. This SQL-level inspectability is the operational payoff over an opaque managed DLQ, and mirrors the [queues DLQ pattern](queues-dlq-patterns.md) semantics without the extra resource.
3. **Persist `last_error` on every failure.** A dead job with no stored error is undebuggable; write the error message (and attempt timestamp) at each failure so the `dead` view is self-explanatory.
4. **Alert on queue depth and dead count.** Because polling hides backlog, add a periodic check on `COUNT(*) WHERE status='pending' AND run_at < now - interval` and `COUNT(*) WHERE status='dead'` — backlog and dead-letter alerts are what turn this from a pattern into an operable system.

## When to use Cloudflare Queues instead

1. **Use a real queue for throughput and fan-out.** [Cloudflare Queues](https://developers.cloudflare.com/queues/) provides push delivery with batching, retries, consumer concurrency, and DLQs as first-class config; it wins when volume is high, when multiple services consume the same stream, or when you need cross-account/cross-service decoupling. Polling a D1 table also burns D1 read/write rows every minute whether or not work exists.
2. **Keep the D1 table when transactionality and SQL visibility matter.** For modest job volumes where the enqueue must be atomic with business writes, or where operators need to query/replay/purge history with SQL, the jobs table is simpler and cheaper than bolting a queue onto the stack. See also [Workflows](https://developers.cloudflare.com/workflows/) for durable multi-step orchestration that needs resumability, not just delivery.
3. **Overlap note.** The existing `queues-dlq-patterns.md` and `queues-http-pull-consumer-lease-and-recovery.md` cover the managed-queue side; this article covers the D1-table side and the SQLite-specific claiming constraints that make the two non-interchangeable.
