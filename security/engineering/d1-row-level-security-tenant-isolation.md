# D1 Row-Level Security for Multi-Tenant Isolation

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A multi-tenant SaaS application stores all tenants in a shared Cloudflare D1 database, and a missing `WHERE tenant_id = ?` clause allows one tenant to read or mutate another tenant's data.

## Context
Cloudflare D1 does not enforce row-level security at the database engine layer the way PostgreSQL's `ROW SECURITY` policies do. Isolation must be implemented in the Worker by extracting a verified `tenant_id` from the authenticated JWT, binding it to every query as a parameterised value, and structurally preventing queries that omit the tenant filter. A thin query-builder abstraction enforces the filter at the call-site and makes cross-tenant access impossible to introduce accidentally.

## Schema Design for Tenant Isolation
Every tenant-scoped table must include a `tenant_id` column with a `NOT NULL` constraint and a composite index on `(tenant_id, <primary lookup column>)` to keep queries efficient.

```sql
-- migrations/0001_tenant_tables.sql
CREATE TABLE resources (
  id          TEXT    NOT NULL,
  tenant_id   TEXT    NOT NULL,
  name        TEXT    NOT NULL,
  payload     TEXT,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (id)
);

CREATE INDEX idx_resources_tenant ON resources (tenant_id, created_at DESC);

CREATE TABLE resource_members (
  resource_id TEXT    NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
  user_id     TEXT    NOT NULL,
  tenant_id   TEXT    NOT NULL,
  role        TEXT    NOT NULL DEFAULT 'viewer',
  PRIMARY KEY (resource_id, user_id)
);

CREATE INDEX idx_members_tenant ON resource_members (tenant_id, user_id);
```

## Extracting the Verified Tenant ID from the JWT
Never accept the tenant ID from the request URL or body. Extract it exclusively from the verified JWT payload to prevent tenant-spoofing.

```typescript
import { validateAccessJWT, type AccessClaims } from "./access-jwt";

interface TenantClaims extends AccessClaims {
  "custom:tenant_id": string;
}

async function getTenantId(request: Request, env: Env): Promise<string> {
  const token =
    request.headers.get("Authorization")?.replace(/^Bearer\s+/, "") ?? "";
  if (!token) throw new AuthError("Missing token");

  const claims = (await validateAccessJWT(
    token,
    env.CF_ACCESS_TEAM_DOMAIN,
    env.CF_ACCESS_AUD
  )) as TenantClaims;

  const tenantId = claims["custom:tenant_id"];
  if (!tenantId || typeof tenantId !== "string" || tenantId.length > 64) {
    throw new AuthError("Invalid tenant claim");
  }

  return tenantId;
}

class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}
```

## Scoped Query Builder
Wrap every D1 query in a `TenantDB` class that automatically prepends the `tenant_id` filter. Callers cannot issue a query without supplying the tenant scope.

```typescript
class TenantDB {
  constructor(
    private readonly db: D1Database,
    private readonly tenantId: string
  ) {}

  async listResources(limit = 50, offset = 0): Promise<Resource[]> {
    const { results } = await this.db
      .prepare(
        "SELECT id, name, created_at FROM resources WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
      )
      .bind(this.tenantId, limit, offset)
      .all<Resource>();
    return results;
  }

  async getResource(id: string): Promise<Resource | null> {
    // Include tenant_id in WHERE to prevent IDOR
    return this.db
      .prepare("SELECT id, name, payload, created_at FROM resources WHERE id = ? AND tenant_id = ?")
      .bind(id, this.tenantId)
      .first<Resource>();
  }

  async createResource(id: string, name: string, payload: string): Promise<void> {
    await this.db
      .prepare("INSERT INTO resources (id, tenant_id, name, payload) VALUES (?, ?, ?, ?)")
      .bind(id, this.tenantId, name, payload)
      .run();
  }

  async deleteResource(id: string): Promise<boolean> {
    const result = await this.db
      .prepare("DELETE FROM resources WHERE id = ? AND tenant_id = ?")
      .bind(id, this.tenantId)
      .run();
    return (result.meta.changes ?? 0) > 0;
  }
}

interface Resource {
  id: string;
  name: string;
  payload?: string;
  created_at: number;
}
```

