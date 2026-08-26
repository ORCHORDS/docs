# PostgreSQL Row-Level Security for Multi-Tenancy

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your multi-tenant SaaS application relies on application-layer WHERE
clauses (`WHERE tenant_id = ?`) to isolate tenant data. A missed filter
in any query leaks data across tenants. Code reviews cannot catch every
instance, and a single ORM scope misconfiguration exposes one customer's
data to another. You need database-enforced isolation that works even
when application code has bugs.

## Context

PostgreSQL Row-Level Security (RLS) enforces access policies at the
database level — the database automatically appends filtering conditions
to every query based on the current session context. Even if application
code omits a tenant filter, RLS ensures that queries only return rows
belonging to the current tenant. In 2026, RLS is the recommended
approach for shared-schema multi-tenancy in PostgreSQL-based SaaS
applications, used by Supabase, Neon, and AWS RDS as the foundation
for tenant isolation. RLS adds minimal query overhead (typically < 5%)
when tenant_id columns are properly indexed.

## Multi-tenancy models

| Model | Isolation | Cost | Complexity | RLS needed? |
|---|---|---|---|---|
| **Database per tenant** | Full | High (N databases) | High (migrations × N) | No |
| **Schema per tenant** | Full | Medium | Medium | No |
| **Shared schema + RLS** | Row-level | Low (1 database) | Low | Yes |
| **Shared schema, app-only** | Application-enforced | Low | Low | Risky |

Shared schema with RLS is the best balance for most SaaS applications —
low infrastructure cost, simple migrations, and database-enforced
isolation.

## Implementation

### 1. Add tenant_id to all tables

```sql
-- Every tenant-scoped table includes tenant_id
CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  customer_id UUID NOT NULL,
  total NUMERIC(10, 2) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_orders_tenant ON orders(tenant_id);
```

### 2. Enable RLS and create policies

```sql
-- Enable RLS on the table
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see rows matching their tenant
CREATE POLICY tenant_isolation ON orders
  USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Policy applies to all operations (SELECT, INSERT, UPDATE, DELETE)
-- For INSERT, use WITH CHECK to validate new rows:
CREATE POLICY tenant_insert ON orders
  FOR INSERT
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::UUID);
```

### 3. Set tenant context per request

```typescript
// Express middleware — set tenant context on every request
async function tenantMiddleware(req, res, next) {
  const tenantId = req.headers['x-tenant-id'];
  if (!tenantId) return res.status(401).json({ error: 'Missing tenant' });

  const client = await pool.connect();
  try {
    await client.query(
      "SET LOCAL app.current_tenant_id = $1",
      [tenantId]
    );
    req.db = client;
    next();
  } catch (err) {
    client.release();
    next(err);
  }
}
```

`SET LOCAL` scopes the setting to the current transaction, ensuring
tenant context does not leak between requests sharing a connection pool.

### 4. Admin bypass

```sql
-- Create a role that bypasses RLS for admin tools
CREATE ROLE app_admin BYPASSRLS;

-- Application role does NOT bypass RLS
CREATE ROLE app_user NOINHERIT;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;
```

`FORCE ROW LEVEL SECURITY` ensures RLS applies even to the table owner.
Without it, the table owner implicitly bypasses all policies.

## ORM integration

### Prisma

```typescript
// Prisma client extension for RLS
const prisma = new PrismaClient().$extends({
  query: {
    $allOperations({ args, query }) {
      return prisma.$transaction(async (tx) => {
        await tx.$executeRawUnsafe(
          `SET LOCAL app.current_tenant_id = '${tenantId}'`
        );
        return query(args);
      });
    },
  },
});
```

### Drizzle

```typescript
// Drizzle with RLS context
async function withTenant<T>(
  tenantId: string,
  fn: (db: DrizzleDB) => Promise<T>
): Promise<T> {
  return db.transaction(async (tx) => {
    await tx.execute(
      sql`SET LOCAL app.current_tenant_id = ${tenantId}`
    );
    return fn(tx);
  });
}
```

## Testing RLS policies

```sql
-- Test: verify tenant isolation
SET app.current_tenant_id = 'tenant-a';
INSERT INTO orders (tenant_id, customer_id, total)
VALUES ('tenant-a', 'cust-1', 100.00);

SET app.current_tenant_id = 'tenant-b';
SELECT * FROM orders;  -- Should return 0 rows

-- Test: verify cross-tenant insert is blocked
SET app.current_tenant_id = 'tenant-b';
INSERT INTO orders (tenant_id, customer_id, total)
VALUES ('tenant-a', 'cust-2', 50.00);  -- Should fail
```

## Anti-patterns

- **RLS without FORCE** — without `ALTER TABLE ... FORCE ROW LEVEL
  SECURITY`, the table owner bypasses all policies. If your application
  connects as the table owner, RLS provides no protection.
- **App-only tenant filtering** — relying solely on ORM scopes or
  middleware WHERE clauses. A single missed filter exposes tenant data.
  RLS is the safety net.
- **Global SET instead of SET LOCAL** — using `SET app.current_tenant_id`
  without `LOCAL` makes the setting persist for the entire connection
  session. With connection pooling, the next request on the same
  connection inherits the previous tenant's context.
- **No index on tenant_id** — RLS adds a WHERE clause to every query.
  Without an index on tenant_id, every query becomes a full table scan.

## Gotchas

- **Connection pooling interaction** — RLS relies on session settings.
  With PgBouncer in transaction mode, `SET LOCAL` is scoped to the
  transaction and safe. In session mode, `SET` persists for the
  connection lifetime — always use `SET LOCAL` with pooling.
- **Superuser bypasses RLS** — PostgreSQL superusers and roles with
  BYPASSRLS always bypass RLS policies. Never connect the application
  as a superuser.
- **RLS and pg_dump** — `pg_dump` runs as a superuser and bypasses RLS,
  so backups include all tenant data. This is correct for backups but
  means tenant-scoped exports require application logic.
- **Performance with complex policies** — simple equality policies
  (`tenant_id = setting`) have minimal overhead. Policies with
  subqueries or joins can add significant query planning cost.

## Verification

- RLS is enabled on all tenant-scoped tables.
- `FORCE ROW LEVEL SECURITY` is set to prevent owner bypass.
- Tenant context uses `SET LOCAL` (not `SET`) for connection pool safety.
- `tenant_id` columns are indexed on all tables.
- Automated tests verify cross-tenant isolation.
- Admin access uses a separate role with explicit BYPASSRLS.

## Related

- `documentation/docs/policies/database/connection-pooling-pgbouncer.md`
- `documentation/docs/policies/database/postgresql-optimization.md`
- `documentation/docs/policies/security/auth-patterns.md`

## Source URLs (verified 2026-08-16)

- PostgreSQL RLS multi-tenant guide — https://oneuptime.com/blog/post/2026-01-25-row-level-security-postgresql/view
- RLS for multi-tenant SaaS — https://medium.com/@anand_thakkar/row-level-security-rls-in-postgresql-for-multi-tenant-saas-apps-ef8c324031d0
- Multi-tenant DB with RLS — https://nileshblog.tech/multi-tenant-database-rls/
- AWS multi-tenant PostgreSQL best practices — https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/best-practices.html
