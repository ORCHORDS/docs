# D1 Write Amplification from Indexes: Budgeting for Write-Heavy Workloads

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 table receives high-frequency inserts (event logs, analytics events, user activity records). As the table grows and team members add indexes to support new query patterns, `INSERT` and `UPDATE` latency climbs from 2 ms to 15–40 ms. `EXPLAIN QUERY PLAN` shows the queries using the correct indexes, so the read performance is fine—but write performance degraded silently because every additional index requires a B-tree update on every write.

## Context

SQLite (the engine under D1) maintains each index as a separate B-tree. Every `INSERT`, `UPDATE`, or `DELETE` on a row must update all indexes that include any of the modified columns. A table with 8 indexes has 8× the write I/O overhead compared to a table with no indexes. In D1's cloud-hosted SQLite this is amplified by distributed durability writes.

**Write amplification factor** for an insert on a table with *n* indexes ≈ `1 + n` B-tree pages written. For write-heavy tables, keep the index count to the minimum needed by the read queries you actually run.

---

## Auditing Index Count with sqlite_master

```typescript
interface Env { DB: D1Database }

interface IndexRow {
  name: string;
  tbl_name: string;
  sql: string | null;
}

export async function auditIndexes(env: Env, table: string): Promise<void> {
  const { results } = await env.DB.prepare(`
    SELECT name, tbl_name, sql
    FROM sqlite_master
    WHERE type = 'index'
      AND tbl_name = ?
    ORDER BY name
  `).bind(table).all<IndexRow>();

  console.log(`Table "${table}" has ${results.length} index(es):`);
  for (const idx of results) {
    console.log(`  ${idx.name}: ${idx.sql ?? "(auto rowid)"}`);
  }
}
```

---

## Measuring Write Amplification with EXPLAIN

```typescript
/**
 * EXPLAIN (not EXPLAIN QUERY PLAN) returns low-level VDBE opcodes.
 * Count "IdxInsert" operations to measure how many index B-trees are touched
 * per INSERT statement.
 */
interface VdbeOp {
  addr: number;
  opcode: string;
  p1: number;
  p2: number;
  p3: number;
  p4: string;
  p5: number;
  comment: string;
}

export async function countIndexWrites(env: Env, insertSql: string): Promise<number> {
  const { results } = await env.DB.prepare(`EXPLAIN ${insertSql}`)
    .all<VdbeOp>();

  const idxInserts = results.filter(op => op.opcode === "IdxInsert").length;
  console.log(`INSERT touches ${idxInserts} index B-tree(s)`);
  return idxInserts;
}

// Usage
await countIndexWrites(
  env,
  "INSERT INTO events (user_id, type, payload, created_at) VALUES (1, 'click', '{}', 1234567890)"
);
```

---

## Replacing Multiple Single-Column Indexes with One Composite Index

```sql
-- Before: 3 separate indexes on a write-heavy events table
-- Each INSERT writes 3 extra B-tree pages
CREATE INDEX idx_events_user   ON events (user_id);
CREATE INDEX idx_events_type   ON events (type);
CREATE INDEX idx_events_ts     ON events (created_at);

-- After: one composite covering common read patterns
-- INSERT now writes 1 extra B-tree page
DROP INDEX idx_events_user;
DROP INDEX idx_events_type;
DROP INDEX idx_events_ts;

CREATE INDEX idx_events_user_type_ts
  ON events (user_id, type, created_at);

-- This covers:
--   WHERE user_id = ?                                (prefix)
--   WHERE user_id = ? AND type = ?                   (prefix)
--   WHERE user_id = ? AND type = ? AND created_at > ?(full)
```

```typescript
// D1 migration to swap indexes atomically
export async function migrateIndexes(env: Env): Promise<void> {
  await env.DB.batch([
    env.DB.prepare("DROP INDEX IF EXISTS idx_events_user"),
    env.DB.prepare("DROP INDEX IF EXISTS idx_events_type"),
    env.DB.prepare("DROP INDEX IF EXISTS idx_events_ts"),
    env.DB.prepare(`
      CREATE INDEX IF NOT EXISTS idx_events_user_type_ts
        ON events (user_id, type, created_at)
    `),
  ]);
}
```

---

## Partial Indexes to Reduce Write Amplification for Sparse Queries

```sql
-- Full index updated on every INSERT even for rows where processed = 0
CREATE INDEX idx_events_unprocessed_full ON events (created_at)
  WHERE processed = 0;

-- A partial index is only updated when the WHERE clause is true at insert time.
-- If 95% of inserts have processed = 0 this barely helps; but for a flag
-- that's only set on ~5% of rows (e.g., flagged_for_review = 1) a partial
-- index covers the rare read path at minimal write cost.
CREATE INDEX idx_events_flagged ON events (created_at)
  WHERE flagged_for_review = 1;
```

