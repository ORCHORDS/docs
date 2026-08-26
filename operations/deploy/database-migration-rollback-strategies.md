# Database Migration Rollback Strategies — Expand-Contract, Ghost Tables, and Blue-Green

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team deploys a migration that renames `customer_name` to
`customer_full_name` in the orders table. The deploy succeeds, but
a running pod still references the old column name — 500 errors
spike immediately. Rolling back the application code does not fix
the database. A second migration to undo the rename fails because
a concurrent query holds a lock on the table. The team resorts to
a 20-minute maintenance window at 2 AM to fix what should have been
a zero-downtime change.

## Context

Database migrations fail safely only when they are backward-compatible
with the currently running application code. The expand-contract
pattern (also called parallel change) handles roughly 80% of migration
scenarios by splitting changes into three independently deployable
and rollable phases. For MySQL, ghost table tools (gh-ost, pt-online-
schema-change) enable zero-downtime DDL on large tables. Blue-green
database deployments handle complex restructures but require 2x
storage during synchronization. The dominant philosophy in 2026 is
"roll forward" — instead of undo migrations, write a new forward
migration to fix the problem, keeping migration history as a strictly
forward-moving timeline.

## Expand-contract pattern

```
Phase 1 — Expand: Add new schema elements, keep old ones
  ALTER TABLE orders ADD COLUMN customer_email VARCHAR(255);
  → Rollback: DROP the new column

Phase 2 — Migrate: Backfill data, dual-write to both columns
  UPDATE orders SET customer_email = customers.email
    FROM customers WHERE orders.customer_id = customers.id
    AND orders.id BETWEEN :start AND :end;
  → Rollback: Stop dual-write, revert to old column

Phase 3 — Contract: Drop old column after ALL consumers migrated
  ALTER TABLE orders DROP COLUMN customer_name;
  → Irreversible by design — wait until all consumers have migrated

Deployment flow:
  1. Deploy expand migration
  2. Gate new code path behind a feature flag
  3. Enable for 1% → 5% → 25% → 100%
  4. Verify metrics for 1-2 weeks
  5. Deploy contract migration
```

## Ghost tables (MySQL zero-downtime DDL)

```
gh-ost (GitHub Online Schema Transmogrifier):
  → Creates ghost table with desired schema
  → Copies existing rows in background
  → Listens to binlog to replicate ongoing changes (no triggers)
  → Atomic cutover via table name swap
  → Throttles on replica lag; checks long-running transactions
  → Cutover lock window: sub-second

pt-online-schema-change (Percona):
  → Creates copy with new schema, copies in chunks
  → Uses triggers to mirror inserts/updates/deletes
  → Explicit chunk sizing, throttle, pause/resume
  → Higher overhead than gh-ost due to triggers

PostgreSQL equivalents: pgroll, pg-osc

Rollback: rename tables back to original names before significant
data divergence occurs. A 2-5 minute observation window catches
anomalies before committing to cutover.

Preflight checklist:
  → Verify disk headroom (1x table size + overhead for ghost table)
  → Scan for long-running transactions holding locks
  → Confirm replica health
  → Validate trigger/FK compatibility with swap
  → Set connection and lock timeouts
```

## Blue-green database deployments

```sql
-- Schema-level blue-green in PostgreSQL
CREATE SCHEMA green;
CREATE TABLE green.orders (
  id BIGINT PRIMARY KEY,
  customer_email TEXT NOT NULL,
  amount NUMERIC(12,2),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Synchronization trigger for dual-write
CREATE OR REPLACE FUNCTION sync_orders() RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO green.orders (id, customer_email, amount, created_at)
  VALUES (NEW.id, NEW.customer_email, NEW.amount, NEW.created_at)
  ON CONFLICT (id) DO UPDATE SET
    customer_email = EXCLUDED.customer_email,
    amount = EXCLUDED.amount;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

-- Atomic cutover via view switching to green schema
```

```
Expand/Contract vs Blue-Green:

  Factor           Expand/Contract      Blue-Green
  ─────────────────────────────────────────────────
  Complexity       Low-medium           High
  Storage          Minimal              2x during sync
  Rollback         Drop new column      Switch view back
  Best for         Additive changes     Type changes, restructures
  Default choice   Yes (80% of cases)   Reserve for major changes
```

