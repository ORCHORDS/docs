# zero-downtime-migrations

**Issue:** Applying schema changes without downtime on live production databases
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A simple `ALTER TABLE ADD COLUMN NOT NULL` on a large table requires a full table lock and blocks traffic.

## Pattern / Solution
```sql
-- Step 1: Add nullable column (instant, no lock)
ALTER TABLE orders ADD COLUMN notes TEXT;

-- Step 2: Backfill in batches (offline, no lock)
UPDATE orders SET notes = '' '' WHERE notes IS NULL AND id BETWEEN $1 AND $2;

-- Step 3: Add NOT NULL constraint with a default (PG11+: instant)
ALTER TABLE orders ALTER COLUMN notes SET NOT NULL;
ALTER TABLE orders ALTER COLUMN notes SET DEFAULT '''';

-- Adding indexes concurrently (no write lock)
CREATE INDEX CONCURRENTLY idx_orders_notes ON orders (notes);
```

## Gotchas
- `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block
- Adding a NOT NULL column with a volatile DEFAULT still rewrites the table in PG < 11
- Dropping a column is instant (just marks it invisible) but reclaims space only after VACUUM

## Related
- `schema-migrations-patterns.md`
- `backward-compatible-migrations.md`
