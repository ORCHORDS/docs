# postgresql-17-18-best-practices

**Issue:** PostgreSQL 17/18 — partitioning, vacuum, indexing
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your DB is 1TB. Queries are slow. Vacuum takes 2
hours. You delete old data, it bloats. The wraparound
warning fires. You wish you had partitioned.

## Root cause
**PostgreSQL needs care.** Use partitioning, tune
vacuum, manage indexes.

**Source:** PostgreSQL docs + dev.to 2026.

## The "PostgreSQL 18 / 17" pattern

For current:
- **18:** Current (2026)
- **17:** Previous stable
- **16:** Still common
- **Partitioning:** Declarative (10+)
- **pg_partman:** Automation
- **HNSW:** Vector (pgvector)

The version is current.

## The "partitioning" pattern

For declarative:
```sql
CREATE TABLE events (
  id bigserial,
  event_type text NOT NULL,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE events_2026_03 PARTITION OF events
  FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

The partition is declarative.

## The "partition strategies" pattern

For choice:
- **RANGE:** Time-series, ranges (date, ID)
- **LIST:** Categorical (region, status)
- **HASH:** Even distribution (when no natural key)
- **Composite:** Multi-key

The strategy is per data.

## The "partition pruning" pattern

For pruning:
- **Enable:** `enable_partition_pruning = on`
- **Query:** Must filter on partition key
- **EXPLAIN:** Verify pruning
- **Without:** Full scan across all partitions

The pruning is required.

## The "pg_partman" pattern

For automation:
```sql
-- Install
CREATE EXTENSION pg_partman SCHEMA partman;

-- Create partition set
SELECT partman.create_parent(
  p_parent_table := 'public.events',
  p_control     := 'created_at',
  p_type        := 'range',
  p_interval    := '1 month'
);

-- Run maintenance
SELECT partman.run_maintenance();
```

The partman auto-creates.

## The "maintenance schedule" pattern

For pg_cron:
```sql
SELECT cron.schedule(
  'partman-maintenance',
  '*/15 * * * *',
  $$SELECT partman.run_maintenance()$$
);
```

The maintenance is per 15min.

## The "VACUUM deep" pattern

For autovacuum:
```ini
# Global
autovacuum_vacuum_scale_factor = 0.05
autovacuum_vacuum_cost_delay = 2ms
autovacuum_vacuum_cost_limit = 1000
autovacuum_max_workers = 5
autovacuum_freeze_max_age = 200000000
```

The vacuum is aggressive.

## The "per-table vacuum" pattern

For hot tables:
```sql
ALTER TABLE sessions SET (
  autovacuum_vacuum_scale_factor = 0.01,
  autovacuum_vacuum_cost_delay = 0
);
```

The hot is aggressive.

## The "partition vacuum" pattern

For partitions:
- **Each partition:** Vacuumed independently
- **Autovacuum:** Per partition
- **Parent:** Not auto-vacuumed (run ANALYZE manually)
- **Hot partitions:** Aggressive
- **Cold partitions:** Relaxed

The partition is per-VAC.

## The "ANALYZE on parent" pattern

For statistics:
```sql
-- Manual ANALYZE on parent
ANALYZE events;

-- Schedule
SELECT cron.schedule('analyze-events', '0 4 * * *',
  $$ANALYZE events$$);
```

The parent is analyzed.

## The "REINDEX CONCURRENTLY" pattern

For index rebuild:
```sql
-- Without lock
REINDEX TABLE CONCURRENTLY events_2026_03;
```

The rebuild is online.

## The "wraparound prevention" pattern

For XID:
- **Monitor:** `age(relfrozenxid)`
- **Freeze max:** 200M transactions
- **Alert:** At 150M
- **Action:** Manual VACUUM FREEZE
- **Downtime:** If wraparound, hard

The wraparound is critical.

## The "shared_buffers" pattern

For memory:
- **25% of RAM:** shared_buffers
- **50-75% of RAM:** effective_cache_size
- **work_mem:** Per query (session-level)
- **maintenance_work_mem:** 1-2 GB

The memory is tuned.

## The "SSD tuning" pattern

For SSDs:
- **random_page_cost:** 1.1
- **effective_io_concurrency:** 200
- **vm.swappiness:** 1
- **I/O scheduler:** none/none
- **Filesystem:** XFS (best for large)

The SSD is tuned.

## The "filesystem" pattern

For FS:
- **XFS:** Large DBs
- **ext4:** Smaller, simpler
- **noatime:** Mount option
- **WAL:** Separate disk (if possible)

The FS is XFS + noatime.

## The "connection pooling" pattern

For connections:
- **PgBouncer:** Transaction mode
- **max_connections:** 100-200 (not 1000)
- **Pool size:** Tune per workload
- **Monitor:** Connection count + pool util

The pool is the answer.

## The "HNSW index" pattern

For vectors (pgvector):
```sql
CREATE INDEX ON documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

