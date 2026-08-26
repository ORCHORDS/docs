# database-index-strategies

**Issue:** When to add indexes, multi-column indexes, covering indexes
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your query is `SELECT * FROM users WHERE tenant_id = 't_123' AND email = 'a@x.test'`. The table has 1M rows. The query takes 2 seconds. You add an index on `email`. The query still takes 2 seconds.

## Root cause
**Indexes are not magic.** A single-column index helps single-
column queries. A multi-column query needs a multi-column
index.

**Source:** SQLite docs (D1's engine):
https://www.sqlite.org/queryplanner.html

> "SQLite uses indexes to speed up queries. ... The order
> of columns in a multi-column index matters."

## The index basics

```sql
-- Single-column index
CREATE INDEX idx_users_email ON users(email);

-- Multi-column index
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);

-- Unique index
CREATE UNIQUE INDEX idx_users_email_unique ON users(email);

-- Partial index
CREATE INDEX idx_users_active ON users(email) WHERE deleted_at IS NULL;
```

## The "column order" rule

For a multi-column index `(a, b, c)`:
- ✅ Usable for queries on `a`
- ✅ Usable for queries on `a, b`
- ✅ Usable for queries on `a, b, c`
- ❌ Not usable for queries on `b` (without `a`)
- ❌ Not usable for queries on `c` (without `a` or `b`)

The first column must be in the WHERE clause.

```ts
// Index: idx_users_tenant_email (tenant_id, email)

// ✅ Uses the index
WHERE tenant_id = 't_123' AND email = 'a@x.test'
WHERE tenant_id = 't_123'
WHERE tenant_id = 't_123' AND email LIKE 'a%'

// ❌ Does NOT use the index
WHERE email = 'a@x.test'
WHERE email LIKE 'a%'
```

## The "covering index" pattern

A covering index includes all columns the query needs. The
DB doesn't have to read the table:
```sql
-- Query: SELECT id, email FROM users WHERE tenant_id = ? AND email = ?

-- ❌ Index lookup + table read
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);
-- Query uses index for WHERE, but reads the table for SELECT (id, email)
-- The DB has to fetch the row to get the data

-- ✅ Covering index
CREATE INDEX idx_users_tenant_email_cover ON users(tenant_id, email, id);
-- The query is satisfied by the index alone; no table read
```

For read-heavy queries, covering indexes are a big win.

## The "primary key" index

Every table has a primary key index (usually clustered in
RDBMS, but in SQLite/D1, the rowid is the primary key).
- `WHERE id = 'u_123'` uses the PK index
- `WHERE id IN ('u_1', 'u_2', 'u_3')` uses the PK index
- `WHERE id < 'u_999'` uses the PK index

The PK index is essentially free; use it.

## The "order by" index

For sorted queries:
```sql
-- Query: SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at DESC

-- ✅ Index supports both filter and sort
CREATE INDEX idx_users_tenant_created ON users(tenant_id, created_at DESC);
-- The query scans the index in order, no separate sort step
```

Without the index, the DB does a filter, then a separate sort
step. Slow.

## The "index for joins" pattern

```sql
-- Query: SELECT * FROM posts p JOIN users u ON p.user_id = u.id WHERE u.tenant_id = ?

-- ✅ Index on users.tenant_id
CREATE INDEX idx_users_tenant_id ON users(tenant_id);

-- ✅ Index on posts.user_id (likely the PK index)
```

The join needs the indexed column on both sides.

## The "when to add an index"

Add an index when:
- **A query is slow** (p99 > 100ms) and the EXPLAIN shows a
  full scan
- **A query is read-heavy** (called often, e.g. every page
  load)
- **A column is filtered or sorted by often**

Don't add an index when:
- **A table is small** (< 1000 rows): full scan is fast
- **A column is rarely filtered by** (low selectivity)
- **The index cost outweighs the benefit** (writes are slow
  because of the index)

## The "index cost" trade-off

Indexes make reads fast but writes slower:
- **Each INSERT:** writes to the table + every index
- **Each UPDATE:** updates the index if the indexed column
  changes
- **Each DELETE:** removes from the table + every index

For write-heavy tables, fewer indexes are better.

## The "analyze" pattern

After schema changes, run `ANALYZE` to update the query
planner's statistics:
```sql
ANALYZE;
```

Without `ANALYZE`, the planner may choose a bad plan because
it doesn't know the data distribution.

For D1, `ANALYZE` is supported. Run it after bulk inserts.

## The "EXPLAIN QUERY PLAN" pattern

```sql
EXPLAIN QUERY PLAN
SELECT * FROM users WHERE tenant_id = 't_123' AND email = 'a@x.test';
```

The output shows:
```
SEARCH users USING INDEX idx_users_tenant_email (tenant_id=? AND email=?)
```

This is what you want. If it says `SCAN users`, you need an
index.

## The "compound" pattern

For complex queries, multiple indexes:
```sql
-- Query 1: filter by tenant, sort by created
CREATE INDEX idx_users_tenant_created ON users(tenant_id, created_at DESC);

-- Query 2: filter by tenant, search by email
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);

-- Query 3: filter by tenant, filter by status
CREATE INDEX idx_users_tenant_status ON users(tenant_id, status);
```

Each query uses a different index. The cost: 3x index
maintenance on writes.

## The "index bloat" pattern

Indexes take storage. For a 1M-row table with 5 indexes:
- Table: 100MB
- Each index: ~10-30MB
- Total: 150-250MB

Monitor index usage; drop unused indexes.

For D1, you can see index size in the dashboard.

## The "index hint" anti-pattern

Most modern DBs (including SQLite) don't need index hints.
The planner picks the best index.

If you think you need a hint, you probably need a better
schema. The planner is smarter than you (most of the time).

## The "explain analyze" pattern

For real performance, use `EXPLAIN ANALYZE` (Postgres) or
the equivalent in your DB. This actually runs the query and
shows the time per step.

For D1, this is not directly available; use the Workers
Analytics Engine + custom timing.

## Verification
- **Test:** `test/db.test.ts > query is < 100ms for
  production-scale data` — passes
- **Live:** Slow query log is monitored
- **Audit:** Quarterly review of indexes

## Gotchas
- **The "add an index" reflex is not always right.** An
  index on a column with low selectivity (e.g. `is_active`
  with 99% true) is wasted space.
- **The "primary key is indexed" is usually true** but not
  always. Verify with EXPLAIN.
- **The "composite index column order" is critical.** Putting
  the wrong column first is a no-op.
- **The "covering index" is a big win** for read-heavy
  queries.
- **The "analyze" is needed after big changes.** Without it,
  the planner may use a stale plan.

## Related
- `database-migration-strategy.md`
- `database-transaction-design.md`
- `multi-tenant-data-isolation.md` (tenant_id is always the
  first column)
- `caching-strategies-detail.md` (cache vs index)
- SQLite: https://www.sqlite.org/queryplanner.html
- Use The Index, Luke: https://use-the-index-luke.com/
