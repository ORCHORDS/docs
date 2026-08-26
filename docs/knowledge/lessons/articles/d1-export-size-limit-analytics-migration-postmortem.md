# D1 Export Size Limit Caused Analytics Migration to Fail Silently

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Analytics migration job ran for 40 minutes, reported success, but destination table
contained only the first ~4 000 rows out of 2.1 million. No error was surfaced to the
Worker; the D1 REST API returned HTTP 200 with a truncated result set and no
`next_cursor` field, so the migration loop believed it had finished.

---

## Context

D1 is a serverless SQLite database. The REST API (`/database/{id}/query`) caps each
HTTP response at **~10 MB of raw JSON**. When a result set exceeds that threshold,
the current API silently clips rows rather than returning a pagination cursor or a
4xx/5xx status. The SQL execution path also enforces a **30 s wall-clock timeout per
statement**. Both limits compound during large analytics exports that try to pull the
whole table in a single `SELECT *`.

This postmortem documents the root-cause analysis, the cursor-paginated migration
rewrite, and the alerting rule added to catch future silent truncations.

---

## The Incident Timeline

| Time  | Event |
|-------|-------|
| 09:14 | Migration Worker deployed; reads `events` table and writes to `analytics_v2`. |
| 09:54 | Worker logs "migration complete – 4 112 rows written". |
| 11:30 | Product reports analytics dashboard shows < 0.2 % of expected data. |
| 12:05 | Engineer queries D1 directly: `SELECT COUNT(*) FROM events` → 2 104 988. |
| 12:20 | Root cause confirmed: REST API truncated response; Worker never detected it. |

---

## Why the REST API Truncates Without an Error

```typescript
// What we assumed the API did on overflow:
// → throws an error or returns HTTP 413

// What it actually does (as of 2026-Q1 REST API):
interface D1Response<T> {
  success: boolean;
  result: [{ results: T[]; meta: QueryMeta }];
  errors: [];
  messages: [];
}
// `meta.rows_read` reflects ONLY rows included in the response, not the table total.
// There is no `truncated: true` flag and no continuation cursor in the raw REST path.
```

The D1 **Workers binding** (`env.DB.prepare(...).all()`) has the same row-count
behaviour but is subject to the 128 MB Worker memory limit; the REST API is subject
to its own 10 MB JSON envelope cap. Neither raises an exception on overflow.

---

## Safe Cursor-Paginated Export Pattern

Use `LIMIT` + `OFFSET`-free keyset pagination on a monotonic column so rows added
during the migration do not cause duplicates or gaps.

```typescript
// src/migrations/export-events.ts
import type { D1Database } from "@cloudflare/workers-types";

interface Event {
  id: number;
  occurred_at: string;
  payload: string;
}

const PAGE_SIZE = 500; // safe under both memory and response-size limits

export async function migrateEvents(
  src: D1Database,
  dst: D1Database,
): Promise<{ migrated: number }> {
  let lastId = 0;
  let totalMigrated = 0;
  let page = 0;

  const insertStmt = dst.prepare(
    "INSERT OR IGNORE INTO analytics_v2 (id, occurred_at, payload) VALUES (?, ?, ?)",
  );

  while (true) {
    const { results, meta } = await src
      .prepare(
        "SELECT id, occurred_at, payload FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
      )
      .bind(lastId, PAGE_SIZE)
      .all<Event>();

    if (results.length === 0) break;

    // Guard: if we somehow got fewer rows than PAGE_SIZE it might be the last page;
    // if we got exactly PAGE_SIZE there are likely more rows.
    console.log(`page=${page} rows=${results.length} rows_read=${meta.rows_read}`);

    // Validate: rows_read should equal results.length; a mismatch signals truncation.
    if (meta.rows_read !== results.length) {
      throw new Error(
        `Truncation detected on page ${page}: ` +
          `rows_read=${meta.rows_read} !== results.length=${results.length}`,
      );
    }

    // Batch insert using D1 batch API (max 100 statements per batch).
    const chunks = chunk(results, 100);
    for (const c of chunks) {
      await dst.batch(
        c.map((row) => insertStmt.bind(row.id, row.occurred_at, row.payload)),
      );
    }

    totalMigrated += results.length;
    lastId = results[results.length - 1].id;
    page++;
  }

  return { migrated: totalMigrated };
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
```

