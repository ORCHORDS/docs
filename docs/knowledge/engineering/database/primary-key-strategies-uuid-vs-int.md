# primary-key-strategies-uuid-vs-int

**Issue:** Choosing between integer sequences and UUIDs as primary keys
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Integer PKs are compact and ordered; UUIDs are globally unique but cause index fragmentation with random values.

## Pattern / Solution
```sql
-- Auto-increment integer (best for single-node, high-insert tables)
CREATE TABLE events (id BIGSERIAL PRIMARY KEY);

-- UUIDv4 (random — causes B-tree fragmentation)
CREATE TABLE items (id UUID PRIMARY KEY DEFAULT gen_random_uuid());

-- UUIDv7 (time-ordered — best of both worlds, Postgres 17+)
CREATE TABLE items (id UUID PRIMARY KEY DEFAULT uuidv7());

-- ULID via extension
CREATE EXTENSION IF NOT EXISTS pgulid;
CREATE TABLE items (id TEXT PRIMARY KEY DEFAULT gen_ulid());
```

## Gotchas
- UUIDv4 as PK on large tables fragments the B-tree index heavily — use UUIDv7 or ULID
- BIGSERIAL can exhaust if you insert billions of rows; use BIGINT not INT
- Exposing integer PKs in URLs leaks row counts to users — prefer UUIDs externally

## Related
- `surrogate-vs-natural-keys.md`
- `composite-keys.md`
