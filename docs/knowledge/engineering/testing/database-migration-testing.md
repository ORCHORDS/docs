# database-migration-testing

**Issue:** Schema migrations are deployed into databases that cannot be rolled back the way code can: an ALTER that drops a column destroys data the still-running old version of the application expects, and a long-running migration can lock a hot table while traffic piles up. The blast radius of a bad migration exceeds almost any other change, yet migrations are often tested only by whether they apply cleanly to a fresh, empty database, which is the easiest possible case. Migration testing means applying changes to production-like data, proving backward compatibility with both old and new application versions, rehearsing rollback, and budgeting for locks and duration.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Expand-and-contract as the testable pattern

1. **Split breaking changes into expand, migrate, contract phases.** Following the Parallel Change pattern (Fowler) and the expand-contract guidance from PlanetScale and Prisma: first add the new structure (expand), then backfill while writing to both structures (migrate), then remove the old structure (contract). Each phase is independently deployable and backward compatible with the previous one, which is exactly what makes it testable.
2. **Test each phase against both adjacent application versions.** During expand, the old application version must work against the new schema (its columns untouched); during contract, the new application must not reference the removed columns. CI jobs that run the app test suite against each migration boundary catch violations.
3. **Never contract in the same release that expands.** The contract step is only safe after every instance of the old application is gone; a test or checklist gate verifies the deployment order (migrate code fully rolled out, soak period elapsed) before the contract migration can run.
4. **Treat each phase as a rollback point.** Because every step is compatible with its predecessor, rollback means redeploying the previous application version, not un-running destructive DDL; the test plan should rehearse exactly that redeploy against the migrated schema.

## What migration tests must cover

1. **Apply against a production-shaped snapshot.** Migrating an empty database proves syntax, not behavior. Restore an anonymized or synthetic production snapshot (full size or statistically sampled volume) and apply the migration; nulls in unexpected places, duplicate keys blocking unique constraints, and oversized varchars only appear with real data shapes.
2. **Verify data integrity after backfill.** For migrations that copy or transform data, assert row counts, checksums, and spot-check invariants (every order has a matching ledger entry) after the backfill, not just the absence of errors.
3. **Test old application version against new schema.** The core backward-compatibility suite: run the previous release's integration tests against the expanded schema. Failures here mean the migration breaks the running fleet before the new code deploys.
4. **Rehearse the rollback path.** Where the tool supports down migrations, apply up then down and assert schema and data equivalence; where it does not (the common case for destructive changes), the rollback rehearsal is restoring the pre-migration snapshot and redeploying the old version, which must also be automated.
5. **Measure lock behavior and duration.** Assert migration wall-clock time and lock scope against a budget using a data-volume copy: an index build or column default that takes 40 minutes on production volume is a deploy blocker the empty-database test will never reveal.

## CI and environment discipline

1. **A dedicated migration job on every schema change.** The job restores a snapshot, applies migrations from the current baseline, runs smoke queries, and exercises rollback if applicable, separate from ordinary integration tests so failures are attributed correctly.
2. **Drift detection between schema and reality.** Continuously diff the migration-tool schema state against the actual environment; drift (a hotfix applied by hand, an environment created outside the pipeline) makes later migrations fail in surprising ways, so surface drift as a visible check.
3. **Version-lock the migration runner.** Test with the same migration tool version in CI and production; runner upgrades change quoting, transactionality, and lock strategies and deserve their own tested rollout.
4. **Isolate destructive DDL in its own reviewable change.** Drop, rename, and type-change statements get their own migration file and PR with the compatibility analysis attached, making the dangerous diff impossible to miss in review.

## Operational rehearsal

1. **Shadow-run on a replica before production.** Applying the migration to a restored replica or a staging database of production volume, while replaying a traffic sample, validates both duration and query behavior under realistic conditions.
2. **Verify the application under the migration window.** Run the integration suite while the migration executes against the shared staging database; lock waits and timeouts experienced by the app during DDL are the failure mode pure schema tests miss.
3. **Monitor the post-deploy contract window.** After each phase lands, watch error rates and slow-query logs for the old-versus-new schema compatibility assumptions; feed any violation back into the suite as a new boundary test before the next migration ships.
4. **Keep migration history immutable and replayable from zero.** A fresh environment must be buildable by replaying the entire history; a test that periodically builds the schema from scratch on a clean database catches hand-edited state and non-idempotent scripts.
