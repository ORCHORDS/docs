# D1 SQLite INTEGER Overflow Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A high-throughput event-tracking service stored sequential row IDs as SQLite `INTEGER PRIMARY KEY`. After approximately 2.1 billion inserts the ID column silently wrapped to negative values, causing foreign-key joins to produce empty result sets and a downstream reporting dashboard to show zero events for all new records.

## Context
SQLite's `INTEGER PRIMARY KEY` with `AUTOINCREMENT` is a 64-bit signed integer, range −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807. Without `AUTOINCREMENT`, SQLite reuses the highest existing rowid + 1; with `AUTOINCREMENT`, it refuses to insert when the max is reached. The service used neither idiom correctly: it used `ROWID` aliasing without `AUTOINCREMENT`, which recycled IDs after the table was periodically truncated. After a partial truncation left a gap with the highest rowid at 2,147,483,647 (max 32-bit signed), a legacy ORM cast the returned ID to a JavaScript 32-bit integer via `>>> 0`, producing a signed overflow. D1 itself was not at fault; the bug lived in the TypeScript layer.

---

## Root Cause Analysis

```sql
-- Original schema (WRONG — relies on implicit rowid recycling)
CREATE TABLE events (
  id    INTEGER PRIMARY KEY,   -- aliased to rowid, NOT AUTOINCREMENT
  ts    INTEGER NOT NULL,
  kind  TEXT    NOT NULL,
  payload TEXT
);
```

The ORM binding returned `id` as a JavaScript `number`. When id > 2^31 − 1, a bitwise coercion in a helper function flipped the sign:

```typescript
// lib/db-helpers.ts — BUGGY
function toId(raw: unknown): number {
  // WRONG: >>> 0 coerces to Uint32, then unary - produces Int32 range
  return (raw as number) >>> 0;  // 2147483648 >>> 0 === 2147483648 (fine)
                                  // 2147483649 >>> 0 === 2147483649 (fine)
                                  // ... but later subtracted from Int32 comparisons
}
```

The real breakage was in a JOIN condition that used the coerced ID:

```typescript
// lib/event-repo.ts — BUGGY
async function getEventById(db: D1Database, rawId: unknown) {
  const id = toId(rawId); // silently produces wrong value above 2^31 - 1
  const result = await db.prepare(
    "SELECT * FROM events WHERE id = ?"
  ).bind(id).first();
  return result;
}
```

---

## Correct Pattern

### 1. Use TEXT UUIDs or explicit BIGINT-safe handling

```sql
-- OPTION A: UUID primary key — no overflow possible
CREATE TABLE events (
  id      TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  ts      INTEGER NOT NULL,
  kind    TEXT    NOT NULL,
  payload TEXT
);

-- OPTION B: Keep integer PK but use AUTOINCREMENT and TEXT in application layer
CREATE TABLE events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      INTEGER NOT NULL,
  kind    TEXT    NOT NULL,
  payload TEXT
);
```

### 2. Return IDs as strings at the D1 boundary

```typescript
// lib/event-repo.ts — FIXED
interface EventRow {
  id: string;   // treat as opaque string, never cast to number
  ts: number;
  kind: string;
  payload: string | null;
}

async function insertEvent(
  db: D1Database,
  kind: string,
  payload: string
): Promise<string> {
  const result = await db.prepare(
    "INSERT INTO events (ts, kind, payload) VALUES (?, ?, ?) RETURNING id"
  ).bind(Date.now(), kind, payload).first<{ id: string }>();

  if (!result) throw new Error("Insert returned no row");
  // id is now a string — never coerce with >>> 0 or parseInt without BigInt
  return result.id;
}

async function getEventById(db: D1Database, id: string): Promise<EventRow | null> {
  return db.prepare(
    "SELECT id, ts, kind, payload FROM events WHERE id = ?"
  ).bind(id).first<EventRow>();
}
```

### 3. Add a schema-level guard migration

```sql
-- migration/003_add_id_range_check.sql
-- Prevent future tables from accidentally using bare INTEGER PK without AUTOINCREMENT
-- Add a check constraint that will alert before silent overflow
ALTER TABLE events ADD COLUMN id_overflow_sentinel INTEGER
  GENERATED ALWAYS AS (CASE WHEN id > 9000000000000000000 THEN 1 ELSE 0 END) VIRTUAL;

-- Separately: monitor max(id) via a scheduled Worker
```

### 4. Monitoring Worker (scheduled)

```typescript
// workers/id-overflow-monitor.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const row = await env.DB.prepare(
      "SELECT MAX(id) as max_id FROM events"
    ).first<{ max_id: number | null }>();

    const maxId = row?.max_id ?? 0;
    const dangerThreshold = 9_000_000_000_000_000_000; // 9e18, ~90% of INT64 max

    if (maxId > dangerThreshold) {
      await env.ALERT_QUEUE.send({
        level: "critical",
        message: `events.id approaching INT64 max: ${maxId}`,
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns
- Using `>>> 0` or `| 0` on values that may represent SQLite `INTEGER` IDs — these are 64-bit but JS bitwise ops truncate to 32-bit.
- Relying on `ROWID` recycling as an implicit identity generator.
- Storing large integer IDs as JavaScript `number` — safe integer range is only ±2^53 − 1, and D1 returns integers as `number` by default.
- Using `parseInt(id, 10)` without checking `Number.isSafeInteger`.
- Omitting `AUTOINCREMENT` when you care about monotonicity; without it, SQLite may reuse deleted rowids.

## Gotchas
- D1 returns `INTEGER` columns as JavaScript `number`, which loses precision above 2^53 − 1. Values between 2^53 and 2^63 − 1 are silently rounded.
- `AUTOINCREMENT` prevents rowid reuse but also prevents SQLite from recycling gaps — tables that delete heavily will exhaust the 64-bit space faster than expected in extreme cases.
- SQLite `WITHOUT ROWID` tables have different ID semantics; the overflow risk still applies to any `INTEGER PRIMARY KEY` column.
- A table truncated with `DELETE FROM events` (not `DROP TABLE`) does NOT reset the autoincrement counter.
- Foreign keys referencing the overflowed ID column silently return no rows rather than raising an error.

## Verification

```sql
-- Check current max ID
SELECT MAX(id) as max_id, COUNT(*) as row_count FROM events;

-- Verify no negative IDs exist (post-incident check)
SELECT COUNT(*) as negative_ids FROM events WHERE id < 0;

-- Confirm AUTOINCREMENT is in use
SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name = 'events';
-- sql should contain AUTOINCREMENT if set
```

```bash
# Verify RETURNING id gives string in your TS layer
wrangler d1 execute <DB_NAME> --command \
  "INSERT INTO events (ts, kind, payload) VALUES (1234567890, 'test', 'x') RETURNING id"
```

## Related
- `d1-write-contention-viral-event-postmortem.md`
- `d1-schema-migration-table-lock-peak-traffic-postmortem.md`
- `d1-migration-rollback-failed-production-lesson.md`
- `silent-data-loss-partial-writes.md`
- `d1-time-travel-bookmark-expired-recovery-failed.md`

## Sources
- https://www.sqlite.org/autoinc.html
- https://www.sqlite.org/datatype3.html#type_affinity
- https://developers.cloudflare.com/d1/platform/client-api/#return-object
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/isSafeInteger
- https://sqlite.org/rowidtable.html
