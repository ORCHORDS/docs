# D1 Generated Columns for Computed Fields in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker extracts a value from a JSON payload column on every read, or concatenates first and last name before every lookup. These repetitive transformations add CPU cycles in the Worker and cannot be indexed. SQLite 3.31 (available in D1) introduced generated columns — computed fields defined once in the schema and usable in queries and indexes without application-side calculation.

## Context

A generated column's expression is evaluated automatically by SQLite on every insert or update (for `STORED`) or on every read (for `VIRTUAL`). Because the expression lives in the schema, you can create a regular index on a generated column and run `WHERE generated_col = ?` queries that the planner resolves with an index scan instead of a full-table scan. D1 Workers benefit doubly: the edge instance does less CPU work per request, and the result set can be narrowed entirely in SQL before network transfer.

## STORED vs VIRTUAL Trade-offs

```sql
-- STORED: the computed value is written to disk on every INSERT/UPDATE.
-- Costs extra write I/O and storage but can be indexed and is free on reads.
CREATE TABLE IF NOT EXISTS events (
  id          TEXT PRIMARY KEY,
  payload     TEXT NOT NULL,          -- raw JSON, e.g. {"amount": 4999, "currency": "usd"}
  amount_cents INTEGER
    GENERATED ALWAYS AS (CAST(json_extract(payload, '$.amount') AS INTEGER))
    STORED,
  currency    TEXT
    GENERATED ALWAYS AS (json_extract(payload, '$.currency'))
    STORED,
  created_at  INTEGER NOT NULL
);

-- Index on a STORED generated column — works exactly like a regular index
CREATE INDEX IF NOT EXISTS idx_events_amount ON events(amount_cents);
CREATE INDEX IF NOT EXISTS idx_events_currency_amount ON events(currency, amount_cents);

-- VIRTUAL: no extra storage. The expression re-runs on every read.
-- Cannot be indexed, but avoids write overhead for rarely queried columns.
CREATE TABLE IF NOT EXISTS contacts (
  id         TEXT PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name  TEXT NOT NULL,
  full_name  TEXT
    GENERATED ALWAYS AS (first_name || ' ' || last_name)
    VIRTUAL,           -- free on disk, computed on SELECT
  email      TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
```

## Indexing Generated Columns for Fast Lookups

```sql
-- STORED full_name for indexable search — trade storage for index speed
CREATE TABLE IF NOT EXISTS staff (
  id         TEXT PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name  TEXT NOT NULL,
  full_name  TEXT
    GENERATED ALWAYS AS (lower(first_name) || ' ' || lower(last_name))
    STORED,
  department TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staff_full_name ON staff(full_name);
CREATE INDEX IF NOT EXISTS idx_staff_dept_name ON staff(department, full_name);

-- Now this query uses the index instead of a full scan
-- EXPLAIN QUERY PLAN: SEARCH staff USING INDEX idx_staff_full_name (full_name=?)
SELECT id, first_name, last_name, department
FROM staff
WHERE full_name = 'alice smith'
LIMIT 10;
```

## Workers Query Patterns

