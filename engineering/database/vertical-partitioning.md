# vertical-partitioning

**Issue:** Wide tables with many columns cause excessive I/O for queries that only need a few columns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Table with 50+ columns. Frequently queried columns live next to rarely used large text/blob columns. Row size causes fewer rows per page, more I/O.

## Pattern / Solution
Split wide table into core table (frequently accessed columns) and extension table (rarely accessed, large columns) linked by the same PK. Or move blob/text columns to object storage and store only reference URL in DB.

## Gotchas
- Joins between core and extension tables add query complexity
- Postgres stores columns > 2KB in TOAST tables automatically -- enabling compression first may be simpler
- Evaluate with pg_column_size before refactoring

## Related
- horizontal-partitioning
- covering-indexes
- json-columns-patterns
