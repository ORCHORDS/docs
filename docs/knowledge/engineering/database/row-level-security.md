# row-level-security

**Issue:** Enforcing tenant/user data isolation at the database layer with RLS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Multi-tenant apps that rely solely on application-layer WHERE clauses risk data leaks from query bugs.

## Pattern / Solution
```sql
-- Enable RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

-- Policy: users see only their own rows
CREATE POLICY user_isolation ON documents
  USING (user_id = current_setting(''app.current_user_id'')::bigint);

-- Set context at session start
SET app.current_user_id = 42;

-- Bypass for service role
CREATE POLICY admin_all ON documents TO service_role USING (true);

-- Tenant isolation
CREATE POLICY tenant_isolation ON documents
  USING (tenant_id = current_setting(''app.tenant_id'')::bigint);
```

## Gotchas
- Table owner bypasses RLS by default — use `FORCE ROW LEVEL SECURITY` to include owner
- Performance: RLS adds a filter to every query; index the policy columns
- `current_setting()` with no default throws an error if not set — use `current_setting(''app.x'', true)` to return NULL instead

## Related
- `column-level-security.md`
- `soft-delete-schema-design.md`
