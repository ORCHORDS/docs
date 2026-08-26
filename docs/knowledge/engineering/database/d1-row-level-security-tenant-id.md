# D1 Multi-Tenancy: Row-Level Security with tenant_id

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You run a SaaS product where every user belongs to a tenant (organization, workspace, account).
All tenants share a single D1 database. A bug where one tenant's query accidentally returns
another tenant's rows is a critical data breach. You need a systematic, enforced pattern that
makes cross-tenant leaks structurally impossible rather than relying on every developer
remembering to add `WHERE tenant_id = ?` to every query.

---

## Context

D1 is SQLite at the edge. Unlike PostgreSQL, D1 has no server-side row-level security
(RLS) directives — there is no `ALTER TABLE … ENABLE ROW LEVEL SECURITY` or `CREATE POLICY`.
Isolation must be enforced at the application layer, inside Cloudflare Workers, using
disciplined query construction and a thin middleware that binds the tenant scope before
any query runs.

Two broad strategies exist:

| Strategy | Isolation | Cost |
|---|---|---|
| Schema-per-tenant (separate D1 databases) | Strongest | N databases, N Wrangler bindings |
| Shared database with `tenant_id` column | Simpler ops | Requires disciplined query layer |

This article covers the shared-database approach with a `tenant_id` column. The schema-isolation
approach is covered in `d1-multi-tenant-schema-isolation.md`.

---

## 1. Schema Design

Every tenant-owned table carries a non-nullable `tenant_id` column as the second column
(after the primary key). A composite index on `(tenant_id, <lookup_column>)` ensures the
planner can satisfy most queries with a single B-tree scan scoped to the tenant.

```sql
-- migrations/0001_tenants.sql
CREATE TABLE tenants (
  id       TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  plan     TEXT NOT NULL DEFAULT 'free',
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE projects (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'active',
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Critical: leading tenant_id in every composite index
CREATE INDEX idx_projects_tenant       ON projects(tenant_id);
CREATE INDEX idx_projects_tenant_name  ON projects(tenant_id, name);
CREATE INDEX idx_projects_tenant_status ON projects(tenant_id, status);

CREATE TABLE tasks (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  done       INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_tasks_tenant          ON tasks(tenant_id);
CREATE INDEX idx_tasks_tenant_project  ON tasks(tenant_id, project_id);
```

---

## 2. Tenant Context in Workers

Create a typed `TenantContext` object that is resolved once per request from the JWT or
session cookie and then threaded through the entire handler chain. Never trust a
`tenant_id` that comes from request body or query-string parameters.

```typescript
// src/lib/tenant-context.ts
export interface TenantContext {
  tenantId: string;
  userId: string;
  plan: 'free' | 'pro' | 'enterprise';
}

export async function resolveTenantContext(
  request: Request,
  env: Env
): Promise<TenantContext> {
  const authHeader = request.headers.get('Authorization') ?? '';
  const token = authHeader.replace(/^Bearer\s+/, '');

  if (!token) {
    throw new Response('Unauthorized', { status: 401 });
  }

  // Verify JWT — replace with your actual JWT library
  const payload = await verifyJwt(token, env.JWT_SECRET);

  if (!payload.tenant_id || !payload.sub) {
    throw new Response('Invalid token claims', { status: 401 });
  }

  return {
    tenantId: payload.tenant_id as string,
    userId: payload.sub as string,
    plan: (payload.plan ?? 'free') as TenantContext['plan'],
  };
}
```

---

## 3. Scoped Query Repository

Wrap every D1 query inside a repository class that accepts `TenantContext` and automatically
injects the `tenant_id` predicate. Developers on your team never write raw `db.prepare()`
calls outside this layer.

