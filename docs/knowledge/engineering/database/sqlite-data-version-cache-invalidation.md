# SQLite data-version cache invalidation

**Problem**

A process-local cache can become stale when another connection commits to the same database.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for lightweight change detection between separate SQLite connections.

## Controls

- Compare `PRAGMA data_version` values only from the same connection over time.
- Treat change as invalidation, not a complete event stream.
- Keep transaction isolation and schema version checks separate.

## Implementation

- Read and store the value after a successful cache fill.
- Recheck before reuse and refresh on change.
- Use application notifications for lower latency when available.

## Tests

- Commit from same and different connections, rollback, WAL checkpoint, and reopen; assert behavior.

## Gotchas

- Values from different connections are not comparable.
- It does not identify changed rows.
- Polling too frequently adds work.

## Official sources

- [Official documentation](https://sqlite.org/pragma.html#pragma_data_version)
