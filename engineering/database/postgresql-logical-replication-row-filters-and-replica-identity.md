# PostgreSQL logical replication row filters and replica identity

**Issue:** A team uses logical-replication row filters for tenancy, regional copies, or performance, then discovers missing rows, unexpected INSERT/DELETE transformations, or replication failures on updates.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat a publication row filter as a replication boundary with explicit data semantics—not as a substitute for application authorization. Design the filter, replica identity, initial synchronization, and subscriber expectations together.

**Sources:**

- [PostgreSQL row filters](https://www.postgresql.org/docs/current/logical-replication-row-filter.html)
- [PostgreSQL publications](https://www.postgresql.org/docs/current/logical-replication-publication.html)
- [PostgreSQL CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html)

## Rules that change behavior

- A filtered row is published only when the expression evaluates true; false and NULL are excluded.
- For UPDATE/DELETE publications, every filter column must be covered by the table’s replica identity.
- When an update crosses the filter boundary, PostgreSQL converts it: non-matching → matching becomes INSERT; matching → non-matching becomes DELETE.
- TRUNCATE is not filtered.
- Initial synchronization has its own semantics and version compatibility requirements.
- Multiple row filters for the same table/publication subscriptions can combine with OR semantics; an unfiltered publication can make filters redundant.

## Operating controls

- require a primary key or deliberately chosen replica identity; avoid `REPLICA IDENTITY FULL` unless its cost is tested and justified;
- keep the publication role least-privileged and test which data is visible under that role;
- use filters only for data distribution, not as the only tenant-isolation control;
- document expected INSERT/UPDATE/DELETE transformations at the boundary;
- include schema, partition-root behavior, and subscriber-version compatibility in change review;
- test initial sync, steady-state DML, filter-crossing updates, TRUNCATE, reconnect, and resubscription.

## Verification

- a row that enters/leaves the predicate produces the expected subscriber INSERT/DELETE;
- an update/delete with every valid key state either replicates correctly or fails before production;
- a sample subscriber receives no unexpected data from another tenant/region;
- a full initial synchronization is inspected against the filter and PostgreSQL-version behavior;
- monitoring catches replication lag, slot growth, apply errors, and unexpected change volume.

## Gotchas

- DDL is not replicated by logical replication; manage it separately.
- A row filter has no effect on TRUNCATE.
- `publish_via_partition_root` affects which partition row filter is applied.
- Do not assume a filtered replica is a safe place for less-restricted users.

## Related

- `the replication section in this file`
- `patterns/multi-tenant-data-isolation.md`
- `security/oauth-best-practices.md`
