# parameterized-queries

**Issue:** String interpolation in queries leads to injection and plan cache misses
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SQL built with string concatenation or template literals. Each unique string is a new query from the planner's perspective, polluting pg_stat_statements and preventing plan reuse.

## Pattern / Solution
Always use positional parameters. Every ORM does this by default. Never interpolate user-controlled values into SQL strings.

## Gotchas
- IN clauses with dynamic arrays require array operators or generating placeholders with a known-length list
- DDL cannot use parameters -- sanitize identifiers with an allowlist
- Logging middleware may log the raw parameterized form without values

## Related
- sql-injection-prevention-orm
- prepared-statements
- n-plus-one-query-detection
