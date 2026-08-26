# batch-update-patterns

**Issue:** Updating large numbers of rows without locking the table
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A single UPDATE of millions of rows holds locks for minutes, blocking reads and writes.

## Pattern / Solution
```sql
-- Batch update in chunks
DO $$
DECLARE
  batch_size INT := 1000;
  updated INT;
BEGIN
  LOOP
    UPDATE orders SET status = ''archived''
    WHERE id IN (
      SELECT id FROM orders WHERE status = ''closed'' AND created_at < now() - interval ''1 year''
      LIMIT batch_size
      FOR UPDATE SKIP LOCKED
    );
    GET DIAGNOSTICS updated = ROW_COUNT;
    EXIT WHEN updated = 0;
    PERFORM pg_sleep(0.1);  -- brief pause to release lock pressure
  END LOOP;
END $$;
```

## Gotchas
- `FOR UPDATE SKIP LOCKED` prevents blocking on rows already locked by other sessions
- Short sleep between batches reduces replication lag and lock contention
- Always test batch size — too small = too many round trips, too large = long locks

## Related
- `bulk-insert-patterns.md`
- `lock-timeout-patterns.md`
