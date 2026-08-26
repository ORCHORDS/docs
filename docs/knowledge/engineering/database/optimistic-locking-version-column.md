# optimistic-locking-version-column

**Issue:** Preventing lost updates with a version counter
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Two users read the same row and both write back — the second write silently overwrites the first.

## Pattern / Solution
```sql
ALTER TABLE documents ADD COLUMN version INT NOT NULL DEFAULT 1;

-- Update only if version matches; increment on success
UPDATE documents
SET title = $1, body = $2, version = version + 1
WHERE id = $3 AND version = $4;
-- If rowcount = 0, conflict occurred — retry or return error

-- Trigger to auto-increment version
CREATE OR REPLACE FUNCTION increment_version()
RETURNS TRIGGER AS $$
BEGIN NEW.version = OLD.version + 1; RETURN NEW; END;
$$ LANGUAGE plpgsql;
```

## Gotchas
- Must check `rowsAffected === 1` in the application; a 0-row update is silent in SQL
- Version column adds 4 bytes per row — negligible but worth noting
- Does not prevent phantom reads; use `REPEATABLE READ` isolation for that

## Related
- `transaction-isolation-levels.md`
- `audit-columns-pattern.md`
