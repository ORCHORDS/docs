# column-level-security

**Issue:** Restricting access to sensitive columns using GRANT and views
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some columns (SSN, salary, credit card) should not be visible to all application roles.

## Pattern / Solution
```sql
-- Create role with restricted column access
CREATE ROLE app_reader;
GRANT SELECT (id, email, name) ON users TO app_reader;
-- app_reader cannot SELECT ssn or salary

-- Use a view to expose only safe columns
CREATE VIEW users_public AS
  SELECT id, email, full_name FROM users;
GRANT SELECT ON users_public TO app_reader;

-- Mask sensitive data for non-privileged roles
CREATE VIEW users_masked AS
  SELECT id, email,
         regexp_replace(phone, ''\d{4}$'', ''****'') AS phone
  FROM users;
```

## Gotchas
- Column-level GRANT is supported in PostgreSQL; not all ORMs respect it
- Views can be a simpler alternative to column GRANTs
- Security definer views run as the view owner — be careful about privilege escalation

## Related
- `row-level-security.md`
- `database-audit-logging.md`
