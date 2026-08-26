# Multi-tenancy Data Isolation in Cloudflare Workers: KV Namespacing and D1 Row-Level Filtering

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A SaaS application built on Cloudflare Workers serves multiple tenants (organizations, teams, or accounts) from the same Worker codebase. Data for all tenants lives in the same D1 database and KV namespace. Without explicit isolation boundaries:

- A bug in tenant A's request handler could leak tenant B's data
- A malicious actor at tenant A could craft requests that reach tenant B's records
- A misconfigured query could aggregate data across tenants (a "noisy neighbor" data leak)
- A developer writing a new query might forget to add the tenant filter, inadvertently exposing all tenants

This article covers the structural patterns that make cross-tenant data access architecturally hard to do by accident.

## Context

Multi-tenancy isolation in a Workers context operates at two layers:

1. **Storage layer**: D1 row filtering and KV key namespacing enforce that queries for tenant A cannot return rows belonging to tenant B, even if the query logic is wrong.
2. **Application layer**: The Worker extracts the tenant identity from the authenticated session and attaches it to every storage operation, making it impossible to call a storage function without supplying a tenant context.

The core principle is **mandatory context propagation**: every function that touches storage accepts a `TenantContext` argument. A function that does not accept one cannot call the storage layer. This makes it a compile-time/code-review error rather than a runtime misfortune to forget the tenant filter.

## D1 Row-Level Isolation

Every table that holds tenant-specific data must have a `tenant_id` column. Every query must filter on it.

### Schema design

```sql
-- Every tenant-specific table carries tenant_id as a NOT NULL column
-- with a composite index to make filtered queries efficient.

CREATE TABLE documents (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  title       TEXT NOT NULL,
  content     TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  created_by  TEXT NOT NULL    -- user_id within the tenant
);

CREATE INDEX idx_documents_tenant ON documents (tenant_id, created_at DESC);

-- Tenant registry table (the source of truth for valid tenant IDs)
CREATE TABLE tenants (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  plan        TEXT NOT NULL DEFAULT 'free',
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
```

### Typed tenant context

```typescript
// src/lib/tenant.ts

export interface TenantContext {
  readonly tenantId: string;
  readonly userId: string;
  readonly plan: 'free' | 'pro' | 'enterprise';
}

/**
 * Extract and validate the tenant context from the authenticated session.
 * Returns null if the session is invalid or the tenant does not exist.
 */
export async function resolveTenantContext(
  sessionToken: string,
  db: D1Database,
  sessions: KVNamespace,
): Promise<TenantContext | null> {
  // 1. Validate the session
  const raw = await sessions.get(`session:${sessionToken}`, 'json') as {
    userId: string;
    tenantId: string;
  } | null;

  if (!raw?.tenantId || !raw?.userId) return null;

  // 2. Confirm the tenant exists and is active
  const tenant = await db
    .prepare('SELECT id, plan FROM tenants WHERE id = ?')
    .bind(raw.tenantId)
    .first<{ id: string; plan: string }>();

  if (!tenant) return null;

  return {
    tenantId: tenant.id,
    userId: raw.userId,
    plan: tenant.plan as TenantContext['plan'],
  };
}
```

### Repository pattern with mandatory tenant context

```typescript
// src/repositories/documents.ts

import type { TenantContext } from '../lib/tenant';

export class DocumentRepository {
  constructor(private readonly db: D1Database) {}

  /** List documents belonging to the tenant — tenant_id is always in the WHERE clause */
  async list(ctx: TenantContext, limit = 50): Promise<Document[]> {
    const rows = await this.db
      .prepare(
        'SELECT id, title, created_at, created_by FROM documents WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?',
      )
      .bind(ctx.tenantId, limit)
      .all<Document>();
    return rows.results;
  }

  /** Fetch a single document — includes tenant_id in WHERE to prevent IDOR */
  async get(ctx: TenantContext, docId: string): Promise<Document | null> {
    return this.db
      .prepare('SELECT * FROM documents WHERE id = ? AND tenant_id = ?')
      .bind(docId, ctx.tenantId)
      .first<Document>();
  }

  /** Insert — tenant_id is set from context, not from the request body */
  async create(
    ctx: TenantContext,
    data: { title: string; content: string },
  ): Promise<Document> {
    const id = crypto.randomUUID();
    await this.db
      .prepare(
        'INSERT INTO documents (id, tenant_id, title, content, created_by) VALUES (?, ?, ?, ?, ?)',
      )
      .bind(id, ctx.tenantId, data.title, data.content, ctx.userId)
      .run();
    return { id, tenantId: ctx.tenantId, ...data, createdBy: ctx.userId };
  }

  /** Delete — always scoped to tenant; a tenant cannot delete another tenant's document */
  async delete(ctx: TenantContext, docId: string): Promise<boolean> {
    const result = await this.db
      .prepare('DELETE FROM documents WHERE id = ? AND tenant_id = ?')
      .bind(docId, ctx.tenantId)
      .run();
    return result.meta.changes > 0;
  }
}

interface Document {
  id: string;
  tenantId: string;
  title: string;
  content: string;
  createdBy: string;
}
```

