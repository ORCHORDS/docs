# jq-json-processing

**Issue:** JSON API responses processed with grep/awk, breaking on nested data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
grep for quoted keys misses nested keys; complex transformations require Python scripts.

## Pattern / Solution
curl ... | jq .data[] pipes JSON through powerful filter. Filters: .[] iterate array, select(.active) filter, map() transform, @csv for output. jq -r for raw string output. jq -s slurps multiple JSON values.

## Gotchas
- jq uses // as alternative operator (not comments) — escape in shell strings
- jq errors are not surfaced by default in pipes; use set -e or check PIPESTATUS

## Related
- curl-advanced-usage, httpie-patterns, fd-find-patterns
