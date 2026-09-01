# Idempotent Migration Zero Downtime Prisma

## Scope

This article covers writing idempotent, zero-downtime database migrations with Prisma Migrate: the discipline required to evolve a schema while the application runs against the old schema in production, the migration operations that are safe under load, the operations that lock the table or break the application, and the workflow that lets a small team ship schema changes without a maintenance window. It addresses Prisma Migrate's `prisma migrate deploy`, shadow database, and migration history, plus the additional SQL that often has to be written outside Prisma's declarative migration language. It excludes raw `prisma db push` workflows used only in development, data backfill orchestration beyond the schema change, and application-level dual-write strategies.

## Workflow or implementation guidance

1. **Treat migrations as a multi-step deploy, not a single SQL statement.** A safe schema change is a sequence: expand (add new shape, write to both old and new), migrate data (backfill if needed), contract (remove old shape). Prisma's declarative diff generates one `migration.sql` file per change; a zero-downtime approach often splits a single conceptual change into multiple `prisma migrate dev` + `prisma migrate deploy` invocations so each step is safe to apply live.
2. **Prefer expanding-with-default before adding constraints.** Adding a `NOT NULL` column is a long lock if Postgres validates existing rows; adding a nullable column then backfilling then adding `NOT NULL` is the conventional expand-then-contract. Prisma will not refuse a one-step dangerous migration, so the team's review must catch this.
3. **Use Prisma's `migrate dev` workflow for local development only.** It requires a shadow database and resets state; running it against production would lose data. Production migrations use `prisma migrate deploy`, which applies the migration history in order without reset or shadow creation.
4. **Write idempotent migrations by hand when Prisma's diff is not.** Prisma's generated SQL is generally safe under rerun semantics for additive changes, but destructive changes (drop column, alter type) often need a custom SQL file authored to be re-runnable. Use `IF EXISTS` / `IF NOT EXISTS` patterns, and write `CREATE INDEX CONCURRENTLY` (which Prisma does not generate by default for Postgres) manually inside the migration file.
5. **Avoid long locks.** Postgres takes an `ACCESS EXCLUSIVE` lock on many DDL operations, blocking reads and writes on the table. The migrations to avoid live are: `ALTER TABLE ... ALTER COLUMN TYPE`, `ADD CONSTRAINT ... CHECK ... NOT VALID` is safe; `ADD CONSTRAINT ... CHECK` without `NOT VALID` is not; `CREATE INDEX` blocks writes, `CREATE INDEX CONCURRENTLY` does not. Prisma will emit the blocking form unless the team intervenes.
6. **Separate the migration into expand/contract files when needed.** A single migration file can combine safe operations; for dangerous operations, split into two migrations: the first applies `ADD COLUMN ... NULL` and is safe to deploy, the second adds `NOT NULL` after the application's deploy guarantees the column is populated. Prisma's history will apply both in order.
7. **Backfill in batches, not in one statement.** A `UPDATE table SET new_col = compute(old_col)` on a large table holds row locks and generates replication lag. Break the backfill into batches of a few thousand rows, run it between deploys, and monitor replication lag. The backfill SQL goes outside Prisma's generated migration because Prisma Migrate does not natively orchestrate batching.
8. **Use the migration lock to prevent concurrent deploys.** `prisma migrate deploy` acquires an advisory lock via the `_prisma_migrations` table; two deploys against the same database at the same time will queue rather than race. The lock is database-scoped; deployments targeting different databases (for example, a primary and its replica) are not coordinated.
9. **Test migrations against a snapshot of production-sized data.** Migrations that work on a development database with 1000 rows may take a lock that a million-row production table cannot tolerate. A staging environment with realistic volume is the only place to verify lock duration and replication lag.
10. **Keep the migration history immutable once deployed.** Editing a deployed migration file causes the next `prisma migrate dev` to drift, and the next deploy to fail a checksum check. If a migration must be corrected, add a new migration; never edit history.

## Controls

