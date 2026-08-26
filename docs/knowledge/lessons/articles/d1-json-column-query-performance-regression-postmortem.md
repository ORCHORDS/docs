# D1 JSON Column Query Performance Regression Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

API p99 latency on `/api/tracks` climbed from 45 ms to 3.2 s over 48 hours. No code deploy had occurred. CloudFlare Workers CPU time metrics looked normal; the spike was entirely in D1 query duration. An alert finally fired when the 5-second Worker CPU wall-clock limit started triggering for the first time.

## Context

The `tracks` table stores per-track metadata in a `settings` TEXT column that holds JSON blobs. A new product feature queried that column with `json_extract()` inside a WHERE clause to filter by a nested flag. The column had no generated column or index. Row count was ~180 k at launch; it crossed 2 M rows 48 hours later after an import job ran overnight.

---

## Root Cause: `json_extract` in WHERE Clause Forces Full Table Scan

SQLite (and therefore D1) cannot use a B-tree index when the index key is a runtime function call. Every row must be read and the JSON parsed in the SQLite VM.

```sql
-- BEFORE (slow path, full scan at 2 M rows)
SELECT id, title
FROM tracks
WHERE json_extract(settings, '$.published') = 1
  AND user_id = ?;
```

At 180 k rows this was invisible. At 2 M rows each query read ~80 MB of raw data across D1's distributed SQLite engine.

## Fix Step 1: Add a Generated Column and Index

SQLite supports stored generated columns. The value is computed at write time and stored physically, making it indexable.

```sql
-- Run in a D1 migration
ALTER TABLE tracks
  ADD COLUMN is_published INTEGER
  GENERATED ALWAYS AS (json_extract(settings, '$.published'))
  STORED;

CREATE INDEX idx_tracks_user_published
  ON tracks (user_id, is_published);
```

After backfilling (D1 runs the STORED generation on ALTER for existing rows), the query plan flipped to an index scan.

## Fix Step 2: Rewrite the Query

```typescript
// src/db/tracks.ts
export async function getPublishedTracks(
  db: D1Database,
  userId: string,
): Promise<Track[]> {
  const stmt = db.prepare(
    `SELECT id, title, created_at
       FROM tracks
      WHERE user_id = ?1
        AND is_published = 1
      ORDER BY created_at DESC
      LIMIT 200`,
  );
  const { results } = await stmt.bind(userId).all<Track>();
  return results;
}
```

## Fix Step 3: Verify the Query Plan Before Deploying

Always run EXPLAIN QUERY PLAN in a migration check script. This can be done against the local D1 dev database or via `wrangler d1 execute`.

```bash
wrangler d1 execute DB --command \
  "EXPLAIN QUERY PLAN
   SELECT id, title FROM tracks
   WHERE user_id = 'test' AND is_published = 1"
```

Expected output after fix:
```
QUERY PLAN
`--SEARCH tracks USING INDEX idx_tracks_user_published (user_id=? AND is_published=?)
```

If the output says `SCAN tracks`, the index is not being used.

## Fix Step 4: Add a Migration Test in CI

```typescript
// tests/migrations/json-column-index.test.ts
import { describe, it, expect } from "vitest";
import { unstable_dev } from "wrangler";

describe("tracks query plan", () => {
  it("uses index for published filter", async () => {
    const worker = await unstable_dev("src/index.ts", {
      experimental: { disableExperimentalWarning: true },
    });

    // query plan check via raw D1 binding
    const result = await worker.fetch("/internal/qplan/tracks-published");
    const plan = await result.text();

    expect(plan).toContain("USING INDEX");
    expect(plan).not.toContain("SCAN tracks");

    await worker.stop();
  });
});
```

## Fix Step 5: Alert on D1 Query Duration at the Right Threshold

The incident was caught too late. Workers Analytics Engine lets you record per-query duration and alert before the Worker wall-clock limit is hit.

```typescript
// src/middleware/d1-metrics.ts
export function withD1Metrics(
  db: D1Database,
  ctx: ExecutionContext,
  env: Env,
): D1Database {
  return new Proxy(db, {
    get(target, prop) {
      if (prop !== "prepare") return Reflect.get(target, prop);
      return (query: string) => {
        const stmt = target.prepare(query);
        return new Proxy(stmt, {
          get(s, method) {
            if (method !== "all" && method !== "first" && method !== "run")
              return Reflect.get(s, method);
            return async (...args: unknown[]) => {
              const start = Date.now();
              try {
                const call = (s as D1PreparedStatement)[method as "all"] as (...values: unknown[]) => unknown;
                return await call(...args);
              } finally {
                const ms = Date.now() - start;
                ctx.waitUntil(
                  env.ANALYTICS.writeDataPoint({
                    blobs: [query.slice(0, 100)],
                    doubles: [ms],
                    indexes: ["d1_query_ms"],
                  }),
                );
              }
            };
          },
        });
      };
    },
  });
}
```

---

## Anti-Patterns

- **Querying JSON columns without generated columns.** Any `json_extract()` in a WHERE clause is a full table scan unless there is a stored generated column + index.
- **Assuming query performance holds as rows grow.** A query that runs in 5 ms at 100 k rows may exceed the 30 s D1 timeout at 5 M rows — and the Worker 5 s CPU limit before that.
- **Running EXPLAIN QUERY PLAN only locally.** The local miniflare/wrangler dev SQLite instance may have a different row count and produce a misleading plan.

## Gotchas

- `json_extract` in a SELECT list (not WHERE) is fine; it does not force a scan if the row set is already narrowed by an indexed column.
- STORED generated columns increase write latency slightly and row size. Budget ~4 bytes per extracted integer column.
- D1's ALTER TABLE to add a STORED generated column is synchronous and blocks writes for the duration on large tables. Schedule it during low-traffic windows and consider a backfill migration instead if the table is very large.
- Generated columns cannot reference other generated columns in SQLite 3.31 (the version D1 uses); flatten the extraction in one expression.

## Verification

1. `EXPLAIN QUERY PLAN` shows `USING INDEX`, not `SCAN tracks`.
2. D1 query duration metric p99 returns to baseline (≤ 50 ms).
3. `/api/tracks` p99 API latency returns to ≤ 60 ms.
4. Worker CPU time limit errors stop occurring.
5. CI migration test passes on every PR touching `src/db/tracks.ts`.

## Related

- `d1-prepared-statement-plan-cache-invalidation-regression.md`
- `d1-write-contention-viral-event-postmortem.md`
- `index-before-not-after-performance-problem.md`
- `n-plus-one-queries-compound-at-scale.md`

## Sources

- SQLite Generated Columns: https://www.sqlite.org/gencol.html
- Cloudflare D1 — SQLite Compatibility: https://developers.cloudflare.com/d1/reference/sqlite-compatibility/
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