```typescript
// Verify selectivity of a candidate partial-index column before creating it
export async function checkSelectivity(
  env: Env,
  table: string,
  column: string,
  condition: string
): Promise<void> {
  const { results } = await env.DB.prepare(`
    SELECT
      COUNT(*) AS total,
      SUM(CASE WHEN ${condition} THEN 1 ELSE 0 END) AS matching,
      ROUND(100.0 * SUM(CASE WHEN ${condition} THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct
    FROM ${table}
  `).all<{ total: number; matching: number; pct: number }>();

  const { total, matching, pct } = results[0];
  console.log(`${column} selectivity: ${matching}/${total} rows match (${pct}%)`);
  // Partial index is beneficial when pct < ~20%
}
```

---

## Benchmarking Write Throughput Before and After Index Reduction

```typescript
export async function benchmarkInserts(
  env: Env,
  iterations = 1000
): Promise<{ durationMs: number; opsPerSec: number }> {
  const start = Date.now();

  // Use a D1 batch for reduced round-trips
  const BATCH = 50;
  for (let i = 0; i < iterations; i += BATCH) {
    const stmts = Array.from({ length: Math.min(BATCH, iterations - i) }, (_, j) =>
      env.DB.prepare(
        "INSERT INTO events (user_id, type, payload, created_at) VALUES (?, ?, ?, ?)"
      ).bind(
        (i + j) % 10_000,
        "benchmark",
        "{}",
        Math.floor(Date.now() / 1000)
      )
    );
    await env.DB.batch(stmts);
  }

  const durationMs = Date.now() - start;
  const opsPerSec = Math.round((iterations / durationMs) * 1000);
  console.log(`${iterations} inserts in ${durationMs} ms = ${opsPerSec} ops/s`);
  return { durationMs, opsPerSec };
}
```

---

## Anti-patterns

- **Adding an index for every column a developer might filter on**: the "safe" default of indexing liberally destroys write performance at scale. Index by *query pattern*, not by column availability.
- **Using a covering index on a write-heavy table when a non-covering index suffices for the read**: covering indexes (with `INCLUDE` columns or wide composite keys) are heavier to maintain on write. Verify the read gain justifies the write cost.
- **Dropping and recreating indexes inside a transaction that also writes data**: D1 does not support online DDL; schema changes block the table exclusively. Run `CREATE/DROP INDEX` migrations during low-traffic windows or use the batch API on a separate connection.
- **Indexing high-cardinality `payload` JSON columns**: D1 supports generated column indexes (`CREATE INDEX ON t(json_extract(payload, '$.type'))`), but the extracted value is recomputed on every write, adding CPU cost on top of B-tree I/O.

## Gotchas

- D1 (SQLite) does not support **`DROP INDEX CONCURRENTLY`** or **online index builds**. Creating an index on a large table blocks all writes for the duration. Use `wrangler d1 execute` off-peak and monitor via the D1 dashboard.
- SQLite's query planner may **not choose your composite index** if statistics are stale. Run `ANALYZE events` periodically or after large bulk inserts to refresh the planner's row-count estimates.
- `EXPLAIN` in D1 returns VDBE bytecode, not `EXPLAIN ANALYZE` with runtime stats. Estimated row counts come from `EXPLAIN QUERY PLAN`; actual write I/O must be inferred from benchmarks.
- D1 **WAL mode** (enabled by default) improves write throughput by deferring B-tree page writes to background checkpoints, but each index still requires an entry in the WAL for every write. WAL amplification is per-index, not absorbed.

## Verification

```bash
# List all indexes on the events table
wrangler d1 execute <DB_NAME> \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='events'"

# Count IdxInsert VDBE ops for an INSERT (proxy for write amplification)
wrangler d1 execute <DB_NAME> \
  --command "EXPLAIN INSERT INTO events (user_id, type, created_at) VALUES (1,'test',1234567890)" \
  | grep IdxInsert | wc -l
# Target: ≤ 2 for write-heavy tables (1 primary rowid + 1 composite index)

# Benchmark write throughput via Worker endpoint
hey -n 1000 -c 20 -m POST \
  -H "Content-Type: application/json" \
  -d '{"type":"bench"}' \
  https://myworker.example.workers.dev/events/insert
```

## Related

- `d1-partial-index-write-performance.md`
- `d1-covering-index-multi-column.md`
- `d1-batch-query-performance-optimization.md`
- `d1-wal-mode-write-throughput.md`
- `d1-pragma-optimize-query-planner.md`

## Sources

- SQLite Index Architecture: https://www.sqlite.org/queryplanner.html
- SQLite EXPLAIN opcode reference: https://www.sqlite.org/opcode.html
- D1 Index documentation: https://developers.cloudflare.com/d1/sql-api/sql-statements/#create-index
- D1 WAL mode: https://developers.cloudflare.com/d1/reference/database-internals/
