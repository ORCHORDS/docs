# zero-downtime-schema-migrations

**Issue:** A deploy that changes both code and database schema in one step works at demo scale and falls over in production: `ALTER TABLE` takes a lock that blocks writes for minutes, the old and new application versions need to agree on the schema during rollout, and a failed migration cannot be rolled back because the previous code no longer matches the migrated data. The 2025-26 standard answer is the expand-contract pattern (also written expand-migrate-contract) — split every breaking schema change into additive, migration, and cleanup phases, each independently deployable and reversible. Only mentioned in passing inside `cell-based-architecture.md` and `active-active-vs-active-passive.md`; this article gives it the full treatment.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why naive migrations break production

1. **Metadata locks block everything.** Even "fast" DDL statements queue behind long-running queries while holding metadata locks that freeze all subsequent access to the table; on a busy Postgres or MySQL table this reads as a full outage.
2. **Code and schema must flip atomically.** If version N expects the new column and version N-1 does not, a rolling deploy has a window where both run against one schema; only strictly additive changes make that window safe.
3. **Rollback asymmetry.** Adding a column is instant; dropping or un-baking a bad data migration is not — deleting the wrong rows during a rollback is permanent. Migration plans must be reversible by design, not by hope.
4. **Destructive DDL is where outages live.** Renames, type changes, and column drops are exactly the operations that take locks, rewrite tables, and cannot be undone; the whole pattern exists to push these into the safest possible position.

## The expand-contract phases

1. **Expand (additive only).** Deploy a migration that only adds: new nullable columns, new tables, new indexes created concurrently (`CREATE INDEX CONCURRENTLY` in Postgres, `ALGORITHM=INPLACE` where MySQL allows). Old code ignores the new structures, so the deploy is a no-op for behavior.
2. **Dual-write and backfill.** Deploy code that writes both old and new representations, then backfill historical rows in batches small enough to avoid replica lag and lock churn; chunked `UPDATE ... WHERE id BETWEEN` loops or a tool like pgroll keep the write path responsive.
3. **Switch reads.** Once dual-written data is verified equal (row counts, checksums, sampled comparisons), flip reads to the new representation behind a flag; this is the commit point and it is instant to flip back.
4. **Contract (cleanup, later).** Only after the old code version is fully retired — not merely after the deploy — drop old columns and constraints; many teams run contract migrations on a schedule weeks later, and that gap is deliberate insurance.

## Rules that keep it safe

1. **One direction per deploy.** Each migration file does expand OR migrate OR contract, never several; mixed migrations cannot be individually verified or rolled back.
2. **Every phase independently reversible.** Expands reverse by dropping what was added; backfills reverse from the still-present old column; contracts are the only irreversible step and happen last, after everyone agrees the old data is dead.
3. **Backfill in the background, never in the deploy.** A migration that walks a billion rows synchronously is an outage with a progress bar; backfill is a job with monitoring, a kill switch, and batch pacing tuned to replica lag.
4. **Verify with data, not vibes.** Before switching reads, compare row counts and per-row checksums between old and new representations on production data; sampled equality is the minimum bar for "the backfill is done."
5. **Respect online-DDL limits per engine.** Postgres additions of columns with defaults rewrite catalog only since PG 11, but type changes and unique-constraint builds still lock; MySQL online DDL has an allowlist of in-place operations and everything else needs gh-ost or pt-online-schema-change. Check the specific operation against the specific version before trusting "it's online."

## Tooling and coordination

1. **Versioned migration tools.** Flyway/Liquibase/golang-migrate give ordering and audit but know nothing about zero-downtime; you encode the phases yourself as separate, ordered migrations with the deploy choreography documented in the runbook.
2. **pgroll-style dual-version schemas.** Tools like pgroll (Xata) automate expand-contract by exposing per-role versioned views of the table so old and new code genuinely see their own schema during the transition window — useful enough that the manual choreography is worth automating once you exceed a handful of breaking changes a quarter.
3. **Combine with feature flags.** The read-switch step is a feature flag flip, which buys instant rollback of the logic change independent of the data migration state; see `feature-flag-architecture.md`.
4. **CI rehearsal.** Run the full phase sequence against a production-sized copy on every schema PR; a migration that has not been timed at production scale has not been validated.

## Failure modes

1. **Skipping contract forever.** Dual-write tax compounds — every table carries ghost columns that new engineers must reverse-engineer; schedule contract cleanup as real work or the schema ossifies.
2. **Backfill starving replication.** Batches sized without watching replica lag cause failover candidates to fall behind and read replicas to serve stale data for minutes; pace on observed lag, not on fixed sleep.
3. **Unique violations surfacing mid-backfill.** Backfilling a new unique column can collide on real dirty data; run a duplicate-detection query before the migration, not during it.
4. **Two-phase deploys nobody rehearsed.** The pattern's cost is operational choreography; if the deploy runbook does not say which code version tolerates which schema state, the next on-call will improvise incorrectly at 3am.

## Related articles in this knowledge base

1. **`backward-compatibility-design.md` and `api-versioning-strategy.md`.** The same additive-then-deprecate discipline applied to API contracts.
2. **`blue-green-architecture.md` and `canary-deployment-architecture.md`.** Deployment topologies that require schema-code independence to work at all.
3. **`feature-flag-architecture.md`.** The read-switch mechanism that makes phase 3 reversible.
4. **`strangler-fig-migration.md`.** The same expand/swing/contract idea applied to whole systems rather than single tables.
