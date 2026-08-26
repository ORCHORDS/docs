# D1 VACUUM and Incremental Maintenance in Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

After weeks of deletes and updates your D1 database file has grown noticeably, query times have crept up, and `PRAGMA page_count` shows many free pages that are never reclaimed. You need a maintenance strategy that reclaims fragmented space and keeps statistics fresh without blocking normal request traffic on a Workers runtime that does not support long-running background threads.

---

## Context

SQLite reclaims deleted pages by adding them to a free-list inside the database file; the file does not shrink on its own. `VACUUM` rebuilds the entire database into a fresh, compacted file — ideal but expensive and unsuitable for hot paths. `PRAGMA incremental_vacuum(N)` moves up to N pages from the free-list back to the OS without a full rebuild, making it safe to call in small doses from a Cron Trigger. D1's execution model means each Workers invocation has a bounded CPU budget; incremental maintenance fits that model far better than a full `VACUUM`.

Key facts about D1 and VACUUM:
- D1 runs SQLite in WAL mode internally; `VACUUM` implicitly checkpoints and rebuilds the WAL.
- `VACUUM INTO 'file'` is not available in D1 (no filesystem access from Workers).
- `PRAGMA auto_vacuum` can be set to `INCREMENTAL` on new databases before any data is written; changing it on an existing database requires a full `VACUUM` to take effect.
- `PRAGMA freelist_count` reports how many pages are on the free-list.

---

## Checking Free-List Size Before Maintenance

```typescript
// src/maintenance/vacuum.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface DbStats {
  pageCount: number;
  freelistCount: number;
  pageSize: number;
  wastedBytes: number;
}

export async function getDbStats(db: D1Database): Promise<DbStats> {
  const [pc, fl, ps] = await db.batch([
    db.prepare('PRAGMA page_count'),
    db.prepare('PRAGMA freelist_count'),
    db.prepare('PRAGMA page_size'),
  ]);

  const pageCount = (pc.results[0] as { page_count: number }).page_count;
  const freelistCount = (fl.results[0] as { freelist_count: number }).freelist_count;
  const pageSize = (ps.results[0] as { page_size: number }).page_size;

  return {
    pageCount,
    freelistCount,
    pageSize,
    wastedBytes: freelistCount * pageSize,
  };
}
```

---

## Incremental VACUUM via Cron Trigger

```typescript
// src/scheduled/maintenance.ts
import type { D1Database } from '@cloudflare/workers-types';
import { getDbStats } from '../maintenance/vacuum';

const PAGES_PER_RUN = 64; // ~512 KB per invocation at 8 KB page size
const FREE_RATIO_THRESHOLD = 0.05; // only run if >5 % pages are free

export async function runIncrementalVacuum(db: D1Database): Promise<string> {
  const stats = await getDbStats(db);
  const freeRatio = stats.freelistCount / stats.pageCount;

  if (freeRatio < FREE_RATIO_THRESHOLD) {
    return `Skipped: free ratio ${(freeRatio * 100).toFixed(1)} % below threshold`;
  }

  // auto_vacuum must be INCREMENTAL for this pragma to move pages
  await db.prepare(`PRAGMA incremental_vacuum(${PAGES_PER_RUN})`).run();

  const after = await getDbStats(db);
  const pagesReclaimed = stats.freelistCount - after.freelistCount;
  return `Reclaimed ${pagesReclaimed} pages (${pagesReclaimed * stats.pageSize} bytes)`;
}
```

```typescript
// src/worker.ts
export default {
  async scheduled(
    event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    ctx.waitUntil(runIncrementalVacuum(env.DB));
  },
} satisfies ExportedHandler<Env>;
```

```jsonc
// wrangler.toml
[triggers]
crons = ["0 3 * * *"]  // 03:00 UTC daily
```

---

## Setting auto_vacuum = INCREMENTAL on a New Database

```sql
-- Must be the very first pragma after CREATE DATABASE, before any tables
PRAGMA auto_vacuum = INCREMENTAL;
```

```typescript
// src/db/init.ts
export async function initDatabase(db: D1Database): Promise<void> {
  // Check current mode — cannot change mode on a populated database without VACUUM
  const row = await db
    .prepare('PRAGMA auto_vacuum')
    .first<{ auto_vacuum: number }>();
  // 0 = NONE, 1 = FULL, 2 = INCREMENTAL
  if (row?.auto_vacuum === 0) {
    console.warn(
      'auto_vacuum is NONE. Run VACUUM once then set PRAGMA auto_vacuum = INCREMENTAL to enable incremental reclaim.'
    );
  }
}
```

