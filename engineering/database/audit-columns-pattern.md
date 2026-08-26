# audit-columns-pattern

**Issue:** Tracking who created and last modified a row
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without audit columns, debugging data issues requires reconstructing history from logs.

## Pattern / Solution
```sql
CREATE TABLE documents (
  id           BIGSERIAL PRIMARY KEY,
  title        TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by   BIGINT REFERENCES users(id),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by   BIGINT REFERENCES users(id)
);

-- Auto-update updated_at via trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_updated_at
  BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

## Gotchas
- `updated_at` trigger fires on every UPDATE even if data unchanged — use `IF ROW(NEW.*) IS DISTINCT FROM ROW(OLD.*)` to skip no-op updates
- `created_by` / `updated_by` require the app to inject the user ID into the session
- For full history, use an audit log table or temporal tables instead

## Related
- `created-at-updated-at.md`
- `optimistic-locking-version-column.md`
