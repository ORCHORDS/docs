# Write Ahead Log Fsync Trade Off Durability

## Scope

This article covers the durability-vs-performance trade-off in PostgreSQL's write-ahead log (WAL) `fsync` configuration: the `fsync`, `synchronous_commit`, and `full_page_writes` settings, and the consequences of turning them down for throughput. It addresses the canonical decision when configuring a database for high write throughput, the failure modes that arise from turning off fsync guarantees, and the operational levers (replication, synchronous_commit on replicas) that allow performance while preserving durability. It excludes backup/recovery strategy beyond `archive_mode` and `restore_command` interactions, and the choice of replication topology (covered elsewhere).

## Workflow or implementation guidance

1. **Leave `fsync = on` unless you have a deliberate reason to disable it.** `fsync = on` is the default and ensures that committed transactions are durable across an OS or hardware crash. Turning it off means committed transactions can be lost on crash; only do this when the application explicitly accepts the loss.
2. **Set `synchronous_commit = off` per transaction when committing without durability is acceptable.** `synchronous_commit = off` returns success to the client as soon as the WAL is written to the OS cache, without waiting for the WAL to be flushed to disk. On crash, the last few transactions may be lost. This is the right knob for high-throughput workloads that tolerate small losses (logging, metrics ingestion, idempotent re-derivable data).
3. **Use `synchronous_commit = remote_write` or `on` for data that must be durable on the primary's replica.** Setting `synchronous_commit = remote_write` waits for the replica to acknowledge receipt but not flush; `on` waits for the replica to flush. These settings trade commit latency for replica durability.
4. **Leave `full_page_writes = on`.** `full_page_writes = on` writes the full first page after a checkpoint to the WAL, so a torn write during a crash can be recovered. Turning it off risks unrecoverable corruption after a crash that hits the page writer; the small performance cost is not worth the recovery risk.
5. **Tune `wal_writer_delay` and `wal_writer_flush_after` for the workload.** The default `wal_writer_delay = 200ms` flushes pending WAL every 200 ms even without `synchronous_commit = off`. Lowering it shrinks the window of potential loss; raising it can improve throughput but increases the loss window.
6. **Configure `commit_delay` and `commit_siblings` if you want batched flushes.** `commit_delay` waits for `commit_siblings` concurrent commits before flushing, allowing a single flush to cover many transactions. This is a tuning lever for workloads with high commit rates.
7. **Use replication to absorb crash loss.** With `synchronous_commit = on` and at least one synchronous replica, the commit is durable on the replica even if the primary crashes; failover preserves the committed transactions. Replication is the right way to keep `synchronous_commit = on` while tolerating single-node crashes.
8. **Set `wal_level = replica` (or `logical` if needed) so WAL records cover replication.** `wal_level = minimal` is enough for crash recovery but not for replication; if the workload relies on replicas, `wal_level` must be raised, with corresponding implications for WAL volume.
9. **Monitor WAL volume and `pg_stat_replication` flush lag.** WAL volume that grows unexpectedly indicates a runaway writer or a stuck replica; a replica's `flush_lsn` lag indicates how far behind durability is.
10. **Test crash recovery in a staging environment.** A controlled crash test (kill -9 the database, restart, observe what was lost and what survived) is the only way to verify the configuration actually delivers the durability the application needs.

## Controls

1. **Per-transaction `synchronous_commit` policy.** A documented mapping of transaction class to `synchronous_commit` setting; enforced at the connection or transaction boundary.
2. **`fsync` policy.** A documented rule that `fsync = on` in production unless an exception is approved; alerts on configuration changes.
3. **WAL volume dashboard.** A monitor tracking WAL generation rate and replica replay rate; alerts on spikes or on growing gaps.
4. **Replica flush lag monitor.** A monitor on `pg_stat_replication`'s `flush_lsn` versus `sent_lsn`; alerts on synchronous-replica lag.
5. **Crash-recovery drill schedule.** Periodic exercises that simulate a primary crash and validate the application's recovery posture, including which transactions were lost.
6. **`full_page_writes` policy.** A documented rule that `full_page_writes` remains `on`; a regression alert on configuration drift.

## Validation evidence

1. **Crash recovery test.** Run a workload under controlled conditions, kill -9 the primary, restart it, observe which transactions are lost; assert the loss matches the documented `synchronous_commit` setting.
2. **`synchronous_commit = off` throughput test.** Compare commit throughput with `on` and `off`; assert the throughput improvement is bounded and matches the workload's tolerance.
3. **`wal_writer_delay` effect test.** Measure commit latency and loss window for different `wal_writer_delay` values; assert the chosen value fits the application's tolerance.
4. **`commit_delay` batching test.** Run a high-concurrency workload with `commit_delay` and `commit_siblings` configured; assert that batching reduces flushes per second without violating the application's latency budget.
5. **Replica flush-lag test.** Configure a synchronous replica and measure commit latency; assert the added latency is acceptable.

## Failure modes and correction

1. **`fsync = off` left in production by mistake.** Symptom: configuration file says `off`; crash recovery loses data the application believed was committed. Correction: enforce `fsync = on` in production configuration; raise a high-severity alert on any deviation.
2. **`synchronous_commit = off` set globally and forgotten.** Symptom: a code path that needed durability loses transactions on crash. Correction: set `synchronous_commit = off` per transaction at the application boundary, not as a session default; review the policy.
3. **`full_page_writes = off` left in production.** Symptom: after a crash, the database fails to recover; corruption is unrecoverable. Correction: re-enable `full_page_writes = on`; if performance is the concern, raise `checkpoint_timeout` and tune `shared_buffers` instead.
4. **Replica falls behind synchronous commit.** Symptom: commit latency rises as the primary waits for the replica. Correction: investigate the replica's bottleneck; consider `synchronous_standby_names = 'ANY 1 (...)'` to allow failover to another replica; or relax to `synchronous_commit = remote_write`.
5. **`wal_level = minimal` blocks replication setup.** Symptom: attempting to enable replication fails; the replica cannot start streaming. Correction: raise `wal_level` to `replica` (or `logical`); restart the primary; expect a brief restart.
6. **WAL volume fills the disk.** Symptom: archiving or replication falls behind; the disk fills. Correction: tune `archive_timeout`, raise `max_wal_size`, or move to a replication topology that streams WAL faster than it is generated.

## Limitations

1. **`synchronous_commit = off` does not affect crash recovery from a torn write**; `full_page_writes` is the lever for that, and the rule is to leave it on.
2. **`fsync = off` makes the database unsafe for any production use**; the only legitimate use is benchmarks and short-lived development databases.
3. **`commit_delay` only helps under sufficient concurrency**; a workload with one writer per second sees no batching benefit.
4. **Durability does not equal recovery.** A committed transaction may still be lost in a multi-host failure (primary and replica both lost); backups and PITR are the recovery story for that case.
5. **WAL configuration interacts with replication and backup topology.** A change to `wal_level` or `archive_mode` must be coordinated with the surrounding system; an isolated change may break replication or backups.

## Canonical sources

- PostgreSQL Documentation, WAL Configuration: https://www.postgresql.org/docs/current/wal-configuration.html
- PostgreSQL Documentation, Runtime Config — Write-Ahead Log: https://www.postgresql.org/docs/current/runtime-config-wal.html
- PostgreSQL Documentation, Reliability and the Write-Ahead Log: https://www.postgresql.org/docs/current/wal.html