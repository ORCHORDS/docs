# migration-linting-ci

**Issue:** Schema migrations are the highest-leverage and highest-risk SQL a team writes: a single `ADD COLUMN ... NOT NULL` without a default, a non-concurrent `CREATE INDEX`, or a rewriting `ALTER TABLE ... TYPE` can lock a hot table for minutes and take production down. Reviews catch some of this, but reviewers tire, contractors don't know which tables are 200 GB, and 3 a.m. hotfixes skip review entirely. Migration linting applies static analysis to migration files in CI so dangerous-but-plausible statements are rejected mechanically, before they reach a production database, with the same philosophy ESLint brought to JavaScript.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What migration linters actually check

1. **Missing `CONCURRENTLY` on index operations.** `CREATE INDEX` and `DROP INDEX` take locks that block writes on the target table; linters such as Squawk flag any index DDL without `CONCURRENTLY` (or the `IF NOT EXISTS` + `CREATE INDEX CONCURRENTLY` dance) because this is the single most common cause of outage-by-migration.
2. **`ADD COLUMN` with a volatile or constant `DEFAULT`.** Before Postgres 11 a non-null column with a default rewrote the whole table; since PG 11 a constant default is metadata-only, but a volatile default (`now()`, `gen_random_uuid()`) still rewrites every row. Linters force the safe sequence: add nullable, backfill in batches, then add `NOT NULL` via `CHECK ... NOT VALID` + `VALIDATE CONSTRAINT`.
3. **Table-rewriting type changes.** `ALTER TABLE ... ALTER COLUMN ... TYPE` on a populated column rewrites the table under an exclusive lock; the linter flags it and the team must justify or split it (new column, dual-write, backfill, switch).
4. **Operations that can deadlock when mixed.** Adding multiple constraints or altering the same table twice in one transaction can deadlock against concurrent traffic; Squawk's `adding-required-field`, `constraint-missing-not-valid`, and `invalid-mult-statement-transaction` rules encode the known footguns.
5. **Renaming and dropping without a deprecation stage.** Dropping a column, constraint, or table that application code still references fails at runtime, not deploy time; linters mark destructive DDL for a two-release cadence (stop writing, then drop later).

## Tooling landscape as of 2025-2026

1. **Squawk is the default open-source choice.** Written in Rust (installable via npm or Homebrew), it parses Postgres-flavored SQL migrations and ships an LSP so editors underline unsafe statements as you type; it runs as a CLI in CI with `squawk migrations/*.sql` and exits non-zero on error. Its rule list is transparent and each error message explains the lock consequence.
2. **Atlas moved its Postgres lint rules behind a paywall.** Since Atlas v0.38 (October 2025), the PostgreSQL-specific lint rules are paid-only, which pushed teams back to Squawk or to pinning older versions; budget for this if Atlas is your migration runner, or keep the linter decoupled from the runner so the two decisions stay independent.
3. **Size-aware linters are the new frontier.** Tools like safe-migrate (a Rust linter that appeared in late 2025) connect to the database and check actual table sizes before flagging: `CREATE INDEX` on a 500-row lookup table is fine, the same statement on 200 GB is not. Static-only linters cannot make this distinction, so expect false positives on small tables and plan an inline-suppression mechanism.
4. **Live-schema linters complement file linters.** pg-language-server and similar tools analyze the running database (missing indexes on FKs, unused indexes, security config), which catches drift that file-based linting cannot; run file linting at PR time and live linting on a schedule.

## Wiring the linter into CI

1. **Lint the migration directory in every PR.** A job that runs `squawk` (or equivalent) over `migrations/**/*.sql` and posts findings as review comments turns each warning into a teachable moment at the exact line; make the job required before merge.
2. **Enforce one-migration-per-file, forward-only naming.** Linting works best when files are small and ordered (timestamp or sequential prefixes); a linter cannot analyze a 900-line omnibus migration, and rollback sections inside the same file defeat forward-only discipline.
3. **Add an explicit escape hatch.** Sometimes a lock is genuinely acceptable (a tiny table, a maintenance window). Support a per-file or per-line `squawk: disable` directive with a required justification comment, so the linter stays strict without becoming an obstacle people route around.
4. **Generate the migration, then lint the output.** ORMs that auto-diff schemas (Prisma, Drizzle Kit, Atlas) can emit unsafe SQL too; pipe the generated file through the linter before it is committed rather than trusting the generator.
5. **Pair linting with a dry-run against a production-shaped database.** Run migrations on a staging copy (or a snapshot/branch of production) in CI on every PR; linting predicts lock risk statically, while the dry run surfaces errors linting can't (dependency ordering, extension availability, statement timeouts).

## Limits of linting and what still needs humans

1. **Linters don't know your traffic.** A lock for 4 seconds is invisible at midnight and fatal at peak; combine lint rules with deployment policy (migrate off-peak, use `lock_timeout` in migration sessions) rather than treating a green lint as proof of safety.
2. **They only see the SQL text.** Data backfills, long-running migration transactions, and application behavior during the deploy window (dual-read, cache invalidation) are outside the linter's view and still need review checklists.
3. **Version-specific rules drift.** Postgres keeps changing what is safe (PG 11 constant defaults, PG 12 `REINDEX CONCURRENTLY`, PG 17 `MERGE` improvements); keep the linter updated and re-read its changelog, because a rule silenced years ago may now be wrong in your favor or against it.
