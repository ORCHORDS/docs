# postgres-high-availability-failover

**Issue:** A single Postgres primary is a single point of failure: the instance dies, every write in the fleet stops until a human notices, promotes a replica, and repoints clients — minutes to hours of downtime. Automated HA (typically Patroni with a distributed configuration store) promotes a replica in seconds, but a badly built cluster is worse than none: split-brain primaries, clients that never reconnect, and failovers that have never once been rehearsed. The problem is assembling replication, leader election, connection routing, and client retry behavior into a system that actually fails over correctly under production load.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Anatomy of an HA cluster

1. **The DCS is the source of truth.** Patroni performs leader election through a distributed configuration store — etcd, Consul, or ZooKeeper — with the cluster leader holding a lease keyed to the DCS quorum. If the DCS itself is not highly available, nothing above it is; three DCS nodes across availability zones is the floor.
2. **Patroni manages, Postgres replicates.** Each database node runs Patroni, which handles streaming replication wiring, primary promotion, replica rewind (`pg_rewind`) for rejoining failed primaries, and lifecycle (start/stop/restart) via DCS decisions — the operator never promotes a replica by hand in steady state.
3. **HAProxy or a Patroni-aware router in front.** Clients never connect "to the primary"; they connect to HAProxy health checks hitting Patroni's REST API (primary on port 5432, replicas on a second listener such as 5002). Promotion flips health checks and traffic follows in seconds, with no DNS change and no client configuration change.
4. **PgBouncer sits between app and HAProxy.** After a failover, thousands of dead connections must be recycled; a pooler absorbs that, and its pause/resume modes make the blight of canceled statements shorter than raw client reconnect storms.
5. **Backups remain separate.** HA protects availability, not data: replication copies corruption and `DROP TABLE` faithfully. PITR/wal-g/basebackup pipelines are a parallel requirement, not a substitute for or from HA.

## Quorum and split-brain avoidance

1. **Three nodes, always.** Patroni requires a DCS majority to elect a leader. Two database nodes plus a three-node DCS works (the DCS, not the DB count, provides quorum); two database nodes with a two-node DCS does not and will either split-brain or freeze.
2. **Witness when a third full replica is too expensive.** A witness node (Patroni with no Postgres) or an external DCS quorum breaks the 2-node tie cheaply; a 50/50 vote with no tiebreaker means the surviving half cannot promote anything.
3. **Synchronous replication is a trade, not a default.** `synchronous_mode` with `synchronous_mode_strict` guarantees zero lost committed transactions on failover but pauses writes if no sync standby is reachable; plain async keeps writes available and risks losing the last few transactions. Choose per RPO — payment state and auth sessions usually justify sync for a subset.
4. **Prevent the old primary from coming back as primary.** Patroni does this via DCS fencing plus `pg_rewind`; if a network partition healed after a promotion, the stale primary must rejoin as a replica. Verify `pg_rewind` works in your setup before you need it — a manual `reinit` under incident pressure is where mistakes happen.

## Failover is a system behavior, not a database event

1. **Client retry logic is part of HA.** During promotion, connections get killed and new ones are refused for seconds. Apps need retry with backoff on connection errors and on `admin shutdown`/`terminating connection` errors, and writes must be idempotent or resumable because an in-flight transaction's fate is unknowable after a kill.
2. **Pgbouncer + retry budget.** Define how long clients retry (e.g. 15–30 seconds covers a clean Patroni promotion) and fail loudly past that. Retries without a budget turn a failover into a self-DDoS.
3. **Logical replication slots break on failover.** Physical streaming replication carries logical slots' state only if `pg_failover_slots` (the PG17-era solution and its successors) is configured; otherwise CDC consumers (Debezium et al.) silently stop receiving changes after promotion. This is the most common post-failover surprise in CDC-heavy stacks.
4. **DNS-based failover is the weak option.** Health-checked HAProxy (or cloud-native equivalents) reacts in seconds; DNS TTLs and connection caches mean DNS-based repointing takes minutes to hours. Use DNS for stable endpoints, routing for the fast path.

## Rehearse, tune, verify

1. **Switchover drills on a schedule.** A planned `patronictl switchover` in business hours monthly proves the mechanism end to end (promotion, routing flip, client reconnect, replica rewind of the old primary). An untested failover plan is a hypothesis, not HA.
2. **Chaos-test the real thing quarterly.** Kill the primary process, unplug a node, partition the network between the primary and DCS — each failure mode behaves differently (fencing, leader lock expiry, no-candidate states) and only practice reveals which alerts fire.
3. **Tune `ttl`, `loop_wait`, `retry_timeout` together.** These Patroni timings set how fast failover happens versus how twitchy the cluster is on transient hiccups; defaults (~30s leader TTL) err conservative. Faster detection shortens downtime but multiplies false failovers on network jitter — change them with measurements of your actual network, not ambition.
4. **Measure RTO and RPO after every drill.** Record seconds-to-promotion and any lost-transaction estimate from the drill, and compare against the SLO. Numbers that drift upward (bigger WAL bursts, slower rewind on grown data) are found in drills, not outages.
