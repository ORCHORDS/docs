# D1 Aggregate FILTER Clause — Pivot Queries and Conditional Aggregation in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to count, sum, or average only the rows that match a specific predicate within a GROUP BY
— for example, a single query that returns both total orders and paid orders per customer, or a
weekly pivot that shows sales broken out by weekday. Without the `FILTER` clause you either run
multiple queries or use `CASE WHEN … ELSE NULL END` inside the aggregate, which is verbose and
harder to read. SQLite 3.25+ (shipped in D1) supports the SQL standard `FILTER (WHERE …)` clause
on every aggregate function.

## Context

The `FILTER` clause attaches a `WHERE` predicate to a single aggregate invocation, evaluated per
row before the aggregate accumulates the value. This is semantically equivalent to `CASE WHEN
condition THEN value ELSE NULL END` inside the aggregate, but is more readable and slightly more
efficient because the query planner can reason about it explicitly.

Supported aggregates in D1/SQLite: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `GROUP_CONCAT`,
`json_group_array`, `json_group_object`, and any window aggregate. `FILTER` works in both grouped
queries and window function contexts.

D1-specific notes:
- Results come back as JavaScript `number` for `SUM`/`AVG`; `null` when the filtered set is empty
  (not `0`) — always coerce in your TypeScript layer.
- `COUNT(*) FILTER (WHERE …)` returns `0` (not `null`) when no rows match — `COUNT` never returns
  null.
- `FILTER` predicates are not index-scannable in isolation; the outer `GROUP BY` index still drives
  the query plan.

## Basic Conditional Count and Sum

```sql
-- How many orders, how many paid, total revenue — all in one pass
SELECT
  customer_id,
  COUNT(*)                                   AS total_orders,
  COUNT(*) FILTER (WHERE status = 'paid')    AS paid_orders,
  SUM(amount) FILTER (WHERE status = 'paid') AS paid_revenue,
  AVG(amount) FILTER (WHERE status = 'paid') AS avg_paid_amount
FROM orders
GROUP BY customer_id;
```

```typescript
// src/analytics/customer-summary.ts
import type { D1Database } from "@cloudflare/workers-types";

interface CustomerSummary {
  customer_id: string;
  total_orders: number;
  paid_orders: number;
  paid_revenue: number | null;
  avg_paid_amount: number | null;
}

export async function getCustomerSummaries(
  db: D1Database
): Promise<CustomerSummary[]> {
  const { results } = await db
    .prepare(
      `SELECT
         customer_id,
         COUNT(*)                                   AS total_orders,
         COUNT(*) FILTER (WHERE status = 'paid')    AS paid_orders,
         SUM(amount) FILTER (WHERE status = 'paid') AS paid_revenue,
         AVG(amount) FILTER (WHERE status = 'paid') AS avg_paid_amount
       FROM orders
       GROUP BY customer_id
       ORDER BY paid_revenue DESC NULLS LAST`
    )
    .all<CustomerSummary>();

  return results.map((r) => ({
    ...r,
    paid_revenue: r.paid_revenue ?? 0,
    avg_paid_amount: r.avg_paid_amount ?? 0,
  }));
}
```

## Weekday Pivot Table

```sql
-- Revenue broken out by day of week — one row per product category
SELECT
  category,
  SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '1') AS monday,
  SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '2') AS tuesday,
  SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '3') AS wednesday,
  SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '4') AS thursday,
  SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '5') AS friday
FROM orders
WHERE ordered_at >= date('now', '-28 days')
GROUP BY category;
```

```typescript
// src/analytics/weekday-pivot.ts
import type { D1Database } from "@cloudflare/workers-types";

interface WeekdayPivotRow {
  category: string;
  monday: number | null;
  tuesday: number | null;
  wednesday: number | null;
  thursday: number | null;
  friday: number | null;
}

export async function getWeekdayPivot(
  db: D1Database,
  lookbackDays = 28
): Promise<WeekdayPivotRow[]> {
  const cutoff = new Date(Date.now() - lookbackDays * 86_400_000)
    .toISOString()
    .slice(0, 10);

  const { results } = await db
    .prepare(
      `SELECT
         category,
         SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '1') AS monday,
         SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '2') AS tuesday,
         SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '3') AS wednesday,
         SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '4') AS thursday,
         SUM(amount) FILTER (WHERE strftime('%w', ordered_at) = '5') AS friday
       FROM orders
       WHERE ordered_at >= ?
       GROUP BY category
       ORDER BY category`
    )
    .bind(cutoff)
    .all<WeekdayPivotRow>();

  return results;
}
```

## FILTER with json_group_array

```sql
-- Return active and archived tags separately, grouped per item
SELECT
  item_id,
  json_group_array(tag) FILTER (WHERE active = 1) AS active_tags,
  json_group_array(tag) FILTER (WHERE active = 0) AS archived_tags
FROM item_tags
GROUP BY item_id;
```

```typescript
// src/analytics/item-tags.ts
import type { D1Database } from "@cloudflare/workers-types";

interface ItemTagRow {
  item_id: string;
  active_tags: string;   // JSON array string
  archived_tags: string;
}

interface ItemTagsParsed {
  item_id: string;
  active_tags: string[];
  archived_tags: string[];
}

export async function getItemTagsSplit(
  db: D1Database
): Promise<ItemTagsParsed[]> {
  const { results } = await db
    .prepare(
      `SELECT
         item_id,
         json_group_array(tag) FILTER (WHERE active = 1) AS active_tags,
         json_group_array(tag) FILTER (WHERE active = 0) AS archived_tags
       FROM item_tags
       GROUP BY item_id`
    )
    .all<ItemTagRow>();

  return results.map((r) => ({
    item_id: r.item_id,
    active_tags: JSON.parse(r.active_tags ?? "[]") as string[],
    archived_tags: JSON.parse(r.archived_tags ?? "[]") as string[],
  }));
}
```

