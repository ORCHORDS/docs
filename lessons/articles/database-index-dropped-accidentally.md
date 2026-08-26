# database-index-dropped-accidentally

**Issue:** Dropping a "redundant" index is treated as harmless cleanup, but it is one of the few schema changes that can take a database from fully healthy to effectively down without a single error at execution time. The DROP succeeds instantly, nothing crashes, and then every query that relied on that index silently degrades to a table scan. Under production load the scans consume buffer pool and I/O, all other queries on the instance slow down from resource competition (a mechanism DBAs confirm: one bad scanning query degrades even well-indexed queries on the same server), replicas fall behind, and connection pools fill. Adjacent public incidents show how schema changes reach production with unintended blast radius: Resend's February 21, 2024 incident report describes a migration gone wrong that deleted production data, and Sentry's engineering blog documents the slow-query pain caused by missing indexes found after the fact.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What happened

1. **An index was flagged as unused.** A cleanup ticket asserted that an index on a 400-million-row table had "no queries using it." The evidence was a query-log sample from a low-traffic week that missed the weekly batch job and several dashboard queries that used the index.

2. **The drop succeeded and everything looked fine.** The DROP INDEX ran during a quiet maintenance window. Within two minutes, dashboard p99 rose; within twenty minutes, the read replicas were lagging by minutes; within an hour, application connection pools were exhausted and the checkout flow was timing out.

3. **Table scans cannibalized the instance.** The unindexed queries were not new, but they now read the entire table from disk on every execution. Buffer pool hit ratio collapsed for every workload on the box because the scans evicted everyone else's hot pages. The damage was not limited to the queries that lost the index.

4. **Recovery required rebuilding under fire.** CREATE INDEX on a huge table under load took over an hour and added its own I/O pressure. The team restored service faster by killing the offending queries at the proxy and pointing dashboards at a snapshot replica, then rebuilding the index off-peak.

## Why dropping an index is not cleanup

1. **Usage evidence is always incomplete.** Index usage counters accumulate since last restart, query logs sample, and some consumers (batch jobs, quarterly reports, failover paths) run rarely. Absence of observed use is not absence of use. The GitLab January 31 postmortem family of incidents exists because deletion actions were taken on stale assumptions about what was expendable.

2. **No error fires at drop time.** The DROP validates nothing about future query plans. Databases generally do not warn that a remaining query will scan, so the failure is deferred until the query runs at production volume.

3. **The blast radius is the instance, not the query.** Scans take locks longer, fill the buffer pool, and saturate I/O. The innocent indexed queries sharing the hardware degrade together, which makes the incident look like a general database problem rather than a schema change from an hour earlier.

4. **Online DDL makes drops feel free, so people stop fearing them.** Instant drops of indexes are cheap to execute, which is precisely why they skip the review gravity that a data migration attracts. The cost is not in the DDL; it is in the query plans left behind.

## Blast radius mechanics

1. **Plan regression is instantaneous and global.** The optimizer switches every dependent query to a scan on the next plan compilation, so degradation hits all replicas and all regions that share the schema, at once.

2. **Replica lag is the second wave.** Long-running scanning queries on replicas block apply threads in ways that vary by engine, so lag spikes even though write volume is unchanged. Read-your-writes features then fail in confusing ways.

3. **Connection exhaustion is the third wave.** Queries that used to take 5 ms now take 60 s. Pool sizing assumes the former. The application saturates and the failure surfaces as timeouts in unrelated services.

## Guardrails

1. **Treat DROP INDEX like a production data migration.** Require a written blast-radius analysis listing every query that referenced the index, generated from a complete plan-audit (for example, checking query plans and index usage views over a full business cycle, not a quiet week), plus a named rollback that has been rehearsed.

2. **Defer, do not drop.** Mark the index invisible or renamed for 30 to 90 days first where the engine supports it. If nothing regresses, drop it. This converts an irreversible guess into a reversible experiment.

3. **Keep the CREATE INDEX statement in the change ticket.** Rollback for a dropped index is a rebuild that can take hours on a large table, so the recovery script and the maintenance window to run it must be planned before the drop, not improvised during the outage.

4. **Stage the post-change check.** After any schema change, compare p99 latency and buffer pool hit ratio for the top 20 queries against a pre-change baseline within the first 30 minutes. Drift beyond 2x halts the change train automatically.

5. **Never batch index drops into the same window as deploys.** If a drop and a code release land together and latency degrades, the team wastes the first hour of the incident deciding which change caused it. One risky change at a time, with monitoring between.
