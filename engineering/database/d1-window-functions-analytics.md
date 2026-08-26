# D1 Window Functions: Analytics Queries with OVER, PARTITION BY, ROW_NUMBER

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You need to add analytics to a Cloudflare Workers API backed by D1: running totals,
per-tenant leaderboards, percentile rankings, week-over-week comparisons, and
"top N per group" queries. A naive approach fetches all rows into the Worker and computes
these in JavaScript — wasteful, slow, and hitting D1 row limits. D1 runs SQLite 3.38+ which
ships full window function support. Computing analytics in the query layer is faster and
returns only the shaped result set.

---

## Context

Window functions were added to SQLite in version 3.25.0 (2018). D1 uses a recent SQLite
build (≥ 3.40 as of 2025) and supports the full window function vocabulary:

| Category | Functions |
|---|---|
| Ranking | `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `NTILE(n)` |
| Navigation | `LAG()`, `LEAD()`, `FIRST_VALUE()`, `LAST_VALUE()`, `NTH_VALUE()` |
| Aggregate | `SUM()`, `AVG()`, `COUNT()`, `MIN()`, `MAX()` (all with OVER) |

Unlike PostgreSQL, SQLite does not support `FILTER (WHERE …)` on window aggregates, and
some `ROWS BETWEEN` frame clauses have restrictions. These are noted per section.

---

## 1. ROW_NUMBER — Pagination with Stable Ranking

`ROW_NUMBER()` assigns a unique sequential integer to each row within a partition, ordered
by a deterministic column. Use it to implement "top N per group" without subqueries.

```typescript
// src/analytics/top-projects-per-tenant.ts

/**
 * Returns the top 3 projects by task count, per tenant.
 * Uses ROW_NUMBER() over a PARTITION BY tenant window.
 */
export async function topProjectsPerTenant(
  db: D1Database
): Promise<Array<{ tenant_id: string; project_id: string; task_count: number; rank: number }>> {
  const { results } = await db
    .prepare(
      `WITH project_counts AS (
         SELECT
           tenant_id,
           project_id,
           COUNT(*) AS task_count
         FROM tasks
         WHERE deleted_at IS NULL
         GROUP BY tenant_id, project_id
       ),
       ranked AS (
         SELECT
           tenant_id,
           project_id,
           task_count,
           ROW_NUMBER() OVER (
             PARTITION BY tenant_id
             ORDER BY task_count DESC
           ) AS rnk
         FROM project_counts
       )
       SELECT tenant_id, project_id, task_count, rnk AS rank
       FROM ranked
       WHERE rnk <= 3
       ORDER BY tenant_id, rnk`
    )
    .all();

  return results as any;
}
```

---

## 2. Running Totals with SUM() OVER

A running (cumulative) sum across time periods is a canonical window function use-case.
In D1, use the default frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

```typescript
// src/analytics/cumulative-tasks.ts

export interface DailyTaskStats {
  day: string;        // ISO date string
  created: number;    // tasks created that day
  cumulative: number; // running total
}

export async function cumulativeTaskCreation(
  db: D1Database,
  tenantId: string,
  days = 30
): Promise<DailyTaskStats[]> {
  const since = Math.floor(Date.now() / 1000) - days * 86_400;

  const { results } = await db
    .prepare(
      `WITH daily AS (
         SELECT
           date(created_at, 'unixepoch') AS day,
           COUNT(*) AS created
         FROM tasks
         WHERE tenant_id = ?
           AND created_at >= ?
           AND deleted_at IS NULL
         GROUP BY day
       )
       SELECT
         day,
         created,
         SUM(created) OVER (
           ORDER BY day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS cumulative
       FROM daily
       ORDER BY day`
    )
    .bind(tenantId, since)
    .all<DailyTaskStats>();

  return results;
}
```

> **D1 frame note**: `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` is the implicit
> default when you write `ORDER BY` inside `OVER()` without a frame clause in SQLite.
> Omitting the frame clause and relying on the default is safe.

---

## 3. LAG / LEAD — Period-over-Period Comparisons

`LAG()` accesses the value from a preceding row without a self-join. Use it for
week-over-week or month-over-month delta calculations.

```typescript
// src/analytics/week-over-week.ts

export interface WeeklyStats {
  week: string;
  tasks_created: number;
  prev_week: number | null;
  delta_pct: number | null;
}

