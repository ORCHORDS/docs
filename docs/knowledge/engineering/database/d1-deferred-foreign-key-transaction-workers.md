# D1 Deferred Foreign Key Transaction Pattern in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Worker needs to insert rows into multiple related tables within a single transaction where the foreign key relationships create a circular dependency or where child rows must be inserted before the parent's final state is committed. With immediate foreign key checking enabled, the insert order triggers constraint violations even though the final state will be referentially consistent.

## Context

SQLite enforces foreign key constraints statement-by-statement by default when `PRAGMA foreign_keys = ON`. For most writes this is fine, but circular references, batch reordering, and bootstrapping scenarios require **deferred checking**: constraints are verified at `COMMIT` time rather than on each individual statement. SQLite's `PRAGMA defer_foreign_keys = ON` and the `DEFERRABLE INITIALLY DEFERRED` clause on individual constraints provide this. In D1's `db.batch()` model, foreign key enforcement order matters because all statements share one transaction.

---

## 1. Enabling Deferred Foreign Keys per Transaction

```sql
-- Standard FK enforcement (per-statement)
PRAGMA foreign_keys = ON;

-- Deferred mode: check all FKs at COMMIT time only, for this transaction
PRAGMA defer_foreign_keys = ON;
```

`defer_foreign_keys` applies only to the current transaction — it resets after each `COMMIT` or `ROLLBACK`. In D1, include it at the start of a `db.batch()` that needs relaxed ordering.

---

## 2. Schema with Circular Foreign Keys

```sql
-- Two tables that reference each other
CREATE TABLE teams (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  lead_user_id TEXT,
  FOREIGN KEY (lead_user_id) REFERENCES users(id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE users (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  team_id TEXT,
  FOREIGN KEY (team_id) REFERENCES teams(id)
    DEFERRABLE INITIALLY DEFERRED
);
```

Without `DEFERRABLE INITIALLY DEFERRED`, inserting either table first violates its FK because the referenced row does not yet exist.

---

## 3. Bootstrapping Circular References in D1 batch()

```typescript
// workers/src/handlers/bootstrap-team.ts
import type { D1Database } from '@cloudflare/workers-types';

interface BootstrapInput {
  teamId: string;
  teamName: string;
  leadUserId: string;
  leadUserName: string;
}

export async function bootstrapTeam(
  db: D1Database,
  input: BootstrapInput,
): Promise<void> {
  const { teamId, teamName, leadUserId, leadUserName } = input;

  // defer_foreign_keys defers ALL FK checks to COMMIT
  await db.batch([
    db.prepare(`PRAGMA defer_foreign_keys = ON`),
    // Insert team first with lead_user_id that doesn't exist yet
    db.prepare(`INSERT INTO teams (id, name, lead_user_id) VALUES (?, ?, ?)`)
      .bind(teamId, teamName, leadUserId),
    // Insert user with team_id referencing the team just inserted
    db.prepare(`INSERT INTO users (id, name, team_id) VALUES (?, ?, ?)`)
      .bind(leadUserId, leadUserName, teamId),
    // At batch COMMIT, both FKs are checked and both rows exist
  ]);
}
```

---

## 4. Ordered Insert Without Circular Dependencies

For non-circular schemas where insert order is simply inconvenient (e.g., bulk seed data), deferred FKs allow any ordering.

```sql
CREATE TABLE categories (
  id        TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  parent_id TEXT REFERENCES categories(id) DEFERRABLE INITIALLY DEFERRED
);
```

```typescript
// workers/src/handlers/seed-categories.ts
interface Category {
  id: string;
  name: string;
  parentId: string | null;
}

export async function seedCategories(
  db: D1Database,
  categories: Category[],
): Promise<void> {
  // Categories arrive in arbitrary order — child before parent is fine
  const insertStmts = categories.map(cat =>
    db.prepare(`INSERT INTO categories (id, name, parent_id) VALUES (?, ?, ?)`)
      .bind(cat.id, cat.name, cat.parentId)
  );

  await db.batch([
    db.prepare(`PRAGMA defer_foreign_keys = ON`),
    ...insertStmts,
    // FK tree is validated at COMMIT — all nodes exist by then
  ]);
}
```

---

## 5. Deferred FK with Rollback on Violation

If the final state at COMMIT time violates a deferred FK, the entire transaction rolls back. Use try/catch to handle this cleanly.

