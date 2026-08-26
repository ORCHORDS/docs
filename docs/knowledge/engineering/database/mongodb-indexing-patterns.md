# mongodb-indexing-patterns

**Issue:** MongoDB queries without proper indexes cause full collection scans
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
explain() shows COLLSCAN instead of IXSCAN. Query response times grow linearly with collection size.

## Pattern / Solution
Create indexes for all query filter fields. Compound index order: equality fields first, sort fields second, range fields last (ESR rule). Text indexes for string search. Partial indexes for sparse data with partialFilterExpression. TTL index for auto-expiry: expireAfterSeconds.

## Gotchas
- Compound index can only be used if query includes the leftmost prefix fields
- Indexes on array fields (multikey indexes) have one key per array element -- higher storage, slower updates
- hint() forces a specific index -- useful when query planner chooses wrong index

## Related
- mongodb-schema-design
- index-selectivity
- composite-index-design
