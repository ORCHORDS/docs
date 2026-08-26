# created-at-updated-at

**Issue:** Standard timestamp columns for tracking record lifecycle
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every table needs creation and modification timestamps for debugging, caching, and sync.

## Pattern / Solution
```sql
-- Always use TIMESTAMPTZ (with timezone), never TIMESTAMP
CREATE TABLE posts (
  id         BIGSERIAL PRIMARY KEY,
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Prisma convention
model Post {
  id        Int      @id @default(autoincrement())
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

## Gotchas
- `TIMESTAMP` stores no timezone info — data becomes ambiguous across DST changes; always use `TIMESTAMPTZ`
- `now()` inside a transaction returns transaction start time, not wall clock — use `clock_timestamp()` for real wall time
- In Prisma, `@updatedAt` is handled client-side; the DB trigger is the safer guarantee

## Related
- `audit-columns-pattern.md`
- `optimistic-locking-version-column.md`
