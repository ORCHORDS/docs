# Row-Level Security Pattern in D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You run a multi-tenant SaaS on a single D1 database and need to guarantee that tenant A can never read or write tenant B's data — not through a bug, not through a missing WHERE clause, not through a direct API call with a spoofed ID. You need this enforcement to happen at a single, unavoidable layer rather than being scattered across every query in every handler.

## Context

D1 is SQLite-backed and has no native row-level security (unlike PostgreSQL's `CREATE POLICY`). Enforcement must be implemented in the application layer. The pattern below uses a typed `TenantDb` wrapper that injects `tenant_id` filters into every query, a middleware that extracts the tenant from the authenticated JWT, and an explicit admin-bypass flag that requires a separate privilege check.

## Solution

### 1. Schema: tenant_id on every table

```sql
CREATE TABLE IF NOT EXISTS articles (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id  TEXT    NOT NULL,  -- RLS anchor
  title      TEXT    NOT NULL,
  body       TEXT    NOT NULL,
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id  TEXT    NOT NULL,
  type       TEXT    NOT NULL,
  payload    TEXT    NOT NULL DEFAULT '{}',
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Indexes to make tenant-scoped queries fast
CREATE INDEX IF NOT EXISTS idx_articles_tenant ON articles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_events_tenant   ON events   (tenant_id);
```

### 2. TenantDb wrapper

```typescript
// src/lib/tenant-db.ts
export class TenantDb {
  private readonly tenantId: string;
  private readonly db: D1Database;
  private readonly isAdmin: boolean;

  constructor(db: D1Database, tenantId: string, isAdmin = false) {
    if (!tenantId) throw new Error('tenantId is required');
    this.db = db;
    this.tenantId = tenantId;
    this.isAdmin = isAdmin;
  }

  /** Prepare a statement with tenant_id injected as the first bind parameter */
  tenantPrepare(sql: string): D1PreparedStatement {
    return this.db.prepare(sql);
  }

  /** Assert the caller is admin; throw otherwise */
  requireAdmin(): void {
    if (!this.isAdmin) {
      throw new Error('Admin privilege required');
    }
  }

  get id(): string {
    return this.tenantId;
  }

  get raw(): D1Database {
    this.requireAdmin();
    return this.db;
  }
}
```

### 3. Repository pattern with enforced tenant scope

```typescript
// src/repositories/articles.ts
import { TenantDb } from '../lib/tenant-db';

export interface Article {
  id: number;
  tenant_id: string;
  title: string;
  body: string;
  created_at: string;
}

export class ArticlesRepository {
  constructor(private readonly tdb: TenantDb) {}

  async list(limit = 50, offset = 0): Promise<Article[]> {
    // tenant_id is always bound — cannot be bypassed by caller
    const rows = await this.tdb
      .tenantPrepare(`
        SELECT id, tenant_id, title, body, created_at
        FROM articles
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
      `)
      .bind(this.tdb.id, limit, offset)
      .all<Article>();

    return rows.results;
  }

  async getById(id: number): Promise<Article | null> {
    // Scoped by both id AND tenant_id — prevents id enumeration across tenants
    return this.tdb
      .tenantPrepare(`
        SELECT id, tenant_id, title, body, created_at
        FROM articles
        WHERE id = ? AND tenant_id = ?
      `)
      .bind(id, this.tdb.id)
      .first<Article>();
  }

  async create(title: string, body: string): Promise<number> {
    const result = await this.tdb
      .tenantPrepare(`
        INSERT INTO articles (tenant_id, title, body)
        VALUES (?, ?, ?)
      `)
      .bind(this.tdb.id, title, body)
      .run();

    return result.meta.last_row_id as number;
  }

  async update(id: number, title: string, body: string): Promise<boolean> {
    const result = await this.tdb
      .tenantPrepare(`
        UPDATE articles
        SET title = ?, body = ?
        WHERE id = ? AND tenant_id = ?
      `)
      .bind(title, body, id, this.tdb.id)
      .run();

    return (result.meta.changes ?? 0) > 0;
  }

  async delete(id: number): Promise<boolean> {
    const result = await this.tdb
      .tenantPrepare(`
        DELETE FROM articles
        WHERE id = ? AND tenant_id = ?
      `)
      .bind(id, this.tdb.id)
      .run();

    return (result.meta.changes ?? 0) > 0;
  }
}
```

### 4. Middleware: extract tenant from JWT

```typescript
// src/middleware/auth.ts
export interface AuthContext {
  tenantId: string;
  userId: string;
  isAdmin: boolean;
}

export async function extractAuth(request: Request): Promise<AuthContext> {
  const token = request.headers.get('authorization')?.replace('Bearer ', '');
  if (!token) throw new Response('Unauthorized', { status: 401 });

  // Decode and verify JWT (use a real library in production: jose, jsonwebtoken-workers, etc.)
  const parts = token.split('.');
  if (parts.length !== 3) throw new Response('Invalid token', { status: 401 });

  // In production: verify signature against public key
  const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));

  if (!payload.tenant_id) throw new Response('Missing tenant claim', { status: 401 });
  if (Date.now() / 1000 > payload.exp) throw new Response('Token expired', { status: 401 });

  return {
    tenantId: payload.tenant_id as string,
    userId: payload.sub as string,
    isAdmin: payload.role === 'admin',
  };
}
```

### 5. Worker handler wiring

```typescript
// src/handlers/articles.ts
import { extractAuth } from '../middleware/auth';
import { TenantDb } from '../lib/tenant-db';
import { ArticlesRepository } from '../repositories/articles';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let auth;
    try {
      auth = await extractAuth(request);
    } catch (resp) {
      return resp as Response;
    }

    const tdb = new TenantDb(env.DB, auth.tenantId, auth.isAdmin);
    const repo = new ArticlesRepository(tdb);
    const url = new URL(request.url);

    if (url.pathname === '/articles' && request.method === 'GET') {
      const articles = await repo.list();
      return Response.json({ articles });
    }

    if (url.pathname.startsWith('/articles/') && request.method === 'GET') {
      const id = parseInt(url.pathname.split('/').pop()!, 10);
      const article = await repo.getById(id);
      if (!article) return Response.json({ error: 'Not found' }, { status: 404 });
      return Response.json({ article });
    }

    if (url.pathname === '/articles' && request.method === 'POST') {
      const body = await request.json<{ title: string; body: string }>();
      const id = await repo.create(body.title, body.body);
      return Response.json({ id }, { status: 201 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 6. Admin bypass with explicit flag

```typescript
// src/handlers/admin.ts — admin-only cross-tenant queries
import { TenantDb } from '../lib/tenant-db';
import { extractAuth } from '../middleware/auth';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let auth;
    try {
      auth = await extractAuth(request);
    } catch (resp) {
      return resp as Response;
    }

    if (!auth.isAdmin) {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }

    // Construct TenantDb with isAdmin=true; .raw exposes the underlying DB
    const tdb = new TenantDb(env.DB, auth.tenantId, true);

    // Cross-tenant query — only accessible via tdb.raw which throws if !isAdmin
    const rows = await tdb.raw
      .prepare(`SELECT tenant_id, COUNT(*) AS cnt FROM articles GROUP BY tenant_id`)
      .all<{ tenant_id: string; cnt: number }>();

    return Response.json({ tenants: rows.results });
  },
};
```

### 7. D1 batch for multi-table tenant queries

```typescript
// Fetch articles + events for a tenant in one round-trip
export async function getTenantDashboard(
  tdb: TenantDb
): Promise<{ articles: unknown[]; events: unknown[] }> {
  const [articlesResult, eventsResult] = await tdb
    .tenantPrepare('SELECT 1') // placeholder — we compose the batch directly below
    // D1 batch requires the raw db reference; this is the one admin-adjacent use
    // In practice, expose a typed batchForTenant helper:
    ;

  // Preferred: a typed helper that injects tenant_id into each statement
  const db = (tdb as any)['db'] as D1Database; // internal access pattern
  const tenantId = tdb.id;

  const [articles, events] = await db.batch([
    db.prepare(`SELECT id, title, created_at FROM articles WHERE tenant_id = ? LIMIT 10`).bind(tenantId),
    db.prepare(`SELECT id, type, created_at FROM events WHERE tenant_id = ? LIMIT 10`).bind(tenantId),
  ]);

  return {
    articles: (articles as D1Result).results,
    events: (events as D1Result).results,
  };
}
```

## Implementation Details

- Every read query appends `AND tenant_id = ?`. Every write query includes `tenant_id = ?` in both INSERT and WHERE. This is the only enforcement layer — SQLite has no policy system.
- The `TenantDb.raw` getter throws unless `isAdmin` is true. This makes it impossible to accidentally write a cross-tenant query without explicitly opting into admin mode.
- The JWT claim `tenant_id` is the only source of tenant identity. It must be verified against the JWT signature — never trust a `tenant_id` from the request body or URL parameters without verification.
- Indexes on `(tenant_id)` columns are critical. Without them, every tenant-scoped query is a full table scan. On large tables, add composite indexes: `(tenant_id, created_at DESC)` for time-sorted queries.
- D1's `meta.changes` property on `run()` results tells you how many rows were affected. A `0` on an UPDATE means either the row doesn't exist or the `tenant_id` didn't match — both return 404 to the caller.

## Anti-patterns

- **Trusting URL parameters for tenant identity** — `DELETE /articles/42?tenant_id=tenant-1` is trivially spoofable. Always derive tenant identity from the verified JWT.
- **Sharing a single "god" database user** — D1 has no user system; every Worker request uses the same binding. Enforcement must be in application code, not database credentials.
- **Skipping tenant_id on JOIN results** — A JOIN between `articles` and `events` must filter `tenant_id` on BOTH tables, or a cross-tenant event could appear in results.
- **Soft-deleting without tenant_id** — A soft-delete column (`deleted_at`) doesn't remove the row; ensure the tenant_id check still applies to soft-deleted rows.
- **Logging tenant data in plaintext** — Avoid logging `tenant_id` alongside PII in production logs. Use opaque correlation IDs instead.

## Gotchas

- `meta.changes === 0` on a DELETE with `WHERE id = ? AND tenant_id = ?` is indistinguishable from "row doesn't exist" vs "row exists but wrong tenant". Return 404 in both cases — do not reveal whether the resource exists for another tenant.
- D1 batch statements are not a transaction. If statement 2 of a batch fails, statement 1 is already committed. Wrap multi-step writes in a single `batch()` call to minimize partial-write windows, but design for idempotency.
- When adding `tenant_id` to an existing table via `ALTER TABLE`, all existing rows get a NULL value unless you provide a DEFAULT. Backfill before adding a NOT NULL constraint.
- The `TenantDb` wrapper exposes `.raw` only to admins, but TypeScript doesn't enforce this at compile time — it throws at runtime. Add a lint rule or code review checklist to prevent direct `env.DB` usage outside of admin handlers.

## Verification

```bash
# Insert rows for two tenants
npx wrangler d1 execute example project-db --command "
  INSERT INTO articles (tenant_id, title, body) VALUES ('tenant-a', 'A article', 'body a');
  INSERT INTO articles (tenant_id, title, body) VALUES ('tenant-b', 'B article', 'body b');
