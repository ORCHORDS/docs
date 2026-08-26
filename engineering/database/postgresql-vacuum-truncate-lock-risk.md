# PostgreSQL VACUUM truncation lock-risk controls

**Issue**

VACUUM can attempt to truncate empty pages at a table's end, requiring an aggressive lock that may interfere with latency-sensitive traffic.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Identify tables where truncation lock attempts create unacceptable latency and evaluate `vacuum_truncate` or per-table storage settings.
- Treat disabling truncation as a latency tradeoff, not space reclamation; monitor relation size and free space.
- Schedule explicit maintenance for tables that accumulate tail free pages.
- Keep autovacuum enabled for tuple cleanup and wraparound protection.

## Verification

1. Reproduce tail-page reclamation on a production-shaped table under concurrent reads and writes.
2. Measure lock waits, query latency, relation size, dead tuples, and transaction age.
3. Verify the chosen per-table setting after schema migration and restore.

## Gotchas

- Disabling truncation does not disable ordinary vacuum cleanup.
- Space may remain reusable inside the relation without returning to the filesystem.
- Manual VACUUM options and autovacuum storage parameters must be reviewed separately.

## Official source

- [Official documentation](https://www.postgresql.org/docs/current/runtime-config-vacuum.html)
