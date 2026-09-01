# Hyperdrive Read Replica Routing Pool Size

## Scope

This article covers the Cloudflare Hyperdrive configuration of read-replica routing and connection pool sizing for Postgres-backed applications running on Cloudflare Workers. It addresses how Hyperdrive positions queries between primary and read-replica databases, how its built-in connection pool interacts with that routing, and the tuning levers for pool size, query timeout, and statement caching. It excludes Hyperdrive-for-MySQL differences (the behaviour diverges subtly around session variables), the Workers RPC/Service Binding layer, and durable-storage reads that bypass the database entirely.

## Workflow or implementation guidance

1. **Understand what Hyperdrive is doing.** Hyperdrive is a connection pooler and read-routing proxy sitting between Workers and a Postgres-compatible backend. It maintains a pool of connections to the configured database, routes read queries to a replica when one is configured, and provides query caching for selected `SELECT` statements. The application issues SQL through the `hyperdrive.binding` from `env.HYPERDRIVE` and Hyperdrive handles the rest.
2. **Configure the primary first, the replica second.** Hyperdrive's `wrangler.jsonc` (or `wrangler.toml`) configuration declares an `origin` (the primary) and an optional `read_replica_origin` (a streaming or logical replica). Both are entered as `host`, `user`, `password`, `database` references. Hyperdrive routes the application differently based on statement type.
3. **Treat the replica as eventually-consistent.** Reads against the replica observe the primary's commits after the replication lag; code that depends on read-your-writes must either read from the primary explicitly or tolerate the lag. Hyperdrive's replica routing is read-only; writes always go to the origin.
4. **Tune the connection pool to match the workload, not the worker count.** A common misconfiguration is to set `max_connections` to the maximum number of Workers; the right number is closer to the database's actual capacity, typically a small fraction of `max_connections` on the Postgres server. Cloudflare exposes `max_connections` per Hyperdrive binding; tune from there.
5. **Use the `caching` configuration to enable query caching only for safe queries.** Hyperdrive can cache `SELECT` results keyed by the parameterised SQL text. Configure cache `max_age`, `max_db_rows`, and `stale_while_revalidate` per query, and only enable caching for queries whose result is stable across the configured age. Reads with strong consistency requirements must opt out.
6. **Set `tls` and `sslmode` correctly for the origin.** TLS configuration must match what the Postgres server expects; misconfiguration leads to handshake failures that surface as `connection refused`-style errors with confusing stack frames. `verify-full` is the safest default.
7. **Avoid session-state features.** Hyperdrive is essentially transaction-scoped pooling; advisory locks at session scope, server-side prepared statements that span transactions, and `LISTEN`/`NOTIFY` are not supported reliably. Application code that needs those must use direct connections or Durable Objects instead.
8. **Prefer `readReplica` only when the replica can serve the queries.** Bulk analytical scans, full-table counts, and `pg_dump`-style workloads are candidates for the replica if the replica can sustain the load; short OLTP reads are usually better on the primary because the round-trip cost dominates.
9. **Watch the metrics.** Cloudflare's dashboard exposes Hyperdrive metrics: active queries, pool utilisation, cache hit rate, replication lag (when measured by Hyperdrive). Set alerts on a sustained high pool utilisation, on cache miss rate, and on error rates.
10. **Test locally with the `wrangler dev` emulation of Hyperdrive.** Local development should still bind a Hyperdrive binding; otherwise the production behaviour diverges. Hyperdrive's local emulation is the right surface to validate configuration changes.

## Controls

1. **Pool sizing policy.** Documented upper bound for `max_connections` derived from the Postgres `max_connections` minus other consumers; explicitly lower than worker concurrency.
2. **Cache policy review.** Each query whose caching is enabled is documented with its staleness tolerance and reviewed periodically; queries that change meaning with new data have caching disabled.
3. **Read-after-write compliance test.** A CI test that issues a write and immediately reads the same row, asserting that the read returns the freshly written value (either by routing the read to the primary or by waiting out the lag).
4. **Replica health check.** A dashboard showing replication lag from the database side (for example a query against `pg_stat_replication` on the primary), plus Hyperdrive-side pool statistics.
5. **TLS verification.** A startup check that the configured `sslmode` is honoured by both origin and replica, with a deliberately bad-mode test that fails the boot.
6. **Connection-reset discipline.** Application code releases connections (`ctx.waitUntil` and try/finally discipline) to keep pool utilisation stable under bursty traffic.

## Validation evidence

1. **Read-after-write test.** A staging test that issues `INSERT` then `SELECT` for the same row, asserting the value matches; run with and without read-routing enabled to expose the lag effect.
2. **Replica fallback test.** Disable the replica in the binding configuration and confirm the application continues to function with reads on the primary; enables a safe failover path.
3. **Pool saturation test.** Drive a synthetic burst from a staging workload and confirm the pool reports active connections close to the configured `max_connections` without exceeding it, and that the request rate plateaus rather than errors.
4. **Cache hit-rate measurement.** After enabling caching for stable queries, confirm a high hit rate on subsequent identical requests and that cached values expire at the configured `max_age`.
5. **Statement-error test.** Issue a malformed statement and confirm the failure surfaces as a clean error rather than a stalled pool connection, evidencing the connection-recycle behaviour.

## Failure modes and correction

1. **Replica lag spikes produce stale reads.** Symptom: a user writes a value and reads the previous one. Correction: route the read to the primary for that flow, or accept and display the lag.
2. **Pool exhaustion under burst.** Symptom: requests time out or error with a pool-related message during traffic spikes. Correction: raise `max_connections` only after verifying the primary can accept more; consider query-level timeouts to fail fast.
3. **Cached stale query returns a wrong value.** Symptom: a query that should have refreshed returns an old result. Correction: lower `max_age` or disable caching for that query; the cache must not outlive the staleness tolerance.
4. **Session-state assumption breaks.** Symptom: `SET search_path = ...` does not survive into the next transaction. Correction: switch to per-transaction `SET LOCAL` or restructure queries so no session state is required.
5. **Misconfigured TLS rejects all connections.** Symptom: errors at first request. Correction: align `sslmode` with the Postgres `pg_hba.conf` requirement; verify with `psql` against the same URL.
6. **Worker RPC hot loop in the application layer.** Symptom: pool is exhausted by re-entrant calls. Correction: audit the request graph for cycles and add backoff or batching.

## Limitations

1. **Hyperdrive does not replicate state.** It routes; it does not move data between primary and replica. Replica provisioning, lag management, and failover remain Postgres operator concerns.
2. **Hyperdrive caching is best-effort.** Cache eviction and consistency across regions are not exposed; relying on cached reads for correctness is fragile.
3. **Session-pooled features are not supported.** Anything that depends on session state must use a direct connection or Durable Objects.
4. **Query plans and execution happen on the database, not Hyperdrive.** Tuning query performance requires server-side actions; Hyperdrive only routes and pools.
5. **Cross-region latency dominates.** Hyperdrive reduces connection overhead but not the underlying network path; geographically distant databases still pay their round-trip cost.

## Canonical sources

- Cloudflare Hyperdrive Documentation: https://developers.cloudflare.com/hyperdrive/
- Cloudflare Hyperdrive Configuration (Connection Pooling and Tuning): https://developers.cloudflare.com/hyperdrive/configuration/connection-pooling/
- Cloudflare Hyperdrive Connection Pool Tuning: https://developers.cloudflare.com/hyperdrive/configuration/tune-connection-pool/