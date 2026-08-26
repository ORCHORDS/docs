# PostgreSQL eager-freeze failure budget

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Eager freezing can reduce future vacuum work, but an unsuitable failure-rate setting can add scans without freezing enough pages.

## When to use

Use when tuning PostgreSQL vacuum freezing from measured page and workload behavior.

## Controls

Baseline defaults, change one scope at a time, retain wraparound safeguards, and budget I/O and WAL.

## Implementation

Measure vacuum logs and table age; canary a table-level setting; compare frozen-page yield and latency; roll back when the budget regresses.

## Tests

Test write-heavy and read-mostly tables, autovacuum overlap, replicas, cancellation, and restoration of defaults.

## Gotchas

This is not a substitute for autovacuum capacity or transaction-ID monitoring.

## Official sources

- [Official documentation](https://www.postgresql.org/docs/current/runtime-config-vacuum.html)
