# sqlite-d1-patterns

**Issue:** Cloudflare D1 (SQLite at edge) has unique constraints and behaviors compared to server Postgres
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Migrating from Postgres to D1 or building edge-native apps. D1 uses SQLite semantics but is accessed over HTTP from Workers -- each request may hit a different replica.

## Pattern / Solution
D1 is eventually consistent across regions. Use db.prepare() for parameterized queries. Batch multiple statements with db.batch([stmt1, stmt2]) for atomicity. Schema migrations via Wrangler: wrangler d1 migrations apply. Use INTEGER PRIMARY KEY for fast inserts.

## Gotchas
- No stored procedures, no extensions, no custom functions
- Read replicas may lag 100-500ms behind primary write
- SQLite type affinity is loose -- enforce types in application layer
- Max database size and row size limits differ from Postgres

## Related
- sqlite-wal-mode
- sqlite-journal-modes
- eventual-consistency-patterns
