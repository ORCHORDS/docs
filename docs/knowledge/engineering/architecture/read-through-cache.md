# read-through-cache

**Issue:** Cache population logic is scattered across multiple call sites
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Different parts of the codebase read the same entity and each has its own cache-check-then-database logic, with subtle differences in TTL and key format.

## Pattern / Solution
The cache layer is responsible for loading from the database on a miss. The application only calls the cache. Cache population is centralized and consistent. Often implemented in a dedicated repository or cache proxy class.

## Gotchas
The cache provider must have access to the data source, which couples them. Cold start performance degrades until the cache warms. Ensure the cache layer handles database errors gracefully without caching error states.

## Related
cache-aside-pattern, write-through-cache, distributed-caching
