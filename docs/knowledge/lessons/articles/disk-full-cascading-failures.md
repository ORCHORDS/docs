# disk-full-cascading-failures

**Issue:** A disk hits 100% and the failure is never contained to the process that filled it. The database can't extend its WAL or commit writes, the log system that would have told you about it also can't write, health checks start failing for unrelated reasons, and Kubernetes evicts pods into a restart loop when the node reports disk pressure. Disk-full incidents are a masterclass in cascading failure because disk is a shared, non-elastic resource that every layer assumes will be there, and the failure mode of "out of space" is often "corrupt or truncate" rather than "error cleanly." The curated postmortem collections (danluu's list alone indexes many storage-exhaustion outages) show this recurring across decades, and the GitLab 2017 saga remains the canonical demonstration of how disk pressure on a primary sets off a chain — replication lag, human troubleshooting under stress, and ultimately catastrophic data deletion.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How disk exhaustion cascades

1. **Databases degrade strangely before they stop.** PostgreSQL refuses new writes when it can't extend the WAL; MySQL binlog growth halts replication; write-ahead logs and temp files fill what little space remains, so the recovery actions themselves fail. The observed symptoms (random write errors, replication stalls, failed DDL) often point responders anywhere but the disk.
2. **Logs are both the disease and the casualty.** The most common fill vector is a log storm — an error loop writing stack traces at megabytes per second — and the first thing that stops working when the disk fills is logging, meaning the evidence you need is exactly what's not being recorded. This feedback loop (GitLab's own timeline notes ERROR-and-above logging flooding disk and Slack) turns diagnosis into archaeology.
3. **Orchestrators make it a platform event.** On Kubernetes, node disk pressure triggers pod eviction across everything scheduled there, including workloads that wrote nothing. One noisy neighbor's logs can take down an entire node's tenants.
4. **Recovery is blocked by the condition itself.** You often can't even run diagnostics, take a backup, or dump data because those operations need scratch space. Teams improvising "delete something" under pressure delete the wrong thing — the GitLab postmortem's darkest lesson.

## Common fill vectors

1. **Unbounded log and audit retention.** Log rotation configured but never verified; a new deploy raising log level to DEBUG in prod; audit-log append-only growth with no archival policy.
2. **Temporary and uncommitted artifacts.** Batch exports, upload staging directories, core dumps, and interrupted-migration leftovers accumulate for months in a corner of the volume nobody dashboards.
3. **Replication and backup duplication.** Binlogs, WAL archives, and snapshot retention can silently double or triple the footprint of "the database," and a retention change on the backup side can regress.
4. **A traffic spike or bug loop.** Any retry storm, error loop, or traffic event that multiplies per-request logging converts hours of headroom into minutes.

## Why alerts fire too late

1. **Thresholds assume linear growth.** An 80% alert on a volume that grew 1% per month for a year feels permanently safe — until a log storm takes it from 80% to 100% in eleven minutes, faster than the alert's evaluation interval.
2. **Free-bytes is the wrong metric at scale.** The meaningful signal is time-to-full: (free space / current write rate). A 500GB-free volume filling at 60GB/hour is an emergency; a 50GB-free volume filling at 1GB/day is a ticket.
3. **Nobody owns the shared volume.** Root disks and node-local storage host writes from a dozen services; each team's capacity plan assumes the others aren't there.

## Prevention

1. **Separate what can be separated.** Logs, database data, WAL/binlogs, temp dirs, and backups each get their own volume or partition so one filler cannot asphyxiate the database.
2. **Enforce caps at the writer.** Log rotation with size limits and retention counts, max-size on temp artifacts, quotas on node-local storage — plus an aggressive, low-impact headroom cleaner (auto-clean of core dumps and stale tmp files) that runs before disk pressure becomes eviction pressure.
3. **Alert on time-to-full and per-partition usage.** Track write rate against free space, and page when projected time-to-full crosses 24 hours. Per-partition (not aggregate) usage dashboards for anything a database depends on.
4. **Chaos-test the full disk.** Deliberately fill a staging volume to 100% and observe what actually happens: which errors surface, what still starts, whether replication resumes automatically on space reclaim. Teams are routinely surprised by which component fails first.

## Recovery pitfalls

1. **Freeing space doesn't undo damage.** Databases halted mid-write may need crash recovery; interrupted WAL extension can leave replication broken even after space returns. Verify replica health explicitly, don't assume catch-up.
2. **Delete only with a runbook.** Under disk pressure, pre-authorize exactly what is safe to delete (rotated logs, tmp files, specific cache dirs) and require two-person review for anything else. Improvised deletion under outage pressure is how data-loss incidents are born.
3. **Watch for the second fill.** The underlying log storm or retry loop usually restarts the moment service resumes. Find and stop the writer before celebrating reclaimed space, or you will be back at 100% within the hour.