---

## Enabling INCREMENTAL Mode on an Existing Database

Changing `auto_vacuum` mode on a database that already has data requires a full `VACUUM` cycle. Do this during a low-traffic maintenance window:

```typescript
// src/maintenance/enable-incremental-vacuum.ts
export async function enableIncrementalVacuum(db: D1Database): Promise<void> {
  // Step 1: set the target mode
  await db.prepare('PRAGMA auto_vacuum = INCREMENTAL').run();
  // Step 2: trigger a full rebuild to apply the new mode
  await db.prepare('VACUUM').run();
  // Subsequent incremental_vacuum(N) calls will now reclaim pages
}
```

> Note: `VACUUM` in D1 is a long-running statement. Schedule it via a Cron Trigger with `ctx.waitUntil` and set a generous CPU limit. Monitor D1 metrics for execution time before running in production.

---

## Tracking Maintenance History

```sql
CREATE TABLE IF NOT EXISTS _maintenance_log (
  id          INTEGER PRIMARY KEY,
  run_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  operation   TEXT    NOT NULL,
  detail      TEXT
);
```

```typescript
// src/maintenance/log.ts
export async function logMaintenance(
  db: D1Database,
  operation: string,
  detail: string
): Promise<void> {
  await db
    .prepare(
      'INSERT INTO _maintenance_log (operation, detail) VALUES (?, ?)'
    )
    .bind(operation, detail)
    .run();
}
```

---

## Anti-patterns

- **Running `VACUUM` on every request** — A full `VACUUM` rebuilds the entire database file; it can take seconds on a large database and will exhaust the Workers CPU budget for that invocation.
- **Skipping the free-ratio check** — `incremental_vacuum(N)` on a database with zero free pages is a no-op that still consumes CPU budget; always gate it on `freelist_count`.
- **Expecting `VACUUM INTO` to work in D1** — D1 Workers have no write access to a local filesystem, so `VACUUM INTO '/path'` will fail. For backups, use the D1 export/snapshot API instead.
- **Changing `auto_vacuum` without `VACUUM`** — The pragma updates a header flag but has no effect until the database is rebuilt. If you skip the follow-up `VACUUM`, the setting is silently ignored.
- **Holding open transactions during VACUUM** — `VACUUM` requires an exclusive lock. Any concurrent read or write transaction will cause it to fail with `SQLITE_BUSY`.

---

## Gotchas

- `PRAGMA incremental_vacuum(N)` without `auto_vacuum = INCREMENTAL` is a no-op. Confirm the mode with `PRAGMA auto_vacuum` before relying on it.
- D1's serverless model means the `VACUUM` statement's CPU time counts against the Worker's 30 s (Paid) / 10 ms (Free) CPU limits. Keep `PAGES_PER_RUN` small and spread maintenance across multiple daily Cron firings for large databases.
- After a large bulk delete, freelist pages accumulate quickly. One incremental run per day may not be enough; tune `PAGES_PER_RUN` or fire the Cron multiple times per day during the purge campaign.
- `PRAGMA page_count` includes free pages; `PRAGMA page_count - freelist_count` gives the count of pages actually holding data.
- D1's internal WAL checkpoint may also compact the WAL file independently of VACUUM; do not conflate WAL size with database free-list size.

---

## Verification

```typescript
// Before / after report
export async function vacuumReport(db: D1Database): Promise<void> {
  const before = await getDbStats(db);
  await db.prepare('PRAGMA incremental_vacuum(128)').run();
  const after = await getDbStats(db);

  console.log({
    pagesReclaimed: before.freelistCount - after.freelistCount,
    bytesReclaimed:
      (before.freelistCount - after.freelistCount) * before.pageSize,
    freelistBefore: before.freelistCount,
    freelistAfter: after.freelistCount,
  });
}
```

```sql
-- Confirm auto_vacuum mode
PRAGMA auto_vacuum;
-- 0 = NONE, 1 = FULL, 2 = INCREMENTAL

-- Check current free pages
PRAGMA freelist_count;
```

---

## Related

- `d1-backup-point-in-time-recovery.md`
- `d1-batch-operations-performance.md`
- `sqlite-journal-modes.md`
- `sqlite-wal-mode.md`
- `sqlite-pragma-optimize-maintenance-budget.md`

---

## Sources

- https://www.sqlite.org/pragma.html#pragma_incremental_vacuum
- https://www.sqlite.org/pragma.html#pragma_auto_vacuum
- https://www.sqlite.org/lang_vacuum.html
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
