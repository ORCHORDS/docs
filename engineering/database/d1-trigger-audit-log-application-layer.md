# Application-Layer Audit Triggers for D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

D1 (SQLite) does not surface trigger output to the application and offers no change-data-capture stream. You need a complete, tamper-evident audit log of every INSERT, UPDATE, and DELETE on critical tables — and the audit entry must land in the same atomic batch as the mutation itself.

## Context

- Runtime: Cloudflare Workers (ESM, TypeScript)
- Database: Cloudflare D1 (SQLite)
- Pattern: wrap every write helper in a function that appends an `audit_log` row in a `db.batch()` call
- Requirement: the audit row and the mutation are committed atomically or both roll back

---

## Section 1: Audit Log Schema

```sql
-- migrations/0002_audit_log.sql

CREATE TABLE IF NOT EXISTS audit_log (
  id           TEXT    NOT NULL DEFAULT (lower(hex(randomblob(16)))),
  tenant_id    TEXT    NOT NULL,
  table_name   TEXT    NOT NULL,
  operation    TEXT    NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
  row_id       TEXT    NOT NULL,
  actor_id     TEXT    NOT NULL,   -- user or service account that caused the change
  before_json  TEXT,               -- JSON snapshot before change (NULL for INSERT)
  after_json   TEXT,               -- JSON snapshot after change  (NULL for DELETE)
  occurred_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_audit_table_row
  ON audit_log (tenant_id, table_name, row_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_actor
  ON audit_log (tenant_id, actor_id, occurred_at DESC);
```

---

## Section 2: Core Audit Batch Helper

The helper composes the user's mutation statement with an `INSERT INTO audit_log` statement and submits both as a single `db.batch()`. D1 batch calls are transactional — all statements succeed or all fail.

```typescript
// src/db/audit.ts
import type { D1Database, D1PreparedStatement } from '@cloudflare/workers-types';

export type Operation = 'INSERT' | 'UPDATE' | 'DELETE';

export interface AuditOptions {
  tenantId: string;
  actorId: string;
  tableName: string;
  operation: Operation;
  rowId: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

/**
 * Execute a write statement and append an audit_log row atomically.
 * Both the mutation and the audit row are in the same db.batch() call.
 */
export async function auditedWrite(
  db: D1Database,
  mutation: D1PreparedStatement,
  opts: AuditOptions,
): Promise<D1Result> {
  const auditStmt = db
    .prepare(
      `INSERT INTO audit_log
         (tenant_id, table_name, operation, row_id, actor_id, before_json, after_json)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      opts.tenantId,
      opts.tableName,
      opts.operation,
      opts.rowId,
      opts.actorId,
      opts.before ? JSON.stringify(opts.before) : null,
      opts.after  ? JSON.stringify(opts.after)  : null,
    );

  const [mutationResult] = await db.batch([mutation, auditStmt]);
  return mutationResult;
}
```

---

## Section 3: Typed Write Wrappers Per Table

Build one thin wrapper per critical table. Each wrapper fetches the before-snapshot, builds the mutation, and calls `auditedWrite`.

```typescript
// src/db/projects-write.ts
import type { D1Database } from '@cloudflare/workers-types';
import { auditedWrite } from './audit';

export interface Project {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
}

export async function updateProjectName(
  db: D1Database,
  tenantId: string,
  actorId: string,
  projectId: string,
  newName: string,
): Promise<void> {
  // 1. Fetch the before-snapshot
  const before = await db
    .prepare(`SELECT * FROM projects WHERE tenant_id = ? AND id = ?`)
    .bind(tenantId, projectId)
    .first<Project>();

  if (!before) throw new Error(`Project ${projectId} not found`);

  // 2. Build the mutation statement
  const mutation = db
    .prepare(
      `UPDATE projects SET name = ? WHERE tenant_id = ? AND id = ?`,
    )
    .bind(newName, tenantId, projectId);

  // 3. Write mutation + audit row atomically
  await auditedWrite(db, mutation, {
    tenantId,
    actorId,
    tableName: 'projects',
    operation: 'UPDATE',
    rowId: projectId,
    before: before as Record<string, unknown>,
    after: { ...before, name: newName },
  });
}

