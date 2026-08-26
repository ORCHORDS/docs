# D1 Index Bloat Slow Insert Regression Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Write latency on a high-throughput event ingestion table climbed from ~4 ms to ~180 ms over six weeks without any schema change. D1 insights showed no obvious query-plan changes; the table had only 8 million rows. Reads were unaffected. A burst-traffic deploy eventually caused p99 insert latency to spike to 1.4 seconds, triggering PagerDuty.

## Context

The `events` table had eight secondary indexes inherited from an early design phase. Three of them covered columns used only in ad-hoc analytics queries that had since been replaced by an Analytics Engine pipeline. The indexes were never removed. SQLite (D1's storage engine) must update every index on every `INSERT` or `UPDATE`. As the table grew, each index B-tree required progressively more page splits, causing write amplification. The team identified the root cause only after running `PRAGMA index_list` and `EXPLAIN QUERY PLAN` against the production D1 database via the REST API.

## 1. Diagnosing Index Bloat

Use the D1 REST API to inspect index metadata without touching application code:

```typescript
// scripts/audit-indexes.ts
const DB_ID = process.env.D1_DATABASE_ID!;
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

async function query(sql: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${DB_ID}/query`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ sql }),
    }
  );
  const json = await res.json() as { result: Array<{ results: unknown[] }> };
  return json.result[0].results;
}

// List all indexes and their sizes
const indexes = await query(`
  SELECT
    m.name  AS table_name,
    il.name AS index_name,
    il."unique",
    il.partial,
    is2.stat AS stat
  FROM sqlite_master m
  JOIN pragma_index_list(m.name) il
  LEFT JOIN sqlite_stat1 is2 ON is2.idx = il.name
  WHERE m.type = 'table'
  ORDER BY m.name, il.name;
`);
console.table(indexes);
```

Run `ANALYZE` first so `sqlite_stat1` is populated:

```typescript
await query("ANALYZE;");
```

## 2. Identifying Unused Indexes

Cross-reference index names against application query plans. Any index not appearing in an `EXPLAIN QUERY PLAN` result for your known queries is a candidate for removal:

```typescript
const candidateQueries = [
  "SELECT * FROM events WHERE user_id = ?1 AND created_at > ?2",
  "SELECT COUNT(*) FROM events WHERE session_id = ?1",
  // ... all production query shapes
];

const usedIndexes = new Set<string>();

for (const sql of candidateQueries) {
  const plan = await query(`EXPLAIN QUERY PLAN ${sql}`);
  for (const row of plan as Array<{ detail: string }>) {
    const match = row.detail.match(/USING INDEX (\S+)/);
    if (match) usedIndexes.add(match[1]);
  }
}

const allIndexes = (indexes as Array<{ index_name: string }>).map((r) => r.index_name);
const unusedIndexes = allIndexes.filter((n) => !usedIndexes.has(n));
console.log("Unused indexes:", unusedIndexes);
```

## 3. Safe Index Removal Migration

Remove indexes in a separate migration, one at a time, with verification between each:

```sql
-- migrations/0012_drop_stale_indexes.sql
-- Drop analytics-only indexes no longer used after Analytics Engine migration

-- Verify the index exists before dropping (idempotent guard)
DROP INDEX IF EXISTS idx_events_referrer;
DROP INDEX IF EXISTS idx_events_country;
DROP INDEX IF EXISTS idx_events_utm_source;
```

```typescript
// worker migration runner — executes via D1 binding
export async function runMigration(db: D1Database): Promise<void> {
  const start = Date.now();
  await db.batch([
    db.prepare("DROP INDEX IF EXISTS idx_events_referrer"),
    db.prepare("DROP INDEX IF EXISTS idx_events_country"),
    db.prepare("DROP INDEX IF EXISTS idx_events_utm_source"),
  ]);
  console.log(`Migration completed in ${Date.now() - start}ms`);
}
```

## 4. Measuring Write Latency Before and After

Instrument inserts with timing before deploying the migration to production:

```typescript
export async function insertEvent(db: D1Database, event: EventRow): Promise<void> {
  const t0 = performance.now();

  await db
    .prepare(
      `INSERT INTO events (id, user_id, session_id, name, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5)`
    )
    .bind(event.id, event.userId, event.sessionId, event.name, event.createdAt)
    .run();

  const duration = performance.now() - t0;

  // Emit to Analytics Engine for tracking regressions over time
  analyticsEngine.writeDataPoint({
    blobs: ["events", "insert"],
    doubles: [duration],
    indexes: ["event_insert_ms"],
  });

  if (duration > 50) {
    console.warn(`Slow insert: ${duration.toFixed(1)}ms`, { eventId: event.id });
  }
}
```

## 5. Preventing Future Index Bloat

Add an index hygiene check to the CI pipeline that fails if the index-to-column usage ratio exceeds a threshold:

```typescript
// scripts/index-hygiene.ts
const MAX_UNUSED_INDEX_RATIO = 0.25; // fail if >25% of indexes are unused

const total = allIndexes.length;
const unused = unusedIndexes.length;
const ratio = unused / total;

console.log(`Index hygiene: ${unused}/${total} unused (${(ratio * 100).toFixed(0)}%)`);

if (ratio > MAX_UNUSED_INDEX_RATIO) {
  console.error(
    `Index bloat threshold exceeded. Remove or justify: ${unusedIndexes.join(", ")}`
  );
  process.exit(1);
}
```

Add to `package.json`:
```json
{
  "scripts": {
    "db:audit": "tsx scripts/audit-indexes.ts && tsx scripts/index-hygiene.ts"
  }
}
```

## Anti-patterns

- Creating indexes speculatively at schema design time without a confirmed query that uses them.
- Copying all indexes from one environment to another (staging → production) without reviewing which are load-bearing.
- Treating slow writes as a hardware or throughput problem before auditing write amplification from indexes.
- Dropping multiple indexes in a single migration without measuring latency improvement between each removal — you lose the ability to pinpoint which index was responsible.

## Gotchas

- SQLite's query planner may use an index that does not appear in `EXPLAIN QUERY PLAN` for range scans with very low selectivity — validate index removal under realistic data volumes.
- `DROP INDEX` on D1 is DDL and acquires a brief write lock; run during low-traffic windows.
- D1 Time Travel cannot roll back a `DROP INDEX` that happened outside a transaction — the index definition is gone even if you restore to a pre-drop bookmark if the DDL was committed. Always keep the migration script so you can re-create the index if needed.
- Running `ANALYZE` frequently on large tables in a Worker is expensive; schedule it as a Cron Trigger during off-peak hours rather than in the hot path.

## Verification

```typescript
// After migration: confirm p95 insert latency has returned to baseline
const p95 = await query(`
  SELECT quantile(duration_ms, 0.95) AS p95
  FROM event_insert_metrics
  WHERE timestamp > now() - INTERVAL '1 hour'
`);
console.log("p95 insert latency:", p95);
```

```bash
# Confirm the dropped indexes are gone
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/d1/database/$D1_ID/query" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT name FROM sqlite_master WHERE type='\''index'\'' AND tbl_name='\''events'\''"}' \
  | jq '.result[0].results'
```

## Related

- d1-missing-index-full-table-scan-production-incident.md
- d1-write-contention-viral-event-postmortem.md
- d1-schema-migration-table-lock-peak-traffic-postmortem.md
- analytics-engine-data-point-limit-exceeded.md

## Sources

- https://developers.cloudflare.com/d1/reference/database-commands/
- https://www.sqlite.org/queryplanner.html
- https://www.sqlite.org/stat.html
