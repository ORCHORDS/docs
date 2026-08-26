# Node SQLite backup operation boundaries

**Issue**

An online SQLite backup must coordinate progress, cancellation, destination handling, and application shutdown.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use the supported `backup()` API with explicit source/destination databases.
- Write to a new controlled path and validate before promotion.
- Bound progress callbacks and cancellation.

## Verification

1. Back up during concurrent writes.
2. Interrupt and retry.
3. Run integrity checks and restore tests.

## Gotchas

- A copied file is not automatically a verified backup.
- Destination replacement needs atomic policy.
- API availability depends on Node version.

## Official source

- [Official documentation](https://nodejs.org/api/sqlite.html)
