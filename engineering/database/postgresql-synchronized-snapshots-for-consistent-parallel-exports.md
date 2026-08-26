# PostgreSQL synchronized snapshots for consistent parallel exports

**Issue:** Parallel export workers that start independent transactions can observe different database states, producing an internally inconsistent backup or analytical extract.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Have a coordinator open an appropriate transaction and export its snapshot, then make each worker import that snapshot before issuing any query. Keep the coordinator transaction open until workers have acquired the snapshot. For supported backups, prefer `pg_dump -j`, which coordinates synchronized snapshots. Bound duration and monitor vacuum impact.

## Verification

During a staging export, mutate related tables concurrently and verify all worker outputs correspond to one consistent point. Restore the result into an isolated database and run referential, row-count, and application invariants. Confirm failure cleanup closes the snapshot-holding transaction.

## Gotchas

Exported snapshots are database-local and valid only while the exporting transaction remains open. Long transactions retain old row versions and can increase bloat; snapshot consistency does not replace restore testing.

## Official sources

- https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION
- https://www.postgresql.org/docs/current/app-pgdump.html