```typescript
import { Env } from './types';

type EventRow = {
  id: string;
  amount_cents: number;
  currency: string;
  created_at: number;
};

type StaffRow = {
  id: string;
  first_name: string;
  last_name: string;
  department: string;
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Query using the generated amount_cents column — no JSON parsing in Worker
    if (url.pathname === '/events/high-value') {
      const threshold = parseInt(url.searchParams.get('min_cents') ?? '10000', 10);
      const currency = url.searchParams.get('currency') ?? 'usd';

      const { results } = await env.DB.prepare(
        `SELECT id, amount_cents, currency, created_at
         FROM events
         WHERE currency = ?
           AND amount_cents >= ?
         ORDER BY amount_cents DESC
         LIMIT 100`
      )
        .bind(currency, threshold)
        .all<EventRow>();

      return Response.json(results);
    }

    // Full-name search using generated + indexed column
    if (url.pathname === '/staff/search') {
      const query = (url.searchParams.get('q') ?? '').toLowerCase().trim();

      // Prefix search on the indexed generated full_name column
      const { results } = await env.DB.prepare(
        `SELECT id, first_name, last_name, department
         FROM staff
         WHERE full_name LIKE ?
         ORDER BY full_name
         LIMIT 20`
      )
        .bind(`${query}%`)
        .all<StaffRow>();

      return Response.json(results);
    }

    // Reading a VIRTUAL generated column — no extra storage cost
    if (url.pathname === '/contacts') {
      const { results } = await env.DB.prepare(
        `SELECT id, full_name, email FROM contacts LIMIT 50`
      ).all<{ id: string; full_name: string; email: string }>();

      return Response.json(results);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## VIRTUAL vs STORED Decision Guide

| Criterion | VIRTUAL | STORED |
|---|---|---|
| Can be indexed? | No | Yes |
| Storage cost | None | Same as a regular column |
| Write overhead | None | Evaluated on every INSERT/UPDATE |
| Best for | Simple display transforms | Filterable / sortable fields |
| JSON extraction | Only if rarely queried | Use when filtering/sorting on it |

## Anti-patterns

- **VIRTUAL column in a WHERE clause without an index** — A `WHERE virtual_col = ?` forces a full-table scan because VIRTUAL columns cannot be indexed; switch to STORED if you need to filter on it.
- **Mutating a generated column** — `INSERT INTO t (generated_col) VALUES (...)` raises an error; generated columns are read-only. Omit them from INSERT/UPDATE statements.
- **Complex non-deterministic expressions** — Expressions using `random()`, `datetime('now')`, or `strftime` are not allowed in generated columns because SQLite requires deterministic expressions.
- **Forgetting to cast JSON numerics** — `json_extract` returns a JSON type; always `CAST(... AS INTEGER)` or `CAST(... AS REAL)` for numeric generated columns to ensure correct index behaviour.

## Gotchas

- Generated columns require SQLite 3.31.0+. Verify via `SELECT sqlite_version();` in the D1 console — D1 ships a recent SQLite build.
- You cannot reference other generated columns in a generated column expression.
- `PRAGMA table_info(t)` shows generated columns with type `GENERATED ALWAYS`; use `PRAGMA table_xinfo(t)` to see the full expression.
- A `STORED` generated column occupies space in the row and affects D1 storage billing like any other column.
- Generated columns are not included in `SELECT *` results unless explicitly listed — always name them in the `SELECT` list.

## Verification

```bash
# Create table with generated columns
wrangler d1 execute example project-db \
  --command "
    CREATE TABLE IF NOT EXISTS events (
      id TEXT PRIMARY KEY,
      payload TEXT NOT NULL,
      amount_cents INTEGER GENERATED ALWAYS AS (CAST(json_extract(payload, '$.amount') AS INTEGER)) STORED,
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_amount ON events(amount_cents);
  "

# Insert a test row (omit the generated column)
wrangler d1 execute example project-db \
  --command "INSERT INTO events VALUES ('e1', '{\"amount\":4999}', unixepoch());"

# Verify the generated column was populated
wrangler d1 execute example project-db \
  --command "SELECT id, amount_cents FROM events;"
# Expected: e1 | 4999

# Confirm the index is used
wrangler d1 execute example project-db \
  --command "EXPLAIN QUERY PLAN SELECT id FROM events WHERE amount_cents >= 1000;"
# Expected: SEARCH events USING INDEX idx_events_amount
```

## Related

- `d1-partial-index-conditional-expressions-workers.md`
- `d1-online-schema-change-zero-downtime-workers.md`
- `d1-geospatial-bounding-box-query-workers.md`

## Sources

- SQLite Generated Columns — https://www.sqlite.org/gencol.html
- Cloudflare D1 Documentation — https://developers.cloudflare.com/d1/
- SQLite JSON Functions — https://www.sqlite.org/json1.html