export async function weekOverWeekGrowth(
  db: D1Database,
  tenantId: string
): Promise<WeeklyStats[]> {
  const { results } = await db
    .prepare(
      `WITH weekly AS (
         SELECT
           strftime('%Y-W%W', created_at, 'unixepoch') AS week,
           COUNT(*) AS tasks_created
         FROM tasks
         WHERE tenant_id = ?
           AND deleted_at IS NULL
         GROUP BY week
       )
       SELECT
         week,
         tasks_created,
         LAG(tasks_created, 1) OVER (ORDER BY week) AS prev_week,
         CASE
           WHEN LAG(tasks_created, 1) OVER (ORDER BY week) IS NULL THEN NULL
           WHEN LAG(tasks_created, 1) OVER (ORDER BY week) = 0     THEN NULL
           ELSE ROUND(
             (tasks_created - LAG(tasks_created, 1) OVER (ORDER BY week)) * 100.0
             / LAG(tasks_created, 1) OVER (ORDER BY week),
             2
           )
         END AS delta_pct
       FROM weekly
       ORDER BY week`
    )
    .bind(tenantId)
    .all<WeeklyStats>();

  return results;
}
```

---

## 4. RANK vs DENSE_RANK — Leaderboards

`RANK()` leaves gaps after ties; `DENSE_RANK()` does not.

```sql
-- Which users completed the most tasks this month?
-- DENSE_RANK so positions are contiguous even with ties
WITH user_completions AS (
  SELECT
    actor_id,
    COUNT(*) AS completed
  FROM audit_events
  WHERE tenant_id = ?
    AND action = 'task.completed'
    AND created_at >= strftime('%s', 'now', 'start of month')
  GROUP BY actor_id
)
SELECT
  actor_id,
  completed,
  DENSE_RANK() OVER (ORDER BY completed DESC) AS position,
  RANK()       OVER (ORDER BY completed DESC) AS rank_with_gaps
FROM user_completions
ORDER BY position
LIMIT 10;
```

```typescript
export interface LeaderboardEntry {
  actor_id: string;
  completed: number;
  position: number;
}

export async function monthlyLeaderboard(
  db: D1Database,
  tenantId: string
): Promise<LeaderboardEntry[]> {
  const { results } = await db
    .prepare(
      `WITH user_completions AS (
         SELECT actor_id, COUNT(*) AS completed
         FROM audit_events
         WHERE tenant_id = ?
           AND action = 'task.completed'
           AND created_at >= strftime('%s','now','start of month')
         GROUP BY actor_id
       )
       SELECT
         actor_id,
         completed,
         DENSE_RANK() OVER (ORDER BY completed DESC) AS position
       FROM user_completions
       ORDER BY position
       LIMIT 10`
    )
    .bind(tenantId)
    .all<LeaderboardEntry>();

  return results;
}
```

---

## 5. NTILE — Percentile Buckets

`NTILE(n)` divides rows into n equal-sized buckets. Use it to segment users or projects
into quartiles, deciles, or percentile bands.

```typescript
// Segment projects into performance quartiles by task completion rate
export async function projectQuartiles(
  db: D1Database,
  tenantId: string
): Promise<Array<{ project_id: string; completion_rate: number; quartile: number }>> {
  const { results } = await db
    .prepare(
      `WITH project_stats AS (
         SELECT
           project_id,
           COUNT(*) AS total,
           SUM(done) AS completed,
           ROUND(SUM(done) * 100.0 / COUNT(*), 2) AS completion_rate
         FROM tasks
         WHERE tenant_id = ?
           AND deleted_at IS NULL
         GROUP BY project_id
         HAVING COUNT(*) > 0
       )
       SELECT
         project_id,
         completion_rate,
         NTILE(4) OVER (ORDER BY completion_rate) AS quartile
       FROM project_stats
       ORDER BY completion_rate DESC`
    )
    .bind(tenantId)
    .all<{ project_id: string; completion_rate: number; quartile: number }>();

  return results;
}
```

---

## 6. FIRST_VALUE / LAST_VALUE — First and Latest Events per Group

Retrieve the first and last event per resource without a correlated subquery.

```typescript
export async function firstAndLastAction(
  db: D1Database,
  tenantId: string,
  resourceType: string
): Promise<Array<{ resource_id: string; first_action: string; last_action: string }>> {
  const { results } = await db
    .prepare(
      `SELECT DISTINCT
         resource_id,
         FIRST_VALUE(action) OVER w AS first_action,
         LAST_VALUE(action)  OVER w AS last_action
       FROM audit_events
       WHERE tenant_id = ? AND resource_type = ?
       WINDOW w AS (
         PARTITION BY resource_id
         ORDER BY created_at
         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       )
       ORDER BY resource_id`
    )
    .bind(tenantId, resourceType)
    .all<{ resource_id: string; first_action: string; last_action: string }>();

  return results;
}
```

> **LAST_VALUE frame warning**: `LAST_VALUE()` without an explicit frame extending to
> `UNBOUNDED FOLLOWING` returns the current row's value, not the last row in the partition.
> Always specify `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` when using
> `LAST_VALUE()`.

---

## D1-Specific Considerations

| Constraint | Detail |
|---|---|
| No `FILTER (WHERE …)` on window aggregates | SQLite does not support `COUNT(*) FILTER (WHERE done=1) OVER (…)`. Use `SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) OVER (…)` instead. |
| No `GROUPS` frame unit | SQLite supports `ROWS` and `RANGE` frames. `GROUPS` (added in SQLite 3.28) is available in recent D1 builds but test first. |
| Window function in WHERE | Illegal in SQL. Always wrap in a CTE or subquery, then filter in the outer query. |
| D1 result row limit | D1 returns up to 10,000 rows per query. For analytics over large datasets, pre-aggregate in a CTE before applying the window function. |
| `EXPLAIN QUERY PLAN` | Run `EXPLAIN QUERY PLAN SELECT …` against a local SQLite replica to check whether your window query triggers a temporary B-tree sort. |

---

## Anti-Patterns

- **Window function in WHERE clause**: `WHERE ROW_NUMBER() OVER (…) <= 3` is a syntax
  error. Use a CTE: `WITH ranked AS (… ROW_NUMBER() …) SELECT … FROM ranked WHERE rnk <= 3`.
- **Repeating the OVER clause**: Writing the same `OVER (PARTITION BY … ORDER BY …)` for
  multiple window functions in one SELECT. Use the `WINDOW` named-window clause to DRY it:
  ```sql
  SELECT a, SUM(a) OVER w, AVG(a) OVER w
  FROM t
  WINDOW w AS (PARTITION BY tenant_id ORDER BY created_at);
  ```
- **Fetching all rows to JavaScript and computing rank**: Defeats the purpose — do it in SQL.
- **Forgetting `DISTINCT` with LAST_VALUE**: Without `DISTINCT`, every row in the partition
  appears in the result set. Add `SELECT DISTINCT` or wrap in an outer query.

---

## Verification

```typescript
// tests/window-functions.test.ts
import { env } from 'cloudflare:test';