The HNSW is for vectors.

## The "covering index" pattern

For index-only scan:
```sql
CREATE INDEX idx_user_email
ON users (email)
INCLUDE (name, created_at);
```

The covering includes cols.

## The "partial index" pattern

For skewed data:
```sql
-- Only active users
CREATE INDEX idx_active_users
ON users (last_login)
WHERE status = 'active';
```

The partial is selective.

## The "GIN" pattern

For JSONB + FTS:
```sql
CREATE INDEX idx_payload
ON events USING GIN (payload);
```

The GIN is for JSONB.

## The "drop unused" pattern

For index bloat:
```sql
-- Find unused
SELECT schemaname, relname, indexrelname,
       idx_scan, idx_tup_read
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

The unused are dropped.

## The "pg_stat_user_tables" pattern

For seq scan detection:
```sql
SELECT schemaname, relname,
       seq_scan, idx_scan,
       n_live_tup,
       ROUND(seq_scan::numeric /
         GREATEST(seq_scan + idx_scan, 1) * 100, 1) AS seq_scan_pct
FROM pg_stat_user_tables
WHERE n_live_tup > 10000
ORDER BY seq_scan_pct DESC
LIMIT 20;
```

The seq scan is detected.

## The "EXPLAIN ANALYZE" pattern

For query plan:
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM events
WHERE created_at >= '2026-01-01';
```

The plan is explained.

## The "keyset pagination" pattern

For pagination:
- **❌ OFFSET:** Slow for large offsets
- **✅ Keyset:** WHERE id > last_id
- **Index:** Required on key

The pagination is keyset.

## The "DROP TABLE partition" pattern

For bulk delete:
- **Old DELETE:** Slow, generates WAL
- **DROP TABLE:** Fast, no vacuum needed
- **DETACH:** Remove from parent, keep table

The drop is per partition.

## The "partition key in PK" pattern

For constraint:
- **Required:** PK must include partition key
- **Why:** Globally unique
- **Pattern:** `PRIMARY KEY (created_at, id)`

The PK is composite.

## The "DEFAULT partition" pattern

For unmapped:
```sql
CREATE TABLE events_default
PARTITION OF events DEFAULT;
```

The default catches outliers.

## The "no partitioning" anti-pattern

For no partition:
- **Issue:** Slow queries, slow vacuum
- **Fix:** Partition by time

The partition is required.

## The "no vacuum" anti-pattern

For no vacuum:
- **Issue:** Bloat, wraparound
- **Fix:** Aggressive autovacuum

The vacuum is required.

## The "too many indexes" anti-pattern

For too many:
- **Issue:** Slow writes
- **Fix:** Drop unused

The indexes are minimal.

## The "WAL on same disk" anti-pattern

For WAL:
- **Issue:** I/O contention
- **Fix:** Separate disk

The WAL is separate.

## The "PostgreSQL checklist" pattern

For checklist:
- [ ] shared_buffers = 25% RAM
- [ ] effective_cache_size = 50-75% RAM
- [ ] XFS + noatime
- [ ] PgBouncer
- [ ] max_connections = 100-200
- [ ] autovacuum aggressive
- [ ] Partition time-series
- [ ] pg_partman + pg_cron
- [ ] Index for slow queries
- [ ] Drop unused
- [ ] REINDEX CONCURRENTLY
- [ ] Wraparound monitored
- [ ] work_mem per session
- [ ] SSD tuned

The checklist is 14.

## Verification
- **Test:** Partition pruning verified
- **Test:** VACUUM runs
- **Test:** No wraparound
- **Test:** Index used
- **Audit:** Quarterly

## Gotchas
- **The "no partitioning" anti-pattern.** Partition.
- **The "no vacuum" anti-pattern.** Aggressive.
- **The "too many indexes" anti-pattern.** Drop.

## Related
- `cloudflare/d1-best-practices.md`
- `cloudflare/d1-pragma-tuning.md`
- `cloudflare/d1-time-travel.md`
- `patterns/data-mesh-vs-fabric.md`
- `infra/iac-best-practices.md`
- PG docs: https://www.postgresql.org/docs/current/ddl-partitioning.html
- YoungJu: https://www.youngju.dev/transcribe/database/2026-03-07-database-postgresql-partitioning-billion-row-tables.en
- dev.to: https://dev.to/_d7eb1c1703182e3ce1782/postgresql-performance-tuning-checklist-2026-complete-guide-65a
