# D1 Triggers Data Validation Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Business rules that must hold across every write path — a `price` that must be positive, a `status` that must follow a state machine, an `end_date` that must be after `start_date` — are scattered across Worker handlers, ORMs, and migration scripts. A new handler skips a check, and invalid data lands in D1. You want the database to enforce invariants regardless of how the write originates.

## Context

D1 is built on SQLite 3.x, which supports `BEFORE` and `AFTER` triggers that fire on `INSERT`, `UPDATE`, and `DELETE`. Triggers can raise errors via `SELECT RAISE(ABORT, 'message')`, halting the statement and rolling back the transaction. This enforces invariants at the storage layer — no Worker code path can bypass them. Use triggers for **cross-column and cross-table rules** that `CHECK` constraints cannot express, and for state-machine transitions where you need to inspect the old value (`OLD.*`).

Note: `CHECK` constraints (covered separately) are simpler and preferred for single-column domain rules. Triggers add power for multi-column or stateful validation.

## Schema with Trigger-Enforced State Machine

```sql
CREATE TABLE subscriptions (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  status      TEXT NOT NULL CHECK(status IN ('trial','active','paused','cancelled')),
  trial_ends  TEXT,
  plan_id     TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

-- Allowed transitions: trial→active, active→paused, paused→active, *→cancelled
CREATE TRIGGER trg_subscriptions_status_transition
BEFORE UPDATE OF status ON subscriptions
FOR EACH ROW
WHEN NEW.status != OLD.status
BEGIN
  SELECT RAISE(ABORT, 'Invalid status transition')
  WHERE NOT (
       (OLD.status = 'trial'     AND NEW.status IN ('active', 'cancelled'))
    OR (OLD.status = 'active'    AND NEW.status IN ('paused', 'cancelled'))
    OR (OLD.status = 'paused'    AND NEW.status IN ('active', 'cancelled'))
    OR (OLD.status = 'cancelled' AND 0=1)   -- terminal state, no exit
  );
END;
```

## Cross-Column Date Range Validation

```sql
CREATE TABLE campaigns (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  starts_at  TEXT NOT NULL,
  ends_at    TEXT NOT NULL
);

-- Enforce ends_at > starts_at on insert and update
CREATE TRIGGER trg_campaigns_date_range_insert
BEFORE INSERT ON campaigns
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'ends_at must be after starts_at')
  WHERE NEW.ends_at <= NEW.starts_at;
END;

CREATE TRIGGER trg_campaigns_date_range_update
BEFORE UPDATE OF starts_at, ends_at ON campaigns
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'ends_at must be after starts_at')
  WHERE NEW.ends_at <= NEW.starts_at;
END;
```

## Enforcing Numeric Business Rules

```sql
CREATE TABLE order_items (
  id          TEXT PRIMARY KEY,
  order_id    TEXT NOT NULL,
  unit_price  INTEGER NOT NULL,   -- cents
  quantity    INTEGER NOT NULL,
  discount    INTEGER NOT NULL DEFAULT 0
);

CREATE TRIGGER trg_order_items_validate
BEFORE INSERT ON order_items
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'unit_price must be positive')
  WHERE NEW.unit_price <= 0;

  SELECT RAISE(ABORT, 'quantity must be between 1 and 9999')
  WHERE NEW.quantity < 1 OR NEW.quantity > 9999;

  SELECT RAISE(ABORT, 'discount cannot exceed unit_price')
  WHERE NEW.discount > NEW.unit_price;
END;
```

## Deploying Triggers in D1 Migrations

```typescript
// migrations/0009_add_validation_triggers.sql
export const triggerMigration = `
-- Drop-and-recreate pattern for idempotency
DROP TRIGGER IF EXISTS trg_subscriptions_status_transition;
CREATE TRIGGER trg_subscriptions_status_transition
BEFORE UPDATE OF status ON subscriptions
FOR EACH ROW
WHEN NEW.status != OLD.status
BEGIN
  SELECT RAISE(ABORT, 'Invalid status transition')
  WHERE NOT (
       (OLD.status = 'trial'  AND NEW.status IN ('active', 'cancelled'))
    OR (OLD.status = 'active' AND NEW.status IN ('paused', 'cancelled'))
    OR (OLD.status = 'paused' AND NEW.status IN ('active', 'cancelled'))
  );
END;
`;
```

Run via Wrangler migrations or directly:

```typescript
// src/migrate.ts
export async function applyTriggers(db: D1Database): Promise<void> {
  // D1 exec() runs multi-statement SQL in a single call
  await db.exec(triggerMigration);
}
```

