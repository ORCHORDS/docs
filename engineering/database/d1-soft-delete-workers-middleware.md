# D1 Soft Deletes: deleted_at Pattern with Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

A user deletes a record. Twenty minutes later they email support: "I accidentally deleted
my project — can you restore it?" If you issued a hard `DELETE` the row is gone from D1
with no recovery path short of restoring a backup. Soft deletes solve this by marking rows
as deleted without removing them, enabling self-serve restore, audit trails, and safe
reference preservation for foreign keys.

---

## Context

The `deleted_at` soft-delete pattern is well established in relational databases, but D1
and Cloudflare Workers introduce specific challenges:

1. **No server-side views or partial views** — you cannot define a PostgreSQL-style view
   with `WHERE deleted_at IS NULL` that transparently hides soft-deleted rows at the DB level.
2. **No triggers enforcing the filter** — every query that touches the table must opt in.
3. **Edge latency budget** — extra filter columns have real cost at D1's query layer;
   indexes must be designed to keep soft-delete-aware queries fast.

This article covers the D1-specific `deleted_at` implementation including schema, Workers
middleware, repository patterns, background purge jobs, and restoration flows.

---

## 1. Schema Design

Add `deleted_at INTEGER` (Unix epoch, nullable) to every table that needs soft delete.
Index it in a way that makes the common case (listing non-deleted rows) cheap.

```sql
-- migrations/0002_soft_delete.sql

ALTER TABLE projects ADD COLUMN deleted_at INTEGER;
ALTER TABLE tasks    ADD COLUMN deleted_at INTEGER;

-- Partial-index equivalent in SQLite: filter index on deleted_at IS NULL
-- SQLite supports WHERE clauses on indexes (partial indexes)
CREATE INDEX idx_projects_active ON projects(tenant_id, created_at)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_tasks_active ON tasks(tenant_id, project_id)
  WHERE deleted_at IS NULL;

-- Index for the recycle-bin query (find deleted rows for restore UI)
CREATE INDEX idx_projects_deleted ON projects(tenant_id, deleted_at)
  WHERE deleted_at IS NOT NULL;
```

> **Note:** D1 supports SQLite partial indexes (`WHERE` clause on `CREATE INDEX`).
> These dramatically reduce the index size for tables where most rows are not deleted.

---

## 2. Repository Base Class

Create a `SoftDeleteRepository` base that all repositories extend. It bakes the
`deleted_at IS NULL` filter into every read method and provides `softDelete`, `restore`,
and `purge` helpers.

```typescript
// src/repositories/soft-delete-repository.ts
export interface SoftDeletable {
  id: string;
  deleted_at: number | null;
}

export abstract class SoftDeleteRepository<T extends SoftDeletable> {
  protected abstract tableName: string;

  constructor(
    protected db: D1Database,
    protected tenantId: string
  ) {}

  protected get activeFilter(): string {
    return `tenant_id = ? AND deleted_at IS NULL`;
  }

  async findAll(): Promise<T[]> {
    const { results } = await this.db
      .prepare(
        `SELECT * FROM ${this.tableName}
         WHERE ${this.activeFilter}
         ORDER BY created_at DESC`
      )
      .bind(this.tenantId)
      .all<T>();
    return results;
  }

  async findById(id: string): Promise<T | null> {
    return this.db
      .prepare(
        `SELECT * FROM ${this.tableName}
         WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL`
      )
      .bind(this.tenantId, id)
      .first<T>();
  }

  /** Soft-delete: stamp deleted_at, row stays in DB */
  async softDelete(id: string): Promise<boolean> {
    const now = Math.floor(Date.now() / 1000);
    const result = await this.db
      .prepare(
        `UPDATE ${this.tableName}
         SET deleted_at = ?
         WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL`
      )
      .bind(now, this.tenantId, id)
      .run();
    return (result.meta.changes ?? 0) > 0;
  }

  /** Restore: clear deleted_at */
  async restore(id: string): Promise<boolean> {
    const result = await this.db
      .prepare(
        `UPDATE ${this.tableName}
         SET deleted_at = NULL
         WHERE tenant_id = ? AND id = ? AND deleted_at IS NOT NULL`
      )
      .bind(this.tenantId, id)
      .run();
    return (result.meta.changes ?? 0) > 0;
  }

  /** Hard-delete a single already-soft-deleted row */
  async purge(id: string): Promise<boolean> {
    const result = await this.db
      .prepare(
        `DELETE FROM ${this.tableName}
         WHERE tenant_id = ? AND id = ? AND deleted_at IS NOT NULL`
      )
      .bind(this.tenantId, id)
      .run();
    return (result.meta.changes ?? 0) > 0;
  }

  /** Recycle bin: rows deleted within the retention window */
  async findDeleted(retentionDays = 30): Promise<T[]> {
    const cutoff = Math.floor(Date.now() / 1000) - retentionDays * 86_400;
    const { results } = await this.db
      .prepare(
        `SELECT * FROM ${this.tableName}
         WHERE tenant_id = ? AND deleted_at > ?
         ORDER BY deleted_at DESC`
      )
      .bind(this.tenantId, cutoff)
      .all<T>();
    return results;
  }
}
```

