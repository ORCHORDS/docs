# database-indexing-strategy

**Issue:** Ad-hoc index creation without a strategy leads to too many indexes slowing writes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Table has 20+ indexes added one-by-one for each slow query. INSERT performance degraded 5x. Indexes duplicating each other or never used.

## Pattern / Solution
Audit indexes with pg_stat_user_indexes: drop unused (idx_scan = 0 after weeks of traffic). Identify duplicate indexes covering same prefix. Create composite indexes rather than multiple single-column indexes for multi-predicate queries. Follow ESR rule: equality, sort, range. Index only columns with high selectivity.

## Gotchas
- Every index adds overhead to INSERT/UPDATE/DELETE proportional to table size
- Partial indexes are more efficient than full indexes for sparse conditions
- Unused indexes still consume storage and slow vacuum -- remove them aggressively

## Related
- composite-index-design
- partial-indexes
- index-selectivity
