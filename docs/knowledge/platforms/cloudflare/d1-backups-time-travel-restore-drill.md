# D1 Backup and Time Travel Restore Drills

D1's Time Travel keeps a rolling window of changes so a database can be restored to a point in time before a bad migration, an erroneous batch update, or an accidental deletion. The feature is only as good as the operator's ability to use it under pressure: picking a timestamp, restoring into a fresh database, verifying the data, and cutting traffic over. Restore drills turn that ability from an assumption into a rehearsed, evidenced capability. This article defines the drill for D1 restore paths — Time Travel restores, backup restores, and export-based recovery — and the verification that proves each one.

## Scope

Covers restore drills for D1 databases: point-in-time recovery via Time Travel, restores from stored backups, and recovery from exported SQL. Applies to production and staging databases where D1 is a system of record. Excludes D1 read replica promotion (covered separately in read replication consistency), schema migration discipline, and application-level soft-delete designs.

## Workflow or implementation guidance

1. Before any drill, record the target database's current state: row counts for key tables, the most recent migration ID, and a checksum or digest of a critical table. This is the "known good now" snapshot the restored copy will be compared against.
2. Run the drill on a copy first. Restore into a new database rather than over production: use the restore-by-timestamp capability to create a database reflecting the chosen point in time.
3. Pick the restore timestamp deliberately: after the incident's damage but before it, depending on the scenario, and confirm it sits inside the available Time Travel window (up to 30 days depending on plan). A timestamp outside the window is a drill failure, not a surprise to discover during an incident.
4. For backup-based scenarios, list available backups, restore the chosen one into a new database, and note how the backup's point compares with the Time Travel point — backups are coarser than arbitrary timestamps.
5. For export-based scenarios, produce an SQL export of the database, then import it into a fresh database. Measure the wall-clock duration; this is the fallback path when neither Time Travel nor backups are usable, and its duration sets expectations.
6. Verify the restored database before any cutover discussion: compare row counts, checksums, schema version, and application smoke tests against the recorded expectations for the target point in time.
7. Document the measured restore time end to end (initiation to verified) and compare it with the stated recovery time objective. If it exceeds the objective, the drill produces an action item, not a pass.
8. Rotate scenarios across drills: point-in-time restore one quarter, backup restore the next, export recovery after that, and occasionally a deliberately impossible scenario (timestamp beyond the window) to test the failure path.

## Controls

- Drill cadence: production D1 databases undergo a documented restore drill at least quarterly.
- Restore-into-new rule: drills never restore over the live production database; cutover is a separate, explicit decision.
- Window-awareness check: the drill record states the database's Time Travel window and confirms the tested timestamp was inside it.
- Verification checklist: row counts, table digests, schema version, and application smoke tests are all required before a drill counts as passed.
- RTO measurement: every drill records elapsed restore-and-verify time against the recovery time objective.
- Failure-path exercise: at least one drill per year deliberately tests an out-of-window or missing-backup scenario to confirm detection and escalation behavior.

## Validation evidence

- Drill report with date, database, scenario type (point-in-time, backup, export), and the operator who executed it.
- Restore command output and resulting database identifier, showing the restore completed without intervention.
- Verification table: expected versus restored row counts, digest comparisons, schema version match, and smoke test results.
- Timing record: initiation to verified-restore elapsed time, compared against the recovery time objective.
- Out-of-window scenario result (from the annual failure-path drill): the error or behavior observed and the escalation taken.
- Action items with owners for any gap found, tracked to closure before the next drill.

## Failure modes and correction

- Restore timestamp outside the Time Travel window: the point-in-time path is unavailable; fall back to the most recent backup or export, and shorten the operational gap by scheduling more frequent exports for critical databases.
- Restored data looks correct but the schema is ahead of the application version being tested: pick the timestamp considering application compatibility, or deploy the matching application version before verifying.
- Export/import takes longer than the RTO: reduce export scope (exclude volatile tables), parallelize where possible, and re-baseline the objective or the architecture — the drill exists to expose this gap.
- Verification passes on counts but not digests: partial or corrupted restore; re-run the restore and add digest checks to the standard checklist (this is why digests are mandatory).
- Confusion between restore and cutover during a real incident: the runbook separates them explicitly — restore produces a candidate, cutover is a named, approval-gated step.
- Drill run only against staging-sized databases: extrapolated timings mislead; at least annually, drill against a production-scale copy or during a low-traffic window with production data volumes.

## Limitations

- Time Travel retention is bounded by plan (up to 30 days); restores beyond the window require backups or exports.
- Point-in-time restores produce a new database; redirecting traffic and updating bindings is a manual cutover step.
- Restores capture the database, not in-flight application state; consistency between the two is the operator's responsibility at cutover.
- Drill timings on quiet systems understate incident conditions; concurrent load can extend restore verification.
- Backup frequency and export freshness bound the worst-case data loss for scenarios outside Time Travel coverage.

## Canonical sources

- Cloudflare D1 docs, "Time Travel and backups": https://developers.cloudflare.com/d1/reference/time-travel/
- Cloudflare D1 docs, "Import and export data": https://developers.cloudflare.com/d1/best-practices/import-export-data/