## FILTER in Window Functions

```typescript
// src/analytics/running-paid.ts
import type { D1Database } from "@cloudflare/workers-types";

interface RunningPaidRow {
  ordered_at: string;
  amount: number;
  running_paid: number | null;
}

// Running sum of paid orders only, ordered by date
export async function getRunningPaidTotal(
  db: D1Database,
  customerId: string
): Promise<RunningPaidRow[]> {
  const { results } = await db
    .prepare(
      `SELECT
         ordered_at,
         amount,
         SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END)
           OVER (ORDER BY ordered_at ROWS UNBOUNDED PRECEDING)
           AS running_paid
       FROM orders
       WHERE customer_id = ?
       ORDER BY ordered_at`
      // Note: SQLite window functions do not support FILTER directly;
      // use CASE WHEN inside the aggregate as shown above for windows.
    )
    .bind(customerId)
    .all<RunningPaidRow>();

  return results;
}
```

## Dynamic Pivot Builder (TypeScript)

```typescript
// src/analytics/dynamic-pivot.ts
import type { D1Database } from "@cloudflare/workers-types";

// Build a pivot query dynamically from a list of category values
export async function buildPivot(
  db: D1Database,
  pivotColumn: string,
  pivotValues: string[],
  measureColumn: string,
  groupByColumn: string,
  tableName: string
): Promise<Record<string, unknown>[]> {
  // Sanitise identifiers — never interpolate user input directly
  const safeId = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const cols = pivotValues
    .map(
      (v) =>
        `SUM(${safeId(measureColumn)}) FILTER (WHERE ${safeId(pivotColumn)} = '${v.replace(/'/g, "''")}') AS ${safeId(v)}`
    )
    .join(",\n  ");

  const sql = `
    SELECT ${safeId(groupByColumn)}, ${cols}
    FROM ${safeId(tableName)}
    GROUP BY ${safeId(groupByColumn)}
  `;

  const { results } = await db.prepare(sql).all<Record<string, unknown>>();
  return results;
}
```

## Anti-patterns

- **Using multiple `SELECT` statements instead of one `FILTER`** — separate queries require
  multiple round trips to D1; a single `FILTER` query is always faster.
- **`SUM(CASE WHEN … THEN val ELSE 0 END)`** — the `ELSE 0` causes `SUM` to return `0` even when
  no rows match, which hides missing data; use `FILTER` with `ELSE NULL` (default) to get `null`
  for truly absent groups.
- **Window `FILTER` in SQLite** — SQLite does not support the `FILTER` clause on window function
  calls (only on plain aggregates). Use `CASE WHEN … ELSE NULL END` inside the window aggregate
  instead.
- **Injecting pivot column values as raw SQL** — always parameterise or escape; D1's `bind()` API
  does not support dynamic column names, so sanitise identifiers carefully in builder functions.

## Gotchas

- `COUNT(*) FILTER (WHERE …)` returns `0` when nothing matches; other aggregates return `null`.
  Coerce to `0` in TypeScript only when `null` and `0` are semantically equivalent.
- `json_group_array() FILTER (WHERE …)` returns `'[]'` (the string) when no rows match — not
  `null` and not an empty result. Parse it with `JSON.parse` on the TypeScript side.
- `strftime('%w', col)` returns `'0'` for Sunday — it is a string `'0'`, not the integer `0`;
  always compare as string in FILTER predicates.
- Results with many pivot columns can exceed D1's single-row 1 MB limit if `json_group_array`
  columns accumulate large arrays; paginate or limit lookback windows.

## Verification

```bash
# Run a quick FILTER pivot via Wrangler
wrangler d1 execute myapp --command \
  "SELECT status,
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE amount > 100) AS high_value
   FROM orders GROUP BY status;"
```

```typescript
// test/filter-aggregate.test.ts
import { expect, it, beforeAll } from "vitest";
import { env } from "cloudflare:test";

beforeAll(async () => {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS orders (
      id TEXT PRIMARY KEY, status TEXT, amount REAL, ordered_at TEXT
    );
    INSERT OR IGNORE INTO orders VALUES
      ('a', 'paid', 150, '2026-08-01'),
      ('b', 'pending', 50, '2026-08-02'),
      ('c', 'paid', 80, '2026-08-03');
  `);
});

it("counts only paid high-value orders", async () => {
  const row = await env.DB.prepare(
    `SELECT COUNT(*) FILTER (WHERE status = 'paid' AND amount > 100) AS n FROM orders`
  ).first<{ n: number }>();
  expect(row?.n).toBe(1);
});
```

## Related

- `d1-window-functions-analytics.md`
- `d1-json-aggregation-analytics.md`
- `d1-cte-common-table-expressions.md`
- `d1-exists-vs-in-subquery-performance.md`

## Sources

- SQLite aggregate FILTER clause: https://www.sqlite.org/lang_aggfunc.html
- SQL standard FILTER syntax (ISO/IEC 9075): https://www.iso.org/standard/63556.html
- Cloudflare D1 supported SQL: https://developers.cloudflare.com/d1/reference/sql-api/
- SQLite window functions (CASE workaround): https://www.sqlite.org/windowfunctions.html