describe('window functions in D1', () => {
  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM tasks`);
    // Seed: project A has 3 tasks, project B has 1 task (same tenant)
    await env.DB.exec(`
      INSERT INTO tasks (id,tenant_id,project_id,title,done,created_at)
      VALUES
        ('t1','ten1','pA','Task 1',0,1000),
        ('t2','ten1','pA','Task 2',1,1001),
        ('t3','ten1','pA','Task 3',0,1002),
        ('t4','ten1','pB','Task 4',1,1003)
    `);
  });

  it('ROW_NUMBER ranks projects by task count', async () => {
    const { results } = await env.DB.prepare(
      `WITH counts AS (
         SELECT project_id, COUNT(*) AS cnt FROM tasks WHERE tenant_id='ten1' GROUP BY project_id
       )
       SELECT project_id, ROW_NUMBER() OVER (ORDER BY cnt DESC) AS rnk FROM counts`
    ).all();

    expect(results[0]).toMatchObject({ project_id: 'pA', rnk: 1 });
    expect(results[1]).toMatchObject({ project_id: 'pB', rnk: 2 });
  });

  it('SUM OVER produces running total', async () => {
    const { results } = await env.DB.prepare(
      `WITH daily AS (SELECT 1 AS day, 3 AS n UNION ALL SELECT 2, 1)
       SELECT day, SUM(n) OVER (ORDER BY day) AS running FROM daily`
    ).all<{ day: number; running: number }>();

    expect(results[0].running).toBe(3);
    expect(results[1].running).toBe(4);
  });
});
```

---

## Related

- `window-functions-patterns.md` — generic PostgreSQL window function patterns
- `d1-audit-event-log.md` — the audit_events table queried in leaderboard examples
- `d1-sqlite-query-optimization.md` — EXPLAIN QUERY PLAN for window queries
- `d1-full-text-search-fts5.md` — other advanced SQLite features in D1
- `cte-common-table-expressions.md` — CTEs used to wrap window functions

---

## Sources

- SQLite window functions documentation — https://www.sqlite.org/windowfunctions.html
- Cloudflare D1 SQLite version — https://developers.cloudflare.com/d1/platform/limits/
- SQLite NTILE documentation — https://www.sqlite.org/windowfunctions.html#ntile
- SQLite LAST_VALUE frame note — https://www.sqlite.org/windowfunctions.html#the_frame_specification