## Wiring TenantDB Into the Request Handler
Instantiate `TenantDB` once per request after authenticating. Pass it to route handlers rather than the raw `D1Database` binding.

```typescript
export interface Env {
  DB: D1Database;
  CF_ACCESS_TEAM_DOMAIN: string;
  CF_ACCESS_AUD: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let tenantId: string;
    try {
      tenantId = await getTenantId(request, env);
    } catch {
      return new Response("Unauthorized", { status: 401 });
    }

    const db = new TenantDB(env.DB, tenantId);
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/resources") {
      const resources = await db.listResources();
      return Response.json(resources);
    }

    if (request.method === "GET" && url.pathname.startsWith("/resources/")) {
      const id = url.pathname.split("/").pop()!;
      const resource = await db.getResource(id);
      return resource
        ? Response.json(resource)
        : new Response("Not Found", { status: 404 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## Cross-Tenant Join Prevention
When joining tables, always include the `tenant_id` in the join condition to prevent cross-tenant data leaking through a related table.

```typescript
async function getResourceWithMembers(
  db: D1Database,
  tenantId: string,
  resourceId: string
): Promise<ResourceWithMembers | null> {
  // Both sides of the join are filtered by tenant_id
  const result = await db
    .prepare(`
      SELECT r.id, r.name, rm.user_id, rm.role
      FROM resources r
      JOIN resource_members rm
        ON rm.resource_id = r.id AND rm.tenant_id = r.tenant_id
      WHERE r.id = ? AND r.tenant_id = ?
    `)
    .bind(resourceId, tenantId)
    .all<ResourceWithMembers>();

  return result.results[0] ?? null;
}

interface ResourceWithMembers {
  id: string;
  name: string;
  user_id: string;
  role: string;
}
```

## Anti-patterns
- Accepting `tenant_id` from URL path parameters or request bodies and using it directly in queries — callers can supply any tenant ID
- Issuing queries against the raw `D1Database` binding from route handlers instead of through the scoped wrapper
- Omitting `tenant_id` from the WHERE clause on UPDATE or DELETE statements — allows cross-tenant mutation
- Using `LIKE` with a user-supplied prefix as the tenant filter — vulnerable to SQL injection and prefix-collision attacks
- Relying on application-layer filtering after a full-table SELECT — fetches cross-tenant data even if it is not returned to the caller

## Gotchas
- D1's `batch()` API runs statements in the same transaction; all statements in a batch must include the tenant filter or the isolation guarantee is broken
- `result.meta.changes` returns `undefined` when no rows are modified — guard with `?? 0` before comparing
- D1 does not yet enforce foreign key constraints by default; run `PRAGMA foreign_keys = ON;` at the start of each transaction when referential integrity matters
- The composite index `(tenant_id, created_at)` is critical for list queries; without it D1 performs a full-table scan per request

## Verification
1. Mint two JWTs with different `custom:tenant_id` values (`tenant-a` and `tenant-b`).
2. Create a resource as `tenant-a`, then attempt to retrieve it using a `tenant-b` token — expect `404`.
3. Attempt deletion of the `tenant-a` resource using a `tenant-b` token — expect `404` and verify `meta.changes === 0`.
4. Run `D1` explain queries to confirm the `(tenant_id, created_at)` index is used for list operations.

## Related
- [Multi-Tenancy Isolation Workers KV D1](multi-tenancy-isolation-workers-kv-d1.md)
- [IDOR Insecure Direct Object Reference](idor-insecure-direct-object-reference.md)
- [SQL Injection Prevention D1 Workers](sql-injection-prevention-d1-workers.md)
- [Cloudflare Access JWT Assertion Validation](cloudflare-access-jwt-assertion-validation.md)

## Sources
- https://developers.cloudflare.com/d1/get-started/
- https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
- https://www.cloudflare.com/learning/security/what-is-zero-trust/
- https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
