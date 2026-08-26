# table-partitioning-postgres

**Issue:** Postgres native partitioning setup, maintenance, and gotchas are non-obvious
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams create partitioned tables but see no performance improvement, or hit errors about constraint violations and missing partitions for new date ranges.

## Pattern / Solution
Declare parent as PARTITION BY RANGE/LIST/HASH. Create child partitions with CREATE TABLE child PARTITION OF parent FOR VALUES FROM (x) TO (y). Use pg_partman extension for automated management. Indexes on parent propagate to children.

## Gotchas
- Default partition catches rows not matching any partition -- can mask errors
- Primary key and unique constraints must include partition key
- Partition pruning only works with immutable expressions; NOW() in WHERE disables pruning

## Related
- horizontal-partitioning
- vacuum-and-bloat-postgres
- autovacuum-tuning