```typescript
// src/repositories/project-repository.ts
import { TenantContext } from '../lib/tenant-context';

export interface Project {
  id: string;
  tenant_id: string;
  name: string;
  status: string;
  created_at: number;
  updated_at: number;
}

export class ProjectRepository {
  constructor(
    private db: D1Database,
    private ctx: TenantContext
  ) {}

  async findAll(status?: string): Promise<Project[]> {
    if (status) {
      const { results } = await this.db
        .prepare(
          `SELECT * FROM projects
           WHERE tenant_id = ? AND status = ?
           ORDER BY created_at DESC`
        )
        .bind(this.ctx.tenantId, status)
        .all<Project>();
      return results;
    }

    const { results } = await this.db
      .prepare(
        `SELECT * FROM projects
         WHERE tenant_id = ?
         ORDER BY created_at DESC`
      )
      .bind(this.ctx.tenantId)
      .all<Project>();
    return results;
  }

  async findById(projectId: string): Promise<Project | null> {
    // tenant_id included — prevents IDOR (insecure direct object reference)
    return this.db
      .prepare(
        `SELECT * FROM projects
         WHERE tenant_id = ? AND id = ?`
      )
      .bind(this.ctx.tenantId, projectId)
      .first<Project>();
  }

  async create(name: string): Promise<Project> {
    const id = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);

    await this.db
      .prepare(
        `INSERT INTO projects (id, tenant_id, name, status, created_at, updated_at)
         VALUES (?, ?, ?, 'active', ?, ?)`
      )
      .bind(id, this.ctx.tenantId, name, now, now)
      .run();

    return (await this.findById(id))!;
  }

  async update(projectId: string, fields: Partial<Pick<Project, 'name' | 'status'>>): Promise<void> {
    // tenant_id in WHERE prevents updating another tenant's row
    const setClauses: string[] = [];
    const values: (string | number)[] = [];

    if (fields.name !== undefined) {
      setClauses.push('name = ?');
      values.push(fields.name);
    }
    if (fields.status !== undefined) {
      setClauses.push('status = ?');
      values.push(fields.status);
    }

    if (setClauses.length === 0) return;

    const now = Math.floor(Date.now() / 1000);
    setClauses.push('updated_at = ?');
    values.push(now, this.ctx.tenantId, projectId);

    await this.db
      .prepare(
        `UPDATE projects SET ${setClauses.join(', ')}
         WHERE tenant_id = ? AND id = ?`
      )
      .bind(...values)
      .run();
  }

  async delete(projectId: string): Promise<void> {
    await this.db
      .prepare(
        `DELETE FROM projects
         WHERE tenant_id = ? AND id = ?`
      )
      .bind(this.ctx.tenantId, projectId)
      .run();
  }
}
```

---

## 4. Workers Middleware Wiring

Use Hono (or a plain middleware chain) to resolve the tenant context once and attach the
repository instances to `c.var` so every route handler gets pre-scoped database access.

```typescript
// src/index.ts
import { Hono } from 'hono';
import { resolveTenantContext } from './lib/tenant-context';
import { ProjectRepository } from './repositories/project-repository';

type Variables = {
  tenantCtx: Awaited<ReturnType<typeof resolveTenantContext>>;
  projects: ProjectRepository;
};

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

// Global auth + tenant resolution middleware
app.use('*', async (c, next) => {
  try {
    const tenantCtx = await resolveTenantContext(c.req.raw, c.env);
    c.set('tenantCtx', tenantCtx);
    c.set('projects', new ProjectRepository(c.env.DB, tenantCtx));
    await next();
  } catch (resp) {
    if (resp instanceof Response) return resp;
    throw resp;
  }
});

app.get('/projects', async (c) => {
  const status = c.req.query('status');
  const projects = await c.var.projects.findAll(status);
  return c.json(projects);
});

app.get('/projects/:id', async (c) => {
  const project = await c.var.projects.findById(c.req.param('id'));
  if (!project) return c.json({ error: 'Not found' }, 404);
  return c.json(project);
});

app.post('/projects', async (c) => {
  const { name } = await c.req.json<{ name: string }>();
  const project = await c.var.projects.create(name);
  return c.json(project, 201);
});

export default app;
```

---

## 5. Cross-Tenant JOIN Safety

When joining tenant-owned tables, include `tenant_id` on both sides. This prevents
a row from one tenant's `projects` from being accidentally joined to another tenant's `tasks`
in a misconfigured query.

```typescript
// src/repositories/task-repository.ts
export class TaskRepository {
  constructor(
    private db: D1Database,
    private ctx: TenantContext
  ) {}

  async findByProject(projectId: string): Promise<Task[]> {
    // Both tables filtered by tenant_id — prevents cross-tenant join leaks
    const { results } = await this.db
      .prepare(
        `SELECT t.*
         FROM tasks t
         INNER JOIN projects p
           ON p.id = t.project_id
           AND p.tenant_id = t.tenant_id   -- explicit cross-table tenant equality
         WHERE t.tenant_id = ?
           AND t.project_id = ?
         ORDER BY t.created_at DESC`
      )
      .bind(this.ctx.tenantId, projectId)
      .all<Task>();
    return results;
  }

  async stats(): Promise<{ total: number; done: number }> {
    const row = await this.db
      .prepare(
        `SELECT
           COUNT(*)          AS total,
           SUM(done)         AS done
         FROM tasks
         WHERE tenant_id = ?`
      )
      .bind(this.ctx.tenantId)
      .first<{ total: number; done: number }>();
    return row ?? { total: 0, done: 0 };
  }
}
```

---

## 6. Enforcement Lint Rule (CI)

