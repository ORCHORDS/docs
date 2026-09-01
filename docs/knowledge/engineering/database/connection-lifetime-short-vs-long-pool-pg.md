# Connection Lifetime Short Vs Long Pool Pg

## Scope

This article covers the trade-off between short-lived and long-lived connections in PostgreSQL application architectures: when to use a connection pooler in transaction mode (connection lifetime equals the transaction), when to use a session-mode pooler or direct connections (connection lifetime equals the application session), and the failure modes that arise when the wrong choice is forced onto the workload. It discusses PgBouncer configuration variables `pool_mode`, `server_lifetime`, `server_idle_timeout`, and `query_wait_timeout`, and applies analogously to other PostgreSQL-aware poolers. It excludes application driver tuning, ORM session management specifics, and TLS/keepalive decisions beyond their interaction with pooler mode.

## Workflow or implementation guidance

1. **Default to transaction-mode pooling for stateless request handlers.** The vast majority of web frameworks issue one or a small, fixed number of transactions per request and have no state that must outlive a transaction. Transaction mode gives the smallest server-connection footprint: a pool of fifty server connections can serve hundreds of worker processes, because each request only borrows a connection for the duration of its transactions.
2. **Move to session-mode pooling when the workload needs session state.** The common offenders are advisory locks, `SET` parameters that must persist (`SET search_path`, `SET ROLE`), server-side prepared statements that must remain valid across transactions, temporary tables, and `LISTEN`/`NOTIFY`. None of these survive transaction boundaries on a different connection. If the application genuinely needs them, the pooler must keep that client pinned to one server connection.
3. **Reserve direct connections for administrative and migration workflows.** Schema changes run by `psql`, `pg_dump`, long analytical queries, and any tool that issues `SET` then `BEGIN` ... then later `COMMIT` need a real server session and will misbehave if they get silently routed through a transaction pooler that drops their state between statements.
4. **Bound server connection lifetime aggressively.** Set `server_lifetime` on the order of 30 minutes to a few hours. Two reasons: it rebalances load across backend processes after configuration changes or maintenance, and it limits the blast radius of any single server connection accumulating unobserved session state. For workloads running only short transactions, much shorter values are safe.
5. **Set `server_idle_timeout` so unused server connections are released** rather than held at minimum-pool size forever; idle server connections still consume backend memory and countable slots.
6. **Configure `query_wait_timeout` and `client_idle_timeout` to fail fast** rather than queue requests indefinitely. A web request that queues for ten seconds in a pooler has already failed its SLO.
7. **Set `application_name` from the pooler-level client connection** so `pg_stat_activity` shows the originating service rather than the pooler name. PgBouncer honours the `application_name` from the client by default; some alternatives require an explicit setting.
8. **Pass authentication through, not around.** Pooler-side `auth_query` (or auth-file mode) keeps the user lookup in Postgres so `pg_stat_activity.usename` reflects the application user, not the pooler user. This matters for `SET ROLE`, row-level security, and audit logs.

## Controls

1. **Pool mode documented per environment.** A configuration table listing which service uses transaction mode, which uses session mode, and why; reviewed whenever a new service connects to the database.
2. **Per-service connection cap.** Each application has a maximum number of pooler client connections and a maximum number of server connections, derived from `max_connections` minus reserved headroom and other services.
3. **Active-connection dashboard.** `SHOW POOLS;` from PgBouncer exposed as a metric; alerts when any pool's `sv_active` approaches the cap or `sv_waiting` is non-zero for more than a few seconds.
4. **Session-state usage detector.** A pre-deployment test that issues the workload's first transaction and verifies that no required state is dropped across a transaction boundary.
5. **Server-lifetime audit.** Periodic confirmation that `server_lifetime` is still bounded; the default of one hour is fine but explicitly documented and increased only with intent.
6. **Reservation budget.** A documented slice of `max_connections` reserved for admin and migration traffic so a runaway application pool cannot starve a release manager's `psql`.

## Validation evidence

1. **Burst test in transaction mode.** Drive a synthetic workload that opens thousands of client connections, each issuing one short transaction; verify the pooler's `sv_active` stays near the server-connection cap and that the total number of server connections is much smaller than the number of clients.
2. **Session-state preservation test.** Under session mode, `BEGIN; SET LOCAL foo='x'; COMMIT; SELECT current_setting('foo');` should return `x` only if the pooler preserves it across transactions; if it returns an empty string, the workload is in the wrong pool mode.
3. **`server_lifetime` rotation test.** Set a short `server_lifetime`, run a sustained workload, and confirm via `SHOW POOLS` that connections are recycled without throughput loss.
4. **Advisory-lock compatibility test.** Acquire a session-scoped advisory lock from a client, then return it to the pool by closing the client connection; verify the lock is released and not orphaned on a different server connection.
5. **Capacity headroom test.** With the application under load and at maximum pool size, attempt a `psql` connection via the reserved admin pool and confirm it succeeds within a few hundred milliseconds, evidencing the reservation budget.

## Failure modes and correction

1. **Session-mode pool silently drops `SET` parameters between transactions.** Symptom: queries suddenly fail with "schema does not exist" after working for years. Correction: switch to transaction mode, move the `SET` into the transaction with `SET LOCAL`, or upgrade to session mode for that workload only.
2. **Prepared statement invalidated by server reuse.** The error `prepared statement "_P1" does not exist` appears when a server connection is recycled between uses and a stale cached statement is referenced. Correction: `DEALLOCATE` on session end, or disable server-side prepared statements at the driver, or rely on the pooler resetting state.
3. **Pool exhaustion manifests as `FATAL: sorry, too many clients already`.** Symptoms are request timeouts and paged database errors. Correction: identify the runaway client, raise the cap only as a temporary measure, and fix the root cause (connection leak, missing pool config).
4. **`LISTEN`/`NOTIFY` event loss.** A transactional pooler reassigns a listening client to a different server connection, and notifications to the prior server are missed. Correction: pin `LISTEN` workloads to session mode or move event delivery to the application via polling a small queue table.
5. **Migration tool stalls because the pooler reroutes its `BEGIN`.** Tools that hold open transactions through long pauses get their connection reclaimed. Correction: run migrations on a dedicated direct connection, bypassing the pooler.
6. **Idle server connections held for hours.** Symptom is `pg_stat_activity` showing many `idle` connections. Correction: lower `server_idle_timeout` and validate that application workloads tolerate server connection churn.

## Limitations

1. **Poolers cannot enforce SQL-level fairness.** They hand out server connections and return them; a single client running long-running statements can still occupy a disproportionate share.
2. **Poolers are not databases** — they neither implement pg_locks nor participate in logical replication. `pg_stat_activity` on the database reflects the *server* connection state, not the *client* request state.
3. **Session-mode pooling recovers less than direct connections** when server connections break mid-statement; in-flight work is lost, not replayed.
4. **Pooler configuration does not fix bad application connection hygiene.** Leaks in the application (connections never returned) still occur, just at a different layer.
5. **Cross-pooler failover coordination** is limited; switching between two poolers in front of two primaries requires application cooperation that is not in the pooler's responsibility.

## Canonical sources

- PgBouncer Documentation, Configuration: https://www.pgbouncer.org/config.html
- PgBouncer Documentation, Features (pooling modes): https://www.pgbouncer.org/features.html
- PostgreSQL Documentation, Connection Settings: https://www.postgresql.org/docs/current/runtime-config-connection.html