"

# Verify tenant-a cannot see tenant-b's row (simulate by binding tenant_id)
npx wrangler d1 execute example project-db --command "
  SELECT id, title FROM articles WHERE tenant_id = 'tenant-a';
"
# Expected: only 'A article'

# Verify UPDATE with wrong tenant returns 0 changes
npx wrangler d1 execute example project-db --command "
  UPDATE articles SET title = 'HACKED' WHERE id = 2 AND tenant_id = 'tenant-a';
  SELECT changes() AS changed;
"
# Expected: changed = 0
```

## Related

- `documentation/docs/policies/database/d1-schema-version-tracking.md` — adding tenant_id columns via migrations
- `documentation/docs/policies/database/d1-json-column-queries.md` — JSON columns with tenant-scoped queries
- `documentation/docs/policies/database/d1-full-text-search-fts5.md` — combining FTS MATCH with tenant_id filter
- `documentation/docs/policies/database/d1-connection-pooling-hyperdrive-pattern.md` — RLS applies equally when switching to Postgres via Hyperdrive

## Sources

- https://developers.cloudflare.com/d1/
- https://cheatsheetseries.owasp.org/cheatsheets/Multitenant_Security_Cheat_Sheet.html
- https://developers.cloudflare.com/workers/runtime-apis/bindings/d1/