## Catching Validation Errors in Workers

```typescript
// src/handlers/subscriptions.ts
interface Env { DB: D1Database }

export async function cancelSubscription(
  env: Env,
  subscriptionId: string
): Promise<Response> {
  try {
    const result = await env.DB
      .prepare(`
        UPDATE subscriptions
        SET status = 'cancelled', updated_at = ?
        WHERE id = ?
      `)
      .bind(new Date().toISOString(), subscriptionId)
      .run();

    if (result.meta.changes === 0) {
      return Response.json({ error: 'Subscription not found' }, { status: 404 });
    }
    return Response.json({ ok: true });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('Invalid status transition')) {
      return Response.json(
        { error: 'Subscription cannot be cancelled from its current state' },
        { status: 422 }
      );
    }
    throw err; // re-throw unexpected errors
  }
}
```

## Listing Installed Triggers for Audit

```typescript
export async function listTriggers(
  db: D1Database
): Promise<Array<{ name: string; tbl_name: string; sql: string }>> {
  const { results } = await db
    .prepare(`
      SELECT name, tbl_name, sql
      FROM sqlite_master
      WHERE type = 'trigger'
      ORDER BY tbl_name, name
    `)
    .all<{ name: string; tbl_name: string; sql: string }>();
  return results;
}
```

## Anti-patterns

- **Putting all validation only in Worker code**: a direct D1 SQL API call, a migration seed, or a future Worker endpoint can bypass application-layer checks. Triggers are the last line of defence.
- **Using `AFTER` triggers for constraint enforcement**: by the time an `AFTER` trigger fires, the row is written. Use `BEFORE` triggers with `RAISE(ABORT, ...)` to prevent the invalid write; `AFTER` triggers are for side-effects (audit logging, denormalization).
- **Complex multi-statement logic in triggers**: SQLite trigger bodies cannot run arbitrary SQL with multiple joins and sub-queries efficiently. Keep trigger bodies simple; push complex business logic to the Worker and use triggers as a safety net.
- **Forgetting the `FOR EACH ROW` clause**: SQLite only supports row-level triggers, but omitting the clause causes a syntax error in some migration tools.

## Gotchas

- `RAISE(ABORT, message)` rolls back only the current statement, not the enclosing transaction, unless you use `RAISE(FAIL, ...)`. Use `ABORT` when a single bad row should not poison a batch; use `FAIL` to stop all remaining statement execution in the transaction.
- `OLD.*` is only available in `UPDATE` and `DELETE` triggers, not `INSERT`. Referencing `OLD` in an `INSERT` trigger body is a SQL error.
- D1's `db.exec()` supports multi-statement DDL including `CREATE TRIGGER`. However, the `db.prepare()` API only supports a single statement — use `db.exec()` for trigger DDL in migration scripts.
- Triggers do not appear in `EXPLAIN QUERY PLAN` output; they are invisible to the query planner but fire at execution time.
- When testing with Miniflare or `@cloudflare/vitest-pool-workers`, triggers created via `db.exec()` persist for the lifetime of the in-memory database, so apply them in the test setup phase.

## Verification

```typescript
// State machine: trial → cancelled should succeed; cancelled → active should fail
await env.DB.prepare("INSERT INTO subscriptions VALUES ('s1','u1','trial',null,'pro',?)")
  .bind(new Date().toISOString()).run();

await env.DB.prepare("UPDATE subscriptions SET status='cancelled', updated_at=? WHERE id='s1'")
  .bind(new Date().toISOString()).run(); // should succeed

try {
  await env.DB.prepare("UPDATE subscriptions SET status='active', updated_at=? WHERE id='s1'")
    .bind(new Date().toISOString()).run();
  console.error('FAIL: should have raised');
} catch (e) {
  const msg = e instanceof Error ? e.message : '';
  console.assert(msg.includes('Invalid status transition'), 'PASS: trigger blocked invalid transition');
}
```

## Related

- `d1-triggers-computed-columns.md`
- `d1-trigger-denormalization-summary-tables-workers.md`
- `d1-cdc-change-tracking-triggers.md`
- `d1-check-constraint-domain-validation-workers.md`

## Sources

- SQLite triggers: https://www.sqlite.org/lang_createtrigger.html
- SQLite RAISE function: https://www.sqlite.org/lang_raise.html
- D1 exec API: https://developers.cloudflare.com/d1/worker-api/d1-database/#exec
