# D1 Date/Time Storage, Functions, and Indexing in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to store timestamps in D1, filter rows by date range, compute
relative dates ("last 30 days", "next week"), and ensure queries against
date columns use an index rather than scanning every row.

## Context

SQLite has no native `TIMESTAMP` or `DATE` type. D1 inherits this; dates are
stored as TEXT (ISO 8601), INTEGER (Unix epoch seconds or milliseconds), or
REAL (Julian day number). SQLite ships a suite of built-in `date()`,
`time()`, `datetime()`, `julianday()`, `unixepoch()`, and `strftime()`
functions that operate on any of the three storage classes.

Choosing the right storage class and query pattern determines whether an
index is used or bypassed.

---

## Recommended Storage: ISO 8601 TEXT vs. INTEGER Epoch

### TEXT — ISO 8601 (UTC)

```sql
CREATE TABLE events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),  -- 'YYYY-MM-DD HH:MM:SS'
  event_date TEXT NOT NULL                              -- 'YYYY-MM-DD'
);
```

TEXT ISO 8601 sorts lexicographically in the correct chronological order,
so `ORDER BY created_at` and range comparisons work without function calls,
enabling B-tree index scans.

### INTEGER — Unix Milliseconds

```sql
CREATE TABLE events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL DEFAULT (
    CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER)
  )
);
```

Integer epoch milliseconds are compact, JS-friendly (`new Date(ms)`), and
equally indexable.

---

## Writing Timestamps from Workers

```typescript
// Option A: Let SQLite set the timestamp (server-side, UTC)
await env.DB.prepare(
  "INSERT INTO events (title) VALUES (?)"
).bind("Launch").run();

// Option B: Bind an ISO 8601 string from Workers (useful for back-dated records)
const now = new Date().toISOString().replace("T", " ").replace(/\.\d+Z$/, "");
// "2026-08-23 14:05:00"
await env.DB.prepare(
  "INSERT INTO events (title, created_at) VALUES (?, ?)"
).bind("Launch", now).run();

// Option C: Bind Unix milliseconds
const ms = Date.now();
await env.DB.prepare(
  "INSERT INTO events (title, created_at_ms) VALUES (?, ?)"
).bind("Launch", ms).run();
```

---

## Date Range Queries

### TEXT ISO 8601 — direct string comparison (index-friendly):

```typescript
async function getRecentEvents(
  db: D1Database,
  days: number
): Promise<{ id: number; title: string; created_at: string }[]> {
  const since = new Date(Date.now() - days * 86_400_000)
    .toISOString()
    .replace("T", " ")
    .slice(0, 19); // "YYYY-MM-DD HH:MM:SS"

  const { results } = await db.prepare(`
    SELECT id, title, created_at
    FROM events
    WHERE created_at >= ?
    ORDER BY created_at DESC
  `).bind(since).all();

  return results as { id: number; title: string; created_at: string }[];
}
```

### INTEGER epoch — arithmetic range:

```typescript
async function getRecentEventsMs(
  db: D1Database,
  days: number
): Promise<{ id: number; title: string; created_at_ms: number }[]> {
  const since = Date.now() - days * 86_400_000;
  const { results } = await db.prepare(`
    SELECT id, title, created_at_ms
    FROM events
    WHERE created_at_ms >= ?
    ORDER BY created_at_ms DESC
  `).bind(since).all();
  return results as { id: number; title: string; created_at_ms: number }[];
}
```

---

## SQLite Date Functions

```typescript
// Current UTC date parts
const { results } = await env.DB.prepare(`
  SELECT
    date('now')                            AS today,
    datetime('now')                        AS now_utc,
    strftime('%Y-%m', 'now')               AS current_month,
    strftime('%W', 'now')                  AS week_number,
    unixepoch('now')                       AS epoch_seconds,
    julianday('now')                       AS julian_day
`).all();

// Relative date arithmetic
const { results: relative } = await env.DB.prepare(`
  SELECT
    date('now', '-30 days')                AS thirty_days_ago,
    date('now', '+7 days')                 AS next_week,
    date('now', 'start of month')          AS month_start,
    date('now', 'start of month', '+1 month', '-1 day') AS month_end
`).all();
```

### Computing Age / Difference Between Two Dates

```typescript
const { results } = await env.DB.prepare(`
  SELECT
    id,
    title,
    CAST(
      (julianday('now') - julianday(created_at)) AS INTEGER
    ) AS age_days
  FROM events
  ORDER BY age_days ASC
`).all<{ id: number; title: string; age_days: number }>();
```

---

## Indexing Date Columns