export async function deleteProject(
  db: D1Database,
  tenantId: string,
  actorId: string,
  projectId: string,
): Promise<void> {
  const before = await db
    .prepare(`SELECT * FROM projects WHERE tenant_id = ? AND id = ?`)
    .bind(tenantId, projectId)
    .first<Project>();

  if (!before) throw new Error(`Project ${projectId} not found`);

  const mutation = db
    .prepare(`DELETE FROM projects WHERE tenant_id = ? AND id = ?`)
    .bind(tenantId, projectId);

  await auditedWrite(db, mutation, {
    tenantId,
    actorId,
    tableName: 'projects',
    operation: 'DELETE',
    rowId: projectId,
    before: before as Record<string, unknown>,
    after: null,
  });
}
```

---

## Section 4: Replay Capability

The audit log stores full before/after JSON snapshots, enabling point-in-time replay for a specific row or actor.

```typescript
// src/db/audit-replay.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface AuditEntry {
  id: string;
  table_name: string;
  operation: 'INSERT' | 'UPDATE' | 'DELETE';
  row_id: string;
  actor_id: string;
  before_json: string | null;
  after_json: string | null;
  occurred_at: string;
}

/** Fetch the full audit trail for a specific row */
export async function getRowHistory(
  db: D1Database,
  tenantId: string,
  tableName: string,
  rowId: string,
): Promise<AuditEntry[]> {
  const { results } = await db
    .prepare(
      `SELECT * FROM audit_log
        WHERE tenant_id = ?
          AND table_name = ?
          AND row_id = ?
        ORDER BY occurred_at ASC`,
    )
    .bind(tenantId, tableName, rowId)
    .all<AuditEntry>();

  return results;
}

/** Reconstruct row state at a given point in time by replaying audit entries */
export function replayRowAt(
  history: AuditEntry[],
  atTimestamp: string,
): Record<string, unknown> | null {
  let state: Record<string, unknown> | null = null;

  for (const entry of history) {
    if (entry.occurred_at > atTimestamp) break;

    if (entry.operation === 'INSERT' && entry.after_json) {
      state = JSON.parse(entry.after_json);
    } else if (entry.operation === 'UPDATE' && entry.after_json) {
      state = JSON.parse(entry.after_json);
    } else if (entry.operation === 'DELETE') {
      state = null;
    }
  }

  return state;
}
```

---

## Anti-patterns

- Inserting the audit row in a separate `await` after the mutation — a Worker crash between the two leaves an unaudited write.
- Using SQLite triggers (`CREATE TRIGGER`) — D1 silently ignores trigger output and there is no way to read RETURNING inside a trigger reliably across all D1 versions.
- Storing only the delta (changed fields) without the full before/after snapshots — replay becomes impossible without the complete state.
- Logging to an external system (Logpush, Analytics Engine) instead of D1 — external logs are not atomic with the write.
- Omitting `actor_id` — an audit log without an actor is forensically useless.

## Gotchas

- `db.batch()` in D1 executes all statements in a single implicit transaction; if any statement fails, all are rolled back.
- `before_json` requires a SELECT before every UPDATE/DELETE — adds one extra read RTT. Cache aggressively or accept the latency.
- `randomblob(16)` in the DEFAULT for `id` requires SQLite 3.31+; D1 satisfies this.
- JSON snapshots of large rows bloat the audit table quickly; consider archiving old entries to R2 after 90 days.
- The audit table itself should never be written through `auditedWrite` (infinite recursion risk).

## Verification

```bash
# Confirm the last 5 audit entries after a test update
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT table_name, operation, row_id, actor_id, occurred_at \
             FROM audit_log ORDER BY occurred_at DESC LIMIT 5;" \
  --remote

# Verify atomicity: check that every project update has a matching audit row
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT p.id, COUNT(a.id) as audit_rows \
             FROM projects p \
             LEFT JOIN audit_log a \
               ON a.table_name='projects' AND a.row_id=p.id \
             GROUP BY p.id \
             HAVING audit_rows = 0;" \
  --remote
```

## Related

- `documentation/categories/database/d1-multi-tenant-row-isolation-pattern.md`
- `documentation/categories/database/d1-time-travel-point-in-time-restore.md`
- `documentation/categories/database/d1-connection-retry-exponential-backoff.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/d1/reference/migrations/
- https://www.sqlite.org/lang_createtrigger.html