---

## Reconciliation Check After Migration

Never trust the migration loop's counter alone. Always run a count-based
reconciliation query before marking the job complete.

```typescript
// src/migrations/reconcile.ts
export async function reconcile(
  src: D1Database,
  dst: D1Database,
): Promise<void> {
  const [srcCount, dstCount] = await Promise.all([
    src.prepare("SELECT COUNT(*) AS n FROM events").first<{ n: number }>(),
    dst.prepare("SELECT COUNT(*) AS n FROM analytics_v2").first<{ n: number }>(),
  ]);

  if (!srcCount || !dstCount) throw new Error("reconcile: count query returned null");

  if (srcCount.n !== dstCount.n) {
    throw new Error(
      `Row count mismatch after migration: src=${srcCount.n} dst=${dstCount.n}`,
    );
  }

  console.log(`Migration verified: ${srcCount.n} rows in both tables.`);
}
```

---

## Worker Cron Entry Point

```typescript
// src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const { migrated } = await migrateEvents(env.SRC_DB, env.DST_DB);
    await reconcile(env.SRC_DB, env.DST_DB);
    console.log(`Cron migration complete: ${migrated} rows processed.`);
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **`SELECT * FROM big_table` without LIMIT** – the single-query approach is what
  caused the silent truncation. Never export unbounded result sets via the Workers
  binding or REST API.
- **Trusting the `success: true` field alone** – D1 REST always returns `success:
  true` if the SQL parsed and executed; it does not mean the result is complete.
- **Using OFFSET-based pagination** – OFFSET rescans from row 0 on each page;
  with millions of rows this becomes O(n²) and exceeds the 30 s statement timeout
  before reaching the end.
- **No reconciliation step** – migration loops that only track their own counter will
  silently under-count when any page is truncated.

---

## Gotchas

- `meta.rows_read` in the Workers binding counts rows **scanned** by SQLite, not rows
  returned to the caller. For a keyset query with a proper index, `rows_read` should
  equal `results.length`; a large discrepancy indicates a full-table scan.
- D1 Batch API accepts a maximum of **100 statements per `db.batch()` call**. Exceeding
  this throws `D1_ERROR: batch too large`.
- **Autoincrement gaps**: if the `id` column is `INTEGER PRIMARY KEY` (SQLite
  ROWID alias), deleted rows leave gaps. Keyset pagination still works; it just skips
  the deleted ids naturally.
- **Clock-based migration ordering**: if you paginate on `occurred_at` (a datetime
  string) rather than `id`, ties between two events with the same timestamp can
  cause rows to be skipped or duplicated. Always paginate on a unique, monotonic key.

---

## Verification

```bash
# After migration: compare row counts with wrangler d1 execute
npx wrangler d1 execute SRC_DB --command "SELECT COUNT(*) FROM events;"
npx wrangler d1 execute DST_DB --command "SELECT COUNT(*) FROM analytics_v2;"

# Spot-check a sample of rows for payload integrity
npx wrangler d1 execute SRC_DB \
  --command "SELECT id, occurred_at FROM events ORDER BY RANDOM() LIMIT 20;"
```

---

## Related

- `d1-write-contention-viral-event-postmortem.md`
- `d1-migration-rollback-failed-production-lesson.md`
- `d1-batch-size-limit-exceeded-postmortem.md`
- `cloudflare-storage-primitive-selection.md`

---

## Sources

- Cloudflare D1 documentation – Limits: https://developers.cloudflare.com/d1/platform/limits/
- Cloudflare D1 Workers Binding API reference
- Internal postmortem ticket #<number> (2026-03-11)
