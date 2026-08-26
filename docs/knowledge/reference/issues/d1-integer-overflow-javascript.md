# d1-integer-overflow-javascript

**Issue:** D1 (SQLite) `INTEGER` can store 64-bit signed integers, but JavaScript `number` only has 53 bits of safe integer precision, causing silent data corruption
**Date:** 2026-08-11
**Status:** documented

## Symptom
A large integer ID (e.g., a Twitter snowflake ID: `1234567890123456789`) is stored correctly in D1 but returns as a slightly different number when read back through the Workers binding, because it exceeds `Number.MAX_SAFE_INTEGER` (2^53 - 1).

## Root cause
D1's SQLite stores 64-bit integers. The Workers binding deserializes them as JavaScript `number` (IEEE 754 double), which can only represent integers exactly up to 2^53. Larger integers lose precision silently.

## Fix
Store large integers as `TEXT` and convert in the application:
```sql
CREATE TABLE events (id TEXT PRIMARY KEY); -- store as string
```
```ts
// Insert
await db.prepare('INSERT INTO events (id) VALUES (?)').bind(BigInt(id).toString()).run();
// Read
const row = await db.prepare('SELECT id FROM events WHERE id = ?').bind(id.toString()).first();
const id = BigInt(row.id);
```

## Detection
```
grep -rn "INTEGER" schema.sql | grep -i "id\|snowflake\|timestamp"
```
If integer PKs or external IDs exceed 2^53, they need text storage.

## Related
- `d1-column-affinity-gotcha.md`
- `json-parse-silent-nan.md`