### Handler wiring

```typescript
// src/handlers/documents.ts

import { resolveTenantContext } from '../lib/tenant';
import { DocumentRepository } from '../repositories/documents';

interface Env {
  DB: D1Database;
  SESSIONS: KVNamespace;
}

export async function handleListDocuments(req: Request, env: Env): Promise<Response> {
  const ctx = await resolveTenantContext(
    req.headers.get('Authorization')?.replace('Bearer ', '') ?? '',
    env.DB,
    env.SESSIONS,
  );

  if (!ctx) {
    return new Response(JSON.stringify({ error: 'Unauthenticated' }), { status: 401 });
  }

  const repo = new DocumentRepository(env.DB);
  const docs = await repo.list(ctx);

  return new Response(JSON.stringify({ documents: docs }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## KV Key Namespacing

KV does not support row-level permissions. Isolation must be enforced through the key structure. All KV keys for tenant-specific data must be prefixed with the tenant ID.

```typescript
// src/lib/tenant-kv.ts

/**
 * A KV accessor that scopes all keys to the tenant's namespace.
 * Callers can never read or write outside their tenant's prefix.
 */
export class TenantKV {
  private readonly prefix: string;

  constructor(
    private readonly kv: KVNamespace,
    ctx: TenantContext,
  ) {
    // Prefix every key with the tenant ID and a separator that cannot appear in IDs
    this.prefix = `t:${ctx.tenantId}:`;
  }

  async get<T>(key: string): Promise<T | null> {
    return this.kv.get<T>(this.prefix + key, 'json');
  }

  async put(key: string, value: unknown, options?: KVNamespacePutOptions): Promise<void> {
    return this.kv.put(this.prefix + key, JSON.stringify(value), options);
  }

  async delete(key: string): Promise<void> {
    return this.kv.delete(this.prefix + key);
  }

  async list(keyPrefix?: string): Promise<KVNamespaceListResult<unknown, string>> {
    return this.kv.list({ prefix: this.prefix + (keyPrefix ?? '') });
  }
}
```

Usage inside a handler:

```typescript
import { TenantKV } from '../lib/tenant-kv';

