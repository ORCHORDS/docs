# PostgreSQL temporal WITHOUT OVERLAPS constraints

**Issue:** Application-only checks for overlapping validity or reservation ranges race under concurrent transactions and allow contradictory rows.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On a supported PostgreSQL release, express temporal uniqueness with a primary-key or unique constraint whose final range or multirange element uses `WITHOUT OVERLAPS`. Model bounds and empty-range behavior explicitly, use a canonical range type, and retain ordinary identifiers for stable references. Treat this as a database invariant; application prechecks may improve messages but must not authorize the write.

Review index access method support, migration locking, and invalid legacy rows before adding the constraint. For temporal referential rules, verify the referenced periods collectively cover the referencing period rather than assuming a single row must cover it.

## Verification

Race two transactions that attempt overlapping ranges and prove one is rejected. Cover adjacent non-overlapping bounds, empty ranges, infinity, timezone transitions, updates that create overlap, and migration over dirty historical data. Inspect the deployed constraint definition after restore.

## Gotchas

- Inclusive and exclusive bounds change whether adjacent periods conflict.
- Current documentation must match the deployed PostgreSQL major version.
- Constraint enforcement does not define business rules for gaps.

## Official source

- [PostgreSQL constraints documentation](https://www.postgresql.org/docs/current/ddl-constraints.html)
