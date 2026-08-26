# database-replication-lag-monitoring

**Issue:** Read replicas, standby nodes, and downstream consumers (CDC pipelines, caches, warehouses) are only as good as how far behind they are, and replication lag is routinely measured wrong: time-based lag reads huge when the primary is simply idle, byte-based lag does not translate into user-visible delay, and lag discovered at failover time becomes data loss. A replica that is 20 minutes behind turns a planned failover into an incident and silently serves stale reads to users who just wrote. This article covers the two dimensions of lag, how to measure each correctly, the classic pitfalls, alerting design, and lag as a failover-readiness signal.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two dimensions of lag

1. **Byte lag: unapplied volume.** In PostgreSQL, comparing write-ahead-log positions with pg_wal_lsn_diff between the primary's pg_stat_replication.send_lsn (or pg_current_wal_lsn) and the standby's pg_last_wal_replay_lsn gives bytes not yet applied; it is exact, always meaningful, and the right basis for capacity alarms (replication slots retaining unbounded WAL).
2. **Time lag: how far behind the replica is.** Time-based measures (the replay_lag column, or managed-service metrics like Cloud SQL's replica_lag) estimate seconds of delay and map better onto user impact, but only when write traffic is flowing — they derive from timestamp arithmetic, not a clock comparison of actual delay.
3. **Carry both, alert differently.** Bytes answer "is the replication channel moving and how much backlog exists"; time answers "how stale are reads on this replica"; neither alone is sufficient, and every serious guide from 2025-2026 recommends tracking both.

## Measurement approaches

1. **Primary-side views for channel health.** On the primary, pg_stat_replication per WAL sender shows state, sent/flush/replay LSN, write/flush/replay lag per attached standby — this is where you detect a broken sender, a stuck state, or one lagging replica among several.
2. **Replica-side views for apply health.** On the standby, pg_last_wal_replay_lsn and pg_last_xact_replay_timestamp show local progress; monitoring only the primary misses a replica that cannot apply what it received.
3. **Heartbeat tables for true end-to-end lag.** A writer commits a timestamped row on a loop and the monitor reads it through the replica; this measures what nothing else does — the actual staleness a replica-reading client observes — and it works identically across engines and managed services where internals are hidden.
4. **Managed-service metrics need verification.** RDS-style ReplicaLag is computed as current time minus the last applied transaction timestamp and misreports when traffic is sparse; know the formula behind every platform metric before alerting on it.
5. **Distinguish network from apply.** Cloud SQL exposes network_lag alongside replica_lag; separating transfer delay from apply delay tells you whether the fix is bandwidth or replica CPU, and the same split can be derived from sent-versus-replay LSN gaps on self-managed clusters.

## Pitfalls that produce false alarms

1. **Idle-primary inflation.** When no transactions commit, time-based lag appears to grow because the last replay timestamp ages; gate time-lag alerts on write activity (recent commit traffic) or the alert pages you every Sunday morning for a healthy database.
2. **Catch-up bursts after batch jobs.** Large maintenance writes (vacuum full, bulk backfills, mass updates) spike byte lag legitimately; alert on sustained lag with burn-style windows rather than instantaneous thresholds.
3. **Ignoring replication-slot retention.** A stuck consumer holding a slot pins WAL on the primary until the disk fills; slot retention size is a primary-side failure mode that replica lag alone never shows.
4. **Averaging across replicas.** Fleet-average lag hides the one pathological replica; alert per instance and aggregate only for dashboards.
5. **Monitoring lag but never measuring read staleness.** Applications reading-your-writes (show a saved profile immediately) need stricter per-request expectations than async replication provides; that mismatch is an architecture finding, not an alerting one.

## Alerting design

1. **Two-tier thresholds.** Warning at a sustained staleness users might notice (for example, 30 seconds of time lag over 10 minutes with write traffic present) and critical at the threshold that blocks failover or forces routing changes; the critical tier should tie to an action, not a feeling.
2. **Alert on channel state changes, not just magnitude.** Streaming-to-catchup transitions, disconnected senders, and slot inactivity are events with clear meanings; magnitude thresholds without state awareness generate the worst kind of noise.
3. **Alert on WAL retention bytes as a disk-protection tripwire.** Primary disk exhaustion from a lagging consumer takes down writes cluster-wide and is the most expensive failure in this domain.

## Lag as failover-readiness signal

1. **Treat current lag as your recovery point estimate.** At failover, unapplied WAL is data loss; a dashboard line of lag over time is effectively a live RPO graph, and failover drills should record what lag translated into lost transactions.
2. **Gate automated failover on lag.** Promotion policies should refuse or escalate when the candidate standby exceeds the data-loss tolerance rather than promoting the freshest-but-broken node automatically.
3. **Drain before planned switchover.** Planned operations should wait for near-zero lag and pause writes; measuring lag continuously makes that gate possible instead of hopeful.
4. **Track lag trend per replica over weeks.** Slowly growing apply lag predicts replica CPU saturation before it becomes an incident; a weekly review of the trend line is cheaper than the 3 a.m. page it prevents.