```typescript
// workers/src/handlers/transfer-ownership.ts
export async function transferOwnership(
  db: D1Database,
  oldOwnerId: string,
  newOwnerId: string,
  resourceIds: string[],
): Promise<{ success: boolean; error?: string }> {
  const updateStmts = resourceIds.map(rid =>
    db.prepare(`UPDATE resources SET owner_id = ? WHERE id = ?`)
      .bind(newOwnerId, rid)
  );

  try {
    await db.batch([
      db.prepare(`PRAGMA defer_foreign_keys = ON`),
      // Temporarily breaks FK if newOwnerId doesn't exist yet
      ...updateStmts,
      // Ensure new owner exists (may already be there)
      db.prepare(
        `INSERT OR IGNORE INTO users (id, name) VALUES (?, 'Imported User')`
      ).bind(newOwnerId),
      // COMMIT validates: resources.owner_id → users.id must all exist
    ]);
    return { success: true };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('FOREIGN KEY')) {
      return { success: false, error: `New owner ${newOwnerId} could not be resolved` };
    }
    throw err;
  }
}
```

---

## 6. Checking Deferred FK Violations Manually

SQLite provides `PRAGMA foreign_key_check` to verify FK integrity without committing.

```typescript
// workers/src/db/fk-check.ts
interface FKViolation {
  table: string;
  rowid: number;
  parent: string;
  fkid: number;
}

export async function checkForeignKeys(db: D1Database): Promise<FKViolation[]> {
  const { results } = await db
    .prepare(`PRAGMA foreign_key_check`)
    .all<FKViolation>();
  return results;
}

export async function assertNoFKViolations(db: D1Database): Promise<void> {
  const violations = await checkForeignKeys(db);
  if (violations.length > 0) {
    const details = violations
      .map(v => `${v.table}[rowid=${v.rowid}] → ${v.parent}`)
      .join(', ');
    throw new Error(`Foreign key violations detected: ${details}`);
  }
}
```

```typescript
// Use in migration verification
await assertNoFKViolations(db);
```

---

## Anti-patterns

- **Using `PRAGMA defer_foreign_keys = ON` without `PRAGMA foreign_keys = ON`.** Deferred checking is only meaningful when FK enforcement is active. If `foreign_keys` is OFF, no checking occurs at all — not immediate and not deferred.
- **Relying on deferred FKs for all writes.** Deferred FKs mask data quality problems. Use them only for bootstrapping, circular deps, or bulk seed; rely on immediate FKs for normal CRUD paths.
- **Not wrapping deferred-FK batches in error handling.** A deferred FK violation silently succeeds until `COMMIT` — the error arrives at the `db.batch()` call level, not per-statement. Always use try/catch.
- **Assuming `defer_foreign_keys` persists across batches.** The pragma resets after each transaction. Repeat it at the start of every `db.batch()` that needs deferred checking.
- **Circular FKs without `DEFERRABLE INITIALLY DEFERRED` in the DDL.** `PRAGMA defer_foreign_keys = ON` defers checking for constraints already declared deferred or for the whole-transaction deferral mode — but schema-level `DEFERRABLE` provides cleaner self-documentation and works with both pragma modes.

---

## Gotchas

- `PRAGMA defer_foreign_keys = ON` defers ALL foreign key checks in the transaction, not just specific ones. If you want per-constraint deferral, declare `DEFERRABLE INITIALLY DEFERRED` on individual FK columns.
- `PRAGMA foreign_key_check` must be run inside the same connection/transaction to see uncommitted data. In D1, run it within a `db.batch()` after your inserts but before commit.
- Cloudflare D1 enables `PRAGMA foreign_keys = ON` by default since late 2024. Older D1 databases created before that may have FK enforcement disabled — verify with a `PRAGMA foreign_keys` query.
- `defer_foreign_keys` does not defer `UNIQUE` or `NOT NULL` constraints — those are still checked per-statement.
- In a `db.batch()`, the pragma must be the first statement; placing it after DML that already violated an immediate FK will not retroactively defer that violation.

---

## Verification

```sql
-- Confirm FK enforcement is on
PRAGMA foreign_keys;  -- Expected: 1

-- Confirm deferred mode is active in the current transaction
PRAGMA defer_foreign_keys;  -- Expected: 1 (only meaningful inside a transaction)

-- Verify no FK violations after bulk load
PRAGMA foreign_key_check;
-- Expected: empty result set

-- Verify circular reference scenario compiles and inserts successfully
BEGIN;
PRAGMA defer_foreign_keys = ON;
INSERT INTO teams (id, name, lead_user_id) VALUES ('t1', 'Alpha', 'u1');
INSERT INTO users (id, name, team_id) VALUES ('u1', 'Alice', 't1');
COMMIT;  -- Both FK checks pass here
```

---

## Related

- `d1-foreign-keys-referential-integrity.md`
- `savepoints-nested-transactions.md`
- `d1-savepoint-nested-transaction-workers.md`
- `d1-batch-operations-performance.md`
- `transaction-isolation-levels.md`
- `foreign-key-constraints.md`

---

## Sources

- https://www.sqlite.org/foreignkeys.html#fk_deferred
- https://www.sqlite.org/pragma.html#pragma_defer_foreign_keys
- https://www.sqlite.org/pragma.html#pragma_foreign_key_check
- https://developers.cloudflare.com/d1/reference/database-commands/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