1. **Migration review checklist.** Each PR with a schema change is checked against the expand/contract discipline, lock duration on production-sized data, and the presence of `CONCURRENTLY` for index work.
2. **Pre-deploy lock check.** A staging run that times `ALTER TABLE ... LOCK` waits and rejects any migration whose lock would block traffic beyond an SLA threshold.
3. **Migration checksum guard.** `prisma migrate deploy` enforces checksums; CI should fail any change that edits a previously-applied migration file.
4. **Concurrent-deploy guard.** Deploy pipeline refuses to apply migrations while another deploy is running; the migration lock is a backstop, not the primary guard.
5. **Backfill progress monitor.** A scheduled job that reports the percent of rows backfilled during a phased migration; alerts on stalled progress.
6. **Replica-lag awareness.** During backfill, the deploy dashboard shows replica lag; backfill is paused when lag exceeds a threshold.

## Validation evidence

1. **Expand/contract drill.** A staging run that applies the expand migration, deploys the new application, runs the backfill, and applies the contract migration, while a synthetic workload continues to read and write the table throughout. Assert no errors are observed and the table state at each stage is consistent with the application's expectations.
2. **Lock-duration measurement.** Capture `pg_locks` while the migration runs and report the longest-held `ACCESS EXCLUSIVE` lock; assert it stays below the application's tolerance.
3. **Replica-lag test.** Run the backfill against a primary with a hot-standby replica and assert the lag stays bounded; abort the backfill when lag exceeds the threshold.
4. **Idempotent rerun.** Apply the same migration twice (manually re-invoke the SQL) and assert the second invocation is a no-op, evidencing idempotency.
5. **Rollback rehearsal.** Plan and document the reverse migration for each forward migration; rehearse the rollback on staging to confirm it works.

## Failure modes and correction

1. **A migration that drops a column the application still expects.** Symptom: `prisma migrate deploy` succeeds; new application deploys fail at runtime with "column does not exist". Correction: enforce the expand/contract split — column drops are a contract step that happens *after* the application deploy, not before.
2. **Long lock blocks reads.** Symptom: API requests time out during deploy. Correction: convert the blocking DDL to its concurrent form where Postgres supports it (`CREATE INDEX CONCURRENTLY`, `ALTER TYPE ADD VALUE`, `VALIDATE CONSTRAINT` after `NOT VALID`); otherwise schedule the migration in a low-traffic window with a maintenance flag.
4. **Migration drift detected.** Symptom: deploy fails because the migration checksum does not match. Correction: investigate the source of the edit; restore the correct file or add a corrective migration; never deploy with `--skip-checksums` as a long-term fix.
5. **Backfill outruns the new column's NOT NULL constraint.** Symptom: rows created during the backfill fail the constraint, or the constraint is added before the backfill completes. Correction: sequence deploys: add column nullable → deploy application that populates it → run backfill to completion → add `NOT NULL`.
6. **Migration applied to the wrong database.** Symptom: a developer runs `prisma migrate deploy` against a non-target environment. Correction: environment-aware config (`DATABASE_URL` per environment), and CI/preview gates that confirm the target before applying.
7. **Concurrent index creation conflicts with an autovacuum.** Symptom: `CREATE INDEX CONCURRENTLY` fails because autovacuum started. Correction: re-run after autovacuum finishes; ensure `maintenance_work_mem` is sized so autovacuum is fast.

## Limitations

1. **Prisma Migrate does not generate every safe form of DDL.** Operations that need `CONCURRENTLY`, partial indexing, or complex triggers must be hand-written; Prisma's role is the model diff and history, not a full SQL safety net.
2. **Prisma Migrate does not orchestrate backfills.** Batched updates, lag awareness, and verification must be implemented outside the migration tool.
3. **Postgres-only considerations apply.** Other backends supported by Prisma (MySQL, SQLite, etc.) have different concurrency semantics and may not support `CONCURRENTLY` equivalents.
4. **Schema and code must deploy together in some cases.** Migrations that assume the new application code is running can break the old code; the deploy order (schema first vs code first) must be planned.
5. **A migration is not a substitute for a test suite.** Edge cases not represented by the migration (constraint failures, type coercions) need application tests to catch them before deploy.

## Canonical sources

- Prisma Documentation, Prisma Migrate: https://www.prisma.io/docs/orm/prisma-migrate
- Prisma Documentation, Understanding Prisma Migrate: https://www.prisma.io/docs/orm/prisma-migrate/understanding-prisma-migrate
- PostgreSQL Documentation, Concurrency Control (DDL locking): https://www.postgresql.org/docs/current/explicit-locking.html