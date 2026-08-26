# PostgreSQL collation-version refresh and reindex

**Issue:** An operating-system or ICU collation upgrade can change sort rules while existing indexes still reflect the old version, producing incorrect ordered behavior.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Inventory collation version mismatches after platform upgrades. Rebuild every affected index and other stored object whose semantics depend on the collation before running `ALTER COLLATION ... REFRESH VERSION`; refreshing metadata alone does not rewrite data. Schedule locks and capacity, identify dependent databases, and prevent writes that rely on affected uniqueness until remediation completes.

## Verification

Create strings whose order differs across the upgrade, reproduce the warning, reindex in a controlled environment, and verify ordering, uniqueness, range queries, and restore behavior. Confirm no mismatch remains after rebuilding and refreshing.

## Gotchas

- Pin and test the exact supported version; defaults and feature states can change.
- Preserve reproducible evidence without storing secrets or personal data.
- Define rollback before production rollout.

## Official source

- [Primary documentation](https://www.postgresql.org/docs/current/sql-altercollation.html)
