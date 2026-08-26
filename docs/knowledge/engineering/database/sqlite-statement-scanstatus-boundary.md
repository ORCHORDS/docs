# SQLite statement scan-status boundary

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Statement scan-status instrumentation adds observability but can impose overhead and tempt production code to depend on diagnostic counters.

## When to use

Use for controlled query-plan diagnostics in test, staging, or sampled troubleshooting.

## Controls

Require a build with scan-status support, enable per connection, exclude secrets from SQL/logs, and disable after capture.

## Implementation

Gate SQLITE_DBCONFIG_STMT_SCANSTATUS behind an operator flag, collect bounded sqlite3_stmt_scanstatus_v2 results, correlate with EXPLAIN QUERY PLAN, then reset.

## Tests

Test unsupported builds, nested loops, reset, prepared-statement reuse, concurrent connections, and disabled-mode overhead.

## Gotchas

Counters describe executed loops and are not a stable application API or optimizer promise.

## Official sources

- [Official documentation](https://www.sqlite.org/c3ref/c_dbconfig_defensive.html)