## Flyway vs Liquibase rollback

```
                  Flyway               Liquibase
──────────────────────────────────────────────────────────
Rollback:         Enterprise only       Starter tier and above
Philosophy:       Explicit scripts      Auto-rollback where feasible
Undo mechanism:   flyway undo           rollback-one-changeset
Free tier:        No rollback           Limited rollback

"Roll forward" pattern (dominant in 2026):
  Instead of undo migrations, write a new forward migration
  to fix the problem. Migration history stays forward-only.
```

## Separating schema and data migrations

```
Treat as distinct concerns:

Schema changes (DDL) — expand phase:
  ALTER TABLE, CREATE INDEX, ADD COLUMN
  Fast, metadata-only where possible

Data migrations (DML) — migrate phase:
  UPDATE, INSERT, backfill operations
  Slow, resource-intensive, run in batches

Backfill approaches:
  1. Online batching: UPDATE 1000 rows per iteration with delays
  2. Change Data Capture: near-real-time with historical backfill
  3. Background job queues: distribute across parallel workers

Separation enables independent rollback:
  → Undo data changes without reverting schema
  → Revert schema without losing backfilled data
```

## Anti-patterns

- **Big-bang migrations** — changing schema and code in one deploy
  loses the ability to independently roll back. Always deploy
  migrations separately from application code.
- **Dropping columns before all consumers migrate** — any running
  pod still referencing the old column gets runtime errors. Wait
  until every consumer has been updated and verified.
- **Skipping advisory locks** — concurrent CI runners can corrupt
  migration state. Use `pg_advisory_lock` or equivalent to serialize
  migration execution.
- **Running `CREATE INDEX CONCURRENTLY` inside a transaction** — it
  will fail or block indefinitely. Use `executeInTransaction=false`
  in Flyway or `runInTransaction="false"` in Liquibase.

## Gotchas

- **MySQL INSTANT DDL** — MySQL 8 supports `INSTANT` for some operations
  (adding nullable columns). Check if your change qualifies before
  reaching for ghost tables. Prefer native DDL when available.
- **Ghost table disk requirements** — you need approximately 1x the
  table size in free disk space plus overhead. Check before starting.
- **Metadata locks in MySQL** — can cause unexpected delays during
  the ghost table swap window. Identify and terminate long-running
  queries pre-cutover.
- **Backward-compatible rename** — renaming a column requires adding
  the new column, dual-writing, backfilling, updating all consumers,
  then dropping the old column. There is no shortcut.
- **TOAST rewriting in PostgreSQL** — changing a column type
  (e.g., VARCHAR to TEXT) can trigger a full table rewrite on large
  tables even though the logical change is trivial.

## Verification

- Migrations are backward-compatible with currently deployed code.
- Expand-contract pattern used for schema changes affecting live traffic.
- Ghost table tools used for large MySQL table DDL changes.
- Data and schema migrations are separate, independently rollable.
- Advisory locks prevent concurrent migration execution.
- Disk headroom verified before ghost table operations.

## Related

- `documentation/categories/database/zero-downtime-schema-migrations.md`
- `documentation/categories/deploy/progressive-canary-deployment-rollback.md`
- `documentation/categories/deploy/feature-flag-lifecycle-management.md`

## Source URLs (verified 2026-08-16)

- Database Migrations Without Drama: Expand/Contract in Practice — https://blogs.reliablepenguin.com/2025/11/16/database-migrations-without-drama-expand-contract-in-practice
- Zero-Downtime MySQL Schema Migrations with gh-ost and pt-osc — https://www.dchost.com/blog/en/zero-downtime-mysql-schema-migrations-the-blue-green-dance-with-gh-ost-and-pt-online-schema-change/
- Flyway vs Liquibase: The Definitive Comparison in 2026 — https://www.bytebase.com/blog/flyway-vs-liquibase/
- Database Migration Strategies for Banks: Zero-Downtime at Scale — https://cloudlogic.dev/2025/12/15/database-migration-strategies-for-banks-zero-downtime-schema-changes-at-scale/
