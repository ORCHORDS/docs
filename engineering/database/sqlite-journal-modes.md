# sqlite-journal-modes

**Issue:** SQLite offers multiple journal modes with different durability and concurrency trade-offs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Choosing between DELETE, WAL, MEMORY, and OFF modes for different deployment contexts (embedded, testing, edge).

## Pattern / Solution
DELETE (default): journal written then deleted on commit, safe, single-writer. WAL: best for concurrent reads with writes, use for production apps. MEMORY: journal in RAM, fast, data lost on crash -- use for tests only. OFF: no journal, fastest, no durability -- use for read-only databases.

## Gotchas
- Changing journal mode acquires exclusive lock -- do it at startup with no other connections
- MEMORY mode fails with multiple processes accessing same file
- PRAGMA synchronous interacts with journal mode

## Related
- sqlite-wal-mode
- sqlite-d1-patterns