### Standard B-tree index on TEXT ISO 8601:

```sql
CREATE INDEX idx_events_created_at ON events (created_at);
```

Range queries `WHERE created_at >= ? AND created_at < ?` use this index
directly because ISO 8601 strings sort correctly.

### Partial index for recent data (performance optimisation):

```sql
-- Index only rows from the last year; older rows excluded
CREATE INDEX idx_events_recent
  ON events (created_at)
  WHERE created_at >= date('now', '-1 year');
```

Note: SQLite evaluates the WHERE clause at index-creation time for the
initial build, but the partial index boundary does **not** shift as time
passes. Rebuild the partial index periodically via a Cron Trigger if
selectivity degrades.

### Expression index for month-level grouping:

```sql
CREATE INDEX idx_events_month
  ON events (strftime('%Y-%m', created_at));
```

```typescript
// Hits the expression index
const { results } = await env.DB.prepare(`
  SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS n
  FROM events
  WHERE strftime('%Y-%m', created_at) = ?
  GROUP BY month
`).bind("2026-08").all<{ month: string; n: number }>();
```

---

## Timezone Handling

SQLite `datetime('now')` is always UTC. There is no timezone-aware type.
Best practice:

1. Store all timestamps as UTC in D1.
2. Convert to the user's local timezone in Workers/TypeScript using
   `Intl.DateTimeFormat` or a library like `date-fns-tz`.

```typescript
function toUserTimezone(isoUtc: string, tz: string): string {
  const date = new Date(isoUtc.replace(" ", "T") + "Z");
  return new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

const display = toUserTimezone("2026-08-23 14:05:00", "America/New_York");
// "Aug 23, 2026, 10:05 AM"
```

---

## Anti-patterns

- **Storing dates as locale-formatted strings** (`"08/23/2026"`): breaks
  chronological sorting and range comparisons. Always use ISO 8601.
- **Applying `strftime()` to a column inside a WHERE clause without an
  expression index**: wrapping a plain column in a function defeats the B-tree
  index. Use `WHERE created_at >= ? AND created_at < ?` with ISO 8601 strings.
- **Using `REAL` Julian day storage for most use-cases**: Julian day arithmetic
  is error-prone; TEXT and INTEGER are both preferable for typical CRUD.
- **Storing timestamps in the user's local timezone**: complicates range
  queries and daylight-saving transitions. Store UTC, display locally.
- **Partial indexes with `date('now', ...)` in the WHERE clause**: the boundary
  is fixed at index creation, not evaluated on every query. Misleads query
  planning over time.

---

## Gotchas

- `datetime('now')` in a `DEFAULT` clause is evaluated at row-insert time by
  SQLite, not at table-creation time — this is correct behaviour.
- `unixepoch('now')` returns seconds, not milliseconds. Multiply by 1000 or
  store as `CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER)` for ms.
- Workers `Date.now()` returns UTC milliseconds; `new Date().toISOString()`
  returns `"YYYY-MM-DDTHH:MM:SS.mmmZ"`. Strip the `T` and trailing milliseconds
  before binding if storing as SQLite `datetime()` format.
- `strftime` format codes differ from JavaScript's `Intl` — `%W` is ISO week
  number in SQLite vs. Intl's `{ week: 'numeric' }`.

---

## Verification

```typescript
// Confirm TEXT ISO 8601 range query uses index
const plan = await env.DB.prepare(`
  EXPLAIN QUERY PLAN
  SELECT id FROM events
  WHERE created_at >= '2026-01-01' AND created_at < '2027-01-01'
`).all();
// Expect "USING INDEX idx_events_created_at" in the detail

// Round-trip: insert and read back a known timestamp
const ts = "2026-08-23 10:00:00";
await env.DB.prepare(
  "INSERT INTO events (title, created_at) VALUES ('test', ?)"
).bind(ts).run();
const row = await env.DB.prepare(
  "SELECT created_at FROM events WHERE title = 'test' LIMIT 1"
).first<{ created_at: string }>();
console.assert(row?.created_at === ts, "Timestamp round-trip mismatch");
```

---

## Related

- `d1-expression-index-function-based-workers.md`
- `d1-partial-index-filtered-queries-workers.md`
- `d1-covering-index-composite-key-workers.md`
- `d1-time-series-partitioning.md`
- `timestamp-timezone-handling.md`

---

## Sources

- SQLite date and time functions: https://www.sqlite.org/lang_datefunc.html
- SQLite expression indexes: https://www.sqlite.org/expridx.html
- Cloudflare D1 Workers API: https://developers.cloudflare.com/d1/worker-api/
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
