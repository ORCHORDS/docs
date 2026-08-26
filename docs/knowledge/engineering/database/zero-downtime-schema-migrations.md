# Zero-Downtime Schema Migrations — Expand-Contract Pattern

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your database migrations cause downtime — `ALTER TABLE` locks tables for
minutes, column renames break the running application, and rollbacks
require restoring from backups. Deploys are coupled to migrations:
the application and schema must change at the exact same moment, creating
a high-risk deployment window. Large table migrations (adding indexes,
changing column types) on multi-million-row tables block reads and
writes, causing cascading failures.

## Context

Zero-downtime schema migrations decouple application deployments from
schema changes by ensuring every migration is backward-compatible with
the currently running code. The expand-contract pattern achieves this
in three phases: expand (add new structures without removing old ones),
migrate (synchronize old and new while applications transition), and
contract (remove deprecated structures after all traffic uses the new
schema). In 2026, large engineering organizations (Stripe, Shopify,
GitHub) treat migrations as multi-step workflows rather than single DDL
operations, sequencing changes across multiple deploy cycles with
automated validation at each step.

## The expand-contract pattern

```
Phase 1: EXPAND (backward-compatible addition)
  Deploy migration → Add new column/table
  Application v1 still works (ignores new column)

Phase 2: MIGRATE (dual-write + backfill)
  Deploy application v2 → Writes to both old and new
  Run backfill job → Populate new column from old data
  Verify → Ensure data consistency

Phase 3: CONTRACT (remove old structures)
  Deploy application v3 → Reads/writes only new column
  Deploy migration → Drop old column
```

## Common migration patterns

### Rename a column

```sql
-- Step 1: Add new column (expand)
ALTER TABLE orders ADD COLUMN total_amount DECIMAL(10,2);

-- Step 2: Backfill (migrate)
UPDATE orders SET total_amount = amount WHERE total_amount IS NULL;
-- For large tables, batch:
-- UPDATE orders SET total_amount = amount
--   WHERE total_amount IS NULL AND id BETWEEN ? AND ? LIMIT 10000;

-- Step 3: Deploy app that writes to both columns
-- Step 4: Deploy app that reads from new column only
-- Step 5: Drop old column (contract)
ALTER TABLE orders DROP COLUMN amount;
```

### Add a NOT NULL column

```sql
-- WRONG: locks table, breaks running app
ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'member';

-- RIGHT: three-step expand-contract
-- Step 1: Add nullable column
ALTER TABLE users ADD COLUMN role VARCHAR(50);

-- Step 2: Backfill with default value (batched)
UPDATE users SET role = 'member' WHERE role IS NULL;

-- Step 3: Add NOT NULL constraint (after backfill complete)
ALTER TABLE users ALTER COLUMN role SET NOT NULL;
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'member';
```

### Add an index without locking

```sql
-- PostgreSQL: CONCURRENTLY prevents table lock
CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id);

-- MySQL: use pt-online-schema-change or gh-ost
-- pt-online-schema-change creates a shadow table, copies data,
-- and swaps atomically
pt-online-schema-change \
  --alter "ADD INDEX idx_user_id (user_id)" \
  D=mydb,t=orders \
  --execute
```

### Change a column type

```sql
-- Step 1: Add new column with target type (expand)
ALTER TABLE events ADD COLUMN payload_jsonb JSONB;

-- Step 2: Backfill (migrate)
UPDATE events SET payload_jsonb = payload::jsonb
  WHERE payload_jsonb IS NULL;

-- Step 3: Deploy app writing to both columns
-- Step 4: Deploy app reading from new column
-- Step 5: Drop old column (contract)
ALTER TABLE events DROP COLUMN payload;
ALTER TABLE events RENAME COLUMN payload_jsonb TO payload;
```

## Migration tooling

| Tool | Database | Approach |
|---|---|---|
| **gh-ost** (GitHub) | MySQL | Triggerless online schema change |
| **pt-online-schema-change** | MySQL | Trigger-based shadow table |
| **pgroll** | PostgreSQL | Versioned, reversible migrations |
| **reshape** | PostgreSQL | Zero-downtime, expand-contract |
| **Flyway** | All major | Version-controlled SQL migrations |
| **Prisma Migrate** | All major | Schema-first, diffable migrations |
| **Atlas** | All major | Declarative + versioned migrations |

## Backfill strategies

```
Small tables (< 100K rows):
  → Single UPDATE statement
  → Lock duration: seconds

Medium tables (100K - 10M rows):
  → Batched UPDATE with LIMIT and WHERE clause
  → Batch size: 1,000-10,000 rows
  → Add sleep between batches to reduce lock contention

Large tables (> 10M rows):
  → Background worker job (Sidekiq, Celery)
  → Track progress in a separate table
  → Throttle based on database load metrics
  → Estimated time: hours to days
```

## Anti-patterns

- **Big bang migrations** — running `ALTER TABLE ... MODIFY COLUMN`
  on a production table with millions of rows during business hours.
  This acquires a table lock that blocks all reads and writes until
  complete. Use online schema change tools.
- **Coupling app deploy to migration** — requiring the application
  and schema to change simultaneously. If the deploy fails mid-way,
  the schema and code are inconsistent. Always make migrations
  backward-compatible with the running code.
- **No rollback plan** — every migration must have a documented
  rollback. For expand-contract, rollback is inherent: the old
  structures are still present during the expand and migrate phases.
- **Unthrottled backfills** — running a bulk UPDATE without batching
  or throttling saturates the database, degrading performance for
  all queries. Batch writes and monitor replication lag.

## Gotchas

- **Replication lag** — large backfill jobs can cause replication lag
  on read replicas. Monitor replica lag and throttle the backfill
  rate when lag exceeds acceptable thresholds (typically 5-10 seconds).
- **Foreign key constraints** — adding or modifying foreign keys can
  lock both the source and target tables. In PostgreSQL, use
  `NOT VALID` to add the constraint without scanning existing rows,
  then `VALIDATE CONSTRAINT` separately.
- **Enum type changes** — in PostgreSQL, `ALTER TYPE ... ADD VALUE`
  cannot be run inside a transaction. Plan enum additions as separate
  migration steps.
- **ORM migration ordering** — ORMs (Django, Rails, Prisma) generate
  migrations from model diffs. Auto-generated migrations may not
  follow expand-contract. Review generated SQL and split into
  multiple migrations when needed.

## Verification

- All production migrations follow the expand-contract pattern.
- No migration acquires a table lock for more than 1 second.
- Backfill jobs are batched and throttled based on database load.
- Every migration has a documented rollback procedure.
- Replication lag is monitored during migration execution.
- Migrations are tested against a production-size dataset in staging.

## Related

- `documentation/docs/policies/database/connection-pooling-pgbouncer.md`
- `documentation/docs/policies/database/postgresql-row-level-security-multi-tenant.md`
- `documentation/docs/policies/deploy/progressive-canary-deployment-rollback.md`

## Source URLs (verified 2026-08-16)

- Database Migrations: Zero-Downtime Schema Changes (2026) — https://dev.to/young_gao/database-migrations-in-production-zero-downtime-schema-changes-5fng
- Zero-Downtime Migrations: Expand/Contract, Triggers, Shadow Reads — https://thebackenddevelopers.substack.com/p/zero-downtime-database-migrations
- Zero-Downtime Database Migrations: Safe Schema Changes — https://www.harness.io/blog/zero-downtime-database-migrations-safe-schema-changes
- Database Schema Migrations with Zero Downtime — https://systemdr.systemdrd.com/p/database-schema-migrations-with-zero
