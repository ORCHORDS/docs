# SQLite hard heap-limit policy

**Problem**

A process embedding SQLite can consume excessive allocator memory unless a connection establishes a hard upper bound.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use as defense in depth where SQLite shares a process with other critical work.

## Controls

- Set a measured limit during trusted initialization.
- Keep OS/cgroup memory limits and query controls.
- Treat limit failures as explicit operational errors.

## Implementation

- Use `PRAGMA hard_heap_limit` only to lower the process limit.
- Record the effective value.
- Separate workloads requiring different budgets into processes.

## Tests

- Run large sorts, blobs, many connections, and memory pressure near the boundary.

## Gotchas

- The hard limit is process-wide, not connection isolation.
- It cannot be raised through the pragma.
- Too-low values cause allocation failures.

## Official sources

- [Official documentation](https://sqlite.org/pragma.html#pragma_hard_heap_limit)
