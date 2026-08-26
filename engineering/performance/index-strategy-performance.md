# index-strategy-performance

**Issue:** Wrong index type or missing composite index causes slow queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Indexes speed up reads but slow down writes. Choosing the right index type and column order in composite indexes is critical for query performance.

## Pattern / Solution
1. B-tree (default): equality and range queries (=, <, >, BETWEEN, LIKE 'prefix%').\n2. Hash: equality only; faster than B-tree for = comparisons.\n3. GIN: full-text search, JSONB, and array contains queries.\n4. Composite index column order: most selective column first.\n5. Partial index: CREATE INDEX ON orders (user_id) WHERE status = 'pending'.

## Gotchas
- LIKE '%suffix' cannot use a B-tree index; use a trigram index (pg_trgm) instead.\n- Function calls on indexed columns bypass indexes; use a functional index instead.\n- Too many indexes slow down INSERT/UPDATE/DELETE and consume disk space.

## Related
sql-query-explain-analyze, database-query-performance, n-plus-one-detection
