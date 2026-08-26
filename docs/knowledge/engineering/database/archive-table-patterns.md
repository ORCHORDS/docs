# archive-table-patterns

**Issue:** Operational tables grow unbounded with historical data, slowing queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
orders table has 5 years of data but 95% of queries only touch the last 90 days. Autovacuum and queries scan old dead tuples constantly.

## Pattern / Solution
Move old rows to archive table with identical schema. Run nightly archival job: INSERT INTO orders_archive SELECT * FROM orders WHERE created_at < NOW() - INTERVAL '90 days'; DELETE FROM orders WHERE created_at < NOW() - INTERVAL '90 days'; Use partitioning for cleaner detach-and-archive pattern.

## Gotchas
- Archival DELETE must run in small batches to avoid long-running transactions
- FK references to archived rows break if archive is in different table
- Verify archive completeness before DELETE; wrap in transaction with row count check

## Related
- data-retention-deletion
- table-partitioning-postgres
- batch-update-patterns
