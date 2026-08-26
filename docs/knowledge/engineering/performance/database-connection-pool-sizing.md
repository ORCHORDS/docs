# database-connection-pool-sizing

**Issue:** Applications open a database connection per request (or per pod) until Postgres hits `max_connections`, at which point new connections are refused, memory per backend balloons, and context-switching on hundreds of idle connections degrades every query. Conversely, undersized pools cause requests to queue for a free connection and time out even though the database itself is nearly idle. This article covers how to size connection pools correctly, when to put PgBouncer in front, how to diagnose exhaustion, and the operational practices that keep the math valid as the fleet scales.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Sizing Fundamentals

1. **Connections are server-side workers, not sockets.** Each Postgres backend is a full process with its own memory (work_mem multipliers per sort/hash) and a scheduler slot; 500 mostly-idle connections slow down the 20 doing work. The database's effective concurrency is bounded by CPU cores and disk parallelism, not by `max_connections`.
2. **Start from the classic formula.** For server-side connections per database node: `connections = (core_count x 2) + effective_spindle_count` (SSDs count as many effective spindles). An 8-core node lands around 20-30 active connections; this formula reflects that active queries are CPU/IO-bound, and more concurrent backends past this point only adds queueing.
3. **Compute the fleet budget, not one pool.** The real constraint is `sum(instances x pool_size) < max_connections - reserved`, where reserved covers migrations, superuser, monitoring, and backups. Horizontal scaling multiplies pools: 20 pods x 10 connections already consumes 200 slots, and the math that worked at 3 pods silently crashes the service at 25.
4. **Right-size for wait-time, not throughput.** If pool wait time (time requests spend queued for a connection) is near zero and connections are not saturated, the pool is big enough; throughput does not improve with more connections once the DB is saturated. Increase pool size only when wait time hurts latency and DB utilization has headroom.
5. **Account for connection acquisition latency.** Direct TLS+auth handshake to Postgres costs tens of milliseconds; pools exist partly to amortize it. Long-lived pooled connections need a validation/liveness check (or TCP keepalives) so firewalls and DB restarts do not hand the app dead sockets.

## Deployment Topologies

1. **In-app pool (pg / node-postgres, HikariCP, SQLAlchemy).** First choice for a small, fixed number of app instances: pool per process, sizes summed against the budget above. Keep per-process pools small (5-20) and total under ~100 per database node; one giant pool inside one process is equally subject to the formula.
2. **External pooler: PgBouncer in transaction mode.** Once instance count x pool size exceeds the server budget, put PgBouncer between: clients hold lightweight client connections while PgBouncer multiplexes a small server pool, reassigning server connections per transaction. Transaction mode supports thousands of client connections with ~10-20 server connections.
3. **Session vs transaction pooling trade-offs.** Session mode pins a server connection per client session (safe for session state, `SET`, prepared statements in some drivers); transaction mode breaks session-bound features (advisory locks held across transactions, `LISTEN/NOTIFY`, some prepared-statement caches) — the driver must be configured accordingly (e.g., `preparedStatements: false` for node-postgres through PgBouncer transaction mode).
4. **Pooler high availability.** Run multiple PgBouncer instances behind a load balancer rather than one shared one; a single pooler is a SPOF that also caps total client throughput, and each instance maintains its own `default_pool_size` toward the shared server budget. Point them at one Postgres primary (or use pooling-aware routing).
5. **Serverless and edge runtimes.** Per-request compute (Lambda, Workers via Hyperdrive-style brokers) cannot hold process-level pools; route through a shared external pooler with connection reuse and keep client-side timeouts short. Never let each invocation open its own direct connection — that is the connection-per-request anti-pattern at fleet scale.

## Exhaustion Symptoms and Diagnosis

1. **Symptom: `too many connections` / `remaining connection slots are reserved`.** The server budget is spent; identify spenders with `SELECT count(*), usename, application_name FROM pg_stat_activity GROUP BY 2,3` and reconcile against the intended per-instance pool size. This error means the fleet math is wrong, not that `max_connections` should be raised.
2. **Symptom: requests stall then time out in acquisition.** Pool wait time climbing while DB CPU stays low means the pool (or PgBouncer `default_pool_size`) is too small for concurrent demand, or connections are being held too long. Check `SHOW POOLS` in PgBouncer: `cl_waiting` above zero for sustained periods is the queue you are looking for.
3. **Symptom: connections leak over process lifetime.** `pg_stat_activity` count creeps up until restart — a code path acquires without releasing (missing `finally`, an early return before `client.release()`), and the pool's max masks it until it cannot. Use pool metrics (checked-out count) and leak-detection timeouts to find the path.
4. **Symptom: long transactions starve the pool.** One request holding a connection across an external API call multiplies required pool size; in transaction mode PgBouncer cannot reuse the server connection until commit/rollback. Inspect `pg_stat_activity` `state = 'idle in transaction'` and move external I/O out of transactions.
5. **Symptom: bursts return 500s with reserve_pool silence.** PgBouncer's `reserve_pool_size` only activates after `reserve_pool_timeout` and per-user caps may still refuse; if bursts regularly dip into reserves, raise steady-state sizing or shed load earlier. Alerts on wait-queue depth catch this before users do.

## Operational Practices

1. **Set hard timeouts at every layer.** `statement_timeout` and `idle_in_transaction_session_timeout` on the server, query timeouts in the driver, and pool acquisition timeouts in the app — an unbounded query otherwise pins a connection forever and converts one slow statement into pool exhaustion.
2. **Name and tag every connection.** Set `application_name` (or JDBC connection properties) to include service and instance so `pg_stat_activity` attributes spenders instantly during an incident. Unnamed pools make fleet-budget reconciliation guesswork.
3. **Expose pool metrics and alert on saturation.** Export checked-out connections, waiters, and wait-time histograms (most drivers/PgBouncer expose these); alert on sustained waiters > 0 or utilization > 80%. Pool saturation precedes user-visible latency by minutes.
4. **Re-run the budget math on every scale event.** Autoscaling groups and per-pod pools change `instances x pool_size` dynamically; cap max replicas or route new instances through a pooler so horizontal scale cannot blow the server budget. Keep the formula in the service's config review checklist.
5. **Migrations and admin work need reserved headroom.** Keep `superuser_reserved_connections` plus a fixed allowance for migrations, pgbouncer admin, and monitoring out of the application budget; an application that can spend every slot will eventually block the very tools needed to fix it.

## Related

d1-query-optimization, database-query-optimization, n-plus-1-queries, redis-pipeline-batching, latency-budget-allocation
