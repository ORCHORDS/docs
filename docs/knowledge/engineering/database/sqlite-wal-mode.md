# sqlite-wal-mode

**Issue:** Default SQLite journal mode causes write locks that block concurrent readers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SQLite application with multiple threads or processes seeing SQLITE_BUSY or serialized reads during writes.

## Pattern / Solution
Enable WAL mode: PRAGMA journal_mode=WAL. WAL allows concurrent readers with a single writer. Set PRAGMA synchronous=NORMAL with WAL for better performance. WAL is per-database and persists across connections.

## Gotchas
- WAL creates extra files (-wal, -shm) -- backup must include these files or use SQLite backup API
- WAL checkpoint happens automatically but can be triggered manually
- WAL performs worse than journal mode for write-heavy workloads with large transactions

## Related
- sqlite-journal-modes
- sqlite-d1-patterns
- database-backup-strategies
