# PostgreSQL session_replication_role trigger boundary

**Issue:** Setting `session_replication_role` to `replica` during a load or migration can silently bypass business triggers and foreign-key checks, leaving data that normal writes could never create.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep the default `origin` for ordinary application and migration sessions. Use `replica` only for a reviewed replication or restore path that owns validation.
- Grant permission to change the setting only to a dedicated role, use an isolated connection, and scope the change as narrowly as possible. Reset it before the connection returns to a pool.
- Inventory every affected trigger and rule. Default triggers do not fire in replica mode; triggers explicitly enabled `ALWAYS` still do.
- Treat foreign keys as affected triggers: replica mode can disable their checks. Validate constraints and application invariants before making imported data visible.
- Expect a plan-cache flush when the setting changes and include that cost in bulk-load timing.

## Verification

Seed rows that would violate a foreign key and rows that should invoke audit or denormalization triggers. Prove the controlled load detects or repairs each invariant, prove normal sessions remain at `origin`, and test failures, cancellation, pooled-connection reuse, and retry.

## Gotchas

- Faster ingestion is not a justification for dropping correctness controls.
- `origin` and `local` are equivalent inside PostgreSQL, although third-party replication systems may assign their own meaning.
- Constraint validation does not reconstruct omitted audit events or other trigger side effects.

## Official source

- [PostgreSQL 18 client connection defaults: session_replication_role](https://www.postgresql.org/docs/18/runtime-config-client.html#GUC-SESSION-REPLICATION-ROLE)