---

## 3. Concrete Repository

```typescript
// src/repositories/project-repository.ts
import { SoftDeleteRepository } from './soft-delete-repository';

export interface Project extends SoftDeletable {
  tenant_id: string;
  name: string;
  status: string;
  created_at: number;
  updated_at: number;
}

export class ProjectRepository extends SoftDeleteRepository<Project> {
  protected tableName = 'projects';

  async create(name: string): Promise<Project> {
    const id = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);
    await this.db
      .prepare(
        `INSERT INTO projects
           (id, tenant_id, name, status, created_at, updated_at, deleted_at)
         VALUES (?, ?, ?, 'active', ?, ?, NULL)`
      )
      .bind(id, this.tenantId, name, now, now)
      .run();
    return (await this.findById(id))!;
  }

  /** Find by name — respects soft-delete filter */
  async findByName(name: string): Promise<Project | null> {
    return this.db
      .prepare(
        `SELECT * FROM projects
         WHERE tenant_id = ? AND name = ? AND deleted_at IS NULL`
      )
      .bind(this.tenantId, name)
      .first<Project>();
  }
}
```

---

## 4. Workers Route Handlers

```typescript
// src/routes/projects.ts
import { Hono } from 'hono';
import { ProjectRepository } from '../repositories/project-repository';

const projects = new Hono<{ Bindings: Env; Variables: { tenantId: string } }>();

// List active projects
projects.get('/', async (c) => {
  const repo = new ProjectRepository(c.env.DB, c.var.tenantId);
  return c.json(await repo.findAll());
});

// Recycle bin
projects.get('/deleted', async (c) => {
  const repo = new ProjectRepository(c.env.DB, c.var.tenantId);
  const days = Number(c.req.query('days') ?? 30);
  return c.json(await repo.findDeleted(days));
});

// Soft-delete
projects.delete('/:id', async (c) => {
  const repo = new ProjectRepository(c.env.DB, c.var.tenantId);
  const deleted = await repo.softDelete(c.req.param('id'));
  if (!deleted) return c.json({ error: 'Not found' }, 404);
  return c.json({ deleted: true });
});

// Restore
projects.post('/:id/restore', async (c) => {
  const repo = new ProjectRepository(c.env.DB, c.var.tenantId);
  const restored = await repo.restore(c.req.param('id'));
  if (!restored) return c.json({ error: 'Not found or already active' }, 404);
  return c.json({ restored: true });
});

// Permanent purge (admin or post-retention)
projects.delete('/:id/purge', async (c) => {
  // Optional: require an admin role check here
  const repo = new ProjectRepository(c.env.DB, c.var.tenantId);
  const purged = await repo.purge(c.req.param('id'));
  if (!purged) return c.json({ error: 'Row not found or not soft-deleted' }, 404);
  return c.json({ purged: true });
});

export { projects };
```

---

## 5. Scheduled Purge Worker (Retention Enforcement)

Rows beyond the retention window (e.g., 30 days after `deleted_at`) should be
hard-deleted on a schedule to reclaim D1 storage and comply with data-retention policies.

```typescript
// src/index.ts (scheduled handler)
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(purgeExpiredRows(env.DB));
  },
};

async function purgeExpiredRows(db: D1Database): Promise<void> {
  const retentionSeconds = 30 * 24 * 60 * 60; // 30 days
  const cutoff = Math.floor(Date.now() / 1000) - retentionSeconds;

  // Batch hard-delete in chunks to avoid a single long-running statement
  let deleted = 0;
  do {
    const result = await db
      .prepare(
        `DELETE FROM projects
         WHERE id IN (
           SELECT id FROM projects
           WHERE deleted_at IS NOT NULL AND deleted_at < ?
           LIMIT 500
         )`
      )
      .bind(cutoff)
      .run();
    deleted = result.meta.changes ?? 0;
    console.log(`Purged ${deleted} expired project rows`);
  } while (deleted === 500); // keep going until < 500 rows remain

  // Repeat for other soft-delete tables
  await db
    .prepare(
      `DELETE FROM tasks
       WHERE deleted_at IS NOT NULL AND deleted_at < ?`
    )
    .bind(cutoff)
    .run();
}
```

```toml
# wrangler.toml — trigger the purge daily
[triggers]
crons = ["0 3 * * *"]  # 03:00 UTC daily
```

