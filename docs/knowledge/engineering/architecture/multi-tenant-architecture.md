# Multi-Tenant Architecture

Multi-tenant architecture allows multiple customers (tenants) to share the same application instance while maintaining data isolation. This approach balances cost efficiency with security requirements.

## Shared Database Patterns

The most cost-effective approach uses a single database with tenant separation at the application level:

```sql
-- Tenant ID column in every table
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMP
);

-- All queries must include tenant filter
SELECT * FROM users WHERE tenant_id = 123;
```

This pattern works well for small to medium tenants but creates performance bottlenecks as data grows.

## Separate Schemas

Database schemas provide better isolation while sharing the same database:

```sql
-- Each tenant gets its own schema
CREATE SCHEMA tenant_123;
CREATE TABLE tenant_123.users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255),
    created_at TIMESTAMP
);

-- Application routes queries to correct schema
SELECT * FROM tenant_123.users WHERE id = 456;
```

Schemas offer better performance isolation but require more complex deployment scripts and monitoring.

## Isolated Instances

Complete database separation provides maximum isolation:

```sql
-- Each tenant gets separate database instance
CREATE DATABASE tenant_123_db;
CREATE TABLE tenant_123_db.users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255),
    created_at TIMESTAMP
);
```

This approach requires significant infrastructure overhead but offers perfect security isolation and performance tuning capabilities.

## Row-Level Security

Modern databases support built-in row-level security:

```sql
-- PostgreSQL example
CREATE POLICY tenant_policy ON users
FOR ALL TO PUBLIC
USING (tenant_id = current_setting('app.current_tenant')::int);

-- Set tenant context per session
SET app.current_tenant = '123';
```

RLS reduces application complexity but may impact query performance and requires database-specific implementation.

## Cost Tradeoffs

**Shared Database**: $0.50-1.00/tenant/month for basic infrastructure, but requires careful monitoring to prevent performance issues. Complex queries can become slow as data grows.

**Separate Schemas**: $2-5/tenant/month for database resources, better performance isolation but increased deployment complexity and backup overhead.

**Isolated Instances**: $10-50/tenant/month for dedicated infrastructure, maximum security but highest operational costs and complexity.

## Real Implementation Gotchas

```python
# Common mistake: forgetting tenant context
def get_user(user_id):
    # Wrong - no tenant filtering
    return User.query.get(user_id)

# Correct - always include tenant
def get_user(user_id):
    return User.query.filter_by(
        id=user_id,
        tenant_id=current_tenant.id
    ).first()
```

**Performance Issues**: Queries without proper indexing on tenant_id columns can cause severe slowdowns. Always index tenant_id fields.

**Backup Complexity**: Shared databases require careful backup strategies to avoid cross-tenant data exposure during restores.

## When to use

Use shared database or schema patterns when:
- You have small to medium tenants (under 10,000 users)
- Cost optimization is critical
- Tenants have similar resource requirements
- You can implement robust monitoring and alerting

Choose isolated instances when:
- Security compliance requires strict data separation
- Tenants have vastly different resource needs
- You need maximum performance isolation
- Regulatory requirements mandate separate databases

## When NOT to use

Avoid shared patterns when:
- Tenants require different database versions or configurations
- Compliance regulations demand complete data separation
- You expect rapid tenant growth with varying resource demands

Don't use isolated instances when:
- You have many small tenants (<100 users each)
- Cost is the primary