Add a custom ESLint rule or a grep-based CI check that fails the build if any `.prepare()`
call inside `src/repositories/` lacks a `tenant_id` bind parameter. This is a lightweight
static guard against regressions.

```bash
# .github/workflows/rls-check.yml (excerpt)
- name: Check tenant_id enforcement
  run: |
    # Fail if any prepare() call in repositories does NOT reference tenant_id
    FILES=$(find src/repositories -name '*.ts')
    for f in $FILES; do
      # count prepare() calls vs tenant_id references in the same file
      PREPARE=$(grep -c '\.prepare(' "$f" || true)
      TENANT=$(grep -c 'tenant_id' "$f" || true)
      if [ "$PREPARE" -gt 0 ] && [ "$TENANT" -eq 0 ]; then
        echo "ERROR: $f has .prepare() calls but no tenant_id reference"
        exit 1
      fi
    done
    echo "tenant_id enforcement OK"
```

---

## Anti-Patterns

- **Trusting client-supplied `tenant_id`**: Never accept `tenant_id` from request body/params.
  Derive it exclusively from the verified JWT or session.
- **Global `WHERE tenant_id IN (…)` helper**: Feels DRY but hides the tenant scope — future
  devs forget it must be applied and add raw queries that bypass it.
- **Skipping `tenant_id` in UPDATE/DELETE WHERE clause**: Updating `WHERE id = ?` alone
  allows any authenticated user to modify any row across tenants if they guess the ID.
- **Non-leading `tenant_id` in composite index**: `CREATE INDEX idx ON tasks(project_id, tenant_id)`
  forces a full `project_id` scan then filters by tenant. Swap the column order.
- **D1 batch without tenant scope**: `db.batch([stmt1, stmt2])` still executes each statement
  — ensure every statement in the batch carries its own `tenant_id` bind.

---

## Gotchas

- **SQLite has no RLS enforcement**: All isolation is in application code. A developer can
  bypass it by writing raw SQL. Code review and the CI lint check are your last line of
  defence.
- **CASCADE deletes cross tenant**: `ON DELETE CASCADE` on `tenant_id` references is safe only
  if the parent `tenants` table itself is protected. Add an explicit check before deleting
  a tenant row in production.
- **D1 `meta.changes` !== tenant-safe**: `result.meta.changes > 0` only tells you a row was
  modified, not that it belonged to the correct tenant. Read back with `findById` if you need
  ownership confirmation.
- **UUID collisions across tenants**: Use `crypto.randomUUID()` (V4) — collision probability
  is negligible, but never use sequential IDs that expose enumeration vectors across tenants.

---

## Verification

```typescript
// tests/tenant-isolation.test.ts
import { env } from 'cloudflare:test';
import { ProjectRepository } from '../src/repositories/project-repository';

describe('tenant isolation', () => {
  const ctxA = { tenantId: 'tenant-a', userId: 'u1', plan: 'pro' as const };
  const ctxB = { tenantId: 'tenant-b', userId: 'u2', plan: 'free' as const };

  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM projects`);
    await env.DB.exec(`DELETE FROM tenants`);
    await env.DB.prepare(
      `INSERT INTO tenants (id, name, plan) VALUES ('tenant-a','A','pro'),('tenant-b','B','free')`
    ).run();
  });

  it('cannot read another tenant project by id', async () => {
    const repoA = new ProjectRepository(env.DB, ctxA);
    const projectA = await repoA.create('Secret Project');

    const repoB = new ProjectRepository(env.DB, ctxB);
    const result = await repoB.findById(projectA.id);

    expect(result).toBeNull(); // tenant B cannot see tenant A's row
  });

  it('findAll returns only own rows', async () => {
    const repoA = new ProjectRepository(env.DB, ctxA);
    const repoB = new ProjectRepository(env.DB, ctxB);

    await repoA.create('Project A1');
    await repoA.create('Project A2');
    await repoB.create('Project B1');

    const resultsA = await repoA.findAll();
    expect(resultsA).toHaveLength(2);
    expect(resultsA.every(p => p.tenant_id === 'tenant-a')).toBe(true);
  });
});
```

---

## Related

- `d1-multi-tenant-schema-isolation.md` — schema-per-tenant alternative
- `postgresql-row-level-security-multi-tenant.md` — Postgres native RLS
- `d1-audit-event-log.md` — tracking tenant actions
- `d1-migrations-wrangler-ci-cd.md` — deploying the schema above
- `database-roles-least-privilege.md` — principle of least privilege

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Hono middleware docs — https://hono.dev/docs/guides/middleware
- OWASP IDOR guidance — https://owasp.org/www-project-web-security-testing-guide/
- SQLite composite index best practices — https://www.sqlite.org/queryplanner.html
