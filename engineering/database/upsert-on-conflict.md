# upsert-on-conflict

**Issue:** Atomically inserting or updating rows to avoid duplicate key errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Insert-or-update patterns with a read-then-write are prone to race conditions under concurrency.

## Pattern / Solution
```sql
-- Upsert with DO UPDATE
INSERT INTO user_settings (user_id, key, value)
VALUES ($1, $2, $3)
ON CONFLICT (user_id, key)
DO UPDATE SET value = EXCLUDED.value, updated_at = now();

-- Upsert, ignore if exists
INSERT INTO events (id, payload)
VALUES ($1, $2)
ON CONFLICT (id) DO NOTHING;

-- Upsert with conditional update
INSERT INTO counters (name, count)
VALUES (''page_views'', 1)
ON CONFLICT (name)
DO UPDATE SET count = counters.count + 1
WHERE counters.updated_at < now() - interval ''1 hour'';
```

## Gotchas
- `ON CONFLICT` requires specifying the conflict target (column or constraint name)
- `EXCLUDED` refers to the row that was attempted to be inserted
- In MySQL the equivalent is `INSERT ... ON DUPLICATE KEY UPDATE`
- Does not work with deferred unique constraints

## Related
- `unique-constraints.md`
- `bulk-insert-patterns.md`
