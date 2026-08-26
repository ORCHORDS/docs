# composite-index-design

**Issue:** Designing multi-column indexes for maximum query coverage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Wrong column order in a composite index means the index is unused or only partially used for common queries.

## Pattern / Solution
```sql
-- Rule: equality columns first, range column last
-- Query: WHERE status = ''active'' AND created_at > ''2026-01-01''
CREATE INDEX idx_orders_status_created
  ON orders (status, created_at);

-- Supports: (status), (status, created_at) — not (created_at) alone
-- Query: WHERE tenant_id = $1 AND user_id = $2 ORDER BY created_at
CREATE INDEX idx_events_tenant_user_time
  ON events (tenant_id, user_id, created_at);
```

## Gotchas
- A composite index on (a, b) does NOT help a query filtering only on b
- Index columns used only for ORDER BY should come last
- More than 3-4 columns in a composite index rarely helps and adds write overhead

## Related
- `index-selectivity.md`
- `covering-indexes.md`
- `explain-analyze-reading.md`
