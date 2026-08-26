# postgres-major-version-upgrade

**Issue:** PostgreSQL major versions EOL roughly every five years, and staying past EOL means no security fixes — yet upgrades get deferred because they touch every node, can brick extensions, and historically meant downtime proportional to database size. Teams need to choose deliberately between the three main paths (dump/restore, `pg_upgrade`, logical replication), rehearse them on production-scale copies, and execute a known post-upgrade checklist. The gap shows up as panic: an EOL-driven rushed upgrade with no rollback plan.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing an upgrade path

1. **pg_upgrade (in-place) is the default.** It converts the on-disk catalog format and reuses data files, taking minutes-to-hours rather than the days of a full restore; with `--link` the data files are hard-linked so copy time drops to near zero, at the cost of losing the old cluster if you keep writing only the new one.
2. **Dump/restore only for small or decluttered databases.** `pg_dump | pg_restore` rewrites every row (and repacks indexes), so it is slow at TB scale — but it is the only path that fully rebuilds and re-checks the cluster, and a good excuse to drop decades of cruft.
3. **Logical replication for near-zero downtime.** Stand up the new-version cluster, publish from old, subscribe on new, let it catch up, then flip traffic — the blue/green pattern now used by every major managed provider. Budget for its known gaps: sequences, DDL, and large objects do not replicate and need manual sync at cutover.
4. **Match versions on extensions first.** Each extension binary must exist for the target version (postgis especially pins PG versions); an unavailable extension is a hard blocker discovered cheapest on a rehearsal run.
5. **Never skip the rehearsal.** Run the full path against a production-sized restore and time it; upgrade night is not when you learn that `pg_upgrade --link` needs the old cluster stopped or that a pre-9.0 flashback aborts the run.

## pg_upgrade mechanics and gotchas

1. **Both clusters must be stopped and on the same machine (or share storage).** pg_upgrade reads and writes both data directories directly; the standard layout is new binaries initialized beside the old datadir, old server stopped.
2. **`--link` trades rollback for speed.** Hard-linked data files mean the old cluster cannot be restarted after the new one runs; keep the old cluster's full backup as the rollback plan instead. Without `--link` you get a copy that leaves the old cluster bootable.
3. **`--check` before committing.** The dry-run flags postmaster-start failures, incompatible relfilenodes, and prepared-transaction leftovers in seconds; run it in the runbook before any maintenance window opens.
4. **Statistics do not survive.** pg_upgrade does not carry over planner statistics, so the first queries after cutover run against empty `pg_statistic` — the post-upgrade `ANALYZE` (or `vacuumdb --analyze-in-stages`) is mandatory, not optional.
5. **Watch `pg_upgrade_internal.log` and old-style users.** Roles/databases are carried by `pg_dumpall --globals-only` in the runbook; a missed globals restore produces confusing "role does not exist" errors on app connect.

## Logical-replication blue/green cutover

1. **Sequence the cutover carefully.** The standard order: stop writers (or flip to read-only), wait for replication to drain, `setval()` every sequence on the new cluster above the old max, re-check extension versions, then repoint the application and re-enable writes.
2. **DDL freeze during initial sync and cutover.** Logical replication carries DML only; any migration shipped mid-sync is silently absent on the target. Freeze deploys from publication creation until after cutover, or replay migrations manually in order.
3. **Use one publication per database and mind restrictions.** Publications are per-database, and tables need a replica identity (primary key) to carry UPDATE/DELETE — the same constraint covered in the row-filters/replica-identity companion article.
4. **PG18 relaxes the biggest pain.** PostgreSQL 18's asymmetric logical replication lets logical subscribers be newer than publishers and lets publications survive major upgrades of the provider, directly targeting this cutover workflow; verify your provider supports it before relying on it.
5. **Keep the old cluster read-only for a bail-out window.** The rollback plan is repoint DNS/pooler back to the old (frozen) cluster and reconcile the small post-cutover writes manually — document which tables can tolerate that and which cannot.

## Post-upgrade checklist and managed-provider notes

1. **ANALYZE everything, then watch plans.** Beyond `vacuumdb --analyze-in-stages`, monitor `pg_stat_statements` for the first days; plan changes from new-version planner behavior are normal and usually favorable but occasionally need statistics targets nudged.
2. **Re-enable and version-check extensions, then run their upgraders.** PostGIS in particular ships `postgis_upgrade()` steps; an extension left on an old so-version works until it doesn't.
3. **Refresh backups and monitoring immediately.** Take a fresh base backup of the new cluster (old backups may not match the new catalog format), and confirm WAL archiving, replication slots, and connection pooling against the new version.
4. **Pre-warm if you can.** First-day latency spikes are often cold cache, not the upgrade; `pg_prewarm` on the hot tables (or a slow ramp behind the pooler) smooths it.
5. **Lean on blue/green features where managed.** AWS RDS/Aurora Blue/Green Deployments, Azure Flexible Server, and Cloud SQL automate the logical-replication dance including the sequence sync; you still own extension compatibility and the application-level verification.
6. **Schedule the next one now.** EOL dates (PG 13 in Nov 2025, each version ~5 years) belong on the ops calendar the day after a successful upgrade — the cheapest upgrade is the one that starts two years before the deadline.