---

## 6. Cascade Soft-Delete

When deleting a parent record (e.g., a project), soft-delete all child records atomically
using `db.batch()`.

```typescript
async softDeleteProjectWithTasks(
  db: D1Database,
  tenantId: string,
  projectId: string
): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  await db.batch([
    db.prepare(
      `UPDATE tasks SET deleted_at = ?
       WHERE tenant_id = ? AND project_id = ? AND deleted_at IS NULL`
    ).bind(now, tenantId, projectId),

    db.prepare(
      `UPDATE projects SET deleted_at = ?
       WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL`
    ).bind(now, tenantId, projectId),
  ]);
}
```

---

## Anti-Patterns

- **Forgetting `deleted_at IS NULL` in one query**: The entire soft-delete pattern
  breaks the moment one route forgets the filter. The base class approach above prevents this.
- **Indexing `deleted_at` as the leading column**: `CREATE INDEX idx ON projects(deleted_at, tenant_id)`
  is useless for the common case. Always lead with `tenant_id` (or the most selective column).
- **Keeping soft-deleted rows forever**: Without a scheduled purge, soft-deleted rows
  accumulate and inflate D1 storage costs. Set a retention policy and enforce it with crons.
- **Soft-deleting without cascading to children**: Deleting a project but leaving tasks
  visible will expose orphaned tasks in child-table queries.
- **Using soft-delete for GDPR erasure**: Soft-deleted rows still contain PII. For
  right-to-erasure requests, hard-delete or overwrite the PII fields before (or instead of)
  setting `deleted_at`.

---

## Gotchas

- **UNIQUE constraints and soft deletes**: If `name` is UNIQUE, a soft-deleted row blocks
  re-creation with the same name. Use a partial unique index:
  ```sql
  CREATE UNIQUE INDEX idx_projects_name_active
    ON projects(tenant_id, name) WHERE deleted_at IS NULL;
  ```
- **Foreign key references to soft-deleted rows**: If `tasks.project_id` references
  `projects.id` with `ON DELETE CASCADE`, SQLite will hard-delete tasks when a project is
  hard-deleted. Ensure the purge order matches: tasks first, then projects.
- **`meta.changes` ambiguity**: After `UPDATE … SET deleted_at = ?`, `meta.changes === 0`
  means the row was already soft-deleted (or doesn't belong to this tenant). Return 404 in
  that case.
- **D1 partial indexes require SQLite ≥ 3.8.0**: D1 runs a recent SQLite version that
  supports partial indexes; verify with `SELECT sqlite_version()` if you observe unexpected
  query plans.

---

## Verification

```typescript
// tests/soft-delete.test.ts
import { env } from 'cloudflare:test';
import { ProjectRepository } from '../src/repositories/project-repository';

describe('soft delete', () => {
  const TENANT = 'tenant-test';
  let repo: ProjectRepository;

  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM projects`);
    repo = new ProjectRepository(env.DB, TENANT);
  });

  it('soft-deleted row is hidden from findAll', async () => {
    const p = await repo.create('My Project');
    await repo.softDelete(p.id);
    const list = await repo.findAll();
    expect(list.find(r => r.id === p.id)).toBeUndefined();
  });

  it('soft-deleted row appears in findDeleted', async () => {
    const p = await repo.create('My Project');
    await repo.softDelete(p.id);
    const deleted = await repo.findDeleted(30);
    expect(deleted.find(r => r.id === p.id)).toBeDefined();
  });

  it('restore makes row visible again', async () => {
    const p = await repo.create('My Project');
    await repo.softDelete(p.id);
    await repo.restore(p.id);
    const found = await repo.findById(p.id);
    expect(found).not.toBeNull();
    expect(found!.deleted_at).toBeNull();
  });

  it('purge removes row permanently', async () => {
    const p = await repo.create('My Project');
    await repo.softDelete(p.id);
    await repo.purge(p.id);
    const { results } = await env.DB
      .prepare(`SELECT * FROM projects WHERE id = ?`)
      .bind(p.id)
      .all();
    expect(results).toHaveLength(0);
  });
});
```

---

## Related

- `soft-delete-patterns.md` — generic soft-delete database theory
- `soft-delete-schema-design.md` — schema considerations across databases
- `d1-audit-event-log.md` — recording who deleted what and when
- `d1-row-level-security-tenant-id.md` — tenant scoping applied to the same tables
- `d1-migrations-wrangler-ci-cd.md` — deploying the schema changes above

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- SQLite partial indexes — https://www.sqlite.org/partialindex.html
- Hono framework — https://hono.dev/
- GDPR Article 17 (right to erasure) — https://gdpr-info.eu/art-17-gdpr/
