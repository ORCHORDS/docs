# Read Replica Lag Tolerant Routing Strategy

## Scope

This article covers PostgreSQL read-replica lag tolerance in application architecture: how to design routing that respects replication lag, where to enforce read-after-write, and the operational levers (synchronous replication, application-side lag awareness, query tagging) that keep the system correct under replica lag. It focuses on streaming-replication-based replicas (the default Postgres primary/replica setup) and the application's responsibilities when some reads can be served from replicas. It excludes logical-replication specifics, multi-region replica placement (which adds latency on top of lag), and pgcat-style proxies beyond their interaction with lag tolerance.

## Workflow or implementation guidance

1. **Define which reads tolerate lag and which do not.** The first decision is the policy: which classes of read can be served from a replica, and which must come from the primary. Examples of lag-tolerant reads: dashboards, search indexes, analytics reports, leaderboards. Examples of lag-intolerant reads: a user reading their own freshly written record, an idempotency-key check after a write, payment-status checks after a payment.
2. **Route writes and lag-intolerant reads to the primary.** Treat the primary as the source of truth; the read replica is a best-effort reader. A simple policy is "writes to primary, reads by default to replica unless flagged". Enforce this in the data-access layer, not by convention.
3. **Use synchronous replication selectively, not globally.** `synchronous_standby_names = 'ANY 1 (replica1, replica2)'` guarantees that at least one replica has acknowledged the write before the primary returns success, but it costs latency on every commit. Apply it only to data that must be on the replica immediately, not to every transaction.
4. **Measure lag continuously.** `SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn(), pg_last_xact_replay_timestamp()` from the replica side returns the lag in bytes and time. A monitoring endpoint polls this and exposes it as a metric; alerts fire when lag exceeds a threshold.
5. **Tag reads with staleness tolerance.** The application sets a `max_staleness_seconds` per read query; the routing layer either confirms the replica's lag is below the tolerance or routes to the primary. This is more sophisticated than "primary or replica" and is appropriate for high-stakes reads.
6. **Use `SET LOCAL statement_timeout = '100ms'` on read-only paths.** Even when reads are fast, a replica under lag may take longer to acknowledge queries; an application timeout prevents a stuck read from blocking a user.
7. **Avoid long transactions on replicas.** Long-running queries on replicas can themselves delay replication replay (`recovery_min_apply_delay` is the explicit lever; in default configurations, vacuum and large queries can still slow down replay). Keep read queries short and use pagination.
8. **Plan for failover.** When the primary fails over to a replica, the new "primary" was previously a replica; any application code that depends on `synchronous_standby_names` for correctness must be re-evaluated in the new topology. Test failover drills.
9. **Tie reads to the user's session for read-after-write.** A common pattern is "the user just wrote, set a session-level flag that the next read must hit the primary". The flag expires after one read or after a TTL, whichever comes first. Session-level flags must respect pooler session lifetime (transaction mode drops them).
10. **Document the routing rules.** A central config maps query class to routing destination; new queries must declare their staleness class. A spreadsheet is fine for the first version; the discipline matters more than the tooling.

## Controls

1. **Lag dashboard with alerting.** Per-replica lag in bytes and time; alerts when lag exceeds a configurable threshold for more than a configurable duration.
2. **Synchronous-replication policy review.** A documented list of which tables and which flows are covered by synchronous replication; reviewed before each change to replication topology.
3. **Read-routing class declaration.** Each query's data-access method declares its staleness tolerance; enforced in code review.
4. **Failover drill schedule.** Periodic exercises that simulate primary failure and validate the application's recovery posture, including lag-aware reads.
5. **Replica-load metric.** A dashboard tracking read-QPS per replica; informs when to add replicas or when to move lag-tolerant reads to a dedicated replica.
6. **`pg_stat_replication` review.** A weekly review of `state`, `sent_lsn`, `write_lsn`, `replay_lsn`, `sync_state` per replica; catches stuck replicas early.

## Validation evidence

1. **Lag-intolerant read test.** Issue a write, then immediately read the same row through the read path that should be tolerant of lag; assert the read returns the freshly written value, evidencing the primary routing or staleness tolerance.
2. **Replica lag injection.** Throttle the replica's apply (for example via `pg_wal_replay_pause()` and a measured delay) and confirm the application's lag-tolerant reads continue without error while lag-intolerant reads route to the primary.
3. **Synchronous replication cost test.** Measure commit latency with synchronous replication enabled; assert the added latency is bounded and acceptable for the workload.
4. **Failover drill.** Stop the primary; assert the application continues to serve reads from the new primary (formerly a replica) and that the lag-aware policies still apply.
5. **Pooler interaction test.** Run the routing logic through a transaction-mode pooler and assert the staleness flags and routing decisions are preserved; session-mode flags must be set per server connection, not per client.

## Failure modes and correction

1. **A lag-intolerant read is accidentally served from a replica.** Symptom: a user sees stale data after writing. Correction: enforce routing by code review and by tests that fail when the routing logic drops the staleness flag.
2. **Replica falls further behind than the application tolerates.** Symptom: lag-intolerant reads start hitting the primary in volume; primary load rises. Correction: investigate the replica's bottleneck (apply is slow, disk is slow, network is slow), add a replica, or reduce the read load on the affected replica.
3. **Synchronous replication causes commit latency spikes.** Symptom: application writes slow under load. Correction: limit synchronous coverage to a smaller subset of writes, or move to `synchronous_standby_names = 'ANY 1 ...'` rather than naming a single replica (so failover is graceful).
4. **Read-after-write fails because of session loss under a pooler.** Symptom: a session-level flag is set but a transaction-mode pooler reassigns the connection. Correction: persist the staleness flag in a request-scoped context (HTTP header, request ID) rather than a session variable; have the data-access layer honour it per request.
5. **Failover leaves lag-aware code stuck on the wrong side.** Symptom: an application that depended on the old primary's identity continues to query it. Correction: re-resolve the primary at failover, or use a connection router that updates automatically.
6. **A long-running read on the replica slows replay.** Symptom: lag grows after a heavy analytical query. Correction: move the analytical query to its own replica or to an analytical store; avoid running queries longer than `wal_receiver_timeout` / apply checkpoints on the replica.

## Limitations

1. **Replica lag is a fundamental physical limit** of streaming replication; no routing strategy can eliminate it, only tolerate it.
2. **`synchronous_standby_names` adds latency** that may not be acceptable for every workload.
3. **Session-level state (read-after-write flags) interacts poorly with pooler modes** that drop session state; the application must be aware.
4. **Failover windows are not zero** even with synchronous replication; the application must tolerate a brief window during which no replica is fully caught up.
5. **Cross-region replicas add network latency on top of replication lag**; the policy must distinguish "lag" (replication delay) from "latency" (round-trip).

## Canonical sources

- PostgreSQL Documentation, High Availability, Load Balancing, and Replication: https://www.postgresql.org/docs/current/high-availability.html
- PostgreSQL Documentation, Hot Standby (read queries on a replica): https://www.postgresql.org/docs/current/hot-standby.html
- PostgreSQL Documentation, Monitoring WAL Shipping (lag metrics): https://www.postgresql.org/docs/current/warm-standby.html