export async function handleGetSettings(req: Request, env: Env): Promise<Response> {
  const ctx = await resolveTenantContext(/* ... */);
  if (!ctx) return new Response('Unauthenticated', { status: 401 });

  // TenantKV constructor takes the context — impossible to create one without it
  const kv = new TenantKV(env.KV, ctx);
  const settings = await kv.get<TenantSettings>('settings');

  return new Response(JSON.stringify(settings ?? {}), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Tenant ID Validation

The tenant ID extracted from a session must be validated against the tenants table on every request. Do not trust a tenant ID embedded in the URL path or request body without cross-referencing it against the session.

```typescript
// Bad: accepting tenantId from the URL
const tenantId = url.pathname.split('/')[2];  // attacker-controlled
const docs = await db.prepare('SELECT * FROM documents WHERE tenant_id = ?').bind(tenantId).all();

// Good: tenantId always comes from the validated session context
const ctx = await resolveTenantContext(sessionToken, db, sessions);
const docs = await repo.list(ctx);  // TenantContext.tenantId is server-validated
```

## Cross-tenant Admin Queries

Super-admin operations that legitimately span tenants must be clearly marked and access-controlled separately:

```typescript
// src/lib/admin-context.ts

export interface AdminContext {
  readonly adminUserId: string;
  readonly scope: 'all_tenants';  // Explicit scope prevents accidental misuse
}

export async function resolveAdminContext(
  token: string,
  db: D1Database,
): Promise<AdminContext | null> {
  const admin = await db
    .prepare('SELECT id FROM admins WHERE api_key_hash = ? AND active = 1')
    .bind(await sha256Hex(token))
    .first<{ id: string }>();

  if (!admin) return null;
  return { adminUserId: admin.id, scope: 'all_tenants' };
}

// Admin repository functions accept AdminContext, not TenantContext
export class AdminDocumentRepository {
  constructor(private readonly db: D1Database) {}

  // Explicitly requires an AdminContext — cannot be called from a tenant handler accidentally
  async listAllTenants(_ctx: AdminContext): Promise<Document[]> {
    return (await this.db.prepare('SELECT * FROM documents LIMIT 1000').all<Document>()).results;
  }
}
```

## Anti-patterns

- **Putting `tenant_id` in the URL path and reading it without session verification**: An attacker changes `/api/tenants/victim-tenant/documents` to enumerate another tenant's data. The tenant ID must always come from the session, not from the URL.
- **Relying on application-layer filtering only, with no DB-layer constraint**: If the D1 query does not include `AND tenant_id = ?`, a coding error (a missing `where` clause, a copy-paste bug) leaks all tenants' data. The DB column constraint is the last-resort safeguard.
- **Using a single KV key prefix for all tenants**: Keys like `settings:{feature}` without a tenant prefix allow one tenant to overwrite another's settings if a bug omits the prefix.
- **Storing the tenant ID in a client-side JWT claim without server-side verification**: JWTs can be inspected and forged (or the alg confusion attack applied). Always verify the session against your sessions store and then look up the tenant from there.
- **Sharing a D1 database handle globally without context**: A global `const db = env.DB` passed around without a tenant context makes it easy to write `db.prepare(...)` without tenant filtering. Wrap the database in a context-aware repository class.

## Gotchas

- **KV list() pagination**: When listing KV keys by tenant prefix, results are paginated. If your list function does not follow `cursor` values, it will silently return only the first 1000 keys. Use a `while (result.list_complete === false)` loop for completeness.
- **D1 batch transactions**: When running multiple queries in a D1 batch (`db.batch([...])`), each prepared statement must independently include the `tenant_id` filter. The batch mechanism does not add it automatically.
- **Durable Object IDs and tenant isolation**: DOs identified by `idFromName('shared-resource')` are shared across all Workers and tenants. Prefix DO names with the tenant ID: `idFromName('${tenantId}:resource-name')`.
- **Log sanitization**: Structured logs that include query parameters may expose tenant IDs. Treat `tenant_id` values as PII in log outputs — hash or truncate them if regulations require.
- **Plan-based feature limits**: Tenant context carries the `plan` field. Enforce plan-based limits (e.g., maximum documents per tenant) inside the repository layer, not just the handler, so the limit applies to API calls, admin imports, and background jobs equally.

## Verification

```sql
-- Run these checks against D1 to verify isolation
-- 1. Every documents row should have a non-null tenant_id
SELECT COUNT(*) FROM documents WHERE tenant_id IS NULL;  -- Must return 0

-- 2. Spot-check: a known tenant's rows should not appear in another tenant's result set
SELECT COUNT(*) FROM documents WHERE tenant_id = 'tenant-a' AND id IN (
  SELECT id FROM documents WHERE tenant_id = 'tenant-b'
);  -- Must return 0

-- 3. All critical tables have the tenant_id column
SELECT name FROM sqlite_master
WHERE type='table' AND name NOT IN ('tenants', 'admins', 'sqlite_stat1')
  AND name NOT IN (SELECT DISTINCT tablename FROM pragma_table_info(name) WHERE name = 'tenant_id');
```

```bash
# Integration test: authenticate as tenant A and attempt to fetch tenant B's document
TENANT_A_TOKEN="..."
TENANT_B_DOC_ID="doc-from-tenant-b"

curl -s -H "Authorization: Bearer $TENANT_A_TOKEN" \
  "https://api.example.com/api/documents/$TENANT_B_DOC_ID" \
  | jq .  # Must return 404 (not found within tenant A's scope) or 403
```

## Related

- `idor-insecure-direct-object-reference.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `sql-injection-prevention-d1-workers.md`
- `durable-objects-auth-patterns.md`
- `select-star-data-leak.md`

## Sources

- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- OWASP multi-tenancy guidance: https://owasp.org/www-project-web-security-testing-guide/
- AWS multi-tenancy isolation patterns (applicable concepts): https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html
