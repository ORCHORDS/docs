# PostgreSQL TOAST compression migration

**Problem**

Changing default TOAST compression affects newly stored values, CPU, storage, and replica compatibility without rewriting existing data.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use after benchmarking large compressible columns on every cluster version.

## Controls

- Choose pglz or lz4 explicitly and confirm build support.
- Preserve replication compatibility.
- Measure CPU, storage, WAL, and latency.

## Implementation

Set defaults or per-column policy deliberately; rewrite only through reviewed migration.

## Tests

Insert/update old and new rows, replicate, dump/restore, and compare size/performance.

## Gotchas

- Defaults affect new values only.
- Compression may be skipped.
- Rewrites are operationally expensive.

## Official sources

- [PostgreSQL client defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
